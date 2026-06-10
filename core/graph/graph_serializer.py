"""
core/graph/graph_serializer.py
Converts NetworkX graphs to/from JSON-serializable dicts.
"""
import json
import networkx as nx
from typing import Any


def graph_to_dict(G: nx.DiGraph) -> dict:
    return {
        "nodes": [{"id": n, **_clean(G.nodes[n])} for n in G.nodes],
        "edges": [
            {"source": u, "target": v, **_clean(G.edges[u, v])}
            for u, v in G.edges
        ],
    }


def dict_to_graph(data: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for node in data.get("nodes", []):
        nid = node.pop("id")
        G.add_node(nid, **node)
    for edge in data.get("edges", []):
        src = edge.pop("source")
        tgt = edge.pop("target")
        G.add_edge(src, tgt, **edge)
    return G


def graph_to_json(G: nx.DiGraph) -> str:
    return json.dumps(graph_to_dict(G), default=str)


def _clean(d: dict) -> dict:
    """Remove non-serializable values."""
    out = {}
    for k, v in d.items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            out[k] = str(v)
    return out
