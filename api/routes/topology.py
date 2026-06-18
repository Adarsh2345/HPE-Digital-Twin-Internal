"""
api/routes/topology.py
GET /api/v1/topology        — full topology graph
GET /api/v1/topology/nodes  — node list
GET /api/v1/topology/node/{node_id} — single node detail
"""
from fastapi import APIRouter, HTTPException
from core.orchestrator import orchestrator
from core.graph.graph_serializer import graph_to_dict
from core.graph.graph_utils import get_node, get_nodes_by_role, get_neighbors

router = APIRouter(prefix="/api/v1/topology", tags=["Topology"])


@router.get("")
def get_topology():
    try:
        G = orchestrator.get_derived_graph()
        return graph_to_dict(G)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/nodes")
def get_nodes():
    G = orchestrator.get_derived_graph()
    return [{"id": n, **G.nodes[n]} for n in G.nodes]


@router.get("/node/{node_id:path}")
def get_node_detail(node_id: str):
    G = orchestrator.get_derived_graph()
    node = get_node(G, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    node["neighbors"] = get_neighbors(G, node_id)
    return node


@router.get("/role/{role}")
def get_by_role(role: str):
    G = orchestrator.get_derived_graph()
    return get_nodes_by_role(G, role)


@router.get("/edges")
def get_edges():
    G = orchestrator.get_derived_graph()
    return [{"source": u, "target": v, **G.edges[u, v]} for u, v in G.edges]
