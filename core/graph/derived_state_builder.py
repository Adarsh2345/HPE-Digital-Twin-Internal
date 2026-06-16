"""
core/graph/derived_state_builder.py
Merges live telemetry metrics into the static topology graph
and derives health states for nodes and edges with flat attributes for easy database streaming.
"""
import copy
import networkx as nx
from config.constants import WARNING_THRESHOLDS, CRITICAL_THRESHOLDS, NODE_STATES, EDGE_STATES
import logging

logger = logging.getLogger(__name__)


def derive_node_state(metrics: dict) -> str:
    cpu = metrics.get("cpu_percent", 0) or metrics.get("cpu", 0)
    memory = metrics.get("memory_percent", 0) or metrics.get("memory", 0)
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
    packet_loss = metrics.get("packet_loss_percent", 0) or metrics.get("packet_loss", 0)

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
        the derived state graph with unified flat layout properties.
        """
        derived = copy.deepcopy(base_graph)

        node_telemetry = telemetry_snapshot.get("nodes", {})
        edge_telemetry = telemetry_snapshot.get("edges", {})

        # Update node states and extract root metrics for database stream syncs
        for node_id in derived.nodes:
            metrics = node_telemetry.get(node_id, {})
            derived.nodes[node_id]["metrics"] = metrics
            
            # Pull metrics upward out of the nested dictionary to make them flat properties
            derived.nodes[node_id]["cpu"] = float(metrics.get("cpu_percent", metrics.get("cpu", 0.0)))
            derived.nodes[node_id]["memory"] = float(metrics.get("memory_percent", metrics.get("memory", 0.0)))
            derived.nodes[node_id]["state"] = derive_node_state(metrics)

        # Update edge states and extract root network metrics
        for u, v in derived.edges:
            edge_key = f"{u}->{v}"
            metrics = edge_telemetry.get(edge_key, {})
            derived.edges[u, v]["metrics"] = metrics
            
            # Flatten out network connection data metrics
            derived.edges[u, v]["latency"] = float(metrics.get("latency_ms", 0.0))
            derived.edges[u, v]["packet_loss"] = float(metrics.get("packet_loss_percent", metrics.get("packet_loss", 0.0)))
            derived.edges[u, v]["state"] = derive_edge_state(metrics)

        logger.debug("Derived state graph updated with latest telemetry")
        return derived

    def graph_to_dict(self, G: nx.DiGraph) -> dict:
        """Serializes the graph objects ensuring all custom flat keys map down smoothly."""
        return {
            "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]} for u, v in G.edges
            ],
        }