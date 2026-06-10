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

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self):
        self._active_clones: dict[str, dict] = {}

    def create_clone(self, graph: nx.DiGraph) -> tuple[str, nx.DiGraph]:
        """
        Creates an isolated deep clone of the graph for simulation.
        Returns (clone_id, cloned_graph).
        The production 12s loop continues on the original graph untouched.
        """
        clone_id = str(uuid.uuid4())[:8]
        cloned = copy.deepcopy(graph)
        self._active_clones[clone_id] = {
            "id": clone_id,
            "created_at": time.time(),
            "graph": cloned,
        }
        logger.info(f"RCU clone created: {clone_id}")
        return clone_id, cloned

    def get_clone(self, clone_id: str) -> nx.DiGraph | None:
        entry = self._active_clones.get(clone_id)
        return entry["graph"] if entry else None

    def release_clone(self, clone_id: str):
        self._active_clones.pop(clone_id, None)
        logger.debug(f"Clone {clone_id} released from memory")

    def list_clones(self) -> list[dict]:
        return [
            {"id": c["id"], "created_at": c["created_at"]}
            for c in self._active_clones.values()
        ]
