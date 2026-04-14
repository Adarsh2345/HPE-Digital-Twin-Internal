import networkx as nx
import logging

logger = logging.getLogger(__name__)

class TwinGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_or_update_node(self, node_id: str, node_type: str, status: str, **kwargs):
        """Add or update a node in the graph."""
        if self.graph.has_node(node_id):
            self.graph.nodes[node_id].update({"status": status, **kwargs})
        else:
            self.graph.add_node(node_id, type=node_type, status=status, **kwargs)
        
        logger.info(f"Updated node {node_id} (Type: {node_type}, Status: {status})")

    def add_relationship(self, parent_id: str, child_id: str, relationship="HOSTS"):
        """Add a directed edge representing a relationship."""
        if not self.graph.has_node(parent_id):
            self.graph.add_node(parent_id, type="unknown", status="unknown")
        if not self.graph.has_node(child_id):
            self.graph.add_node(child_id, type="unknown", status="unknown")
            
        self.graph.add_edge(parent_id, child_id, type=relationship)
        logger.info(f"Added relationship {parent_id} -[{relationship}]-> {child_id}")

    def propagate_risk_zone(self, server_id: str):
        """Flag all child VMs as risk_zone due to an overheated parent server."""
        if not self.graph.has_node(server_id):
            return
        descendants = nx.descendants(self.graph, server_id)
        for d in descendants:
            node_data = self.graph.nodes[d]
            if node_data.get("type") == "vm":
                node_data["status"] = "risk_zone"
                logger.info(f"Flagged VM {d} as risk_zone due to server {server_id} overheat")

    def get_node_state(self, node_id: str) -> dict:
        """Get the current state of a node."""
        if self.graph.has_node(node_id):
            return {"node_id": node_id, **self.graph.nodes[node_id]}
        return {}

    def get_children(self, node_id: str) -> list:
        if self.graph.has_node(node_id):
            return list(self.graph.successors(node_id))
        return []

    def get_all_nodes(self) -> dict:
        return dict(self.graph.nodes(data=True))

# Singleton instance
twin_graph = TwinGraph()
