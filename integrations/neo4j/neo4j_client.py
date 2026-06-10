"""
integrations/neo4j/neo4j_client.py
Neo4j driver wrapper for persisting derived state graph snapshots
with immutable timestamp index for timeline analysis.
"""
import time
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = None
        self.uri = uri
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            with self._driver.session() as session:
                session.run("RETURN 1")
            logger.info(f"Neo4j connected: {uri}")
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}) — snapshots will be skipped")

    def save_snapshot(self, graph_dict: dict, tick: int):
        """Persist a derived state snapshot with timestamp index."""
        if self._driver is None:
            return
        try:
            with self._driver.session() as session:
                ts = time.time()
                snapshot_json = json.dumps(graph_dict, default=str)
                session.run(
                    """
                    CREATE (s:Snapshot {
                        tick: $tick,
                        timestamp: $ts,
                        data: $data
                    })
                    """,
                    tick=tick, ts=ts, data=snapshot_json,
                )
                # Upsert nodes
                for node in graph_dict.get("nodes", []):
                    session.run(
                        """
                        MERGE (n:Node {id: $id})
                        SET n.state = $state,
                            n.role  = $role,
                            n.ip    = $ip,
                            n.last_updated = $ts
                        """,
                        id=node["id"], state=node.get("state", "unknown"),
                        role=node.get("role", ""), ip=node.get("ip", ""),
                        ts=time.time(),
                    )
        except Exception as e:
            logger.warning(f"Neo4j write failed: {e}")

    def get_node_history(self, node_id: str, limit: int = 20) -> list:
        if self._driver is None:
            return []
        try:
            with self._driver.session() as session:
                result = session.run(
                    """
                    MATCH (n:Node {id: $id})
                    RETURN n ORDER BY n.last_updated DESC LIMIT $limit
                    """,
                    id=node_id, limit=limit,
                )
                return [dict(r["n"]) for r in result]
        except Exception as e:
            logger.warning(f"Neo4j read failed: {e}")
            return []

    def close(self):
        if self._driver:
            self._driver.close()
