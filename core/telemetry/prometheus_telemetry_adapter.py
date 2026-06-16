"""
core/telemetry/prometheus_telemetry_adapter.py
Adapter that translates raw Prometheus query results (bare node names,
e.g. "server-1") into the composite node-id scheme used by the topology
graph (e.g. "droplet-1-tor1/server-1"). Keeps the id-mapping concern out
of the scraper and the graph/simulation code entirely.
"""
import logging

import requests

logger = logging.getLogger(__name__)

NODE_METRIC_FIELDS = {
    "cpu_percent": "node_telemetry_cpu_percent",
    "memory_percent": "node_telemetry_memory_percent",
    "disk_iops": "node_telemetry_disk_iops",
    "power_watts": "node_telemetry_power_watts",
    "temperature_celsius": "node_telemetry_temperature_celsius",
}

EDGE_METRIC_FIELDS = {
    "latency_ms": "edge_telemetry_latency_ms",
    "packet_loss_percent": "edge_telemetry_packet_loss_percent",
    "bandwidth_mbps": "edge_telemetry_bandwidth_mbps",
}


def _query(prometheus_url: str, promql_query: str) -> list:
    try:
        response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={"query": promql_query},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "success":
            return payload.get("data", {}).get("result", [])
        return []
    except Exception as exc:
        logger.warning(f"Prometheus query failed ({promql_query}): {exc}")
        return []


def fetch_snapshot(prometheus_url: str, graph_node_ids: list[str]) -> dict:
    """
    Queries real Prometheus and remaps its bare node names onto the
    composite graph node ids ("{droplet}/{name}"), returning a snapshot
    shaped as {"nodes": {graph_id: {...}}, "edges": {"src->tgt": {...}}}.
    """
    bare_to_full = {node_id.rsplit("/", 1)[-1]: node_id for node_id in graph_node_ids}

    nodes_map: dict[str, dict] = {}
    for field, metric_name in NODE_METRIC_FIELDS.items():
        for item in _query(prometheus_url, metric_name):
            metric = item.get("metric", {})
            full_id = bare_to_full.get(metric.get("id"))
            if not full_id:
                continue
            entry = nodes_map.setdefault(full_id, {
                "role": metric.get("role"),
                "droplet": metric.get("droplet", "unknown"),
            })
            entry[field] = float(item.get("value", [0, 0])[1])

    edges_map: dict[str, dict] = {}
    for field, metric_name in EDGE_METRIC_FIELDS.items():
        for item in _query(prometheus_url, metric_name):
            metric = item.get("metric", {})
            source = bare_to_full.get(metric.get("source"))
            target = bare_to_full.get(metric.get("target"))
            if not source or not target:
                continue
            edge_key = f"{source}->{target}"
            entry = edges_map.setdefault(edge_key, {})
            entry[field] = float(item.get("value", [0, 0])[1])

    return {"nodes": nodes_map, "edges": edges_map}
