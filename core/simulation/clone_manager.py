"""
core/simulation/clone_manager.py
Read-Copy-Update (RCU) isolation barrier.
Creates deep clones of the derived state graph for safe what-if simulation.
"""
import copy
import uuid
import time
import networkx as nx
import logging
import threading

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self):
        self._active_clones: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_clone(self, graph: nx.DiGraph) -> tuple[str, nx.DiGraph]:
        """
        Creates an isolated deep clone of the graph for simulation.
        Returns (clone_id, cloned_graph).
        The production 12s loop continues on the original graph untouched.
        """
        clone_id = str(uuid.uuid4())[:8]
        cloned = copy.deepcopy(graph)
        with self._lock:
            self._active_clones[clone_id] = {
                "id": clone_id,
                "created_at": time.time(),
                "graph": cloned,
            }
        logger.info(f"RCU clone created: {clone_id}")
        return clone_id, cloned

    def get_clone(self, clone_id: str) -> nx.DiGraph | None:
        with self._lock:
            entry = self._active_clones.get(clone_id)
            return copy.deepcopy(entry["graph"]) if entry else None

    def release_clone(self, clone_id: str):
        with self._lock:
            self._active_clones.pop(clone_id, None)
        logger.debug(f"Clone {clone_id} released from memory")

    def list_clones(self) -> list[dict]:
        with self._lock:
            return [
                {"id": c["id"], "created_at": c["created_at"]}
                for c in self._active_clones.values()
            ]

    def cleanup(self, max_age_seconds: float = 300) -> int:
        cutoff = time.time() - max_age_seconds
        with self._lock:
            expired = [clone_id for clone_id, item in self._active_clones.items() if item["created_at"] < cutoff]
            for clone_id in expired:
                self._active_clones.pop(clone_id, None)
        return len(expired)
