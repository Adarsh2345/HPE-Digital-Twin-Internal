from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Severity(StrEnum):
    HARD_BLOCK = "HARD_BLOCK"
    RISK_WARNING = "RISK_WARNING"
    INFO = "INFO"


class RequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    projection_steps: int = Field(default=3, ge=1, le=10)
    request_text: str | None = None
    parser_used: Literal["form", "rule_based", "gemini", "fallback"] = "form"
    requested_by: str | None = None


class MoveServer(RequestBase):
    action: Literal["move_server"]
    server_id: str
    target_router_id: str
    target_rack_id: str | None = None


class AddCompute(RequestBase):
    action: Literal["add_compute"]
    node_id: str | None = None
    target_router_id: str
    target_rack_id: str
    model: str | None = None
    quantity: int = Field(default=1, ge=1, le=100)
    u_size: int = Field(default=1, ge=1)
    max_power_w: float = Field(default=500, ge=0)
    nics: int = Field(default=1, ge=1)
    ip: str | None = None


class RemoveNode(RequestBase):
    action: Literal["remove_node"]
    node_id: str


class InjectCompute(RequestBase):
    action: Literal["inject_compute"]
    node_id: str
    cpu_pct: float | None = Field(default=None, ge=0, le=100)
    memory_pct: float | None = Field(default=None, ge=0, le=100)
    power_w: float | None = Field(default=None, ge=0)
    temp_c: float | None = None


class InjectNetwork(RequestBase):
    action: Literal["inject_network"]
    source_node_id: str
    target_node_id: str
    latency_ms: float | None = Field(default=None, ge=0)
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100)
    bandwidth_mbps: float | None = Field(default=None, ge=0)


class InjectStorage(RequestBase):
    action: Literal["inject_storage"]
    node_id: str
    disk_iops: float | None = Field(default=None, ge=0)
    capacity_used_gb: float | None = Field(default=None, ge=0)


class MigrateRack(RequestBase):
    action: Literal["migrate_rack"]
    node_id: str
    target_rack_id: str
    target_router_id: str


class BlastRadiusQuery(RequestBase):
    action: Literal["blast_radius_query"]
    failed_device_id: str


SimulationRequest = Annotated[
    MoveServer | AddCompute | RemoveNode | InjectCompute | InjectNetwork |
    InjectStorage | MigrateRack | BlastRadiusQuery,
    Field(discriminator="action"),
]
REQUEST_ADAPTER = TypeAdapter(SimulationRequest)


def normalize_request(payload: dict[str, Any]) -> SimulationRequest:
    if "params" not in payload:
        return REQUEST_ADAPTER.validate_python(payload)
    params = dict(payload.get("params") or {})
    action = payload.get("action")
    aliases = {
        "target_router": "target_router_id", "router_id": "target_router_id",
        "target_droplet": "target_rack_id", "source_node": "source_node_id",
        "target_node": "target_node_id", "cpu_percent": "cpu_pct",
        "memory_percent": "memory_pct", "power_watts": "power_w",
        "packet_loss_percent": "packet_loss_pct",
    }
    normalized = {aliases.get(key, key): value for key, value in params.items()}
    if action == "add_compute":
        normalized.setdefault("target_rack_id", _rack_from_router(normalized.get("target_router_id", "")))
    return REQUEST_ADAPTER.validate_python({
        "action": action,
        "projection_steps": payload.get("projection_steps", 3),
        "request_text": payload.get("request_text"),
        "parser_used": payload.get("parser_used", "form"),
        "requested_by": payload.get("requested_by"),
        **normalized,
    })


def _rack_from_router(router_id: str) -> str:
    return router_id.split("/", 1)[0] if "/" in router_id else ""


class Violation(BaseModel):
    code: str
    severity: Severity
    scope: str
    device_id: str | None = None
    message: str
    current_value: float | str | None = None
    limit_value: float | str | None = None
    unit: str | None = None
    threshold_source: str = "default"
    projected: bool = False
    projection_step: int | None = None
    telemetry_provenance: str = "Synthetic Demo"


class BlastRadiusResult(BaseModel):
    failed_device_id: str
    affected_by_type: dict[str, list[str]] = Field(default_factory=dict)
    paths: list[list[str]] = Field(default_factory=list)
    affected_count: int = 0
    execution_time_ms: float = 0
    truncated: bool = False


class AlternativeScore(BaseModel):
    target: str
    score: float
    components: dict[str, float]
    capacity: dict[str, float]
    warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    sim_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    request_text: str | None = None
    parser_used: str = "form"
    allowed: bool
    verdict: str
    graph_version: str
    telemetry_timestamp: datetime | None = None
    telemetry_provenance: str = "Synthetic Demo"
    mutation_summary: dict[str, Any] = Field(default_factory=dict)
    current_violations: list[Violation] = Field(default_factory=list)
    projected_violations: list[Violation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blast_radius: BlastRadiusResult | None = None
    alternatives: list[AlternativeScore] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    report_url: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_time_ms: float
    reasons: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    tier_results: dict[str, Any] = Field(default_factory=dict)
    projections: list[dict[str, Any]] = Field(default_factory=list)
    projected_graph: dict[str, Any] = Field(default_factory=dict)
    clone_id: str = ""
