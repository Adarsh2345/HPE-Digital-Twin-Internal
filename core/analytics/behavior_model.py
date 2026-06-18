"""
core/analytics/behavior_model.py
Phase 9: RandomForest BehaviorModel.
Trains separate RF regressors per node per target metric.
Covers compute (CPU, memory, power), network (latency, packet_loss),
and storage (disk_iops) prediction domains.
"""
import os
import pickle
import logging
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from integrations.influxdb.history_fetcher import HistoryFetcher

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")

# Input features used to train every RF model
FEATURE_COLS = [
    "bandwidth_mbps",
    "cpu_percent",
    "disk_iops",
    "power_watts",
    "latency_ms",
    "hour_of_day",
    "day_of_week",
]

# Per-domain targets — RF trained separately for each
COMPUTE_TARGETS = ["cpu_percent", "memory_percent", "power_watts"]
NETWORK_TARGETS = ["latency_ms", "packet_loss_percent"]
STORAGE_TARGETS = ["disk_iops"]
ALL_TARGETS     = COMPUTE_TARGETS + NETWORK_TARGETS + STORAGE_TARGETS


class BehaviorModel:
    def __init__(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        # { node_id: { target_metric: RandomForestRegressor } }
        self.models: dict[str, dict[str, RandomForestRegressor]] = {}
        self.training_summary: dict = {}
        self.fetcher = HistoryFetcher()

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #
    def train_all(self, days: int = 30) -> dict:
        raw = self.fetcher.fetch_node_series(days=days)
        summary = {}
        for node_id, series in raw.items():
            result = self._train_node(node_id, series)
            if result:
                summary[node_id] = result
        self.training_summary = summary
        logger.info(f"BehaviorModel: trained {len(summary)} nodes")
        return summary

    def _train_node(self, node_id: str, series: dict) -> dict:
        # Build hour/day columns from timestamps
        timestamps = series.get("timestamps", [])
        n_ts = len(timestamps)
        hours = [int(t % 86400 // 3600) for t in timestamps] if n_ts else []
        days  = [int((t // 86400) % 7)  for t in timestamps] if n_ts else []

        # Build feature matrix
        col_arrays = []
        n_min = None
        for col in FEATURE_COLS:
            if col == "hour_of_day":
                arr = np.array(hours, dtype=float) if hours else np.zeros(0)
            elif col == "day_of_week":
                arr = np.array(days, dtype=float) if days else np.zeros(0)
            else:
                arr = np.array(series.get(col, []), dtype=float)

            if len(arr) == 0:
                arr = np.zeros(50)
            col_arrays.append(arr)
            n_min = len(arr) if n_min is None else min(n_min, len(arr))

        if n_min is None or n_min < 50:
            logger.debug(f"Skipping {node_id}: only {n_min} samples")
            return {}

        X = np.column_stack([a[:n_min] for a in col_arrays])
        self.models[node_id] = {}
        results = {}

        for target in ALL_TARGETS:
            y_raw = series.get(target, [])
            if len(y_raw) < n_min:
                continue
            y = np.array(y_raw[:n_min], dtype=float)

            # Remove NaN rows
            mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
            Xc, yc = X[mask], y[mask]
            if len(Xc) < 30:
                continue

            X_tr, X_te, y_tr, y_te = train_test_split(Xc, yc, test_size=0.2, random_state=42)
            rf = RandomForestRegressor(
                n_estimators=100,
                max_features="sqrt",
                random_state=42,
                n_jobs=-1,
            )
            rf.fit(X_tr, y_tr)
            r2 = rf.score(X_te, y_te)
            self.models[node_id][target] = rf
            results[target] = {"r2": round(r2, 4), "samples": int(len(Xc))}
            logger.debug(f"  {node_id}/{target}: R²={r2:.4f}")

        self._save_node_models(node_id)
        return results

    # ------------------------------------------------------------------ #
    # Inference                                                            #
    # ------------------------------------------------------------------ #
    def predict(
        self,
        node_id: str,
        current_metrics: dict,
        traffic_delta_mbps: float = 0.0,
        hour_of_day: int = 12,
        day_of_week: int = 1,
    ) -> dict:
        """
        Predict new metric values after a traffic delta is applied.
        Returns a dict with all predicted targets.
        """
        self._ensure_loaded(node_id)
        node_models = self.models.get(node_id)

        new_bw = max(0.0, current_metrics.get("bandwidth_mbps", 500) + traffic_delta_mbps)
        features = np.array([[
            new_bw,
            current_metrics.get("cpu_percent", 30),
            current_metrics.get("disk_iops", 800),
            current_metrics.get("power_watts", 180),
            current_metrics.get("latency_ms", 12),
            float(hour_of_day),
            float(day_of_week),
        ]])

        predictions = {}
        if node_models:
            for target, model in node_models.items():
                raw = float(model.predict(features)[0])
                # Clamp to sensible ranges
                if target.endswith("_percent"):
                    raw = min(100.0, max(0.0, raw))
                elif target == "disk_iops":
                    raw = max(0.0, raw)
                elif target == "power_watts":
                    raw = max(0.0, raw)
                elif target == "latency_ms":
                    raw = max(0.0, raw)
                predictions[target] = round(raw, 2)
        else:
            predictions = self._linear_fallback(current_metrics, traffic_delta_mbps)

        return predictions

    def _linear_fallback(self, current: dict, delta_mbps: float) -> dict:
        """Simple linear approximation when no model exists."""
        cpu_bump = delta_mbps * 0.006
        lat_bump = max(0.0, delta_mbps - 800) * 0.15
        return {
            "cpu_percent":          min(100.0, current.get("cpu_percent", 30) + cpu_bump),
            "memory_percent":       current.get("memory_percent", 45),
            "power_watts":          current.get("power_watts", 180) + delta_mbps * 0.1,
            "latency_ms":           current.get("latency_ms", 12) + lat_bump,
            "packet_loss_percent":  current.get("packet_loss_percent", 0.05),
            "disk_iops":            current.get("disk_iops", 800),
        }

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_name(node_id: str) -> str:
        # Composite ids ("droplet-1-tor1/server-1") contain "/" which is a
        # path separator on every OS — replace with "__" for safe filenames.
        return node_id.replace("/", "__")

    def _save_node_models(self, node_id: str):
        path = os.path.join(MODEL_DIR, f"{self._safe_name(node_id)}_models.pkl")
        with open(path, "wb") as f:
            pickle.dump(self.models[node_id], f)

    def _ensure_loaded(self, node_id: str):
        if node_id in self.models:
            return
        path = os.path.join(MODEL_DIR, f"{self._safe_name(node_id)}_models.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                self.models[node_id] = pickle.load(f)