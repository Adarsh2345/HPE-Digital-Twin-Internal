"""
core/graph/derived_state_builder.py
Merges live telemetry metrics into the static topology graph
and derives health states for nodes and edges.
"""
import copy
import networkx as nx
from config.constants import WARNING_THRESHOLDS, CRITICAL_THRESHOLDS, NODE_STATES, EDGE_STATES
import logging

logger = logging.getLogger(__name__)


def derive_node_state(metrics: dict) -> str:
    cpu = metrics.get("cpu_percent", 0)
    memory = metrics.get("memory_percent", 0)
    power = metrics.get("power_watts", 0)

    if (
        cpu >= CRITICAL_THRESHOLDS["cpu"]
        or memory >= CRITICAL_THRESHOLDS["memory"]
        or power >= CRITICAL_THRESHOLDS["power_watts"]
    ):
        return NODE_STATES["CRITICAL"]
    if (
        cpu >= WARNING_THRESHOLDS["cpu"]
        or memory >= WARNING_THRESHOLDS["memory"]
        or power >= WARNING_THRESHOLDS["power_watts"]
    ):
        return NODE_STATES["WARNING"]
    return NODE_STATES["HEALTHY"]


def derive_edge_state(metrics: dict) -> str:
    latency = metrics.get("latency_ms", 0)
    packet_loss = metrics.get("packet_loss_percent", 0)

    if latency >= CRITICAL_THRESHOLDS["latency_ms"] or packet_loss >= CRITICAL_THRESHOLDS["packet_loss"]:
        return EDGE_STATES["DOWN"]
    if latency >= WARNING_THRESHOLDS["latency_ms"] or packet_loss >= WARNING_THRESHOLDS["packet_loss"]:
        return EDGE_STATES["DEGRADED"]
    return EDGE_STATES["ACTIVE"]


class DerivedStateBuilder:
    def build_derived_state(
        self, base_graph: nx.DiGraph, telemetry_snapshot: dict
    ) -> nx.DiGraph:
        """
        Merge telemetry into a deep copy of the base graph and return
        the derived state graph.
        """
        derived = copy.deepcopy(base_graph)

        node_metrics = telemetry_snapshot.get("nodes", {})
        edge_metrics = telemetry_snapshot.get("edges", {})

        # Update node states
        for node_id in derived.nodes:
            metrics = node_metrics.get(node_id, {})
            derived.nodes[node_id]["metrics"] = metrics
            derived.nodes[node_id]["state"] = derive_node_state(metrics)

        # Update edge states
        for u, v in derived.edges:
            edge_key = f"{u}->{v}"
            metrics = edge_metrics.get(edge_key, {})
            derived.edges[u, v]["metrics"] = metrics
            derived.edges[u, v]["state"] = derive_edge_state(metrics)

        logger.debug("Derived state graph updated with latest telemetry")
        return derived

    def graph_to_dict(self, G: nx.DiGraph) -> dict:
        return {
            "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]} for u, v in G.edges
            ],
        }
