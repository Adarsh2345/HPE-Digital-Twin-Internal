from fastapi import FastAPI, Depends, HTTPException, Body, BackgroundTasks
from typing import Dict, Any
import os

from src.api.auth import verify_operator
from src.registry.schema import validate_telemetry
from src.twin.graph import twin_graph
from src.state.hot import hot_state
from src.state.cold import init_db, record_asset_drift, record_system_drift, load_latest_state

app = FastAPI(title="Schema-based Private Cloud Digital Twin")

@app.on_event("startup")
def startup_event():
    init_db()
    
    # Reload from cold state to ensure data survives server restart
    assets, systems = load_latest_state()
    for a in assets:
        twin_graph.add_or_update_node(
            a.asset_id, node_type=a.asset_type, status=a.status,
            temperature=a.temperature, cpu_utilization=a.cpu_utilization
        )
    for s in systems:
        twin_graph.add_or_update_node(
            s.system_id, node_type=s.system_type, status=s.status,
            memory_utilization=s.memory_utilization
        )
        if s.parent_asset_id:
            twin_graph.add_relationship(s.parent_asset_id, s.system_id)

def check_anomalies(node_id: str):
    node_data = twin_graph.get_node_state(node_id)
    if not node_data:
        return
    
    node_type = node_data.get("type", "")
    if node_type in ["server", "switch", "storage", "vm", "hypervisor"] and node_data.get("temperature", 0.0) > 90.0:
        # Automatically update node to critical
        twin_graph.add_or_update_node(node_id, node_type=node_type, status="critical")
        hot_state.set_node_state(node_id, twin_graph.get_node_state(node_id))
        
        # Risk Propagation to VMs
        twin_graph.propagate_risk_zone(node_id)
        for nid, ndata in twin_graph.get_all_nodes().items():
            if ndata.get("status") == "risk_zone":
                hot_state.set_node_state(nid, twin_graph.get_node_state(nid))
                
        # Generate Anomaly Alert Artifact in workspace
        alert_file = os.path.join(os.path.dirname(__file__), "..", "..", "anomaly_alerts.md")
        with open(alert_file, "a") as f:
            f.write(f"- [ANOMALY] Server {node_id} exceeded 90.0C (Current: {node_data.get('temperature')}C). VMs flagged as risk_zone.\n")


@app.post("/ingest/asset", dependencies=[Depends(verify_operator)])
async def ingest_asset(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    try:
        validate_telemetry(payload, schema_type="asset")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    twin_graph.add_or_update_node(
        payload["asset_id"], 
        node_type=payload["asset_type"], 
        status=payload["status"],
        temperature=payload.get("temperature"),
        cpu_utilization=payload.get("cpu_utilization")
    )
    
    hot_state.set_node_state(payload["asset_id"], twin_graph.get_node_state(payload["asset_id"]))
    record_asset_drift(payload)
    
    background_tasks.add_task(check_anomalies, payload["asset_id"])
    return {"message": "Asset telemetry ingested successfully", "asset_id": payload["asset_id"]}

@app.post("/ingest/system", dependencies=[Depends(verify_operator)])
async def ingest_system(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    try:
        validate_telemetry(payload, schema_type="system")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    twin_graph.add_or_update_node(
        payload["system_id"], 
        node_type=payload["system_type"], 
        status=payload["status"],
        memory_utilization=payload.get("memory_utilization")
    )
    twin_graph.add_relationship(payload["parent_asset_id"], payload["system_id"])
    
    hot_state.set_node_state(payload["system_id"], twin_graph.get_node_state(payload["system_id"]))
    record_system_drift(payload)
    
    background_tasks.add_task(check_anomalies, payload["system_id"])
    return {"message": "System telemetry ingested successfully", "system_id": payload["system_id"]}

@app.get("/twin/nodes")
async def get_all_nodes():
    return twin_graph.get_all_nodes()

@app.get("/twin/state/hot/{node_id}")
async def get_hot_state(node_id: str):
    # Fix 404: Try Redis hot_state first, then safely fallback to memory TwinGraph
    state = hot_state.get_node_state(node_id)
    if not state:
        state = twin_graph.get_node_state(node_id)
    if not state:
        raise HTTPException(status_code=404, detail="Node hot state not found")
    return state
