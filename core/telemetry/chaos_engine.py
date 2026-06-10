"""
core/telemetry/chaos_engine.py
Toggles chaos mode which switches Gaussian distribution bounds
to simulate heavy infrastructure strain.
"""
import logging

logger = logging.getLogger(__name__)


class ChaosEngine:
    def __init__(self):
        self._chaos_active = False
        self._affected_nodes: list[str] = []
        self._chaos_scenario: str = "full"

    @property
    def is_active(self) -> bool:
        return self._chaos_active

    @property
    def affected_nodes(self) -> list[str]:
        return self._affected_nodes

    @property
    def scenario(self) -> str:
        return self._chaos_scenario

    def enable(self, nodes: list[str] = None, scenario: str = "full"):
        self._chaos_active = True
        self._affected_nodes = nodes or []
        self._chaos_scenario = scenario
        logger.warning(
            f"🔥 CHAOS MODE ENABLED — scenario={scenario}, "
            f"nodes={nodes or 'all'}"
        )

    def disable(self):
        self._chaos_active = False
        self._affected_nodes = []
        self._chaos_scenario = "full"
        logger.info("✅ Chaos mode disabled — returning to healthy state")

    def is_node_affected(self, node_id: str) -> bool:
        if not self._chaos_active:
            return False
        if not self._affected_nodes:
            return True  # All nodes affected
        return node_id in self._affected_nodes

    def get_status(self) -> dict:
        return {
            "active": self._chaos_active,
            "scenario": self._chaos_scenario,
            "affected_nodes": self._affected_nodes,
        }
