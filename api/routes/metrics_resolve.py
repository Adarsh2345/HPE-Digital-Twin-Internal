from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from core.orchestrator import orchestrator
from core.simulation.simulator import Simulator
from core.validation.validator_engine import ValidatorEngine
from core.recommendations.recommendation_engine import RecommendationEngine
from core.graph.graph_serializer import dict_to_graph
from simulation.models import normalize_request
from simulation.nlp_parser import parse_request

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])

# Pipeline Singletons mirror simulation.py routing behaviors
_simulator = Simulator()
_validator = ValidatorEngine()
_recommender = RecommendationEngine()


@router.post("/resolve")
def resolve_metrics(payload: dict = Body(...)):
    """
    Parses natural-language infrastructure intent, resolves entities to inventory,
    executes full sandbox isolated mutations, projections, and constraint tracking.
    """
    try:
        base_graph = orchestrator.get_derived_graph()
        
        # 1. Parse and extract structure/metric fields using Gemini -> Rule-based
        request = (
            parse_request(payload["request_text"], base_graph.nodes)
            if set(payload) == {"request_text"}
            else normalize_request(payload)
        )
        
        # Check for unresolvable structural tokens
        if request.parser_used == "fallback" or (
            request.action == "blast_radius_query" and request.failed_device_id == "__unresolved__"
        ):
            hint = _unresolved_hint(payload.get("request_text", ""))
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": "NLP_REQUEST_UNRESOLVED",
                    "path": "request_text",
                    "message": hint,
                }],
            )

        # 2. Extract specific actions and pack fields into standard parameters
        request_dict = request.model_dump(exclude_none=True)
        action = request_dict.pop("action")
        projection_steps = request_dict.pop("projection_steps", 3)
        
        # Clean background transport metrics out to pass exact parameter dictionaries
        request_dict.pop("request_text", None)
        request_dict.pop("parser_used", None)
        request_dict.pop("requested_by", None)

        simulation_params = _remap_simulation_params(request_dict)

        # 3. Core Phase 3 Sandbox processing — Isolated Clone mutations
        sim_result = _simulator.run(
            base_graph,
            action=action,
            params=simulation_params,
            projection_steps=projection_steps,
        )

        if not sim_result["success"]:
            raise HTTPException(status_code=400, detail=sim_result["mutation"])

        # 4. Phase 4 Verification — 4-Tier validation loop matching /simulate
        projected_graph = dict_to_graph(sim_result["projected_graph"])
        projections = sim_result["projections"]
        validation = _validator.validate(projected_graph, projections)

        # 5. Phase 5 Report Formulation — Remediate failures automatically
        report = _recommender.generate_report(
            action=action,
            params=request_dict,
            validation_result=validation,
            mutation_result=sim_result["mutation"],
            projections=projections,
        )

        return {
            "parser_metadata": {
                "request_text": request.request_text,
                "parser_used": request.parser_used,
                "action": action,
            },
            "simulation_report": report,
            "clone_id": sim_result["clone_id"],
            "projected_graph": sim_result["projected_graph"],
            "projections": projections,
            "tier_results": validation.get("tier_results", {}),
            "scenario_results": sim_result.get("scenario_results", []),
            "impact_predictions": sim_result.get("impact_predictions", {}),
        }

    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_errors(exc)) from None
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=[{"code": "MISSING_FIELD", "path": str(exc), "message": "Required request field is missing"}]) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


def _remap_simulation_params(params: dict) -> dict:
    """Align API schema keys with mutator parameter names (mirrors simulation.py)."""
    simulation_params = dict(params)
    if "target_router_id" in simulation_params:
        simulation_params["target_router"] = simulation_params["target_router_id"]
        simulation_params["router_id"] = simulation_params["target_router_id"]
    if "target_rack_id" in simulation_params:
        simulation_params["target_droplet"] = simulation_params["target_rack_id"]
    if "server_id" in simulation_params:
        simulation_params["server"] = simulation_params["server_id"]
    if "source_node_id" in simulation_params:
        simulation_params["source_node"] = simulation_params["source_node_id"]
    if "target_node_id" in simulation_params:
        simulation_params["target_node"] = simulation_params["target_node_id"]
    if "cpu_pct" in simulation_params:
        simulation_params["cpu_percent"] = simulation_params["cpu_pct"]
    if "memory_pct" in simulation_params:
        simulation_params["memory_percent"] = simulation_params["memory_pct"]
    if "power_w" in simulation_params:
        simulation_params["power_watts"] = simulation_params["power_w"]
    if "packet_loss_pct" in simulation_params:
        simulation_params["packet_loss_percent"] = simulation_params["packet_loss_pct"]
    return simulation_params


def _validation_errors(exc):
    return [{
        "code": item["type"].upper(),
        "path": ".".join(str(part) for part in item["loc"]),
        "message": item["msg"],
        "value": str(item.get("input", ""))[:200],
    } for item in exc.errors(include_url=False)]


_ACTION_HINTS = {
    "move_server": 'Try: "move server-1 to router-2"',
    "add_compute": 'Try: "add compute node server-5 to router-1"',
    "remove_node": 'Try: "remove server-4"',
    "inject_compute": 'Try: "inject CPU 92% on server-1"',
    "inject_network": 'Try: "latency 160ms spine-router to router-1"',
    "inject_storage": 'Try: "3900 iops on server-2"',
    "migrate_rack": 'Try: "migrate server-1 to droplet-2-tor2 router-2"',
}


def _unresolved_hint(text: str) -> str:
    normalized = text.strip().lower().replace(" ", "_").replace("-", "_")
    for action, example in _ACTION_HINTS.items():
        if normalized == action or normalized == action.replace("_", ""):
            return (
                f'"{text}" is an action name, not a full command. '
                f"Describe the change in plain English with node names. {example}"
            )
    return (
        "Could not parse this request. Use a full natural-language command with node names "
        '(e.g. "move server-1 to router-2"). Click an example chip below to get started.'
    )