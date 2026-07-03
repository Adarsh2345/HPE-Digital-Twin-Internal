from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class RequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    projection_steps: int = Field(default=3, ge=1, le=10)
    request_text: str | None = None
    parser_used: Literal["form", "llm", "fallback"] = "form"
    requested_by: str | None = None


class MoveServer(RequestBase):
    action: Literal["move_server"]
    server_id: str = Field(min_length=1)
    target_router_id: str = Field(min_length=1)
    target_rack_id: str | None = Field(default=None, min_length=1)


class AddCompute(RequestBase):
    action: Literal["add_compute"]
    node_id: str | None = Field(default=None, min_length=1)
    target_router_id: str = Field(min_length=1)
    target_rack_id: str = Field(min_length=1)
    model: str | None = None
    quantity: int = Field(default=1, ge=1, le=100)
    u_size: int = Field(default=1, ge=1)
    max_power_w: float = Field(default=500, ge=0)
    nics: int = Field(default=1, ge=1)
    ip: str | None = None
    cpu_pct: float | None = Field(default=None, ge=0, le=100)
    memory_pct: float | None = Field(default=None, ge=0, le=100)


class RemoveNode(RequestBase):
    action: Literal["remove_node"]
    node_id: str = Field(min_length=1)


class InjectCompute(RequestBase):
    action: Literal["inject_compute"]
    node_id: str = Field(min_length=1)
    cpu_pct: float | None = Field(default=None, ge=0, le=100)
    memory_pct: float | None = Field(default=None, ge=0, le=100)
    power_w: float | None = Field(default=None, ge=0)
    temp_c: float | None = None


class InjectNetwork(RequestBase):
    action: Literal["inject_network"]
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    latency_ms: float | None = Field(default=None, ge=0)
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100)
    bandwidth_mbps: float | None = Field(default=None, ge=0)


class InjectStorage(RequestBase):
    action: Literal["inject_storage"]
    node_id: str = Field(min_length=1)
    disk_iops: float | None = Field(default=None, ge=0)
    capacity_used_gb: float | None = Field(default=None, ge=0)


class MigrateRack(RequestBase):
    action: Literal["migrate_rack"]
    node_id: str = Field(min_length=1)
    target_rack_id: str = Field(min_length=1)
    target_router_id: str = Field(min_length=1)


class BlastRadiusQuery(RequestBase):
    action: Literal["blast_radius_query"]
    failed_device_id: str = Field(min_length=1)


SimulationRequest = Annotated[
    MoveServer | AddCompute | RemoveNode | InjectCompute | InjectNetwork |
    InjectStorage | MigrateRack | BlastRadiusQuery,
    Field(discriminator="action"),
]
REQUEST_ADAPTER = TypeAdapter(SimulationRequest)


def normalize_request(payload: dict[str, Any]) -> SimulationRequest:
    action = payload.get("action")

    if "params" not in payload:
        # Flat payload from NLP parser — apply rack inference then validate
        flat = dict(payload)
        if action == "add_compute":
            flat = _ensure_rack(flat)
        return REQUEST_ADAPTER.validate_python(flat)

    params = dict(payload.get("params") or {})
    aliases = {
        "target_router": "target_router_id", "router_id": "target_router_id",
        "target_droplet": "target_rack_id", "source_node": "source_node_id",
        "target_node": "target_node_id", "cpu_percent": "cpu_pct",
        "memory_percent": "memory_pct", "power_watts": "power_w",
        "packet_loss_percent": "packet_loss_pct",
    }
    normalized = {aliases.get(key, key): value for key, value in params.items()}
    if action == "add_compute":
        normalized = _ensure_rack(normalized)
    return REQUEST_ADAPTER.validate_python({
        "action": action,
        "projection_steps": payload.get("projection_steps", 3),
        "request_text": payload.get("request_text"),
        "parser_used": payload.get("parser_used", "form"),
        "requested_by": payload.get("requested_by"),
        **normalized,
    })


def _ensure_rack(d: dict[str, Any]) -> dict[str, Any]:
    """Fill target_rack_id from target_router_id, or vice versa, whichever is missing."""
    if not d.get("target_rack_id"):
        d = {**d, "target_rack_id": _rack_from_router(d.get("target_router_id", ""))}
    if not d.get("target_router_id"):
        d = {**d, "target_router_id": _router_from_rack(d.get("target_rack_id", ""))}
    return d


_ROUTER_TO_RACK: dict[str, str] = {
    "router-1": "droplet-1-tor1",
    "droplet-1-tor1/router-1": "droplet-1-tor1",
    "router-2": "droplet-2-tor2",
    "droplet-2-tor2/router-2": "droplet-2-tor2",
    "storage-router": "droplet-4-storage",
    "droplet-4-storage/storage-router": "droplet-4-storage",
}

_RACK_TO_ROUTER: dict[str, str] = {
    "droplet-1-tor1": "droplet-1-tor1/router-1",
    "droplet-2-tor2": "droplet-2-tor2/router-2",
    "droplet-4-storage": "droplet-4-storage/storage-router",
}

def _rack_from_router(router_id: str) -> str:
    if router_id in _ROUTER_TO_RACK:
        return _ROUTER_TO_RACK[router_id]
    if "/" in router_id:
        return router_id.split("/", 1)[0]
    return ""

def _router_from_rack(rack_id: str) -> str:
    return _RACK_TO_ROUTER.get(rack_id, "")
