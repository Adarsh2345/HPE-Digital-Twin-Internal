from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from core.orchestrator import orchestrator
from core.simulation.simulator import Simulator
from core.validation.validator_engine import ValidatorEngine
from core.recommendations.recommendation_engine import RecommendationEngine
from core.graph.graph_serializer import dict_to_graph
from simulation.models import normalize_request
from simulation.nlp_parser import parse_request, ParseFailure

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
        try:
            request = (
                parse_request(payload["request_text"], base_graph.nodes)
                if set(payload) == {"request_text"}
                else normalize_request(payload)
            )
        except ParseFailure as exc:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": exc.code,
                    "path": "request_text",
                    "message": exc.message,
                    "details": exc.details,
                }],
            ) from None

        # No LLM signal at all (e.g. API key/model not configured) — pure fallback.
        if request.parser_used == "fallback":
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": "NLP_UNAVAILABLE",
                    "path": "request_text",
                    "message": "The natural-language assistant is currently unavailable. Please try again shortly.",
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

        simulation_params = _simulation_params(request_dict, base_graph=base_graph)

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
                # Raw parsed fields (pre-remap) for pre-filling confirm forms —
                # field names here match the frontend's form keys (cpu_pct, etc.)
                "parsed_params": request_dict,
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


def _simulation_params(request_dict: dict, base_graph=None) -> dict:
    """Remap NLP/schema field names to mutator-compatible keys (mirrors simulation.py)."""
    params = dict(request_dict)
    _RACK_TO_ROUTER = {
        "droplet-1-tor1": "droplet-1-tor1/router-1",
        "droplet-2-tor2": "droplet-2-tor2/router-2",
    }
    if "target_rack_id" in params and "target_router_id" not in params:
        rack = params["target_rack_id"]
        if rack in _RACK_TO_ROUTER:
            params["target_router_id"] = _RACK_TO_ROUTER[rack]
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
    if "max_power_w" in params:
        params["power_watts"] = params.pop("max_power_w")
    if "packet_loss_pct" in params:
        params["packet_loss_percent"] = params.pop("packet_loss_pct")

    # For add_compute: auto-generate node_id if the LLM didn't supply one
    if params.get("node_id") is None and base_graph is not None:
        params["node_id"] = _next_server_id(base_graph)

    # Resolve user-typed node references case-insensitively against real
    # inventory IDs (the confirm form accepts free text, e.g. "Server-1").
    # If a token doesn't match anything in inventory, leave it as-is —
    # add_compute's node_id is often a *new* node name that won't exist yet.
    if base_graph is not None:
        for key in ("node_id", "server_id", "target_router_id", "source_node_id", "target_node_id"):
            if params.get(key):
                params[key] = _resolve_existing_id(params[key], base_graph) or params[key]

    return params


def _fold_id(s: str) -> str:
    """Normalize a node token for loose matching: lowercase, spaces/underscores -> hyphens."""
    return s.strip().lower().replace("_", "-").replace(" ", "-")


def _resolve_existing_id(token: str, base_graph) -> str | None:
    """
    Match a short or composite token to a canonical graph node id, tolerating
    case and separator differences (e.g. "Server 1", "server_1" -> "server-1").
    """
    val = str(token).strip()
    if not val:
        return None
    short = val.split("/", 1)[1] if "/" in val else val
    folded_short = _fold_id(short)
    for nid in base_graph.nodes:
        nid_short = nid.split("/", 1)[1] if "/" in nid else nid
        if nid == val or _fold_id(nid_short) == folded_short:
            return nid
    return None


def _next_server_id(G) -> str:
    """Find the next available server-N name not already in the graph."""
    existing = {
        n.split("/")[-1] for n in G.nodes
        if n.split("/")[-1].startswith("server-")
    }
    i = 1
    while f"server-{i}" in existing:
        i += 1
    return f"server-{i}"


def _validation_errors(exc):
    return [{
        "code": item["type"].upper(),
        "path": ".".join(str(part) for part in item["loc"]),
        "message": item["msg"],
        "value": str(item.get("input", ""))[:200],
    } for item in exc.errors(include_url=False)]