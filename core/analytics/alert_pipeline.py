"""
core/analytics/alert_pipeline.py

Central pipeline that wires all detection, simulation, and recommendation
layers together.  Called every tick by the orchestrator.

Flow:
  1. ThresholdChecker  → immediate WARNING / CRITICAL alerts (no ML)
         │ critical alert?
         ▼
     GeminiClient.get_threshold_breach_summary()   [fast triage]

  2. AnomalyDetector   → Isolation Forest scores every node
         │ anomaly detected?
         ▼
     RF Classifier      → classifies anomaly_type

  3. For each anomaly:
       a. Build remediation action suggestion (anomaly_type → action)
       b. Run Simulator + ValidatorEngine
            PASS ✅ → record accepted action
            FAIL ❌ → RecommendationEngine rule-based suggestions
       c. GeminiClient  → rich LLM recommendation in both paths

  4. Store all alerts in a rolling in-memory buffer (last 50 events)
     exposed to the API via get_recent_alerts().
"""
import time
import logging
import networkx as nx
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# Maps anomaly type → the simulation action most likely to relieve it
# and a function that builds the params dict from (node_id, graph).
def _parent_router(graph: nx.DiGraph, node_id: str) -> str:
    """Return the ToR router that node_id connects to, or empty string."""
    for pred in graph.predecessors(node_id):
        role = graph.nodes[pred].get("role", "")
        if role in ("tor-router", "spine-switch"):
            return pred
    return ""

def _alt_router(graph: nx.DiGraph, node_id: str) -> str:
    """Return a router different from node_id's current parent."""
    current = _parent_router(graph, node_id)
    for nid in graph.nodes:
        if graph.nodes[nid].get("role") == "tor-router" and nid != current:
            return nid
    return ""

ANOMALY_ACTION_MAP: dict[str, dict] = {
    "cpu_spike": {
        "action": "move_server",
        "build_params": lambda nid, g: {
            "server_id": nid,
            "target_router": _alt_router(g, nid) or "router-2",
        },
        "description": "Move server to less-loaded ToR to redistribute CPU pressure",
    },
    "memory_pressure": {
        "action": "add_compute",
        "build_params": lambda nid, g: {
            "node_id": f"relief-{nid}",
            "router_id": _parent_router(g, nid) or "router-1",
        },
        "description": "Add a sibling compute node to absorb workload",
    },
    "disk_saturation": {
        "action": "inject_storage",
        "build_params": lambda nid, g: {
            "node_id": nid,
            "disk_iops": 3900,
        },
        "description": "Validate disk saturation; recommendation engine will suggest caching",
    },
    "thermal_anomaly": {
        "action": "move_server",
        "build_params": lambda nid, g: {
            "server_id": nid,
            "target_router": _alt_router(g, nid) or "router-2",
        },
        "description": "Migrate workload away from overheating node",
    },
    "network_saturation": {
        "action": "inject_network",
        "build_params": lambda nid, g: {
            "source_node": _parent_router(g, nid) or "spine-router",
            "target_node": nid,
            "latency_ms": 160.0,
            "packet_loss_percent": 6.5,
        },
        "description": "Validate network saturation; recommend ECMP / reroute",
    },
    "cascading_failure": {
        "action": "remove_node",
        "build_params": lambda nid, g: {"node_id": nid},
        "description": "Isolate the cascading node to protect remaining topology",
    },
}


