from __future__ import annotations

import copy
from typing import Callable

import networkx as nx

from simulation.models import AlternativeScore, SimulationRequest
from simulation.validators import (
    COOLING_CAPACITY_BTU, PDU_CAPACITY_W, RACK_U, SWITCH_PORTS,
    Severity, validate_all_constraints,
)


def rank_alternatives(
    base_graph: nx.DiGraph,
    request: SimulationRequest,
    mutate: Callable[[nx.DiGraph, SimulationRequest], dict],
    limit: int = 3,
) -> list[AlternativeScore]:
    original = getattr(request, "target_rack_id", None)
    racks = sorted({data.get("droplet") for _, data in base_graph.nodes(data=True) if data.get("droplet")})
    alternatives = []
    for rack in racks:
        if rack == original:
            continue
        routers = sorted(
            node_id for node_id, data in base_graph.nodes(data=True)
            if data.get("droplet") == rack and data.get("role") in {"tor-router", "storage-tor"}
        )
        if not routers:
            continue
        candidate_request = request.model_copy(deep=True)
        updates = {}
        if hasattr(candidate_request, "target_rack_id"):
            updates["target_rack_id"] = rack
        if hasattr(candidate_request, "target_router_id"):
            updates["target_router_id"] = routers[0]
        candidate_request = candidate_request.model_copy(update=updates)
        candidate = copy.deepcopy(base_graph)
        mutation = mutate(candidate, candidate_request)
        if not mutation.get("success"):
            continue
        findings = validate_all_constraints(candidate, {rack})
        if any(item.severity == Severity.HARD_BLOCK for item in findings):
            continue
        components, capacity = _score(candidate, rack)
        score = round(
            components["power"] * .4 + components["u_space"] * .3 +
            components["thermal"] * .2 + components["ports"] * .1, 4
        )
        alternatives.append(AlternativeScore(
            target=rack, score=score, components=components, capacity=capacity,
            warnings=[item.message for item in findings if item.severity == Severity.RISK_WARNING],
            reasons=["Candidate mutation completed without hard-block violations"],
        ))
    return sorted(alternatives, key=lambda item: (-item.score, item.target))[:limit]


def _score(graph: nx.DiGraph, rack: str):
    nodes = [data for _, data in graph.nodes(data=True) if data.get("droplet") == rack]
    used_u = sum(float(data.get("capacity", {}).get("u_size", 1)) for data in nodes)
    power = sum(float(data.get("metrics", {}).get("power_watts", 0)) for data in nodes)
    cooling = power * 3.412
    ports = sum(1 for data in nodes if data.get("role") not in {"metrics-exporter", "container-metrics"})
    components = {
        "power": max(0, 1 - power / PDU_CAPACITY_W),
        "u_space": max(0, 1 - used_u / RACK_U),
        "thermal": max(0, 1 - cooling / COOLING_CAPACITY_BTU),
        "ports": max(0, 1 - ports / SWITCH_PORTS),
    }
    capacity = {
        "power_headroom_w": max(0, PDU_CAPACITY_W - power),
        "u_headroom": max(0, RACK_U - used_u),
        "thermal_margin_btu_hr": max(0, COOLING_CAPACITY_BTU - cooling),
        "ports_free": max(0, SWITCH_PORTS - ports),
    }
    return components, capacity
