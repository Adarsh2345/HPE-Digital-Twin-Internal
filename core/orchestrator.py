"""
core/orchestrator.py
Central system orchestrator.
Phase 1: Bootstrap — parse YAML → build topology graph → sync to Neo4j & InfluxDB
Phase 2: 12s async loop — scrape metrics → derive state → cache to Redis, Neo4j, & InfluxDB
FIXED: Connection timeout limits implemented to prevent silent socket hangs under CLI run.
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
    PROMETHEUS_URL,
)
from config.constants import REDIS_KEYS
from integrations.influxdb.influx_client import InfluxClient

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.parser: Optional[object] = None
        self.topology: Optional[dict] = None
        self.initial_graph: Optional[nx.DiGraph] = None
        self.derived_graph: Optional[nx.DiGraph] = None

        self.chaos_engine = None
        self.scraper = None
        self.processor = None
        self.state_builder = None
        self.neo4j_client = None
        self.influx_client = None  # 🟢 Allocated slot in memory map

        self._redis = None
        self._loop_task: Optional[asyncio.Task] = None
        self._tick_count = 0
        self._last_tick: float = 0.0
        self._last_alert_cycle: dict = {}
        self.alert_pipeline = None

    def bootstrap(self):
        logger.info("============================================================")
        logger.info("    HPE DIGITAL TWIN — BOOTSTRAPPING ENGINE METADATA        ")
        logger.info("============================================================")
        
        from core.parser.yaml_parser import YAMLParser
        from core.parser.topology_loader import TopologyLoader
        from core.graph.topology_builder import TopologyBuilder
        from core.graph.derived_state_builder import DerivedStateBuilder
        from core.telemetry.prometheus_scraper import PrometheusScraper
        from core.telemetry.telemetry_processor import TelemetryProcessor
        from core.telemetry.chaos_engine import ChaosEngine

        self.chaos_engine = ChaosEngine()
        self.scraper = PrometheusScraper(prometheus_url=PROMETHEUS_URL)
        self.processor = TelemetryProcessor()
        self.state_builder = DerivedStateBuilder()
        self.influx_client = InfluxClient()

        from core.analytics.alert_pipeline import AlertPipeline
        self.alert_pipeline = AlertPipeline()

        self.parser = YAMLParser(INFRASTRUCTURE_YAML)
        self.parser.load()

        loader = TopologyLoader(self.parser)
        self.topology = loader.load_topology()

        builder = TopologyBuilder()
        self.initial_graph = builder.build(self.topology)
        self.derived_graph = self.initial_graph.copy()

        logger.info(f"Topology compiled cleanly: {self.initial_graph.number_of_nodes()} nodes loaded.")

        # Fire resilient fallback connection hooks
        self._connect_redis()
        self._connect_and_sync_neo4j()
        self.influx_client.connect()  # 🟢 Establish structural socket connection link

        # 🟢 FIXED: Clean, multi-space indentation block ensuring accurate syntax parsing
        try:
            from core.analytics.model_registry import registry as _ml_registry
            _ml_registry.bootstrap(days=30)
            logger.info("✅ ML analytics pipeline bootstrapped successfully.")
        except Exception as e:
            logger.warning(f"ML analytics bootstrap skipped: {e}")

    def _connect_redis(self):
        try:
            import redis as redis_lib
            logger.info(f"Pinging Redis cache cluster node on {REDIS_HOST}:{REDIS_PORT}...")
            self._redis = redis_lib.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                socket_connect_timeout=1, socket_timeout=1, decode_responses=True,
            )
            self._redis.ping()
            logger.info(f"✅ Redis cluster cache layer link active.")
        except Exception as e:
            logger.warning(f"⚠ Redis database target unreachable. Falling back to clean local in-memory caching matrix mode.")
            self._redis = None

    def _connect_and_sync_neo4j(self):
        try:
            from integrations.neo4j.neo4j_client import Neo4jClient
            from core.graph.graph_serializer import graph_to_dict

            logger.info(f"Connecting to Neo4j transaction graph instance on {NEO4J_URI}...")
            self.neo4j_client = Neo4jClient(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
            
            base_dict = graph_to_dict(self.initial_graph)
            self.neo4j_client.save_base_topology(base_dict)
            logger.info(f"✅ Neo4j immutable baseline topology synchronized successfully.")
        except Exception as e:
            logger.warning(f"⚠ Neo4j ledger database instance offline. Skipping automated point-in-time snapshot timeline generation.")
            self.neo4j_client = None

    async def start_telemetry_loop(self):
        logger.info(f"🚀 Heartbeat background harvester loop active ({TELEMETRY_INTERVAL_SECONDS}s intervals).")
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Harvester loop error context: {e}", exc_info=True)
            await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)

    async def _tick(self):
        from core.telemetry.metrics_generator import MetricsGenerator
        
        self._tick_count += 1
        self._last_tick = time.time()

        nodes = [{"id": n, **self.initial_graph.nodes[n]} for n in self.initial_graph.nodes]
        edges = [{"source": u, "target": v, **self.initial_graph.edges[u, v]} for u, v in self.initial_graph.edges]

        generator = MetricsGenerator(chaos_mode=self.chaos_engine.is_active)
        self.scraper.set_generator(generator)
        raw_snapshot = await self.scraper.scrape(nodes, edges)
        processed = self.processor.process(raw_snapshot)

        self.derived_graph = self.state_builder.build_derived_state(self.initial_graph, processed)
        
        self._cache_to_redis(processed)
        self._sync_to_neo4j()
        self._sync_to_influxdb()

        # Run alert pipeline (threshold + anomaly detection + remediation)
        try:
            self._last_alert_cycle = self.alert_pipeline.run(self.derived_graph)
        except Exception as e:
            logger.warning(f"Alert pipeline error: {e}")

    def _cache_to_redis(self, snapshot: dict):
        if self._redis is None:
            return
        try:
            state_dict = self.state_builder.graph_to_dict(self.derived_graph)
            self._redis.set(REDIS_KEYS["DERIVED_STATE"], json.dumps(state_dict, default=str))
            self._redis.set(REDIS_KEYS["CHAOS_MODE"], str(self.chaos_engine.is_active))
        except Exception as e:
            logger.warning(f"Redis write bypassed: {e}")

    def _sync_to_neo4j(self):
        if self.neo4j_client is None:
            return
        try:
            from core.graph.graph_serializer import graph_to_dict
            derived_dict = graph_to_dict(self.derived_graph)
            self.neo4j_client.save_live_metrics(derived_dict, tick=self._tick_count)
        except Exception as e:
            logger.warning(f"Neo4j snapshot backup skipped: {e}")

    def _sync_to_influxdb(self):
        if self.influx_client is None:
            return
        try:
            from core.graph.graph_serializer import graph_to_dict
            derived_dict = graph_to_dict(self.derived_graph)
            self.influx_client.write_snapshot_points(derived_dict)  # 🟢 Write live points
        except Exception as e:
            logger.warning(f"InfluxDB time-series streaming skipped: {e}")

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
            "influx_connected": self.influx_client is not None and self.influx_client.write_api is not None,
        }


orchestrator = Orchestrator()