"""
api/routes/reports.py
GET  /api/v1/reports/health     — current system health summary
GET  /api/v1/reports/validate   — validate current live state against all constraints
GET  /api/v1/reports/node/{id}  — per-node telemetry report
"""
from fastapi import APIRouter, HTTPException
from core.orchestrator import orchestrator
from core.validation.validator_engine import ValidatorEngine
from core.graph.graph_utils import get_nodes_by_state
from core.graph.graph_serializer import graph_to_dict
import time

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])
_validator = ValidatorEngine()


@router.get("/health")
def health_report():
    G = orchestrator.get_derived_graph()
    nodes = [{"id": n, **G.nodes[n]} for n in G.nodes]

    state_counts = {}
    for node in nodes:
        s = node.get("state", "unknown")
        state_counts[s] = state_counts.get(s, 0) + 1

    critical_nodes = [n for n in nodes if n.get("state") == "critical"]
    warning_nodes = [n for n in nodes if n.get("state") == "warning"]

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_health": "critical" if critical_nodes else "warning" if warning_nodes else "healthy",
        "state_counts": state_counts,
        "critical_nodes": [n["id"] for n in critical_nodes],
        "warning_nodes": [n["id"] for n in warning_nodes],
        "chaos_active": orchestrator.chaos_engine.is_active,
        "tick_count": orchestrator.get_status()["tick_count"],
    }


@router.get("/validate")
def validate_live_state():
    """Run 4-tier validation against the current live derived state."""
    G = orchestrator.get_derived_graph()
    result = _validator.validate(G)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **result,
    }


@router.get("/node/{node_id:path}")
def node_report(node_id: str):
    G = orchestrator.get_derived_graph()
    if node_id not in G.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    node = {"id": node_id, **G.nodes[node_id]}
    history = orchestrator.processor.get_node_history(node_id)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": node,
        "history_points": len(history),
        "history": history[-10:],
    }


@router.get("/summary")
def full_summary():
    G = orchestrator.get_derived_graph()
    validation = _validator.validate(G)
    status = orchestrator.get_status()
    graph_data = graph_to_dict(G)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "validation": validation,
        "graph": graph_data,
    }
