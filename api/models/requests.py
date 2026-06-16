"""
api/models/requests.py
Pydantic request body models for all API endpoints.
EXTENDED: Updated interactive documentation examples to use strict normalized keys
(e.g., target_router_id, target_rack_id) to eliminate validation drops in Swagger UI.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any


class SimulationRequest(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Mutation action: "
            "move_server | add_compute | remove_node | "
            "inject_compute | inject_network | inject_storage | migrate_rack"
        ),
    )
    params: dict[str, Any] = Field(..., description="Action parameters")
    projection_steps: int = Field(default=3, ge=1, le=10)

    class Config:
        json_schema_extra = {
            "examples": [
                # ─── Topology mutations ───────────────────────────
                {
                    "action": "move_server",
                    "params": {
                        "server_id": "droplet-1-tor1/server-1", 
                        "target_router_id": "droplet-2-tor2/router-2"
                    },
                    "projection_steps": 3,
                },
                {
                    "action": "add_compute",
                    "params": {
                        "node_id": "server-5",
                        "target_router_id": "droplet-1-tor1/router-1",
                        "target_rack_id": "droplet-1-tor1",
                        "ip": "10.10.1.13",
                    },
                    "projection_steps": 3,
                },
                {
                    "action": "remove_node",
                    "params": {"node_id": "droplet-2-tor2/server-4"},
                    "projection_steps": 3,
                },
                # ─── Compute stress injection ─────────────────────
                {
                    "action": "inject_compute",
                    "params": {
                        "node_id": "droplet-1-tor1/server-1",
                        "cpu_percent": 92.0,
                        "memory_percent": 88.0,
                        "power_watts": 310.0,
                    },
                    "projection_steps": 5,
                },
                # ─── Network degradation injection ────────────────
                {
                    "action": "inject_network",
                    "params": {
                        "source_node": "droplet-3-mgmt/spine-router",
                        "target_node": "droplet-1-tor1/router-1",
                        "latency_ms": 160.0,
                        "packet_loss_percent": 6.5,
                    },
                    "projection_steps": 3,
                },
                # ─── Storage IOPS injection ───────────────────────
                {
                    "action": "inject_storage",
                    "params": {
                        "node_id": "droplet-1-tor1/server-2",
                        "disk_iops": 3900,
                    },
                    "projection_steps": 5,
                },
                # ─── Rack migration ───────────────────────────────
                {
                    "action": "migrate_rack",
                    "params": {
                        "node_id": "droplet-1-tor1/server-1",
                        "target_droplet": "droplet-2-tor2",
                        "target_router": "droplet-2-tor2/router-2",
                    },
                    "projection_steps": 3,
                },
            ]
        }


class ChaosRequest(BaseModel):
    enable: bool = Field(..., description="True to enable chaos, False to disable")
    nodes: Optional[list[str]] = Field(
        default=None,
        description="Specific nodes to affect (empty = all nodes)"
    )
    scenario: Optional[str] = Field(
        default="full",
        description="Chaos scenario type: full | compute | network | storage"
    )


class NodeQueryRequest(BaseModel):
    node_id: str