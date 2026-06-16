"""
integrations/neo4j/neo4j_client.py
Handles structural graph mutations inside Neo4j.
Separates static Base Infrastructure from Live Telemetry metrics.
FIXED: Connection timeout variables added to clear runtime execution drops.
"""
from neo4j import GraphDatabase
import logging
import time

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self, uri, user, password):
        try:
            # We enforce a strict connection timeout limit inside the driver allocation block
            self.driver = GraphDatabase.driver(
                uri, 
                auth=(user, password),
                connection_timeout=1.0,
                max_connection_lifetime=2.0
            )
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
        tx.run("MATCH (n:BaseNode) DETACH DELETE n")

        for node in graph_dict.get("nodes", []):
            tx.run("""
                MERGE (b:BaseNode {id: $id})
                ON CREATE SET b.role = $role, b.ip = $ip
            """, id=node["id"], role=node.get("role", "unknown"), ip=node.get("ip", "N/A"))

        for edge in graph_dict.get("edges", []):
            tx.run("""
                MATCH (source:BaseNode {id: $source})
                MATCH (target:BaseNode {id: $target})
                MERGE (source)-[:WIRED_TO]->(target)
            """, source=edge["source"], target=edge["target"])
        
        logger.info("Static Base Topology layout mapped permanently into Neo4j.")

    @staticmethod
    def _create_live_metrics_tx(tx, graph_dict, tick):
        timestamp = time.strftime('%H:%M:%S')
        
        tx.run("""
            MERGE (s:Snapshot {tick: $tick})
            ON CREATE SET s.timestamp = $timestamp
        """, tick=tick, timestamp=timestamp)

        for node in graph_dict.get("nodes", []):
            cpu = node.get("cpu", 0.0)
            memory = node.get("memory", 0.0)
            state = node.get("state", "healthy")

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
                
                CREATE (b)-[:CURRENT_METRICS]->(l)
                CREATE (s)-[:INCLUDES]->(l)
            """, id=node["id"], tick=tick, cpu=cpu, memory=memory, state=state, timestamp=timestamp)