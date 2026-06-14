from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import networkx as nx

from simulation.models import Severity, Violation

RACK_U = 42
PDU_CAPACITY_W = 1400.0
COOLING_CAPACITY_BTU = PDU_CAPACITY_W * 3.412
SWITCH_PORTS = 48
STALE_SECONDS = 60


def validate_all_constraints(
    graph: nx.DiGraph,
    affected_ids: set[str] | None = None,
    projected: bool = False,
    projection_step: int | None = None,
) -> list[Violation]:
    findings: list[Violation] = []
    findings.extend(_validate_racks(graph, affected_ids, projected, projection_step))
    findings.extend(_validate_live(graph, affected_ids, projected, projection_step))
    findings.extend(_validate_storage(graph, affected_ids, projected, projection_step))
    findings.extend(_validate_network(graph, affected_ids, projected, projection_step))
    return findings


def _v(code: str, severity: Severity, device: str, message: str, current=None,
       limit=None, unit=None, projected=False, step=None, scope="node") -> Violation:
    return Violation(
        code=code, severity=severity, scope=scope, device_id=device,
        message=message, current_value=current, limit_value=limit, unit=unit,
        projected=projected, projection_step=step,
    )


def _validate_racks(graph: nx.DiGraph, affected: set[str] | None, projected: bool, step: int | None) -> list[Violation]:
    out: list[Violation] = []
    racks = sorted({data.get("droplet") for _, data in graph.nodes(data=True) if data.get("droplet")})
    for rack in racks:
        if affected and rack not in affected and not any(
            node_id in affected and data.get("droplet") == rack
            for node_id, data in graph.nodes(data=True)
        ):
            continue
        nodes = [(node_id, data) for node_id, data in graph.nodes(data=True) if data.get("droplet") == rack]
        used_u = sum(float(data.get("capacity", {}).get("u_size", _u_size(data.get("role")))) for _, data in nodes)
        power_values = [_metric(data, "power_w", "power_watts") for _, data in nodes]
        power = sum(value for value in power_values if value is not None)
        ports = sum(1 for _, data in nodes if data.get("role") not in {"metrics-exporter", "container-metrics"})
        out.extend(_capacity_findings(rack, used_u, RACK_U, .9, 1.0, "RACK_NEAR_CAPACITY", "RACK_OVERFLOW", "U", projected, step))
        if any(value is None for value in power_values):
            out.append(_v("POWER_DATA_MISSING", Severity.RISK_WARNING, rack, "Power telemetry is missing for one or more rack devices", projected=projected, step=step, scope="rack"))
        out.extend(_capacity_findings(rack, power, PDU_CAPACITY_W, .8, .9, "POWER_WARNING", "POWER_EXCEEDED", "W", projected, step))
        cooling = power * 3.412
        out.extend(_capacity_findings(rack, cooling, COOLING_CAPACITY_BTU, .75, .85, "COOLING_WARNING", "COOLING_EXCEEDED", "BTU/hr", projected, step))
        out.extend(_capacity_findings(rack, ports, SWITCH_PORTS, .9, 1.0, "NETWORK_PORTS_LOW", "NO_NETWORK_PORTS", "ports", projected, step))
    return out


def _capacity_findings(device: str, value: float, capacity: float, warn: float, hard: float,
                       warning_code: str, hard_code: str, unit: str, projected: bool, step: int | None) -> list[Violation]:
    if value > capacity * hard:
        return [_v(hard_code, Severity.HARD_BLOCK, device, f"{device} exceeds its {unit} operating limit", value, capacity * hard, unit, projected, step, "rack")]
    if value >= capacity * warn:
        return [_v(warning_code, Severity.RISK_WARNING, device, f"{device} is near its {unit} operating limit", value, capacity * warn, unit, projected, step, "rack")]
    return []


