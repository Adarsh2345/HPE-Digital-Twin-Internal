from fastapi import APIRouter, Body, HTTPException, Response

from api.routes.simulation import audit
from simulation.models import SimulationResult
from simulation.report import render_pdf

router = APIRouter(prefix="/api/v1", tags=["Simulation Audit"])


@router.get("/simulations")
def list_simulations(limit: int = 50, offset: int = 0):
    return {"items": audit.list(limit, offset), "limit": limit, "offset": offset}


@router.get("/simulations/{sim_id}")
def get_simulation(sim_id: str):
    return _get(sim_id)


@router.post("/simulations/{sim_id}/approve")
def approve(sim_id: str, payload: dict = Body(...)):
    return _decide(sim_id, "APPROVED", payload)


@router.post("/simulations/{sim_id}/reject")
def reject(sim_id: str, payload: dict = Body(...)):
    return _decide(sim_id, "REJECTED", payload)


@router.get("/reports/simulations/{sim_id}.html")
def simulation_html(sim_id: str):
    item = _get(sim_id)
    return Response(item.get("report_html") or "", media_type="text/html")


@router.get("/reports/simulations/{sim_id}.pdf")
def simulation_pdf(sim_id: str):
    item = _get(sim_id)
    result = SimulationResult.model_validate(item["result"])
    return Response(render_pdf(result), media_type="application/pdf")


def _get(sim_id):
    item = audit.get(sim_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found")
    return item


def _decide(sim_id, status, payload):
    actor = str(payload.get("actor", "")).strip()
    if not actor:
        raise HTTPException(status_code=422, detail="actor is required")
    try:
        item = audit.decide(sim_id, status, actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not item:
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found")
    return item
