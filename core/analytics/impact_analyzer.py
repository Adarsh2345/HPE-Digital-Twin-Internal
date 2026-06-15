"""
core/analytics/impact_analyzer.py
Phase 8: ImpactAnalyzer.
Graph traversal to compute traffic deltas after a topology mutation,
then feeds deltas into BehaviorModel to produce per-node predictions
across compute, network, and storage dimensions.
"""
import networkx as nx
import logging
from datetime import datetime
from core.analytics.behavior_model import BehaviorModel

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    def __init__(self, behavior_model: BehaviorModel):
        self.model = behavior_model

    def analyze(
        self,
        graph_before: nx.DiGraph,
        graph_after:  nx.DiGraph,
        mutation_result: dict,
        action: str = "",
    ) -> dict:
        """
        Returns:
          {
            node_id: {
              traffic_delta_mbps: float,
              compute: { cpu_percent, memory_percent, power_watts },
              network: { latency_ms, packet_loss_percent },
              storage: { disk_iops },
            }
          }
        """
        now = datetime.now()
        hour_of_day = now.hour
        day_of_week = now.weekday()

        traffic_deltas = self._compute_traffic_deltas(
            graph_before, graph_after, mutation_result, action
        )

        predictions = {}
        for node_id, delta_mbps in traffic_deltas.items():
            current_m = dict(graph_after.nodes.get(node_id, {}).get("metrics", {}))
            raw = self.model.predict(
                node_id, current_m, delta_mbps,
                hour_of_day=hour_of_day,
                day_of_week=day_of_week,
            )
            predictions[node_id] = {
                "traffic_delta_mbps": round(delta_mbps, 1),
                "compute": {
                    "cpu_percent":    raw.get("cpu_percent",    current_m.get("cpu_percent", 0)),
                    "memory_percent": raw.get("memory_percent", current_m.get("memory_percent", 0)),
                    "power_watts":    raw.get("power_watts",    current_m.get("power_watts", 0)),
                },
                "network": {
                    "latency_ms":          raw.get("latency_ms",          current_m.get("latency_ms", 0)),
                    "packet_loss_percent": raw.get("packet_loss_percent",  current_m.get("packet_loss_percent", 0)),
                },
                "storage": {
                    "disk_iops": raw.get("disk_iops", current_m.get("disk_iops", 0)),
                },
            }

        logger.debug(f"ImpactAnalyzer: predicted impacts on {list(predictions.keys())}")
        return predictions

    # ------------------------------------------------------------------ #
    # Traffic delta calculators per action type                            #
    # ------------------------------------------------------------------ #
    def _compute_traffic_deltas(
        self,
        G_before: nx.DiGraph,
        G_after:  nx.DiGraph,
        mutation_result: dict,
        action: str,
    ) -> dict[str, float]:

        if action in ("move_server", "migrate_rack"):
            return self._delta_move_server(G_before, G_after, mutation_result)
        elif action == "add_compute":
            return self._delta_add_compute(G_before, G_after, mutation_result)
        elif action == "remove_node":
            return self._delta_remove_node(G_before, G_after, mutation_result)
        elif action == "inject_compute":
            return self._delta_inject_compute(G_after, mutation_result)
        elif action == "inject_network":
            return self._delta_inject_network(G_after, mutation_result)
        elif action == "inject_storage":
            return self._delta_inject_storage(G_after, mutation_result)
        else:
            return self._delta_generic(G_before, G_after)

    def _delta_move_server(self, G_before, G_after, result: dict) -> dict:
        server      = result.get("server", result.get("node_id", ""))
        old_routers = result.get("old_routers", [])
        new_router  = result.get("new_router", "")

        server_bw = (
            G_before.nodes.get(server, {})
            .get("metrics", {})
            .get("bandwidth_mbps", 300)
        )

        deltas: dict[str, float] = {}
        for old in old_routers:
            deltas[old] = deltas.get(old, 0) - server_bw
        if new_router:
            deltas[new_router] = deltas.get(new_router, 0) + server_bw

        # Spine carries inter-ToR traffic
        spine_nodes = [
            n for n in G_after.nodes
            if G_after.nodes[n].get("role") == "spine-switch"
        ]
        for spine in spine_nodes:
            deltas[spine] = deltas.get(spine, 0) + server_bw * 0.4

        # Storage fabric sees proportional IOPS change
        storage_nodes = [
            n for n in G_after.nodes
            if G_after.nodes[n].get("role") in ("storage-controller", "storage-tor")
        ]
        for sn in storage_nodes:
            deltas[sn] = deltas.get(sn, 0) + server_bw * 0.15

        return deltas

    def _delta_add_compute(self, G_before, G_after, result: dict) -> dict:
        router  = result.get("router", result.get("router_id", ""))
        new_bw  = 300.0   # estimate for a new blade
        deltas  = {}
        if router:
            deltas[router] = new_bw
        for spine in [n for n in G_after.nodes if G_after.nodes[n].get("role") == "spine-switch"]:
            deltas[spine] = new_bw * 0.4
        return deltas

    def _delta_remove_node(self, G_before, G_after, result: dict) -> dict:
        removed  = result.get("removed", "")
        old_bw   = G_before.nodes.get(removed, {}).get("metrics", {}).get("bandwidth_mbps", 300)
        old_preds = list(G_before.predecessors(removed))
        deltas   = {}
        for pred in old_preds:
            deltas[pred] = deltas.get(pred, 0) - old_bw
        return deltas

    def _delta_inject_compute(self, G_after, result: dict) -> dict:
        """Compute injection doesn't change traffic — return the node for metric update."""
        node_id = result.get("node_id", "")
        return {node_id: 0.0} if node_id else {}

    def _delta_inject_network(self, G_after, result: dict) -> dict:
        """Network injection primarily affects the link endpoints."""
        src = result.get("source_node", result.get("link", "").split("->")[0])
        tgt = result.get("target_node", "")
        deltas = {}
        if src:
            deltas[src] = 0.0
        if tgt:
            deltas[tgt] = 0.0
        return deltas

    def _delta_inject_storage(self, G_after, result: dict) -> dict:
        node_id = result.get("node_id", "")
        return {node_id: 0.0} if node_id else {}

    def _delta_generic(self, G_before, G_after) -> dict:
        before_edges = set(G_before.edges())
        after_edges  = set(G_after.edges())
        deltas: dict[str, float] = {}
        for u, v in after_edges - before_edges:
            deltas[u] = deltas.get(u, 0) + 200.0
            deltas[v] = deltas.get(v, 0) + 200.0
        for u, v in before_edges - after_edges:
            deltas[u] = deltas.get(u, 0) - 200.0
            deltas[v] = deltas.get(v, 0) - 200.0
        return deltas