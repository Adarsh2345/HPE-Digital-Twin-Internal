"""
core/graph/topology_builder.py
Builds the Initial Topology Graph in NetworkX from loader data.
"""
import networkx as nx
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TopologyBuilder:
    def __init__(self):
        self.graph: Optional[nx.DiGraph] = None

    def build(self, topology: dict) -> nx.DiGraph:
        G = nx.DiGraph()
        # Add nodes
        for node in topology["nodes"]:
            G.add_node(node["id"], **node)

        # Add edges
        for edge in topology["edges"]:
            G.add_edge(
                edge["source"],
                edge["target"],
                **{k: v for k, v in edge.items() if k not in ("source", "target")},
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
            "nodes": [
                {"id": n, **G.nodes[n]} for n in G.nodes
            ],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]}
                for u, v in G.edges
            ],
        }
