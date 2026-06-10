"""
core/graph/graph_utils.py
Helper utilities for graph traversal and querying.
"""
import networkx as nx
from typing import Optional


def get_node(G: nx.DiGraph, node_id: str) -> Optional[dict]:
    if node_id in G.nodes:
        return {"id": node_id, **G.nodes[node_id]}
    return None


def get_neighbors(G: nx.DiGraph, node_id: str) -> list[str]:
    return list(G.successors(node_id)) + list(G.predecessors(node_id))


def get_nodes_by_role(G: nx.DiGraph, role: str) -> list[dict]:
    return [
        {"id": n, **G.nodes[n]}
        for n in G.nodes
        if G.nodes[n].get("role") == role
    ]


def get_nodes_by_state(G: nx.DiGraph, state: str) -> list[dict]:
    return [
        {"id": n, **G.nodes[n]}
        for n in G.nodes
        if G.nodes[n].get("state") == state
    ]


def get_subnet_nodes(G: nx.DiGraph, subnet: str) -> list[dict]:
    return [
        {"id": n, **G.nodes[n]}
        for n in G.nodes
        if G.nodes[n].get("subnet") == subnet
    ]


def path_exists(G: nx.DiGraph, source: str, target: str) -> bool:
    try:
        return nx.has_path(G, source, target)
    except nx.NetworkXError:
        return False


def get_all_paths(G: nx.DiGraph, source: str, target: str) -> list:
    try:
        return list(nx.all_simple_paths(G, source, target))
    except (nx.NetworkXError, nx.NodeNotFound):
        return []
