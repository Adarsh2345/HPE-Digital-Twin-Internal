"""
api/models/requests.py
Pydantic request body models for all API endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any


class SimulationRequest(BaseModel):
    action: str = Field(..., description="Mutation action: move_server | add_compute | remove_node")
    params: dict[str, Any] = Field(..., description="Action parameters")
    projection_steps: int = Field(default=3, ge=1, le=10)

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "action": "move_server",
                    "params": {"server_id": "server-1", "target_router": "router-2"},
                    "projection_steps": 3,
                },
                {
                    "action": "add_compute",
                    "params": {"node_id": "server-5", "router_id": "router-1", "ip": "10.10.1.13"},
                    "projection_steps": 3,
                },
            ]
        }


class ChaosRequest(BaseModel):
    enable: bool = Field(..., description="True to enable chaos, False to disable")
    nodes: Optional[list[str]] = Field(default=None, description="Specific nodes to affect (empty = all)")
    scenario: Optional[str] = Field(default="full", description="Chaos scenario type")


class NodeQueryRequest(BaseModel):
    node_id: str
