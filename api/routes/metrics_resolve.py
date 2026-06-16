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

        # 3. Core Phase 3 Sandbox processing — Isolated Clone mutations
        sim_result = _simulator.run(
            base_graph,
            action=action,
            params=request_dict,
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


def _validation_errors(exc):
    return [{
        "code": item["type"].upper(),
        "path": ".".join(str(part) for part in item["loc"]),
        "message": item["msg"],
        "value": str(item.get("input", ""))[:200],
    } for item in exc.errors(include_url=False)]