def _validate_live(graph: nx.DiGraph, affected: set[str] | None, projected: bool, step: int | None) -> list[Violation]:
    out: list[Violation] = []
    rack_cpu: dict[str, list[float]] = {}
    for node_id, data in _scoped_nodes(graph, affected):
        if data.get("role") != "compute-node":
            continue
        rack = data.get("droplet", "unknown")
        cpu = _metric(data, "cpu_pct", "cpu_percent")
        memory = _metric(data, "memory_pct", "memory_percent")
        temp = _metric(data, "temp_c", "temperature_celsius")
        observed = data.get("metrics", {}).get("observed_at") or data.get("metrics", {}).get("timestamp")
        if cpu is None:
            out.append(_v("LIVE_METRIC_MISSING", Severity.RISK_WARNING, node_id, "CPU metric is missing; risk cannot be treated as zero", projected=projected, step=step))
        else:
            rack_cpu.setdefault(rack, []).append(cpu)
            if cpu >= 95:
                out.append(_v("LIVE_CPU_HIGH", Severity.HARD_BLOCK, node_id, "Live CPU exceeds the compute safety limit", cpu, 95, "%", projected, step))
            elif cpu > 80:
                out.append(_v("LIVE_CPU_HIGH", Severity.RISK_WARNING, node_id, "Live CPU exceeds the operational warning threshold", cpu, 80, "%", projected, step))
        if memory is None:
            out.append(_v("LIVE_METRIC_MISSING", Severity.RISK_WARNING, node_id, "Memory metric is missing; risk cannot be treated as zero", projected=projected, step=step))
        elif memory >= 95:
            out.append(_v("LIVE_MEMORY_HIGH", Severity.HARD_BLOCK, node_id, "Live memory exceeds the compute safety limit", memory, 95, "%", projected, step))
        elif memory > 85:
            out.append(_v("LIVE_MEMORY_HIGH", Severity.RISK_WARNING, node_id, "Live memory exceeds the operational warning threshold", memory, 85, "%", projected, step))
        if temp is None:
            out.append(_v("LIVE_METRIC_MISSING", Severity.RISK_WARNING, node_id, "Temperature metric is missing; risk cannot be treated as zero", projected=projected, step=step))
        elif temp > 85:
            out.append(_v("LIVE_THERMAL_DANGER", Severity.HARD_BLOCK, node_id, "Live temperature exceeds the thermal safety limit", temp, 85, "C", projected, step))
        elif temp > 75:
            out.append(_v("LIVE_TEMP_HIGH", Severity.RISK_WARNING, node_id, "Live temperature exceeds the warning threshold", temp, 75, "C", projected, step))
        anomaly = _metric(data, "anomaly_score")
        if anomaly is not None and anomaly >= .65:
            out.append(_v("LIVE_ANOMALY_DETECTED", Severity.RISK_WARNING, node_id, "Synthetic baseline anomaly score exceeds threshold", anomaly, .65, "score", projected, step))
        if observed is not None and _age_seconds(observed) > STALE_SECONDS:
            out.append(_v("LIVE_METRIC_STALE", Severity.RISK_WARNING, node_id, "Live telemetry is stale", _age_seconds(observed), STALE_SECONDS, "seconds", projected, step))
    for rack, values in rack_cpu.items():
        average = sum(values) / len(values)
        if average > 70:
            out.append(_v("LIVE_RACK_CPU_HIGH", Severity.RISK_WARNING, rack, "Rack average CPU exceeds the operational warning threshold", average, 70, "%", projected, step, "rack"))
    return out


def _validate_storage(graph: nx.DiGraph, affected: set[str] | None, projected: bool, step: int | None) -> list[Violation]:
    out = []
    for node_id, data in _scoped_nodes(graph, affected):
        iops = _metric(data, "disk_iops")
        if iops is None:
            continue
        limit = float(data.get("capacity", {}).get("iops", 4000))
        if iops >= limit:
            out.append(_v("STORAGE_IOPS_EXCEEDED", Severity.HARD_BLOCK, node_id, "Storage IOPS exceeds capacity", iops, limit, "IOPS", projected, step))
        elif iops >= limit * .75:
            out.append(_v("STORAGE_IOPS_WARNING", Severity.RISK_WARNING, node_id, "Storage IOPS is near capacity", iops, limit * .75, "IOPS", projected, step))
        used_gb = _metric(data, "capacity_used_gb")
        capacity_gb = data.get("capacity", {}).get("capacity_gb")
        if used_gb is not None and capacity_gb:
            if used_gb > capacity_gb:
                out.append(_v("STORAGE_CAPACITY_EXCEEDED", Severity.HARD_BLOCK, node_id, "Storage usage exceeds capacity", used_gb, capacity_gb, "GB", projected, step))
            elif used_gb >= capacity_gb * .85:
                out.append(_v("STORAGE_CAPACITY_WARNING", Severity.RISK_WARNING, node_id, "Storage usage is near capacity", used_gb, capacity_gb * .85, "GB", projected, step))
    return out


