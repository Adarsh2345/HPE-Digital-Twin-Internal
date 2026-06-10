"""
core/simulation/simulator.py
Orchestrates the full what-if simulation pipeline:
1. RCU clone isolation
2. Topology mutation
3. Future metric projection
4. Passes result to validator engine
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
        """
        Full simulation pipeline.
        Returns mutation result, projected graph dict, and future projections.
        The base_graph (production) is NEVER modified.
        """
        # Phase 3 Step 1: RCU deep clone
        clone_id, cloned_graph = self.clone_manager.create_clone(base_graph)
        logger.info(f"Simulation started — clone={clone_id}, action={action}, params={params}")

        # Phase 3 Step 2: Apply topological mutation
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

        # Phase 3 Step 3: Project future metric trends
        projections = self.predictor.project(cloned_graph, steps=projection_steps)

        # Serialise the mutated graph for response
        projected_graph = graph_to_dict(cloned_graph)

        # Release clone from memory
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
