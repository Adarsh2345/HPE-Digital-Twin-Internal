"""
core/analytics/threshold_checker.py

Fast, stateless threshold layer — runs every tick BEFORE the ML pipeline.
If a metric is already beyond its limit, raise an immediate alert without
waiting for Isolation Forest to score it.  These alerts feed directly into
the AlertPipeline which decides on remediation actions.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Per-metric thresholds ──────────────────────────────────────────────────
# Each metric has (warning, critical) levels.
# critical = act now;  warning = watch + log.
THRESHOLDS: dict[str, dict] = {
    "cpu_percent":         {"warning": 80.0,  "critical": 92.0},
    "memory_percent":      {"warning": 82.0,  "critical": 92.0},
    "temperature_celsius": {"warning": 72.0,  "critical": 85.0},
    "disk_iops":           {"warning": 3200,  "critical": 4500},
    "packet_loss_percent": {"warning": 1.5,   "critical": 5.0},
    "latency_ms":          {"warning": 80.0,  "critical": 150.0},
    "power_watts":         {"warning": 320.0, "critical": 420.0},
    "network_rx_mbps":     {"warning": 800.0, "critical": 950.0},
    "network_tx_mbps":     {"warning": 800.0, "critical": 950.0},
    "load5":               {"warning": 4.0,   "critical": 8.0},
    "disk_used_percent":   {"warning": 80.0,  "critical": 92.0},
}

# Anomaly type to suggest when a specific metric breaches critical
METRIC_TO_ANOMALY_HINT: dict[str, str] = {
    "cpu_percent":         "cpu_spike",
    "memory_percent":      "memory_pressure",
    "disk_iops":           "disk_saturation",
    "disk_used_percent":   "disk_saturation",
    "temperature_celsius": "thermal_anomaly",
    "packet_loss_percent": "network_saturation",
    "latency_ms":          "network_saturation",
    "network_rx_mbps":     "network_saturation",
    "network_tx_mbps":     "network_saturation",
    "power_watts":         "thermal_anomaly",
    "load5":               "cpu_spike",
}


@dataclass
class ThresholdAlert:
    node_id:      str
    role:         str
    metric:       str
    value:        float
    threshold:    float
    level:        str          # "warning" | "critical"
    anomaly_hint: str          # suggested anomaly type for downstream pipeline
    source:       str = "threshold"
    needs_action: bool = field(init=False)

    def __post_init__(self):
        self.needs_action = self.level == "critical"

    def to_dict(self) -> dict:
        return {
            "node_id":      self.node_id,
            "role":         self.role,
            "metric":       self.metric,
            "value":        self.value,
            "threshold":    self.threshold,
            "level":        self.level,
            "anomaly_hint": self.anomaly_hint,
            "source":       self.source,
            "needs_action": self.needs_action,
        }


class ThresholdChecker:
    """Stateless checker — call check() every tick with the derived graph."""

    def __init__(self, thresholds: dict = None):
        self.thresholds = thresholds or THRESHOLDS

    def check(self, derived_graph) -> list[ThresholdAlert]:
        """
        Iterate over all nodes, compare every metric to its threshold.
        Returns a list of ThresholdAlert objects (warnings + criticals).
        """
        alerts: list[ThresholdAlert] = []

        for node_id in derived_graph.nodes:
            node    = derived_graph.nodes[node_id]
            metrics = node.get("metrics", {})
            role    = node.get("role", "unknown")

            for metric, limits in self.thresholds.items():
                value = metrics.get(metric)
                if value is None:
                    continue

                level = None
                threshold_hit = None

                if value >= limits.get("critical", float("inf")):
                    level         = "critical"
                    threshold_hit = limits["critical"]
                elif value >= limits.get("warning", float("inf")):
                    level         = "warning"
                    threshold_hit = limits["warning"]

                if level:
                    alerts.append(ThresholdAlert(
                        node_id      = node_id,
                        role         = role,
                        metric       = metric,
                        value        = round(float(value), 3),
                        threshold    = threshold_hit,
                        level        = level,
                        anomaly_hint = METRIC_TO_ANOMALY_HINT.get(metric, "unknown"),
                    ))

        if alerts:
            crit = [a for a in alerts if a.level == "critical"]
            warn = [a for a in alerts if a.level == "warning"]
            logger.info(
                f"ThresholdChecker: {len(crit)} critical, {len(warn)} warning alerts"
            )

        return alerts

    def check_node(self, node_id: str, role: str, metrics: dict) -> list[ThresholdAlert]:
        """Check a single node's metrics dict (used by alert pipeline)."""
        alerts = []
        for metric, limits in self.thresholds.items():
            value = metrics.get(metric)
            if value is None:
                continue
            level = None
            threshold_hit = None
            if value >= limits.get("critical", float("inf")):
                level, threshold_hit = "critical", limits["critical"]
            elif value >= limits.get("warning", float("inf")):
                level, threshold_hit = "warning", limits["warning"]
            if level:
                alerts.append(ThresholdAlert(
                    node_id      = node_id,
                    role         = role,
                    metric       = metric,
                    value        = round(float(value), 3),
                    threshold    = threshold_hit,
                    level        = level,
                    anomaly_hint = METRIC_TO_ANOMALY_HINT.get(metric, "unknown"),
                ))
        return alerts
