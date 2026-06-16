"""
core/recommendations/recommendation_engine.py

Generates structured recommendation reports for two paths:
  1. Simulation path  — action was run through validator (PASS or FAIL)
  2. Anomaly path     — Isolation Forest + RF Classifier flagged a node

Both paths produce rule-based suggestions.  The LLM layer (GeminiClient)
is called by AlertPipeline on top of these suggestions for richer output.
"""
import time
import logging
from core.recommendations.remediation_rules import generate_remediation

logger = logging.getLogger(__name__)

# Anomaly-type → remediation template strings (rule-based fallback)
ANOMALY_REMEDIATION: dict[str, list[str]] = {
    "cpu_spike": [
        "Kill or throttle the runaway process on {node} (check `docker top` or `top -H`).",
        "Move {node} workload to a sibling compute node under the same ToR switch.",
        "Set cgroup CPU quota to cap the container at 80% to prevent future runaway.",
    ],
    "memory_pressure": [
        "Check for memory leaks in the application running on {node} (`docker stats`).",
        "Add a sibling compute node under the same ToR router to absorb workload.",
        "Enable Redis caching layer to reduce in-process memory footprint.",
    ],
    "disk_saturation": [
        "Enable read caching (Redis) on {node} to reduce raw disk IOPS pressure.",
        "Attach an additional NVMe volume or expand the storage pool.",
        "Reschedule heavy I/O batch jobs to off-peak hours (02:00–06:00).",
    ],
    "thermal_anomaly": [
        "Immediately reduce workload on {node} — migrate containers to a cooler node.",
        "Check physical cooling / CRAC unit for the rack hosting {node}.",
        "If temperature exceeds 88°C, initiate emergency graceful shutdown sequence.",
    ],
    "network_saturation": [
        "Enable ECMP load-balancing on the BGP path through {node}.",
        "Check for NIC flapping or MTU mismatch on the link to {node}.",
        "Activate an alternate spine route to bypass the congested segment.",
    ],
    "cascading_failure": [
        "Isolate {node} immediately — disconnect from ToR to stop cascade spread.",
        "Redistribute traffic across remaining healthy nodes in the rack.",
        "Alert on-call team: cascading failure may require physical intervention.",
    ],
}


class RecommendationEngine:

    # ── Simulation path (existing) ─────────────────────────────────────────

    def generate_report(
        self,
        action:            str,
        params:            dict,
        validation_result: dict,
        mutation_result:   dict = None,
        projections:       list[dict] = None,
    ) -> dict:
        """Original simulation report — called by simulation API route."""
        allowed  = validation_result.get("allowed", False)
        reasons  = validation_result.get("reasons", [])
        warnings = validation_result.get("warnings", [])

        recommendations = []
        if not allowed:
            recommendations = generate_remediation(reasons)

        report = {
            "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action":           action,
            "params":           params,
            "allowed":          allowed,
            "verdict":          "PASS ✅" if allowed else "FAIL ❌",
            "reasons":          reasons,
            "warnings":         warnings,
            "recommendations":  recommendations,
            "tier_results":     validation_result.get("tier_results", {}),
            "mutation_summary": mutation_result,
            "projection_steps": len(projections) if projections else 0,
        }

        logger.info(
            f"Simulation report — allowed={allowed}, "
            f"violations={len(reasons)}, recommendations={len(recommendations)}"
        )
        return report

    # ── Anomaly path (new) ─────────────────────────────────────────────────

    def generate_anomaly_recommendations(
        self,
        node_id:      str,
        anomaly_type: str,
        score:        float,
        role:         str,
    ) -> list[str]:
        """
        Return rule-based recommendation strings for a detected anomaly.
        Used by AlertPipeline before calling the LLM for enrichment.
        """
        templates = ANOMALY_REMEDIATION.get(anomaly_type, [])
        suggestions = [t.format(node=node_id) for t in templates]

        # Add severity note
        if score > 0.7:
            suggestions.insert(0, f"CRITICAL: {node_id} anomaly score={score:.2f} — immediate action required.")
        elif score > 0.5:
            suggestions.insert(0, f"HIGH: {node_id} anomaly score={score:.2f} — escalate within 10 minutes.")

        logger.debug(
            f"Anomaly recommendations for {node_id}/{anomaly_type}: "
            f"{len(suggestions)} rules matched"
        )
        return suggestions

    def generate_anomaly_report(
        self,
        node_id:      str,
        role:         str,
        anomaly_type: str,
        score:        float,
        confidence:   float,
        rule_suggestions: list[str],
        llm_summary:  str = "",
    ) -> dict:
        """
        Full structured report for an anomaly event.
        Stored in alert buffer and returned via API.
        """
        severity = (
            "critical" if score > 0.7
            else "high" if score > 0.5
            else "medium"
        )
        return {
            "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node_id":          node_id,
            "role":             role,
            "anomaly_type":     anomaly_type,
            "anomaly_score":    round(score, 4),
            "confidence":       round(confidence, 3),
            "severity":         severity,
            "verdict":          f"ANOMALY DETECTED ⚠️  [{severity.upper()}]",
            "recommendations":  rule_suggestions,
            "llm_analysis":     llm_summary,
            "source":           "isolation_forest + rf_classifier",
        }