class AlertPipeline:
    """
    Stateful pipeline — instantiated once, called every tick.
    Keeps a rolling buffer of recent alert events.
    """

    def __init__(self, max_buffer: int = 50):
        from core.analytics.threshold_checker import ThresholdChecker
        from core.analytics.anomaly_detector  import AnomalyDetector
        from core.recommendations.recommendation_engine import RecommendationEngine
        from core.llm.gemini_client            import GeminiClient

        self.threshold_checker = ThresholdChecker()
        self.anomaly_detector  = AnomalyDetector()
        self.recommender       = RecommendationEngine()
        self.llm               = GeminiClient()

        self._buffer: deque[dict] = deque(maxlen=max_buffer)
        self._last_alert_ts: dict[str, float] = {}   # node_id → last alert time
        self._cooldown_s = 120   # suppress repeated alerts for same node for 2 min

    # ── Main entry point ───────────────────────────────────────────────────

    def run(self, derived_graph: nx.DiGraph) -> dict:
        """
        Called every tick.  Returns a summary dict with all alerts and
        recommended actions discovered this cycle.
        """
        tick_ts    = time.time()
        cycle_out  = {
            "timestamp":        tick_ts,
            "threshold_alerts": [],
            "anomaly_alerts":   [],
            "actions_tried":    [],
            "llm_summaries":    [],
        }

        # ── Step 1: threshold checks (fast, no ML) ─────────────────────
        th_alerts = self.threshold_checker.check(derived_graph)
        critical  = [a for a in th_alerts if a.level == "critical"]

        for alert in th_alerts:
            cycle_out["threshold_alerts"].append(alert.to_dict())

        if critical:
            critical_nodes = list({a.node_id for a in critical})
            if self._should_alert(critical_nodes[0], tick_ts):
                llm_triage = self.llm.get_threshold_breach_summary(
                    [a.to_dict() for a in critical], critical_nodes
                )
                event = {
                    "type":         "threshold_critical",
                    "nodes":        critical_nodes,
                    "alerts":       [a.to_dict() for a in critical],
                    "llm_summary":  llm_triage,
                    "timestamp":    tick_ts,
                }
                self._buffer.append(event)
                cycle_out["llm_summaries"].append(event)

        # ── Step 2: anomaly detection (IF → RF Classifier) ─────────────
        anomalies = self.anomaly_detector.detect_all(derived_graph)

        for anom in anomalies:
            node_id      = anom["node_id"]
            anomaly_type = anom["anomaly_type"]
            role         = anom.get("role", "unknown")
            score        = anom["anomaly_score"]

            cycle_out["anomaly_alerts"].append(anom)

            if not self._should_alert(node_id, tick_ts):
                continue

            node_metrics = dict(derived_graph.nodes[node_id].get("metrics", {}))
            connected    = list(derived_graph.successors(node_id)) + list(derived_graph.predecessors(node_id))

            # Baseline from historical analyzer if available
            baseline = self._get_baseline(node_id)

            # ── Step 3a: suggest remediation action ────────────────────
            action_result = self._try_remediation(
                node_id, anomaly_type, derived_graph
            )
            cycle_out["actions_tried"].append(action_result)

            # ── Step 3b: rule-based recommendations ────────────────────
            rule_recs = self.recommender.generate_anomaly_recommendations(
                node_id=node_id,
                anomaly_type=anomaly_type,
                score=score,
                role=role,
            )

            # ── Step 3c: LLM recommendation ────────────────────────────
            severity = (
                "critical" if score > 0.7
                else "high" if score > 0.5
                else "medium"
            )
            llm_text = self.llm.get_anomaly_recommendation(
                node_id          = node_id,
                role             = role,
                anomaly_type     = anomaly_type,
                severity         = severity,
                current_metrics  = node_metrics,
                baseline_metrics = baseline,
                connected_nodes  = connected,
                rule_suggestions = rule_recs,
            )

            event = {
                "type":            "anomaly",
                "node_id":         node_id,
                "role":            role,
                "anomaly_type":    anomaly_type,
                "anomaly_score":   score,
                "severity":        severity,
                "confidence":      anom["confidence"],
                "action_tried":    action_result,
                "rule_suggestions":rule_recs,
                "llm_summary":     llm_text,
                "timestamp":       tick_ts,
            }
            self._buffer.append(event)
            cycle_out["llm_summaries"].append(event)
            self._last_alert_ts[node_id] = tick_ts

        return cycle_out

    # ── Remediation simulation ─────────────────────────────────────────────

    def _try_remediation(
        self, node_id: str, anomaly_type: str, graph: nx.DiGraph
    ) -> dict:
        """
        Look up the suggested action for this anomaly type, run it through
        the simulator and validator, and return the outcome.
        """
        mapping = ANOMALY_ACTION_MAP.get(anomaly_type)
        if not mapping:
            # For unclassified anomalies, infer action from the node's live metrics
            try:
                from core.analytics.anomaly_detector import METRIC_TYPE_HINTS
                node_metrics = dict(graph.nodes[node_id].get("metrics", {}))
                for col, threshold, atype in METRIC_TYPE_HINTS:
                    if float(node_metrics.get(col, 0.0)) > threshold:
                        mapping = ANOMALY_ACTION_MAP.get(atype)
                        if mapping:
                            break
            except Exception:
                pass
            if not mapping:
                return {"status": "no_action_mapped", "anomaly_type": anomaly_type}

        action = mapping["action"]
        try:
            params = mapping["build_params"](node_id, graph)
        except Exception as exc:
            return {"status": "param_build_failed", "error": str(exc)}

        # Late import to avoid circular dependencies
        try:
            from core.simulation.simulator       import Simulator
            from core.validation.validator_engine import ValidatorEngine
            from core.graph.graph_serializer      import dict_to_graph

            sim    = Simulator()
            val    = ValidatorEngine()

            result = sim.run(graph, action=action, params=params, projection_steps=2)

            if not result["success"]:
                return {
                    "status":  "simulation_failed",
                    "action":  action,
                    "params":  params,
                    "reason":  result.get("mutation", "unknown"),
                }

            proj_graph = dict_to_graph(result["projected_graph"])
            validation = val.validate(proj_graph, result.get("projections", []))
            allowed    = validation.get("allowed", False)

            if allowed:
                logger.info(
                    f"AlertPipeline: remediation ACCEPTED — {action} on {node_id}"
                )
                return {
                    "status":     "accepted",
                    "action":     action,
                    "params":     params,
                    "description": mapping["description"],
                }
            else:
                # Validation failed → call LLM with failure context
                reasons      = validation.get("reasons", [])
                rule_recs    = self.recommender.generate_report(
                    action=action, params=params,
                    validation_result=validation,
                ).get("recommendations", [])

                llm_fail_txt = self.llm.get_simulation_failure_recommendation(
                    action          = action,
                    params          = params,
                    failure_reasons = reasons,
                    rule_suggestions= rule_recs,
                    impact_preview  = result.get("impact_predictions", {}),
                )
                logger.warning(
                    f"AlertPipeline: remediation REJECTED — {action} on {node_id}: "
                    f"{reasons}"
                )
                return {
                    "status":          "rejected",
                    "action":          action,
                    "params":          params,
                    "failure_reasons": reasons,
                    "rule_suggestions":rule_recs,
                    "llm_explanation": llm_fail_txt,
                }

        except Exception as exc:
            logger.error(f"AlertPipeline._try_remediation error: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    # ── Public accessors ───────────────────────────────────────────────────

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        """Return the most recent alert events (newest first)."""
        return list(reversed(list(self._buffer)))[:limit]

    def get_active_anomalies(self) -> list[dict]:
        """Return anomaly-type events from the last 5 minutes."""
        cutoff = time.time() - 300
        return [
            e for e in self._buffer
            if e.get("type") == "anomaly" and e.get("timestamp", 0) >= cutoff
        ]

    # ── Helpers ────────────────────────────────────────────────────────────

    def _should_alert(self, node_id: str, now: float) -> bool:
        last = self._last_alert_ts.get(node_id, 0.0)
        return (now - last) >= self._cooldown_s

    def _get_baseline(self, node_id: str) -> dict:
        """Pull p50 baseline from the historical analyzer if available."""
        try:
            from core.analytics.model_registry import registry
            profile = registry.get_profile(node_id)
            compute = profile.get("compute", {})
            return {
                metric: data.get("p50", 0.0)
                for metric, data in compute.items()
            }
        except Exception:
            return {}
