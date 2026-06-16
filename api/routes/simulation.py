"""
api/routes/simulation.py
POST /api/v1/simulate         — run a what-if simulation with full validation
GET  /api/v1/simulate/actions — list supported actions (extended catalog)
"""
from fastapi import APIRouter, HTTPException, Body
from api.models.requests import SimulationRequest
from core.orchestrator import orchestrator
from core.simulation.simulator import Simulator
from core.validation.validator_engine import ValidatorEngine
from core.recommendations.recommendation_engine import RecommendationEngine
from core.graph.graph_serializer import dict_to_graph

router = APIRouter(prefix="/api/v1/simulate", tags=["Simulation"])

_simulator = Simulator()
_validator = ValidatorEngine()
_recommender = RecommendationEngine()


@router.post("")
def run_simulation(
    req: SimulationRequest = Body(
        ...,
        openapi_examples={
            "Scenario 1: Move Server": {
                "summary": "Move server between ToR switches",
                "description": "Clips old edge, maps new edge, and updates subnet assignments in memory.",
                "value": {
                    "action": "move_server",
                    "params": {"server_id": "droplet-1-tor1/server-1", "target_router_id": "droplet-2-tor2/router-2"},
                    "projection_steps": 3
                }
            },
            "Scenario 2: Add Compute Node": {
                "summary": "Provision new hardware node",
                "description": "Checks rack vertical U-space and power headroom capacity bounds on target subnet.",
                "value": {
                    "action": "add_compute",
                    "params": {"node_id": "server-5", "target_router_id": "droplet-1-tor1/router-1", "target_rack_id": "droplet-1-tor1", "ip": "10.10.1.13"},
                    "projection_steps": 3
                }
            },
            "Scenario 3: Remove Node": {
                "summary": "Decommission an existing asset",
                "description": "Removes a node from topology to validate remaining capacity balances.",
                "value": {
                    "action": "remove_node",
                    "params": {"node_id": "droplet-2-tor2/server-4"},
                    "projection_steps": 3
                }
            },
            "Scenario 4: Compute Stress Peak": {
                "summary": "Inject CPU & Power Stress Load",
                "description": "Simulates heavy processing batch jobs spikes or runaway hypervisor processes.",
                "value": {
                    "action": "inject_compute",
                    "params": {"node_id": "droplet-1-tor1/server-1", "cpu_percent": 92.0, "memory_percent": 88.0, "power_watts": 310.0},
                    "projection_steps": 5
                }
            },
            "Scenario 5: BGP Link Congestion": {
                "summary": "Degrade Network Link SLA",
                "description": "Injects severe latency and packet loss to force routing path degradation warnings.",
                "value": {
                    "action": "inject_network",
                    "params": {"source_node_id": "droplet-3-mgmt/spine-router", "target_node_id": "droplet-1-tor1/router-1", "latency_ms": 160.0, "packet_loss_percent": 6.5},
                    "projection_steps": 3
                }
            },
            "Scenario 6: NVMe Disk IOPS Saturation": {
                "summary": "Inject Storage Pool Pressure",
                "description": "Simulates storage network path congestion or heavy full-table indexing scans.",
                "value": {
                    "action": "inject_storage",
                    "params": {"node_id": "droplet-1-tor1/server-2", "disk_iops": 3900},
                    "projection_steps": 5
                }
            },
            "Scenario 7: Rack Chassis Migration": {
                "summary": "Full Cross-Droplet Migration",
                "description": "Atomically shifts container droplet allocation structures and rewires switch links.",
                "value": {
                    "action": "migrate_rack",
                    "params": {"node_id": "droplet-1-tor1/server-1", "target_rack_id": "droplet-2-tor2", "target_router_id": "droplet-2-tor2/router-2"},
                    "projection_steps": 3
                }
            }
        }
    )
):
    """
    Phase 3 + 4 + 5 Sandbox Simulation Processing Pipeline.
    Select an architectural operation or performance stress vector from the dropdown to run compliance checks.
    """
    try:
        base_graph = orchestrator.get_derived_graph()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # ─── REMAP INCOMING SCHEMA KEYS FOR MUTATOR COMPATIBILITY ───
    simulation_params = dict(req.params)
    
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

    # Phase 3: RCU clone + mutation/injection + projection
    sim_result = _simulator.run(
        base_graph,
        action=req.action,
        params=simulation_params,
        projection_steps=req.projection_steps,
    )

    if not sim_result["success"]:
        raise HTTPException(status_code=400, detail=sim_result["mutation"])

    # Phase 4: 4-tier validation on projected graph
    projected_graph = dict_to_graph(sim_result["projected_graph"])
    projections = sim_result["projections"]
    validation = _validator.validate(projected_graph, projections)

    # Phase 5: Recommendation report
    report = _recommender.generate_report(
        action=req.action,
        params=req.params,
        validation_result=validation,
        mutation_result=sim_result["mutation"],
        projections=projections,
    )

    return {
        **report,
        "clone_id": sim_result["clone_id"],
        "projected_graph": sim_result["projected_graph"],
        "projections": projections,
        "tier_results": validation.get("tier_results", {}),
        "scenario_results":   sim_result.get("scenario_results", []),
        "impact_predictions": sim_result.get("impact_predictions", {}),
    }


