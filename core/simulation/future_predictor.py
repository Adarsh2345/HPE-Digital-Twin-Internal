"""
core/simulation/future_predictor.py
Projects future metric trends using BehaviorModel (RandomForest) when available,
with linear compounding fallback for untrained nodes.
Covers compute, network, and storage projections.
"""
import networkx as nx
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.analytics.behavior_model import BehaviorModel

logger = logging.getLogger(__name__)

LINEAR_CPU_DEGRADATION     = 1.05
LINEAR_MEM_DEGRADATION     = 1.03
EXPONENTIAL_LATENCY_FACTOR = 1.08
LINEAR_IOPS_FACTOR         = 0.10   # +10% per step
LINEAR_POWER_FACTOR        = 0.05   # +5% per step


class FuturePredictor:
    def __init__(self, behavior_model: "BehaviorModel | None" = None):
        self.behavior_model = behavior_model

    def project(self, G: nx.DiGraph, steps: int = 3) -> list[dict]:
        projections = []
        current = self._extract_metrics(G)
        now = datetime.now()

        for step in range(1, steps + 1):
            hour = (now.hour + step) % 24
            dow  = now.weekday()

            proj_nodes = {}
            for node_id, metrics in current["nodes"].items():
                if self.behavior_model:
                    # Use RF — increment bandwidth 5% per step as load proxy
                    bw_delta = metrics.get("bandwidth_mbps", 500) * 0.05 * step
                    preds = self.behavior_model.predict(
                        node_id, metrics, bw_delta,
                        hour_of_day=hour, day_of_week=dow,
                    )
                    proj_nodes[node_id] = {
                        "cpu_percent":         min(100.0, preds.get("cpu_percent",    metrics.get("cpu_percent", 0))),
                        "memory_percent":      min(100.0, preds.get("memory_percent", metrics.get("memory_percent", 0))),
                        "power_watts":         preds.get("power_watts",  metrics.get("power_watts", 0)),
                        "disk_iops":           preds.get("disk_iops",    metrics.get("disk_iops", 0)),
                        "latency_ms":          preds.get("latency_ms",   metrics.get("latency_ms", 0)),
                        "packet_loss_percent": preds.get("packet_loss_percent", metrics.get("packet_loss_percent", 0)),
                        "step": step,
                    }
                else:
                    proj_nodes[node_id] = self._linear_node(metrics, step)

            proj_edges = {
                k: self._project_edge(m, step)
                for k, m in current["edges"].items()
            }

            projections.append({"step": step, "nodes": proj_nodes, "edges": proj_edges})

        logger.debug(f"Projected {steps} steps (model={'RF' if self.behavior_model else 'linear'})")
        return projections

    def _linear_node(self, metrics: dict, step: int) -> dict:
        cpu   = min(100.0, metrics.get("cpu_percent", 0)    * (LINEAR_CPU_DEGRADATION ** step))
        mem   = min(100.0, metrics.get("memory_percent", 0) * (LINEAR_MEM_DEGRADATION ** step))
        iops  = metrics.get("disk_iops", 0)    * (1 + LINEAR_IOPS_FACTOR  * step)
        power = metrics.get("power_watts", 0)  * (1 + LINEAR_POWER_FACTOR * step)
        return {
            "cpu_percent":         round(cpu, 2),
            "memory_percent":      round(mem, 2),
            "disk_iops":           round(iops),
            "power_watts":         round(power, 1),
            "latency_ms":          metrics.get("latency_ms", 0),
            "packet_loss_percent": metrics.get("packet_loss_percent", 0),
            "step": step,
        }

    def _project_edge(self, metrics: dict, step: int) -> dict:
        latency = metrics.get("latency_ms", 0) * (EXPONENTIAL_LATENCY_FACTOR ** step)
        loss    = min(100.0, metrics.get("packet_loss_percent", 0) * (1 + 0.2 * step))
        return {
            "latency_ms":           round(latency, 2),
            "packet_loss_percent":  round(loss, 3),
            "step": step,
        }

    def _extract_metrics(self, G: nx.DiGraph) -> dict:
        nodes = {n: G.nodes[n].get("metrics", {}) for n in G.nodes}
        edges = {}
        for u, v in G.edges:
            edges[f"{u}->{v}"] = G.edges[u, v].get("metrics", {})
        return {"nodes": nodes, "edges": edges}