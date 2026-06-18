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
        if request.parser_used == "fallback" or request.action == "blast_radius_query" and request.failed_device_id == "__unresolved__":
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": "NLP_REQUEST_UNRESOLVED",
                    "path": "request_text",
                    "message": "Request text could not be mapped safely or mapped parameters did not match active inventory.",
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

        simulation_params = _simulation_params(request_dict)

        # 3. Core Phase 3 Sandbox processing — Isolated Clone mutations
        sim_result = _simulator.run(
            base_graph,
            action=action,
            params=simulation_params,
            projection_steps=projection_steps,
        )

        if not sim_result["success"]:
            raise HTTPException(status_code=400, detail=sim_result["mutation"])

        # 4. Phase 4 Verification — 4-tier validation loop matching /simulate
        projected_graph = dict_to_graph(sim_result["projected_graph"])
        projections = sim_result["projections"]

        _INJECT_NODE_METRIC_MAP = {
            "inject_compute": ("node_id", ("cpu_percent", "memory_percent", "power_watts")),
            "inject_storage": ("node_id", ("disk_iops",)),
        }
        if action in _INJECT_NODE_METRIC_MAP:
            id_key, metric_keys = _INJECT_NODE_METRIC_MAP[action]
            target = simulation_params.get(id_key)
            if target and target in projected_graph.nodes:
                metrics = dict(projected_graph.nodes[target].get("metrics", {}))
                for key in metric_keys:
                    if key in simulation_params:
                        metrics[key] = float(simulation_params[key])
                projected_graph.nodes[target]["metrics"] = metrics

        validation = _validator.validate(projected_graph, projections)

        # 5. Phase 5 Report Formulation — Remediate failures automatically
        report = _recommender.generate_report(
            action=action,
            params=simulation_params,
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


def _simulation_params(request_dict: dict) -> dict:
    """Remap NLP/schema field names to mutator-compatible keys (mirrors simulation.py)."""
    params = dict(request_dict)
    if "target_router_id" in params:
        params["target_router"] = params["target_router_id"]
        params["router_id"] = params["target_router_id"]
    if "target_rack_id" in params:
        params["target_droplet"] = params["target_rack_id"]
    if "server_id" in params:
        params["server"] = params["server_id"]
    if "source_node_id" in params:
        params["source_node"] = params["source_node_id"]
    if "target_node_id" in params:
        params["target_node"] = params["target_node_id"]
    if "cpu_pct" in params:
        params["cpu_percent"] = params.pop("cpu_pct")
    if "memory_pct" in params:
        params["memory_percent"] = params.pop("memory_pct")
    if "power_w" in params:
        params["power_watts"] = params.pop("power_w")
    if "packet_loss_pct" in params:
        params["packet_loss_percent"] = params.pop("packet_loss_pct")
    return params


def _validation_errors(exc):
    return [{
        "code": item["type"].upper(),
        "path": ".".join(str(part) for part in item["loc"]),
        "message": item["msg"],
        "value": str(item.get("input", ""))[:200],
    } for item in exc.errors(include_url=False)]