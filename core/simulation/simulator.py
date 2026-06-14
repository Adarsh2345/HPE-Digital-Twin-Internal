"""
core/simulation/simulator.py
Orchestrates the full predictive sandbox simulation engine lifecycle.
Forces metric mapping synchronization across time-steps to support stress scenarios.
"""
import networkx as nx
import logging
from core.simulation.clone_manager import CloneManager
from core.simulation.mutators import TopologyMutator
from core.simulation.future_predictor import FuturePredictor
from core.graph.graph_serializer import graph_to_dict

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self):
        self.clone_manager = CloneManager()
        self.mutator = TopologyMutator()
        self.predictor = FuturePredictor()

    def run(
        self,
        base_graph: nx.DiGraph,
        action: str,
        params: dict,
        projection_steps: int = 3,
    ) -> dict:
        """Full isolated sandbox validation execution workflow."""
        # Phase 3 Step 1: Create an isolated RCU deep copy
        clone_id, cloned_graph = self.clone_manager.create_clone(base_graph)
        logger.info(f"Simulation execution pipeline initialized — ID: {clone_id} | Action: {action}")

        # Phase 3 Step 2: Route request parameters straight into mutator mapping
        mutation_result = self.mutator.apply_mutation(cloned_graph, action, params)
        if not mutation_result.get("success"):
            self.clone_manager.release_clone(clone_id)
            return {
                "success": False,
                "clone_id": clone_id,
                "mutation": mutation_result,
                "projected_graph": None,
                "projections": [],
            }

        # Phase 3 Step 3: Run the predictive metric time-step calculations
        projections = self.predictor.project(cloned_graph, steps=projection_steps)

        # Sync the final step metrics back onto the root of the graph object
        if projections:
            final_step = projections[-1]
            
            for nid, node_metrics in final_step.get("nodes", {}).items():
                if nid in cloned_graph.nodes:
                    # Update both the raw root parameters and the nested properties map
                    cloned_graph.nodes[nid]["metrics"].update(node_metrics)
                    cloned_graph.nodes[nid]["cpu"] = node_metrics.get("cpu", node_metrics.get("cpu_percent", 0.0))
                    cloned_graph.nodes[nid]["memory"] = node_metrics.get("memory", node_metrics.get("memory_percent", 0.0))
                    
            for ekey, edge_metrics in final_step.get("edges", {}).items():
                try:
                    u, v = ekey.split("->")
                    if cloned_graph.has_edge(u, v):
                        cloned_graph.edges[u, v]["metrics"].update(edge_metrics)
                        cloned_graph.edges[u, v]["latency"] = edge_metrics.get("latency", edge_metrics.get("latency_ms", 0.0))
                        cloned_graph.edges[u, v]["packet_loss"] = edge_metrics.get("packet_loss", edge_metrics.get("packet_loss_percent", 0.0))
                except ValueError:
                    pass

        # Serialize results into a standard JSON dataset dictionary
        projected_graph = graph_to_dict(cloned_graph)
        self.clone_manager.release_clone(clone_id)

        return {
            "success": True,
            "clone_id": clone_id,
            "action": action,
            "params": params,
            "mutation": mutation_result,
            "projected_graph": [projected_graph] if isinstance(projected_graph, str) else projected_graph,
            "projections": projections,
        }