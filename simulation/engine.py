from __future__ import annotations

import copy
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import networkx as nx

from core.recommendations.remediation_rules import generate_remediation
from core.simulation.future_predictor import FuturePredictor
from core.simulation.mutators import TopologyMutator
from simulation.blast_radius import compute_blast_radius
from simulation.models import Severity, SimulationRequest, SimulationResult
from simulation.recommender import rank_alternatives
from simulation.validators import apply_projection, validate_all_constraints
from core.graph.graph_serializer import graph_to_dict


class SimulationEngine:
    def __init__(self):
        self.mutator = TopologyMutator()
        self.predictor = FuturePredictor()

    def run(self, live_graph: nx.DiGraph, request: SimulationRequest) -> SimulationResult:
        started = perf_counter()
        snapshot = copy.deepcopy(live_graph)
        graph_version = str(snapshot.graph.get("version", "unversioned"))
        candidate = copy.deepcopy(snapshot)
        clone_id = str(uuid4())[:8]
        mutation = self.apply_mutation(candidate, request)
        if not mutation.get("success"):
            raise ValueError(mutation.get("error", "simulation mutation failed"))

        affected = _affected(candidate, request, mutation)
        current = validate_all_constraints(candidate, affected)
        projections = self.predictor.project(candidate, request.projection_steps)
        projected = []
        for projection in projections:
            projected_graph = apply_projection(candidate, projection)
            projected.extend(validate_all_constraints(
                projected_graph, affected, projected=True,
                projection_step=projection["step"],
            ))
        hard_blocks = [v for v in current + projected if v.severity == Severity.HARD_BLOCK]
        warnings = [v.message for v in current + projected if v.severity == Severity.RISK_WARNING]
        allowed = not hard_blocks
        failed_id = getattr(request, "failed_device_id", None)
        if request.action == "remove_node":
            failed_id = request.node_id
        blast = compute_blast_radius(snapshot, failed_id) if failed_id else None
        alternatives = rank_alternatives(snapshot, request, self.apply_mutation) if not allowed and hasattr(request, "target_rack_id") else []
        reasons = [v.message for v in hard_blocks]
        remediation = generate_remediation(reasons)
        timestamp = _telemetry_timestamp(snapshot)
        result = SimulationResult(
            action=request.action, request_text=request.request_text,
            parser_used=request.parser_used, allowed=allowed,
            verdict="ALLOWED" if allowed else "DENIED",
            graph_version=graph_version, telemetry_timestamp=timestamp,
            telemetry_provenance=str(snapshot.graph.get("telemetry_provenance", "Synthetic Demo")),
            mutation_summary=mutation, current_violations=current,
            projected_violations=projected, warnings=warnings,
            blast_radius=blast, alternatives=alternatives,
            remediation=remediation,
            report_url=None,
            execution_time_ms=(perf_counter() - started) * 1000,
            reasons=reasons, recommendations=remediation,
            tier_results=_legacy_tiers(current, projected),
            projections=projections, projected_graph=graph_to_dict(candidate),
            clone_id=clone_id,
        )
        result.report_url = f"/api/v1/reports/simulations/{result.sim_id}.html"
        return result

    def apply_mutation(self, graph: nx.DiGraph, request: SimulationRequest) -> dict:
        action = request.action
        data = request.model_dump()
        if action == "blast_radius_query":
            return {"success": True, "failed_device_id": request.failed_device_id}
        if action == "move_server":
            return self.mutator.move_server(
                graph, _resolve(graph, request.server_id),
                _resolve(graph, request.target_router_id),
            )
        if action == "add_compute":
            results = []
            router = _resolve(graph, request.target_router_id)
            for index in range(request.quantity):
                local = request.node_id or f"sim-compute-{index + 1}"
                node_id = local if request.quantity == 1 else f"{local}-{index + 1}"
                result = self.mutator.add_compute_node(graph, node_id, router, ip=request.ip or "")
                if not result.get("success"):
                    return result
                graph.nodes[node_id]["droplet"] = request.target_rack_id
                graph.nodes[node_id]["capacity"] = {
                    "u_size": request.u_size, "max_power_w": request.max_power_w,
                    "nics": request.nics,
                }
                graph.nodes[node_id]["metrics"] = {
                    "cpu_percent": 0, "memory_percent": 0,
                    "power_watts": request.max_power_w,
                    "temperature_celsius": 25, "disk_iops": 0,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "provenance": "Synthetic Demo",
                }
                results.append(result)
            return {"success": True, "added": results, "target_rack": request.target_rack_id}
        if action == "remove_node":
            return self.mutator.remove_node(graph, _resolve(graph, request.node_id))
        if action == "inject_compute":
            node_id = _resolve(graph, request.node_id)
            result = self.mutator.inject_compute_stress(
                graph, node_id, request.cpu_pct or 0, request.memory_pct or 0,
                request.power_w or 0,
            )
            if result.get("success") and request.temp_c is not None:
                graph.nodes[node_id].setdefault("metrics", {})["temperature_celsius"] = request.temp_c
            return result
        if action == "inject_network":
            return self.mutator.inject_network_degradation(
                graph, _resolve(graph, request.source_node_id),
                _resolve(graph, request.target_node_id),
                request.latency_ms or 0, request.packet_loss_pct or 0,
            )
        if action == "inject_storage":
            node_id = _resolve(graph, request.node_id)
            result = self.mutator.inject_storage_pressure(
                graph, node_id, int(request.disk_iops or 0),
            )
            if result.get("success") and request.capacity_used_gb is not None:
                graph.nodes[node_id].setdefault("metrics", {})["capacity_used_gb"] = request.capacity_used_gb
            return result
        if action == "migrate_rack":
            return self.mutator.migrate_rack(
                graph, _resolve(graph, request.node_id), request.target_rack_id,
                _resolve(graph, request.target_router_id),
            )
        return {"success": False, "error": f"unsupported action '{action}'"}


def _resolve(graph: nx.DiGraph, value: str) -> str:
    if value in graph:
        return value
    matches = [node_id for node_id, data in graph.nodes(data=True) if data.get("display_name") == value or data.get("name") == value]
    return matches[0] if len(matches) == 1 else value


def _affected(graph, request, mutation) -> set[str]:
    values = {_resolve(graph, value) for key, value in request.model_dump().items() if key.endswith("_id") and isinstance(value, str)}
    rack = getattr(request, "target_rack_id", None)
    if rack:
        values.add(rack)
    values.update(str(value) for key, value in mutation.items() if key in {"node_id", "server", "target_rack"})
    link = mutation.get("link")
    if isinstance(link, str) and "->" in link:
        values.update(link.split("->", 1))
    return values


def _telemetry_timestamp(graph):
    timestamps = []
    for _, data in graph.nodes(data=True):
        value = data.get("metrics", {}).get("timestamp")
        if isinstance(value, (int, float)):
            timestamps.append(value)
    return datetime.fromtimestamp(max(timestamps), timezone.utc) if timestamps else None


def _legacy_tiers(current, projected):
    return {
        "structured": {
            "passed": not any(v.severity == Severity.HARD_BLOCK for v in current + projected),
            "violations": [v.model_dump(mode="json") for v in current],
            "future_violations": [v.model_dump(mode="json") for v in projected],
        }
    }
