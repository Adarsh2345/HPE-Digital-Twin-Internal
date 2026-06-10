"""
api/routes/simulation.py
POST /api/v1/simulate   — run a what-if simulation with full validation
GET  /api/v1/simulate/actions — list supported actions
"""
from fastapi import APIRouter, HTTPException
from api.models.requests import SimulationRequest
from core.orchestrator import orchestrator
from core.simulation.simulator import Simulator
from core.validation.validator_engine import ValidatorEngine
from core.recommendations.recommendation_engine import RecommendationEngine
from core.graph.graph_serializer import dict_to_graph

router = APIRouter(prefix="/api/v1/simulate", tags=["Simulation"])

_simulator = Simulator()
_validator = ValidatorEngine()
_recommender = RecommendationEngine()


@router.post("")
def run_simulation(req: SimulationRequest):
    """
    Phase 3 + 4 + 5:
    1. RCU deep clone of live derived state graph
    2. Apply topology mutation
    3. Project future metrics
    4. Run 4-tier constraint validation
    5. Return verdict + recommendation report
    """
    try:
        base_graph = orchestrator.get_derived_graph()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Phase 3: RCU clone + mutation + projection
    sim_result = _simulator.run(
        base_graph,
        action=req.action,
        params=req.params,
        projection_steps=req.projection_steps,
    )

    if not sim_result["success"]:
        raise HTTPException(status_code=400, detail=sim_result["mutation"])

    # Phase 4: 4-tier validation on projected graph
    projected_graph = dict_to_graph(sim_result["projected_graph"])
    projections = sim_result["projections"]
    validation = _validator.validate(projected_graph, projections)

    # Phase 5: Recommendation report
    report = _recommender.generate_report(
        action=req.action,
        params=req.params,
        validation_result=validation,
        mutation_result=sim_result["mutation"],
        projections=projections,
    )

    return {
        **report,
        "clone_id": sim_result["clone_id"],
        "projected_graph": sim_result["projected_graph"],
        "projections": projections,
        "tier_results": validation.get("tier_results", {}),
    }


@router.get("/actions")
def list_actions():
    return {
        "actions": [
            {
                "action": "move_server",
                "description": "Move a compute node to a different ToR switch",
                "params": {"server_id": "string", "target_router": "string"},
                "example": {"server_id": "server-1", "target_router": "router-2"},
            },
            {
                "action": "add_compute",
                "description": "Add a new compute node under a ToR switch",
                "params": {"node_id": "string", "router_id": "string", "ip": "string (optional)"},
                "example": {"node_id": "server-5", "router_id": "router-1", "ip": "10.10.1.13"},
            },
            {
                "action": "remove_node",
                "description": "Remove a node from the topology",
                "params": {"node_id": "string"},
                "example": {"node_id": "server-4"},
            },
        ]
    }
