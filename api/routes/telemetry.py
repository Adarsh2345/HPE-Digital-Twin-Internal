"""
api/routes/telemetry.py
GET /api/v1/telemetry            — latest snapshot for all nodes
GET /api/v1/telemetry/{node_id}  — single node metrics + history
GET /api/v1/telemetry/status     — orchestrator tick status
"""
from fastapi import APIRouter, HTTPException
from core.orchestrator import orchestrator
from core.graph.graph_serializer import graph_to_dict

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])


@router.get("")
def get_all_telemetry():
    G = orchestrator.get_derived_graph()
    nodes_metrics = {}
    for n in G.nodes:
        nodes_metrics[n] = {
            "state": G.nodes[n].get("state", "unknown"),
            "metrics": G.nodes[n].get("metrics", {}),
        }
    edges_metrics = {}
    for u, v in G.edges:
        edges_metrics[f"{u}->{v}"] = {
            "state": G.edges[u, v].get("state", "active"),
            "metrics": G.edges[u, v].get("metrics", {}),
        }
    return {
        "nodes": nodes_metrics,
        "edges": edges_metrics,
        "chaos_active": orchestrator.chaos_engine.is_active,
        "tick_count": orchestrator.get_status()["tick_count"],
    }


@router.get("/status")
def get_status():
    return orchestrator.get_status()


@router.get("/{node_id:path}")
def get_node_telemetry(node_id: str):
    G = orchestrator.get_derived_graph()
    if node_id not in G.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    node = G.nodes[node_id]
    history = orchestrator.processor.get_node_history(node_id)
    return {
        "node_id": node_id,
        "state": node.get("state", "unknown"),
        "metrics": node.get("metrics", {}),
        "rolling_avg_cpu": node.get("metrics", {}).get("rolling_avg_cpu"),
        "anomaly_detected": node.get("metrics", {}).get("anomaly_detected", False),
        "history_count": len(history),
        "recent_history": history[-5:] if history else [],
    }
