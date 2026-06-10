"""
integrations/neo4j/neo4j_client.py
Handles structural graph mutations inside Neo4j.
Separates static Base Infrastructure from Live Telemetry metrics.
"""
from neo4j import GraphDatabase
import logging
import time

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self, uri, user, password):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Test connectivity
            self.driver.verify_connectivity()
        except Exception as e:
            logger.error(f"Failed to establish connection with Neo4j daemon: {e}")
            raise e

    def close(self):
        self.driver.close()

    def save_base_topology(self, graph_dict: dict):
        """Creates the permanent static structural layout nodes and network connections."""
        with self.driver.session() as session:
            session.execute_write(self._create_base_topology_tx, graph_dict)

    def save_live_metrics(self, graph_dict: dict, tick: int):
        """Creates timestamped metric snapshots linked to their base infrastructure assets."""
        with self.driver.session() as session:
            session.execute_write(self._create_live_metrics_tx, graph_dict, tick)

    @staticmethod
    def _create_base_topology_tx(tx, graph_dict):
        # 1. Clear previous structure to prevent node compounding duplicates
        tx.run("MATCH (n:BaseNode) DETACH DELETE n")

        # 2. Write static physical assets
        for node in graph_dict.get("nodes", []):
            tx.run("""
                MERGE (b:BaseNode {id: $id})
                ON CREATE SET b.role = $role, b.ip = $ip
            """, id=node["id"], role=node.get("role", "unknown"), ip=node.get("ip", "N/A"))

        # 3. FIXED: Swapped "links" to "edges" to parse the network map correctly
        for edge in graph_dict.get("edges", []):
            tx.run("""
                MATCH (source:BaseNode {id: $source})
                MATCH (target:BaseNode {id: $target})
                MERGE (source)-[:WIRED_TO]->(target)
            """, source=edge["source"], target=edge["target"])
        
        logger.info("📐 Static Base Topology layout mapped permanently into Neo4j.")

    @staticmethod
    def _create_live_metrics_tx(tx, graph_dict, tick):
        timestamp = time.strftime('%H:%M:%S')
        
        # 1. Create a primary Timeline Node tracking this specific heartbeat execution
        tx.run("""
            MERGE (s:Snapshot {tick: $tick})
            ON CREATE SET s.timestamp = $timestamp
        """, tick=tick, timestamp=timestamp)

        # 2. Loop through every derived node to attach metrics to the base layer
        for node in graph_dict.get("nodes", []):
            # Isolate metric values safely
            cpu = node.get("cpu", 0.0)
            memory = node.get("memory", 0.0)
            state = node.get("state", "healthy")

            # Create a localized status node and hook it into the static hardware frame
            tx.run("""
                MATCH (b:BaseNode {id: $id})
                MATCH (s:Snapshot {tick: $tick})
                
                CREATE (l:LiveState {
                    tick: $tick, 
                    cpu: $cpu, 
                    memory: $memory, 
                    state: $state,
                    timestamp: $timestamp
                })
                
                // Link the live telemetry metrics to the physical base asset
                CREATE (b)-[:CURRENT_METRICS]->(l)
                // Link the live metrics to the global point-in-time timeline snapshot
                CREATE (s)-[:INCLUDES]->(l)
            """, id=node["id"], tick=tick, cpu=cpu, memory=memory, state=state, timestamp=timestamp)