@router.get("/actions")
def list_actions():
    """List all supported simulation actions with parameter specs and interactive examples."""
    return {
        "actions": [
            # ─── Topology Mutations ───────────────────────────────────────────
            {
                "category": "topology",
                "action": "move_server",
                "description": "Move a compute node to a different ToR switch. Clips old edge, creates new edge, updates subnet assignment.",
                "params": {
                    "server_id": "string — ID of the compute node to move",
                    "target_router_id": "string — ID of the destination ToR router",
                },
                "example": {"server_id": "droplet-1-tor1/server-1", "target_router_id": "droplet-2-tor2/router-2"},
                "constraints_checked": ["power_envelope", "rack_u_space", "compute_overload", "network_sla"],
            },
            {
                "category": "topology",
                "action": "add_compute",
                "description": "Provision a new compute blade under a ToR switch. Validates rack U-space and power headroom before allowing.",
                "params": {
                    "node_id": "string — unique ID for the new node",
                    "target_router_id": "string — parent ToR router ID",
                    "target_rack_id": "string — parent Rack/Droplet ID",
                    "ip": "string (optional) — static IP in the ToR subnet",
                    "role": "string (optional, default: compute-node)",
                },
                "example": {"node_id": "server-5", "target_router_id": "droplet-1-tor1/router-1", "target_rack_id": "droplet-1-tor1", "ip": "10.10.1.13"},
                "constraints_checked": ["rack_u_space", "power_envelope", "compute_overload"],
            },
            {
                "category": "topology",
                "action": "remove_node",
                "description": "Decommission any node from the topology. Validates remaining capacity after removal.",
                "params": {
                    "node_id": "string — ID of the node to remove",
                },
                "example": {"node_id": "droplet-2-tor2/server-4"},
                "constraints_checked": ["compute_overload", "power_envelope"],
            },
            # ─── Metric Injection Scenarios ───────────────────────────────
            {
                "category": "compute",
                "action": "inject_compute",
                "description": "Inject CPU, memory, and power stress metrics directly into a node. Simulates batch job peaks, VM migration load, or runaway processes.",
                "params": {
                    "node_id": "string — target compute node",
                    "cpu_percent": "float — simulated CPU load (0-100). Warning >70%, Critical >85%, Limit 95%",
                    "memory_percent": "float — simulated memory load (0-100). Warning >75%, Critical >90%, Limit 95%",
                    "power_watts": "float — simulated power draw per node. Warning >1200W subnet total, Limit 1400W",
                },
                "example": {
                    "node_id": "droplet-1-tor1/server-1",
                    "cpu_percent": 92.0,
                    "memory_percent": 88.0,
                    "power_watts": 310.0,
                },
                "constraints_checked": ["compute_overload", "power_envelope", "future_cpu_projection"],
            },
            {
                "category": "network",
                "action": "inject_network",
                "description": "Inject latency and packet-loss metrics onto a specific BGP link. Simulates NIC flap, MTU mismatch, or congested spine path.",
                "params": {
                    "source_node_id": "string — link source (e.g. spine-router, router-1)",
                    "target_node_id": "string — link target (e.g. router-1, server-1)",
                    "latency_ms": "float — injected latency. Warning >100ms, SLA Breach >150ms",
                    "packet_loss_percent": "float — injected packet loss. Warning >2%, Breach >5%",
                },
                "example": {
                    "source_node_id": "droplet-3-mgmt/spine-router",
                    "target_node_id": "droplet-1-tor1/router-1",
                    "latency_ms": 160.0,
                    "packet_loss_percent": 6.5,
                },
                "constraints_checked": ["network_sla", "packet_loss", "future_latency_projection"],
            },
            {
                "category": "storage",
                "action": "inject_storage",
                "description": "Inject elevated disk IOPS into a compute, middleware, or graph-database node. Simulates storage network path congestion or heavy full-table indexing scans.",
                "params": {
                    "node_id": "string — target node (compute-node, middleware, or graph-database)",
                    "disk_iops": "int — injected IOPS. Warning >3000, Breach >4000 (NVMe limit)",
                },
                "example": {
                    "node_id": "droplet-1-tor1/server-2",
                    "disk_iops": 3900,
                },
                "constraints_checked": ["storage_iops", "future_iops_projection"],
            },
            {
                "category": "topology",
                "action": "migrate_rack",
                "description": "Migrate a node to a different physical rack (droplet) and ToR switch in one operation. Updates both the network edge and the droplet metadata tag.",
                "params": {
                    "node_id": "string — node to migrate",
                    "target_rack_id": "string — destination rack droplet (e.g. droplet-2-tor2)",
                    "target_router_id": "string — destination ToR router (e.g. router-2)",
                },
                "example": {
                    "node_id": "droplet-1-tor1/server-1",
                    "target_rack_id": "droplet-2-tor2",
                    "target_router_id": "droplet-2-tor2/router-2",
                },
                "constraints_checked": ["rack_u_space", "power_envelope", "network_sla"],
            },
        ]
    }