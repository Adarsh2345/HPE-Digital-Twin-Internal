from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from config.settings import SIMULATION_DB_PATH
from core.orchestrator import orchestrator
from simulation.audit import AuditStore
from simulation.engine import SimulationEngine
from simulation.models import normalize_request
from simulation.nlp_parser import parse_request
from simulation.report import render_html

router = APIRouter(prefix="/api/v1/simulate", tags=["Simulation"])
engine = SimulationEngine()
audit = AuditStore(SIMULATION_DB_PATH)


@router.post("")
def run_simulation(payload: dict = Body(...)):
    try:
        graph = orchestrator.get_derived_graph()
        request = parse_request(payload["request_text"], graph.nodes) if set(payload) == {"request_text"} else normalize_request(payload)
        if request.parser_used == "fallback":
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": "NLP_REQUEST_UNRESOLVED",
                    "path": "request_text",
                    "message": "Request could not be mapped safely to a supported simulation action",
                }],
            )
        result = engine.run(graph, request)
        result.historical_context = _fetch_historical_context(request, graph)
        audit.save(request, result, render_html(result))
        return result.model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_errors(exc)) from None
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=[{"code": "MISSING_FIELD", "path": str(exc), "message": "Required request field is missing"}]) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/parse")
def parse_simulation(payload: dict = Body(...)):
    text = str(payload.get("request_text", "")).strip()
    if not text:
        raise HTTPException(status_code=422, detail="request_text is required")
    try:
        inventory = orchestrator.get_derived_graph().nodes
    except RuntimeError:
        inventory = ()
    request = parse_request(text, inventory)
    if request.parser_used == "fallback":
        raise HTTPException(
            status_code=422,
            detail=[{
                "code": "NLP_REQUEST_UNRESOLVED",
                "path": "request_text",
                "message": "Request could not be mapped safely to a supported simulation action",
            }],
        )
    return request.model_dump(mode="json")


@router.get("/actions")
def list_actions():
    specs = {
        "move_server": ["server_id", "target_router"],
        "add_compute": ["node_id", "router_id", "target_rack_id"],
        "remove_node": ["node_id"],
        "inject_compute": ["node_id", "cpu_percent", "memory_percent", "power_watts", "temp_c"],
        "inject_network": ["source_node", "target_node", "latency_ms", "packet_loss_percent", "bandwidth_mbps"],
        "inject_storage": ["node_id", "disk_iops", "capacity_used_gb"],
        "migrate_rack": ["node_id", "target_droplet", "target_router"],
        "blast_radius_query": ["failed_device_id"],
    }
    return {
        "actions": [
            {
                "category": "impact" if action == "blast_radius_query" else "simulation",
                "action": action,
                "description": f"Run the {action} what-if operation on an isolated graph snapshot.",
                "params": {name: "value" for name in params},
            }
            for action, params in specs.items()
        ]
    }


def _fetch_historical_context(request, graph) -> dict:
    """On-demand 30-day InfluxDB history for the node(s) named in this request."""
    node_ids = {
        value for key, value in request.model_dump().items()
        if key.endswith("_id") and isinstance(value, str) and value in graph
    }
    if not node_ids or not orchestrator.influx_client:
        return {}
    return {
        node_id: orchestrator.influx_client.get_node_history(node_id)
        for node_id in node_ids
    }


def _validation_errors(exc):
    return [{
        "code": item["type"].upper(),
        "path": ".".join(str(part) for part in item["loc"]),
        "message": item["msg"],
        "value": str(item.get("input", ""))[:200],
    } for item in exc.errors(include_url=False)]
