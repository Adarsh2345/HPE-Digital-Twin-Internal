"""
core/graph/topology_builder.py
Builds the Initial Topology Graph in NetworkX from loader data.
"""
import networkx as nx
from typing import Optional
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TopologyBuilder:
    def __init__(self):
        self.graph: Optional[nx.DiGraph] = None

    def build(self, topology: dict) -> nx.DiGraph:
        G = nx.DiGraph()

        for node in topology["nodes"]:
            G.add_node(node["id"], **node)

        for edge in topology["edges"]:
            attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
            if G.has_edge(edge["source"], edge["target"]):
                existing = G.edges[edge["source"], edge["target"]]
                existing.setdefault("physical_links", []).append(attrs)
                existing["link_count"] = len(existing["physical_links"])
            else:
                attrs["physical_links"] = [dict(attrs)]
                attrs["link_count"] = 1
                G.add_edge(edge["source"], edge["target"], **attrs)

        G.graph.update(
            version=str(uuid.uuid4()),
            built_at=datetime.now(timezone.utc).isoformat(),
            telemetry_provenance="Synthetic Demo",
        )

        self.graph = G
        logger.info(
            f"Initial Topology Graph built: {G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges"
        )
        return G

    def get_graph(self) -> nx.DiGraph:
        if self.graph is None:
            raise RuntimeError("Graph not built yet. Call build() first.")
        return self.graph

    def to_dict(self) -> dict:
        G = self.get_graph()
        return {
            "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]}
                for u, v in G.edges
            ],
        }