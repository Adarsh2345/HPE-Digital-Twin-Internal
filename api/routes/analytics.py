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
from core.orchestrator import orchestrator

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


# ── Anomaly detection endpoints ────────────────────────────────────────────

@router.get("/anomalies/recent")
def get_recent_anomalies(limit: int = 20):
    """Return the most recent alert events from the live alert pipeline buffer."""
    if not orchestrator.alert_pipeline:
        raise HTTPException(status_code=503, detail="Alert pipeline not initialised — run bootstrap first")
    return {
        "alerts": orchestrator.alert_pipeline.get_recent_alerts(limit=limit),
        "count":  min(limit, 50),
    }


@router.get("/anomalies/active")
def get_active_anomalies():
    """Return anomaly events from the last 5 minutes (currently active)."""
    if not orchestrator.alert_pipeline:
        raise HTTPException(status_code=503, detail="Alert pipeline not initialised")
    active = orchestrator.alert_pipeline.get_active_anomalies()
    return {
        "active_anomalies": active,
        "count": len(active),
    }


@router.post("/anomalies/detect")
def detect_now(node_id: str = None):
    """
    Trigger an on-demand anomaly detection pass on the live derived graph.
    Optionally filter to a single node_id.
    """
    try:
        graph = orchestrator.get_derived_graph()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    detector = registry.anomaly_detector
    if node_id:
        node = graph.nodes.get(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
        result = detector.detect(node_id, node.get("metrics", {}), role=node.get("role", ""))
        return {"node_id": node_id, "result": result}

    results = detector.detect_all(graph)
    return {
        "anomalies_detected": results,
        "count": len(results),
        "total_nodes_checked": graph.number_of_nodes(),
    }


@router.post("/anomalies/train")
def train_anomaly_detector(days: int = 7):
    """Retrain Isolation Forest + RF Classifier from InfluxDB data."""
    try:
        summary = registry.anomaly_detector.train(days=days)
        return {"message": "AnomalyDetector retrained", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies/last-cycle")
def get_last_alert_cycle():
    """Return the full output from the most recent alert pipeline tick."""
    cycle = orchestrator._last_alert_cycle
    if not cycle:
        return {"message": "No alert cycle run yet — wait for next tick"}
    return cycle