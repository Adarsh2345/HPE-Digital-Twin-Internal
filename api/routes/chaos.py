"""
api/routes/chaos.py
POST /api/v1/chaos/enable   — enable chaos mode
POST /api/v1/chaos/disable  — disable chaos mode
GET  /api/v1/chaos/status   — current chaos state
"""
from fastapi import APIRouter
from api.models.requests import ChaosRequest
from core.orchestrator import orchestrator

router = APIRouter(prefix="/api/v1/chaos", tags=["Chaos"])


@router.post("/enable")
def enable_chaos(req: ChaosRequest):
    orchestrator.chaos_engine.enable(
        nodes=req.nodes or [],
        scenario=req.scenario or "full",
    )
    return {
        "message": "🔥 Chaos mode ENABLED",
        **orchestrator.chaos_engine.get_status(),
    }


@router.post("/disable")
def disable_chaos():
    orchestrator.chaos_engine.disable()
    return {
        "message": "✅ Chaos mode DISABLED — system returning to healthy baseline",
        **orchestrator.chaos_engine.get_status(),
    }


@router.get("/status")
def chaos_status():
    return orchestrator.chaos_engine.get_status()


@router.post("/toggle")
def toggle_chaos():
    if orchestrator.chaos_engine.is_active:
        orchestrator.chaos_engine.disable()
        return {"message": "Chaos disabled", "active": False}
    else:
        orchestrator.chaos_engine.enable()
        return {"message": "Chaos enabled", "active": True}
