"""
core/telemetry/telemetry_processor.py
Processes raw telemetry snapshots: aggregation, rolling averages, anomaly flags.
"""
import time
from collections import deque
import logging

logger = logging.getLogger(__name__)

MAX_HISTORY = 50  # Keep last 50 snapshots per node


class TelemetryProcessor:
    def __init__(self):
        self._history: dict[str, deque] = {}
        self._anomaly_model = None

    def process(self, snapshot: dict) -> dict:
        """Enrich snapshot with rolling stats and anomaly flags."""
        enriched_nodes = {}
        for node_id, metrics in snapshot.get("nodes", {}).items():
            self._push_history(node_id, metrics)
            enriched = {
                **metrics,
                "rolling_avg_cpu": self._rolling_avg(node_id, "cpu_percent"),
                "rolling_avg_memory": self._rolling_avg(node_id, "memory_percent"),
                "anomaly_detected": self._detect_anomaly(node_id, metrics),
                "provenance": "Synthetic Demo",
            }
            try:
                if self._anomaly_model is None:
                    from ml.isolation_forest import SyntheticIsolationForest
                    self._anomaly_model = SyntheticIsolationForest()
                anomaly = self._anomaly_model.score_one({
                    "cpu_pct": metrics.get("cpu_percent", 0),
                    "memory_pct": metrics.get("memory_percent", 0),
                    "temp_c": metrics.get("temperature_celsius", 0),
                    "power_w": metrics.get("power_watts", 0),
                    "net_io_mbps": metrics.get("network_rx_mbps", 0) + metrics.get("network_tx_mbps", 0),
                })
                enriched.update(anomaly)
            except ImportError:
                pass
            enriched_nodes[node_id] = enriched

        return {
            **snapshot,
            "nodes": enriched_nodes,
            "processed_at": time.time(),
        }

    def _push_history(self, node_id: str, metrics: dict):
        if node_id not in self._history:
            self._history[node_id] = deque(maxlen=MAX_HISTORY)
        self._history[node_id].append(metrics)

    def _rolling_avg(self, node_id: str, key: str) -> float:
        history = self._history.get(node_id, deque())
        values = [m.get(key, 0) for m in history if key in m]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    def _detect_anomaly(self, node_id: str, metrics: dict) -> bool:
        history = self._history.get(node_id, deque())
        if len(history) < 5:
            return False
        cpu_vals = [m.get("cpu_percent", 0) for m in list(history)[-5:]]
        avg = sum(cpu_vals) / len(cpu_vals)
        current = metrics.get("cpu_percent", 0)
        return abs(current - avg) > 25.0  # Spike > 25% from recent average

    def get_node_history(self, node_id: str) -> list:
        return list(self._history.get(node_id, []))
