"""
core/simulation/mutators.py
Applies structural topology mutations to a cloned graph:
- Move server between racks/subnets
- Add/remove compute nodes
- Change link configurations
"""
import networkx as nx
import logging

logger = logging.getLogger(__name__)


class TopologyMutator:
    def move_server(self, G: nx.DiGraph, server_id: str, target_router: str) -> dict:
        """
        Move a compute node from its current ToR switch to a target ToR switch.
        Clips old edge and adds new edge.
        """
        if server_id not in G.nodes:
            return {"success": False, "error": f"Node '{server_id}' not found"}
        if target_router not in G.nodes:
            return {"success": False, "error": f"Target router '{target_router}' not found"}

        # Find current parent router (predecessor)
        old_routers = [
            pred for pred in G.predecessors(server_id)
            if G.nodes[pred].get("role") in ("tor-router", "spine-switch")
        ]

        removed_edges = []
        for old_router in old_routers:
            if G.has_edge(old_router, server_id):
                attrs = dict(G.edges[old_router, server_id])
                G.remove_edge(old_router, server_id)
                removed_edges.append((old_router, server_id, attrs))
                logger.info(f"Clipped edge: {old_router} → {server_id}")

        # Hook up new edge
        old_subnet = G.nodes[server_id].get("subnet", "")
        new_subnet = G.nodes[target_router].get("subnet", old_subnet)
        G.nodes[server_id]["subnet"] = new_subnet

        G.add_edge(target_router, server_id, description=f"Moved: {server_id} to {target_router}", state="active", metrics={})
        logger.info(f"New edge: {target_router} → {server_id}")

        return {
            "success": True,
            "server": server_id,
            "old_routers": old_routers,
            "new_router": target_router,
            "old_subnet": old_subnet,
            "new_subnet": new_subnet,
        }

    def add_compute_node(self, G: nx.DiGraph, node_id: str, router_id: str,
                         ip: str = "", role: str = "compute-node") -> dict:
        if node_id in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' already exists"}
        if router_id not in G.nodes:
            return {"success": False, "error": f"Router '{router_id}' not found"}

        subnet = G.nodes[router_id].get("subnet", "")
        G.add_node(node_id, id=node_id, name=node_id, role=role, ip=ip,
                   image="ubuntu:24.04", droplet="", description=f"Added: {node_id}",
                   subnet=subnet, state="healthy", metrics={})
        G.add_edge(router_id, node_id, description=f"New link to {node_id}", state="active", metrics={})
        logger.info(f"Added node '{node_id}' under router '{router_id}'")
        return {"success": True, "node_id": node_id, "router": router_id, "subnet": subnet}

    def remove_node(self, G: nx.DiGraph, node_id: str) -> dict:
        if node_id not in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        G.remove_node(node_id)
        logger.info(f"Removed node '{node_id}'")
        return {"success": True, "removed": node_id}

    def apply_mutation(self, G: nx.DiGraph, action: str, params: dict) -> dict:
        if action == "move_server":
            return self.move_server(G, params["server_id"], params["target_router"])
        elif action == "add_compute":
            return self.add_compute_node(
                G, params["node_id"], params["router_id"],
                ip=params.get("ip", ""), role=params.get("role", "compute-node")
            )
        elif action == "remove_node":
            return self.remove_node(G, params["node_id"])
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
