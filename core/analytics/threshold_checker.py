"""
core/analytics/threshold_checker.py
Rule-based threshold checks using WARNING and CRITICAL limits from
config/constants.py.  Runs before the ML layer so hard threshold
violations are always caught even if the anomaly model isn't trained.
"""
from config.constants import WARNING_THRESHOLDS, CRITICAL_THRESHOLDS

# Maps metric field names to threshold dict keys
_METRIC_THRESHOLD_MAP = {
    "cpu_percent":    "cpu",
    "memory_percent": "memory",
    "disk_iops":      "iops",
    "power_watts":    "power_watts",
    "latency_ms":     "latency_ms",
}


def check_thresholds(node_id: str, metrics: dict) -> dict:
    violations: list[dict] = []
    warnings:   list[dict] = []

    for metric, key in _METRIC_THRESHOLD_MAP.items():
        v = metrics.get(metric)
        if v is None:
            continue
        v = float(v)
        crit = CRITICAL_THRESHOLDS.get(key)
        warn = WARNING_THRESHOLDS.get(key)

        if crit is not None and v >= crit:
            violations.append({
                "metric": metric, "value": v,
                "threshold": crit, "level": "CRITICAL",
            })
        elif warn is not None and v >= warn:
            warnings.append({
                "metric": metric, "value": v,
                "threshold": warn, "level": "WARNING",
            })

    return {
        "node_id":     node_id,
        "violations":  violations,
        "warnings":    warnings,
        "critical":    bool(violations),
        "any_warning": bool(violations or warnings),
    }
