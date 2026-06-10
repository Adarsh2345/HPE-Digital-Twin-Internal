"""
core/orchestrator.py
Central system orchestrator.
- Phase 1: Bootstrap — parse YAML → build topology graph → sync initial structure to Neo4j
- Phase 2: 12s async loop — scrape metrics → derive state → cache to Redis & timeline to Neo4j
- Exposes the live derived_state_graph for API and simulation layers
"""
import asyncio
import time
import logging
import json
import networkx as nx
from typing import Optional

from config.settings import (
    INFRASTRUCTURE_YAML,
    TELEMETRY_INTERVAL_SECONDS,
    REDIS_HOST, REDIS_PORT, REDIS_DB,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
)
from config.constants import REDIS_KEYS

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.parser: Optional[object] = None
        self.topology: Optional[dict] = None
        self.initial_graph: Optional[nx.DiGraph] = None
        self.derived_graph: Optional[nx.DiGraph] = None

        # Defer dependent class instantiations to bootstrap to prevent circular import loops
        self.chaos_engine = None
        self.scraper = None
        self.processor = None
        self.state_builder = None
        self.neo4j_client = None

        self._redis = None
        self._loop_task: Optional[asyncio.Task] = None
        self._tick_count = 0
        self._last_tick: float = 0.0

    # ------------------------------------------------------------------
    # Phase 1: Bootstrap
    # ------------------------------------------------------------------
    def bootstrap(self):
        logger.info("═══ Phase 1: Bootstrapping — parsing infrastructure YAML ═══")
        
        # Inline imports to break top-level cyclic import chains
        from core.parser.yaml_parser import YAMLParser
        from core.parser.topology_loader import TopologyLoader
        from core.graph.topology_builder import TopologyBuilder
        from core.graph.derived_state_builder import DerivedStateBuilder
        from core.telemetry.prometheus_scraper import PrometheusScraper
        from core.telemetry.telemetry_processor import TelemetryProcessor
        from core.telemetry.chaos_engine import ChaosEngine

        # Initialize engines
        self.chaos_engine = ChaosEngine()
        self.scraper = PrometheusScraper()
        self.processor = TelemetryProcessor()
        self.state_builder = DerivedStateBuilder()

        self.parser = YAMLParser(INFRASTRUCTURE_YAML)
        self.parser.load()

        loader = TopologyLoader(self.parser)
        self.topology = loader.load_topology()

        builder = TopologyBuilder()
        self.initial_graph = builder.build(self.topology)

        # Initialise derived graph to initial (no metrics yet)
        self.derived_graph = self.initial_graph.copy()

        logger.info(
            f"Bootstrap complete — "
            f"{self.initial_graph.number_of_nodes()} nodes, "
            f"{self.initial_graph.number_of_edges()} edges"
        )

        # Connect and synchronize database backends
        self._connect_redis()
        self._connect_and_sync_neo4j()

    def _connect_redis(self):
        try:
            import redis as redis_lib
            self._redis = redis_lib.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                socket_connect_timeout=2, decode_responses=True,
            )
            self._redis.ping()
            logger.info(f"Redis connected at {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — state will be in-memory only")
            self._redis = None

    def _connect_and_sync_neo4j(self):
        try:
            from integrations.neo4j.neo4j_client import Neo4jClient
            from core.graph.graph_serializer import graph_to_dict

            # Instantiate client connection
            self.neo4j_client = Neo4jClient(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
            logger.info(f"Neo4j Client connected at {NEO4J_URI}")

            # Instantly sync the initial physical topology configuration wireframe
            base_dict = graph_to_dict(self.initial_graph)
            self.neo4j_client.save_base_topology(base_dict)
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}) — database timeline tracking will be skipped")
            self.neo4j_client = None

    # ------------------------------------------------------------------
    # Phase 2: 12-second telemetry loop
    # ------------------------------------------------------------------
    async def start_telemetry_loop(self):
        logger.info(
            f"═══ Phase 2: Telemetry loop started "
            f"(interval={TELEMETRY_INTERVAL_SECONDS}s) ═══"
        )
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Telemetry loop error: {e}", exc_info=True)
            await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)

    async def _tick(self):
        from core.telemetry.metrics_generator import MetricsGenerator
        
        self._tick_count += 1
        self._last_tick = time.time()

        nodes = [{"id": n, **self.initial_graph.nodes[n]} for n in self.initial_graph.nodes]
        edges = [
            {"source": u, "target": v, **self.initial_graph.edges[u, v]}
            for u, v in self.initial_graph.edges
        ]

        # Generate metrics (chaos-aware)
        generator = MetricsGenerator(chaos_mode=self.chaos_engine.is_active)
        self.scraper.set_generator(generator)
        raw_snapshot = await self.scraper.scrape(nodes, edges)

        # Process and enrich snapshot
        processed = self.processor.process(raw_snapshot)

        # Derive state graph
        self.derived_graph = self.state_builder.build_derived_state(
            self.initial_graph, processed
        )

        # 1. Push real-time snapshot payload to cache layer
        self._cache_to_redis(processed)

        # 2. Push timeline metrics entry automatically to graph layers
        self._sync_to_neo4j()

        chaos_tag = " [🔥 CHAOS]" if self.chaos_engine.is_active else ""
        logger.info(
            f"Tick #{self._tick_count}{chaos_tag} — "
            f"derived state synchronized to Redis & Neo4j at {time.strftime('%H:%M:%S')}"
        )

    def _cache_to_redis(self, snapshot: dict):
        if self._redis is None:
            return
        try:
            state_dict = self.state_builder.graph_to_dict(self.derived_graph)
            self._redis.set(REDIS_KEYS["DERIVED_STATE"], json.dumps(state_dict, default=str))
            self._redis.set(REDIS_KEYS["CHAOS_MODE"], str(self.chaos_engine.is_active))
        except Exception as e:
            logger.warning(f"Redis write failed: {e}")

    def _sync_to_neo4j(self):
        if self.neo4j_client is None:
            return
        try:
            from core.graph.graph_serializer import graph_to_dict
            derived_dict = graph_to_dict(self.derived_graph)
            
            # Send live metrics down to build snapshot links over time
            self.neo4j_client.save_live_metrics(derived_dict, tick=self._tick_count)
        except Exception as e:
            logger.warning(f"Neo4j auto-snapshot sync failed: {e}")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def get_derived_graph(self) -> nx.DiGraph:
        if self.derived_graph is None:
            raise RuntimeError("Orchestrator not bootstrapped yet.")
        return self.derived_graph

    def get_topology_dict(self) -> dict:
        return self.topology or {}

    def get_status(self) -> dict:
        return {
            "tick_count": self._tick_count,
            "last_tick": self._last_tick,
            "chaos": self.chaos_engine.get_status() if self.chaos_engine else {"active": False},
            "nodes": self.initial_graph.number_of_nodes() if self.initial_graph else 0,
            "edges": self.initial_graph.number_of_edges() if self.initial_graph else 0,
            "redis_connected": self._redis is not None,
            "neo4j_connected": self.neo4j_client is not None,
        }


# Instantiate the singleton cleanly
orchestrator = Orchestrator()