def _validate_network(graph: nx.DiGraph, affected: set[str] | None, projected: bool, step: int | None) -> list[Violation]:
    out = []
    for source, target, data in graph.edges(data=True):
        if affected and source not in affected and target not in affected:
            continue
        latency = _edge_metric(data, "latency_ms")
        loss = _edge_metric(data, "packet_loss_pct", "packet_loss_percent")
        bandwidth = _edge_metric(data, "bandwidth_mbps")
        capacity = data.get("capacity", {}).get("bandwidth_mbps")
        edge_id = f"{source}->{target}"
        if latency is not None:
            if latency >= 150:
                out.append(_v("NETWORK_LATENCY_EXCEEDED", Severity.HARD_BLOCK, edge_id, "Link latency exceeds SLA", latency, 150, "ms", projected, step, "link"))
            elif latency >= 100:
                out.append(_v("NETWORK_LATENCY_WARNING", Severity.RISK_WARNING, edge_id, "Link latency is near SLA", latency, 100, "ms", projected, step, "link"))
        if loss is not None:
            if loss >= 5:
                out.append(_v("PACKET_LOSS_EXCEEDED", Severity.HARD_BLOCK, edge_id, "Packet loss exceeds SLA", loss, 5, "%", projected, step, "link"))
            elif loss >= 2:
                out.append(_v("PACKET_LOSS_WARNING", Severity.RISK_WARNING, edge_id, "Packet loss is near SLA", loss, 2, "%", projected, step, "link"))
        if bandwidth is not None and capacity:
            utilization = bandwidth / capacity
            if utilization > 1:
                out.append(_v("BANDWIDTH_EXCEEDED", Severity.HARD_BLOCK, edge_id, "Bandwidth exceeds link capacity", bandwidth, capacity, "Mbps", projected, step, "link"))
            elif utilization >= .8:
                out.append(_v("BANDWIDTH_WARNING", Severity.RISK_WARNING, edge_id, "Bandwidth is near link capacity", bandwidth, capacity * .8, "Mbps", projected, step, "link"))
    return out


def apply_projection(base: nx.DiGraph, projection: dict) -> nx.DiGraph:
    projected = base.copy()
    for node_id, metrics in projection.get("nodes", {}).items():
        if node_id in projected:
            projected.nodes[node_id]["metrics"] = {**projected.nodes[node_id].get("metrics", {}), **metrics}
    for key, metrics in projection.get("edges", {}).items():
        source, target = key.split("->", 1)
        if projected.has_edge(source, target):
            projected.edges[source, target]["metrics"] = {**projected.edges[source, target].get("metrics", {}), **metrics}
    return projected


def _scoped_nodes(graph: nx.DiGraph, affected: set[str] | None) -> Iterable[tuple[str, dict]]:
    for node_id, data in graph.nodes(data=True):
        if affected and node_id not in affected and data.get("droplet") not in affected:
            continue
        yield node_id, data


def _metric(data: dict, *keys: str) -> float | None:
    metrics = data.get("metrics", {})
    for key in keys:
        if key in metrics and metrics[key] is not None:
            return float(metrics[key])
    return None


def _edge_metric(data: dict, *keys: str) -> float | None:
    return _metric(data, *keys)


def _u_size(role: str | None) -> int:
    return 2 if role in {"tor-router", "storage-tor", "storage-controller"} else 4 if role == "spine-switch" else 1


def _age_seconds(value) -> float:
    try:
        timestamp = datetime.fromtimestamp(float(value), timezone.utc) if isinstance(value, (int, float)) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - timestamp).total_seconds())
    except (TypeError, ValueError):
        return float("inf")
