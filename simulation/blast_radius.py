from __future__ import annotations

from collections import deque
from time import perf_counter

import networkx as nx

from simulation.models import BlastRadiusResult

DEPENDENT_EDGE_TYPES = {
    "powered_by", "hosted_on", "storage_attached", "uplink",
    "network_link", "contains", "occupies_slot", "depends_on", "replicates_to",
}


def compute_blast_radius(graph: nx.DiGraph, failed_device_id: str, max_nodes: int = 500) -> BlastRadiusResult:
    started = perf_counter()
    if failed_device_id not in graph:
        return BlastRadiusResult(failed_device_id=failed_device_id)
    queue = deque([(failed_device_id, [failed_device_id])])
    visited = {failed_device_id}
    affected: list[str] = []
    paths: list[list[str]] = []
    truncated = False
    while queue:
        failed, path = queue.popleft()
        for dependent in _dependents(graph, failed, visited):
            if len(visited) >= max_nodes:
                truncated = True
                queue.clear()
                break
            visited.add(dependent)
            affected.append(dependent)
            next_path = path + [dependent]
            paths.append(next_path)
            queue.append((dependent, next_path))
    grouped: dict[str, list[str]] = {}
    for node_id in sorted(affected):
        node_type = graph.nodes[node_id].get("node_type", graph.nodes[node_id].get("role", "unknown"))
        grouped.setdefault(node_type, []).append(node_id)
    return BlastRadiusResult(
        failed_device_id=failed_device_id,
        affected_by_type=grouped,
        paths=paths,
        affected_count=len(affected),
        execution_time_ms=(perf_counter() - started) * 1000,
        truncated=truncated,
    )


def _dependents(graph: nx.DiGraph, provider: str, failed: set[str]):
    candidates = set()
    for source, _, data in graph.in_edges(provider, data=True):
        if _edge_type(data) in DEPENDENT_EDGE_TYPES:
            candidates.add(source)
    for _, target, data in graph.out_edges(provider, data=True):
        if _edge_type(data) in {"network_link", "uplink", "contains"}:
            candidates.add(target)
    for candidate in sorted(candidates):
        if candidate in failed:
            continue
        provider_groups: dict[str, set[str]] = {}
        for _, target, data in graph.out_edges(candidate, data=True):
            edge_type = _edge_type(data)
            if edge_type in {"powered_by", "hosted_on", "storage_attached", "uplink", "depends_on"}:
                provider_groups.setdefault(edge_type, set()).add(target)
        relevant = next((group for group in provider_groups.values() if provider in group), set())
        if len(relevant) > 1 and any(provider_id not in failed and provider_id != provider for provider_id in relevant):
            continue
        yield candidate


def _edge_type(data: dict) -> str:
    return data.get("edge_type") or data.get("link_type") or "network_link"
