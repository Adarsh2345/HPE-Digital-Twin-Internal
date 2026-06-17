"""
core/analytics/alert_pipeline.py
Single entry-point that combines:
  1. Threshold checker (rule-based, fast, always runs)
  2. Device-level anomaly detector (IF + RF, ML-based)
  3. RecommendationEngine (same engine used for simulation failures —
     anomaly alerts are routed through the same remediation path so
     the platform speaks with one unified recommendation voice).
"""
import logging
from core.analytics.anomaly_detector  import detector
from core.analytics.threshold_checker import check_thresholds
from core.recommendations.recommendation_engine import RecommendationEngine

logger = logging.getLogger(__name__)
_rec   = RecommendationEngine()

# Maps live metric names / IF trigger tags → reason strings that match
# the keyword patterns in remediation_rules.REMEDIATION_RULES.
_METRIC_REASON = {
    "cpu_percent":           "Compute Overload on {node}",
    "memory_percent":        "Compute Overload on {node}",
    "disk_iops":             "Storage IOPS Breach on {node}",
    "power_watts":           "Power Envelope Breach on {node}",
    "temperature_celsius":   "Power Envelope Breach on {node}",
    "latency_ms":            "Network SLA Breach on {node}",
    "packet_loss_percent":   "Packet Loss Breach on {node}",
}
# IF anomaly_type prefixes after stripping "if_anomaly:"
_IF_REASON = {
    "disk_iops":   "Storage IOPS Breach on {node}",
    "cpu_percent": "Compute Overload on {node}",
    "power_watts": "Power Envelope Breach on {node}",
    "latency_ms":  "Network SLA Breach on {node}",
}


def _triggers_to_reasons(triggers: list[str], node_id: str) -> list[str]:
    seen, reasons = set(), []
    for t in triggers:
        if t.startswith("if_anomaly:"):
            atype = t.split(":", 1)[1]
            tmpl  = _IF_REASON.get(atype, "Compute Overload on {node}")
        else:
            tmpl  = _METRIC_REASON.get(t, f"Compute Overload on {node_id}")
        reason = tmpl.format(node=node_id)
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)
    return reasons


def run_alert_pipeline(node_id: str, metrics: dict) -> dict:
    """
    Evaluate a single live node snapshot and return a unified alert envelope.

    Returns
    -------
    dict with keys:
      node_id, alert_level ('normal'|'warning'|'critical'),
      triggers (list of what fired), threshold (raw check result),
      anomaly (raw detector result), recommendations (list).
    """
    threshold = check_thresholds(node_id, metrics)
    anomaly   = detector.detect(node_id, metrics)

    alert_level = "normal"
    triggers: list[str] = []

    # Threshold violations take precedence for alert level
    if threshold["critical"]:
        alert_level = "critical"
        triggers += [v["metric"] for v in threshold["violations"]]
    elif threshold["any_warning"]:
        alert_level = "warning"
        triggers += [w["metric"] for w in threshold["warnings"]]

    # IF anomaly can escalate level but not downgrade it
    if anomaly.get("anomaly"):
        if alert_level == "normal":
            alert_level = "warning"
        reason = anomaly.get("anomaly_type") or "unknown"
        triggers.append(f"if_anomaly:{reason}")

    # Route into RecommendationEngine when anything fired
    recommendations: list[dict] = []
    if alert_level != "normal":
        reasons = _triggers_to_reasons(triggers, node_id)
        report  = _rec.generate_report(
            action="anomaly_alert",
            params=metrics,
            validation_result={
                "allowed": False,
                "reasons": reasons,
                "warnings": [],
            },
        )
        recommendations = report.get("recommendations", [])
        logger.info(
            f"Alert [{alert_level}] on {node_id}: {triggers} → "
            f"{len(recommendations)} recommendation(s)"
        )

    return {
        "node_id":         node_id,
        "alert_level":     alert_level,
        "triggers":        triggers,
        "threshold":       threshold,
        "anomaly":         anomaly,
        "recommendations": recommendations,
    }
