"""
core/simulation/mutators.py
Applies structural topology mutations to a cloned graph.
EXTENDED: now supports all simulation scenario types including
compute stress injection, network SLA breach, storage IOPS injection,
rack migration, and full decommission.
"""
import networkx as nx
import logging

logger = logging.getLogger(__name__)


class TopologyMutator:

    # ------------------------------------------------------------------ #
    # EXISTING: Move server between ToR switches                           #
    # ------------------------------------------------------------------ #
    def move_server(self, G: nx.DiGraph, server_id: str, target_router: str) -> dict:
        """Move a compute node from its current ToR switch to a target ToR switch."""
        if server_id not in G.nodes:
            return {"success": False, "error": f"Node '{server_id}' not found"}
        if target_router not in G.nodes:
            return {"success": False, "error": f"Target router '{target_router}' not found"}

        old_routers = [
            pred for pred in G.predecessors(server_id)
            if G.nodes[pred].get("role") in ("tor-router", "spine-switch")
        ]

        for old_router in old_routers:
            if G.has_edge(old_router, server_id):
                G.remove_edge(old_router, server_id)
                logger.info(f"Clipped edge: {old_router} -> {server_id}")

        old_subnet = G.nodes[server_id].get("subnet", "")
        new_subnet = G.nodes[target_router].get("subnet", old_subnet)
        G.nodes[server_id]["subnet"] = new_subnet

        G.add_edge(target_router, server_id,
                   description=f"Moved: {server_id} to {target_router}",
                   state="active", metrics={})
        logger.info(f"New edge: {target_router} -> {server_id}")

        return {
            "success": True,
            "server": server_id,
            "old_routers": old_routers,
            "new_router": target_router,
            "old_subnet": old_subnet,
            "new_subnet": new_subnet,
        }

    # ------------------------------------------------------------------ #
    # EXISTING: Add new compute node                                       #
    # ------------------------------------------------------------------ #
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
        G.add_edge(router_id, node_id,
                   description=f"New link to {node_id}", state="active", metrics={})
        logger.info(f"Added node '{node_id}' under router '{router_id}'")
        return {"success": True, "node_id": node_id, "router": router_id, "subnet": subnet}

    # ------------------------------------------------------------------ #
    # EXISTING: Remove node                                                #
    # ------------------------------------------------------------------ #
    def remove_node(self, G: nx.DiGraph, node_id: str) -> dict:
        if node_id not in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        G.remove_node(node_id)
        logger.info(f"Removed node '{node_id}'")
        return {"success": True, "removed": node_id}

    # ------------------------------------------------------------------ #
    # NEW: Inject compute stress metrics into a node                       #
    # ------------------------------------------------------------------ #
    def inject_compute_stress(self, G: nx.DiGraph, node_id: str,
                               cpu_percent: float = 92.0,
                               memory_percent: float = 75.0,
                               power_watts: float = 280.0) -> dict:
        """
        Inject high CPU / memory / power metrics directly into a node's
        metrics dict to simulate a compute overload scenario.
        Useful for validating threshold breach without waiting for chaos mode.
        """
        if node_id not in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}

        existing = G.nodes[node_id].get("metrics", {})
        injected = {
            **existing,
            "cpu_percent": float(cpu_percent),
            "memory_percent": float(memory_percent),
            "power_watts": float(power_watts),
            "injected": True,
        }
        G.nodes[node_id]["metrics"] = injected
        # Also flatten for derived_state_builder compatibility
        G.nodes[node_id]["cpu"] = float(cpu_percent)
        G.nodes[node_id]["memory"] = float(memory_percent)
        logger.info(f"Compute stress injected on '{node_id}': CPU={cpu_percent}% MEM={memory_percent}%")
        return {
            "success": True,
            "node_id": node_id,
            "injected_cpu": cpu_percent,
            "injected_memory": memory_percent,
            "injected_power": power_watts,
        }

    # ------------------------------------------------------------------ #
    # NEW: Inject network latency / packet loss on a link                  #
    # ------------------------------------------------------------------ #
    def inject_network_degradation(self, G: nx.DiGraph,
                                    source_node: str, target_node: str,
                                    latency_ms: float = 160.0,
                                    packet_loss_percent: float = 0.5) -> dict:
        """
        Inject latency and packet-loss metrics onto a specific edge to
        simulate BGP path degradation or NIC flap.
        Creates the edge if it doesn't exist (useful for modelling new paths).
        """
        if source_node not in G.nodes:
            return {"success": False, "error": f"Source node '{source_node}' not found"}
        if target_node not in G.nodes:
            return {"success": False, "error": f"Target node '{target_node}' not found"}

        if not G.has_edge(source_node, target_node):
            G.add_edge(source_node, target_node,
                       description=f"Injected link: {source_node}->{target_node}",
                       state="degraded", metrics={})
            created = True
        else:
            created = False

        existing = G.edges[source_node, target_node].get("metrics", {})
        injected = {
            **existing,
            "latency_ms": float(latency_ms),
            "packet_loss_percent": float(packet_loss_percent),
            "injected": True,
        }
        G.edges[source_node, target_node]["metrics"] = injected
        G.edges[source_node, target_node]["latency"] = float(latency_ms)
        G.edges[source_node, target_node]["packet_loss"] = float(packet_loss_percent)

        logger.info(
            f"Network degradation injected on {source_node}->{target_node}: "
            f"latency={latency_ms}ms loss={packet_loss_percent}%"
        )
        return {
            "success": True,
            "link": f"{source_node}->{target_node}",
            "injected_latency_ms": latency_ms,
            "injected_packet_loss_percent": packet_loss_percent,
            "edge_created": created,
        }

    # ------------------------------------------------------------------ #
    # NEW: Inject high IOPS metrics into a storage-bearing node            #
    # ------------------------------------------------------------------ #
    def inject_storage_pressure(self, G: nx.DiGraph, node_id: str,
                                 disk_iops: int = 3800) -> dict:
        """
        Inject elevated disk IOPS into a node to simulate NVMe saturation,
        backup jobs, or database full-scan workloads.
        """
        if node_id not in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}

        existing = G.nodes[node_id].get("metrics", {})
        injected = {**existing, "disk_iops": int(disk_iops), "injected": True}
        G.nodes[node_id]["metrics"] = injected

        logger.info(f"Storage pressure injected on '{node_id}': IOPS={disk_iops}")
        return {
            "success": True,
            "node_id": node_id,
            "injected_iops": disk_iops,
        }

    # ------------------------------------------------------------------ #
    # NEW: Migrate a node between droplets (rack migration)                #
    # ------------------------------------------------------------------ #
    def migrate_rack(self, G: nx.DiGraph, node_id: str,
                     target_droplet: str, target_router: str) -> dict:
        """
        Migrate a node to a different physical rack (droplet) and ToR switch.
        Updates both the droplet tag and the network edge in one atomic operation.
        This combines move_server with a droplet metadata update.
        """
        if node_id not in G.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        if target_router not in G.nodes:
            return {"success": False, "error": f"Target router '{target_router}' not found"}

        old_droplet = G.nodes[node_id].get("droplet", "unknown")

        # Re-use move_server to handle edge rewiring
        move_result = self.move_server(G, node_id, target_router)
        if not move_result["success"]:
            return move_result

        # Update rack metadata
        G.nodes[node_id]["droplet"] = target_droplet
        logger.info(
            f"Rack migration complete: '{node_id}' "
            f"from {old_droplet} -> {target_droplet}, router -> {target_router}"
        )
        return {
            "success": True,
            "node_id": node_id,
            "old_droplet": old_droplet,
            "new_droplet": target_droplet,
            "new_router": target_router,
            **move_result,
        }

    # ------------------------------------------------------------------ #
    # DISPATCHER: apply_mutation — routes all action strings               #
    # ------------------------------------------------------------------ #
    def apply_mutation(self, G: nx.DiGraph, action: str, params: dict) -> dict:
        """
        Central dispatcher. Supports all simulation action strings.

        Supported actions:
          move_server         — move compute node to another ToR
          add_compute         — add new compute blade
          remove_node         — decommission a node
          inject_compute      — inject CPU/mem/power stress metrics
          inject_network      — inject latency/packet-loss on a link
          inject_storage      — inject high IOPS on a node
          migrate_rack        — move node to different droplet + ToR
        """
        if action == "move_server":
            return self.move_server(
                G,
                params["server_id"],
                params["target_router"]
            )

        elif action == "add_compute":
            return self.add_compute_node(
                G,
                params["node_id"],
                params["router_id"],
                ip=params.get("ip", ""),
                role=params.get("role", "compute-node"),
            )

        elif action == "remove_node":
            return self.remove_node(G, params["node_id"])

        elif action == "inject_compute":
            return self.inject_compute_stress(
                G,
                node_id=params["node_id"],
                cpu_percent=float(params.get("cpu_percent", 92.0)),
                memory_percent=float(params.get("memory_percent", 75.0)),
                power_watts=float(params.get("power_watts", 280.0)),
            )

        elif action == "inject_network":
            return self.inject_network_degradation(
                G,
                source_node=params["source_node"],
                target_node=params["target_node"],
                latency_ms=float(params.get("latency_ms", 160.0)),
                packet_loss_percent=float(params.get("packet_loss_percent", 0.5)),
            )

        elif action == "inject_storage":
            return self.inject_storage_pressure(
                G,
                node_id=params["node_id"],
                disk_iops=int(params.get("disk_iops", 3800)),
            )

        elif action == "migrate_rack":
            return self.migrate_rack(
                G,
                node_id=params["node_id"],
                target_droplet=params["target_droplet"],
                target_router=params["target_router"],
            )

        else:
            return {"success": False, "error": f"Unknown action: '{action}'"}