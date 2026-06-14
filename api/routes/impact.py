from fastapi import APIRouter, HTTPException, Query

from core.orchestrator import orchestrator
from simulation.blast_radius import compute_blast_radius

router = APIRouter(prefix="/api/v1/topology", tags=["Topology"])


@router.get("/blast-radius/{device_id:path}")
def blast_radius(device_id: str, max_nodes: int = Query(default=500, ge=1, le=5000)):
    graph = orchestrator.get_derived_graph()
    if device_id not in graph:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return compute_blast_radius(graph, device_id, max_nodes).model_dump(mode="json")
