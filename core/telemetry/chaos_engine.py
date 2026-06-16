"""
core/telemetry/chaos_engine.py
Toggles chaos mode which switches Gaussian distribution bounds
to simulate heavy infrastructure strain.
"""
import logging
import copy

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
            return True
        return node_id in self._affected_nodes

    def get_status(self) -> dict:
        return {
            "active": self._chaos_active,
            "scenario": self._chaos_scenario,
            "affected_nodes": self._affected_nodes,
        }

    def apply(self, snapshot: dict, graph) -> dict:
        result = copy.deepcopy(snapshot)
        if not self._chaos_active:
            result["telemetry_provenance"] = "Synthetic Demo"
            return result

        targets = set(self._affected_nodes) or set(result.get("nodes", {}))
        scenario = self._chaos_scenario

        for node_id in targets:
            metrics = result.get("nodes", {}).get(node_id)
            if metrics is None:
                continue
            if scenario in {"full", "compute", "compute_saturation"}:
                metrics.update(cpu_percent=98.0, memory_percent=92.0)
            elif scenario == "thermal_rise":
                metrics["temperature_celsius"] = 90.0
            elif scenario in {"storage", "storage_iops_saturation"}:
                metrics["disk_iops"] = 5500
            elif scenario in {"pdu_failure", "tor_failure", "storage_controller_failure"}:
                metrics.update(power_watts=0.0, state="offline", failure_scenario=scenario)

        for key, metrics in result.get("edges", {}).items():
            source, target = key.split("->", 1)
            if self._affected_nodes and source not in targets and target not in targets:
                continue
            if scenario in {"full", "network", "spine_latency"}:
                metrics["latency_ms"] = 250.0
            if scenario in {"full", "network", "packet_loss"}:
                metrics["packet_loss_percent"] = 8.0

        result["chaos_mode"] = True
        result["telemetry_provenance"] = "Synthetic Demo"
        return result