"""
core/simulation/simulator.py
Full 12-phase simulation pipeline.
Phases: Clone → Mutate → ImpactAnalyze → BehaviorPredict → ScenarioLoop → Validate → Report
"""
import copy
import networkx as nx
import logging
from core.simulation.clone_manager   import CloneManager
from core.simulation.mutators        import TopologyMutator
from core.simulation.future_predictor import FuturePredictor
from core.graph.graph_serializer     import graph_to_dict

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self):
        self.clone_manager = CloneManager()
        self.mutator       = TopologyMutator()

    def run(
        self,
        base_graph:       nx.DiGraph,
        action:           str,
        params:           dict,
        projection_steps: int  = 3,
        run_scenarios:    bool = True,
    ) -> dict:
        # -------------------------------------------------------------- #
        # Phase 5: Clone production graph — never touch original          #
        # -------------------------------------------------------------- #
        clone_id, cloned_graph = self.clone_manager.create_clone(base_graph)
        logger.info(f"[Simulator] clone={clone_id} action={action}")

        # -------------------------------------------------------------- #
        # Phase 6: Topology Mutation                                       #
        # -------------------------------------------------------------- #
        mutation_result = self.mutator.apply_mutation(cloned_graph, action, params)
        if not mutation_result.get("success"):
            self.clone_manager.release_clone(clone_id)
            return {
                "success": False,
                "clone_id": clone_id,
                "mutation": mutation_result,
                "projected_graph": None,
                "projections": [],
                "scenario_results": [],
                "impact_predictions": {},
            }

        # -------------------------------------------------------------- #
        # Phase 8: ImpactAnalyzer — what changed in the graph?            #
        # -------------------------------------------------------------- #
        impact_predictions: dict = {}
        try:
            from core.analytics.model_registry import registry as _reg
            if _reg.ready:
                impact_predictions = _reg.impact_analyzer.analyze(
                    base_graph, cloned_graph, mutation_result, action=action
                )
        except Exception as e:
            logger.warning(f"ImpactAnalyzer skipped: {e}")

        # -------------------------------------------------------------- #
        # Phase 9: BehaviorModel projection                                #
        # -------------------------------------------------------------- #
        try:
            from core.analytics.model_registry import registry as _reg
            bm = _reg.behavior_model if _reg.ready else None
        except Exception:
            bm = None

        predictor   = FuturePredictor(behavior_model=bm)
        projections = predictor.project(cloned_graph, steps=projection_steps)

        # Sync final projected metrics back to the cloned graph
        if projections:
            self._sync_projections(cloned_graph, projections[-1])

        # -------------------------------------------------------------- #
        # Phase 7 / 10: Run each discovered scenario                       #
        # -------------------------------------------------------------- #
        scenario_results: list[dict] = []
        if run_scenarios:
            scenario_results = self._run_scenario_loop(
                base_graph, cloned_graph, action, params,
                mutation_result, predictor, projection_steps
            )

        projected_graph = graph_to_dict(cloned_graph)
        self.clone_manager.release_clone(clone_id)

        return {
            "success":            True,
            "clone_id":           clone_id,
            "action":             action,
            "params":             params,
            "mutation":           mutation_result,
            "projected_graph":    projected_graph,
            "projections":        projections,
            "scenario_results":   scenario_results,
            "impact_predictions": impact_predictions,
        }

    # ------------------------------------------------------------------ #
    # Scenario loop — Phase 7 / 10                                        #
    # ------------------------------------------------------------------ #
    def _run_scenario_loop(
        self,
        base_graph: nx.DiGraph,
        mutated_graph: nx.DiGraph,
        action: str,
        params: dict,
        mutation_result: dict,
        predictor: FuturePredictor,
        projection_steps: int,
    ) -> list[dict]:
        from core.validation.validator_engine import ValidatorEngine
        from core.analytics.model_registry import registry as _reg

        if not _reg.ready:
            return []

        scenarios = _reg.get_scenarios()
        validator = ValidatorEngine()
        results   = []

        for scenario in scenarios:
            # Apply scenario baseline metrics to all compute nodes in a fresh clone
            s_graph = copy.deepcopy(mutated_graph)
            s_metrics = scenario.get("metrics", {})

            for nid in s_graph.nodes:
                role = s_graph.nodes[nid].get("role", "")
                m    = dict(s_graph.nodes[nid].get("metrics", {}))

                if role == "compute-node":
                    m.update({
                        k: v for k, v in s_metrics.items()
                        if k in ("cpu_percent", "memory_percent", "disk_iops", "power_watts")
                    })
                elif role in ("tor-router", "spine-switch"):
                    m.update({
                        k: v for k, v in s_metrics.items()
                        if k in ("bandwidth_mbps", "latency_ms")
                    })
                elif role in ("storage-controller", "storage-tor"):
                    if "disk_iops" in s_metrics:
                        m["disk_iops"] = s_metrics["disk_iops"]

                s_graph.nodes[nid]["metrics"] = m

            # Run impact analysis under this scenario's load
            s_impact: dict = {}
            try:
                s_impact = _reg.impact_analyzer.analyze(
                    base_graph, s_graph, mutation_result, action=action
                )
                # Apply impact predictions back to the scenario graph
                for nid, pred in s_impact.items():
                    if nid in s_graph.nodes:
                        m = dict(s_graph.nodes[nid].get("metrics", {}))
                        m.update(pred.get("compute", {}))
                        m.update(pred.get("storage", {}))
                        s_graph.nodes[nid]["metrics"] = m
            except Exception as e:
                logger.debug(f"Scenario impact skipped: {e}")

            s_proj  = predictor.project(s_graph, steps=1)
            s_valid = validator.validate(s_graph, s_proj)

            # Collect impacted nodes
            affected = [
                nid for nid, pred in s_impact.items()
                if abs(pred.get("traffic_delta_mbps", 0)) > 50
            ]

            results.append({
                "scenario":        scenario["name"],
                "label":           scenario.get("label", scenario["name"]),
                "status":          "PASS" if s_valid["allowed"] else "FAIL",
                "violations":      s_valid.get("reasons", []),
                "warnings":        s_valid.get("warnings", []),
                "affected_nodes":  affected,
                "predicted_state": {
                    nid: {
                        "compute": p.get("compute", {}),
                        "network": p.get("network", {}),
                        "storage": p.get("storage", {}),
                    }
                    for nid, p in s_impact.items()
                },
            })

        return results

    # ------------------------------------------------------------------ #
    # Helper                                                               #
    # ------------------------------------------------------------------ #
    def _sync_projections(self, G: nx.DiGraph, final_step: dict):
        for nid, nm in final_step.get("nodes", {}).items():
            if nid in G.nodes:
                G.nodes[nid]["metrics"].update(nm)
                G.nodes[nid]["cpu"]    = nm.get("cpu_percent", 0.0)
                G.nodes[nid]["memory"] = nm.get("memory_percent", 0.0)
        for ekey, em in final_step.get("edges", {}).items():
            try:
                u, v = ekey.split("->")
                if G.has_edge(u, v):
                    G.edges[u, v]["metrics"].update(em)
                    G.edges[u, v]["latency"]      = em.get("latency_ms", 0.0)
                    G.edges[u, v]["packet_loss"]   = em.get("packet_loss_percent", 0.0)
            except ValueError:
                pass