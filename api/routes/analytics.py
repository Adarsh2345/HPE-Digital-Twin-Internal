"""
api/routes/analytics.py
GET  /api/v1/analytics/profiles              — all node P50/P90/P95/P99 profiles
GET  /api/v1/analytics/profile/{node_id}     — single node profile (compute+storage)
GET  /api/v1/analytics/edge/{edge_key}       — edge network profile
GET  /api/v1/analytics/scenarios             — discovered workload scenarios
GET  /api/v1/analytics/correlations/{node}   — metric correlation pairs
POST /api/v1/analytics/retrain               — re-run the full pipeline
"""
from fastapi import APIRouter, HTTPException
from core.analytics.model_registry import registry

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/profiles")
def get_all_profiles():
    return {
        "ready":        registry.ready,
        "node_profiles": registry.analyzer.profiles,
        "edge_profiles": registry.analyzer.edge_profiles,
    }


@router.get("/profile/{node_id}")
def get_node_profile(node_id: str):
    profile = registry.get_profile(node_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile for '{node_id}'")
    return {
        **profile,
        "night_batch_detected": registry.analyzer.detect_night_batch(node_id),
        "weekend_idle_detected": registry.analyzer.detect_weekend_idle(node_id),
    }


@router.get("/edge/{edge_key:path}")
def get_edge_profile(edge_key: str):
    profile = registry.get_edge_profile(edge_key)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile for edge '{edge_key}'")
    return profile


@router.get("/scenarios")
def get_scenarios():
    return {
        "scenarios": registry.get_scenarios(),
        "best_k":    registry.scenario_gen.best_k,
        "source":    "kmeans" if registry.ready else "static_fallback",
    }


@router.get("/correlations/{node_id}")
def get_correlations(node_id: str):
    profile = registry.get_profile(node_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile for '{node_id}'")
    return {
        "node_id":      node_id,
        "correlations": profile.get("correlations", {}),
    }


@router.post("/retrain")
def retrain(days: int = 30):
    registry.bootstrap(days=days)
    return {
        "message":   "Retraining complete",
        "scenarios": len(registry.get_scenarios()),
        "best_k":    registry.scenario_gen.best_k,
    }