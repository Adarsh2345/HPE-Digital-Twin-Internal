from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from core.orchestrator import orchestrator
from simulation.models import normalize_request
from simulation.nlp_parser import parse_request

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])


@router.post("/resolve")
def resolve_metrics(payload: dict = Body(...)):
    """
    Parses a natural-language (or structured) request, resolves it to a
    node/action, and returns the current Prometheus snapshot plus the
    last-30-days InfluxDB history for the resolved node(s). No simulation,
    mutation, or validation is performed here.
    """
    try:
        graph = orchestrator.get_derived_graph()
        request = (
            parse_request(payload["request_text"], graph.nodes)
            if set(payload) == {"request_text"}
            else normalize_request(payload)
        )
        if request.parser_used == "fallback":
            raise HTTPException(
                status_code=422,
                detail=[{
                    "code": "NLP_REQUEST_UNRESOLVED",
                    "path": "request_text",
                    "message": "Request could not be mapped safely to a supported action",
                }],
            )

        node_ids = {
            value for key, value in request.model_dump().items()
            if key.endswith("_id") and isinstance(value, str) and value in graph
        }

        current_snapshot = {
            node_id: graph.nodes[node_id].get("metrics", {})
            for node_id in node_ids
        }
        historical_context = (
            {
                node_id: orchestrator.influx_client.get_node_history(node_id)
                for node_id in node_ids
            }
            if orchestrator.influx_client
            else {}
        )

        return {
            "action": request.action,
            "request_text": request.request_text,
            "parser_used": request.parser_used,
            "resolved_node_ids": sorted(node_ids),
            "current_snapshot": current_snapshot,
            "historical_context": historical_context,
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
