"""
core/simulation/future_predictor.py
Projects future metric trends for simulated graph states.
Uses linear compounding and exponential degradation scaling.
"""
import networkx as nx
import logging

logger = logging.getLogger(__name__)

# Per-step linear degradation factors
LINEAR_CPU_DEGRADATION = 1.05    # 5% per step
LINEAR_MEM_DEGRADATION = 1.03
EXPONENTIAL_LATENCY_FACTOR = 1.08


class FuturePredictor:
    def project(self, G: nx.DiGraph, steps: int = 3) -> list[dict]:
        """
        Project graph metrics forward `steps` time steps.
        Returns list of projected snapshots.
        """
        projections = []
        current_metrics = self._extract_metrics(G)

        for step in range(1, steps + 1):
            projected = {}
            for node_id, metrics in current_metrics["nodes"].items():
                projected[node_id] = self._project_node(metrics, step)

            edge_projected = {}
            for edge_key, metrics in current_metrics["edges"].items():
                edge_projected[edge_key] = self._project_edge(metrics, step)

            projections.append({
                "step": step,
                "nodes": projected,
                "edges": edge_projected,
            })

        logger.debug(f"Projected {steps} future steps")
        return projections

    def _project_node(self, metrics: dict, step: int) -> dict:
        cpu = min(100.0, metrics.get("cpu_percent", 0) * (LINEAR_CPU_DEGRADATION ** step))
        mem = min(100.0, metrics.get("memory_percent", 0) * (LINEAR_MEM_DEGRADATION ** step))
        iops = metrics.get("disk_iops", 0) * (1 + 0.1 * step)
        power = metrics.get("power_watts", 0) * (1 + 0.05 * step)
        return {
            "cpu_percent": round(cpu, 2),
            "memory_percent": round(mem, 2),
            "disk_iops": round(iops),
            "power_watts": round(power, 1),
            "step": step,
        }

    def _project_edge(self, metrics: dict, step: int) -> dict:
        latency = metrics.get("latency_ms", 0) * (EXPONENTIAL_LATENCY_FACTOR ** step)
        loss = min(100.0, metrics.get("packet_loss_percent", 0) * (1 + 0.2 * step))
        return {
            "latency_ms": round(latency, 2),
            "packet_loss_percent": round(loss, 3),
            "step": step,
        }

    def _extract_metrics(self, G: nx.DiGraph) -> dict:
        nodes = {n: G.nodes[n].get("metrics", {}) for n in G.nodes}
        edges = {}
        for u, v in G.edges:
            key = f"{u}->{v}"
            edges[key] = G.edges[u, v].get("metrics", {})
        return {"nodes": nodes, "edges": edges}
