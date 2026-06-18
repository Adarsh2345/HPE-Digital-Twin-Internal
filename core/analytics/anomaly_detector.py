"""
core/analytics/anomaly_detector.py
Per-device two-stage anomaly detection pipeline.

Stage 1 — Isolation Forest (unsupervised):
    Trained on raw (non-aggregated) historical telemetry per device so
    training variance matches live single-point readings.  Flags whether
    a live snapshot is statistically anomalous for that specific device.

Stage 2 — RF Classifier (supervised):
    Trained on healthy InfluxDB history (label=0) and chaos_mode=True
    synthetic snapshots (label=1).  Estimates confidence that a flagged
    point is a genuine anomaly, not a boundary-case outlier.

Both models are saved to models/anomaly_detector.pkl and loaded at
startup so training (which fetches raw history + generates chaos data)
only needs to run once via train_models.py or the /anomaly/train API.
"""
import os
import pickle
import logging
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config.settings import INFLUXDB_BUCKET
from integrations.influxdb.history_fetcher import HistoryFetcher

logger = logging.getLogger(__name__)

FEATURES = [
    "cpu_percent",
    "memory_percent",
    "disk_iops",
    "power_watts",
    "temperature_celsius",
]
MODEL_DIR     = os.path.join(os.path.dirname(__file__), "..", "..", "models")
DETECTOR_PATH = os.path.join(MODEL_DIR, "anomaly_detector.pkl")


class DeviceAnomalyDetector:
    def __init__(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        self.scalers:       dict[str, StandardScaler]         = {}
        self.if_models:     dict[str, IsolationForest]        = {}
        self.rf_models:     dict[str, RandomForestClassifier] = {}
        self.healthy_stats: dict[str, dict]                   = {}
        self._trained = False
        self.fetcher  = HistoryFetcher()

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #
    def train(self, days: int = 7, chaos_snapshots: int = 3000) -> dict:
        logger.info(f"AnomalyDetector: fetching raw {days}-day history...")
        healthy_series = self.fetcher.fetch_node_series_raw(days=days)
        logger.info(f"AnomalyDetector: received series for {len(healthy_series)} devices")

        logger.info(f"AnomalyDetector: generating {chaos_snapshots} chaos snapshots...")
        chaos_data = self._generate_chaos_data(n=chaos_snapshots)

        trained = skipped = 0
        for device_id, series in healthy_series.items():
            X_healthy = self._series_to_matrix(series)
            if X_healthy is None:
                logger.debug(f"  skip {device_id}: insufficient healthy samples")
                skipped += 1
                continue
            X_chaos = chaos_data.get(device_id)
            self._train_device(device_id, X_healthy, X_chaos)
            trained += 1

        self._trained = True
        self.save()
        logger.info(f"AnomalyDetector: trained {trained} devices, skipped {skipped}")
        return {"devices_trained": trained, "devices_skipped": skipped}

    def _train_device(
        self,
        device_id: str,
        X_healthy: np.ndarray,
        X_chaos: "np.ndarray | None",
    ) -> None:
        # 1. Scaler fitted on healthy data only
        scaler = StandardScaler().fit(X_healthy)
        Xs_healthy = scaler.transform(X_healthy)

        # 2. Store per-feature healthy stats for z-score explanation at inference
        self.healthy_stats[device_id] = {
            f: {
                "mean": float(X_healthy[:, i].mean()),
                "std":  max(float(X_healthy[:, i].std()), 1e-6),
            }
            for i, f in enumerate(FEATURES)
        }

        # 3. Isolation Forest — trained on scaled healthy data
        self.if_models[device_id] = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        ).fit(Xs_healthy)

        # 4. RF Classifier — healthy (0) vs chaos (1)
        if X_chaos is not None and len(X_chaos) >= 50:
            rng   = np.random.default_rng(seed=42)
            n     = min(len(X_healthy), len(X_chaos), 10_000)
            idx_h = rng.choice(len(X_healthy), n, replace=False)
            idx_c = rng.choice(len(X_chaos),   n, replace=False)
            X_tr  = np.vstack([X_healthy[idx_h], X_chaos[idx_c]])
            y_tr  = np.array([0] * n + [1] * n)
            Xs_tr = scaler.transform(X_tr)
            self.rf_models[device_id] = RandomForestClassifier(
                n_estimators=100,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ).fit(Xs_tr, y_tr)

        self.scalers[device_id] = scaler
        logger.debug(
            f"  {device_id}: {len(X_healthy)} healthy pts, "
            f"{len(X_chaos) if X_chaos is not None else 0} chaos pts"
        )

    def _generate_chaos_data(self, n: int) -> dict[str, np.ndarray]:
        from core.telemetry.metrics_generator import MetricsGenerator
        from core.orchestrator import orchestrator

        if not getattr(orchestrator, "initial_graph", None):
            orchestrator.bootstrap()

        gen       = MetricsGenerator(chaos_mode=True)
        graph     = orchestrator.initial_graph
        node_list = [{"id": nid, **data} for nid, data in graph.nodes(data=True)]
        edge_list = [{"source": u, "target": v} for u, v in graph.edges()]

        raw: dict[str, list] = {}
        for _ in range(n):
            snap = gen.generate_full_snapshot(node_list, edge_list)
            for nid, metrics in snap["nodes"].items():
                raw.setdefault(nid, []).append(
                    [float(metrics.get(f, 0.0)) for f in FEATURES]
                )

        return {nid: np.array(rows, dtype=float) for nid, rows in raw.items()}

    @staticmethod
    def _series_to_matrix(series: dict) -> "np.ndarray | None":
        lengths = [len(series.get(f, [])) for f in FEATURES]
        n = min(lengths)
        if n < 100:
            return None
        cols = [np.array(series[f][:n], dtype=float) for f in FEATURES]
        X = np.column_stack(cols)
        # Cap at 50k rows so training stays fast even on full 30-day history
        if len(X) > 50_000:
            idx = np.random.default_rng(seed=42).choice(len(X), 50_000, replace=False)
            X = X[idx]
        mask = ~np.isnan(X).any(axis=1)
        return X[mask] if mask.sum() >= 100 else None

    # ------------------------------------------------------------------ #
    # Inference                                                            #
    # ------------------------------------------------------------------ #
    def detect(self, node_id: str, metrics: dict) -> dict:
        if node_id not in self.if_models:
            return {"node_id": node_id, "status": "no_model", "anomaly": False}

        row = np.array([[float(metrics.get(f, 0.0)) for f in FEATURES]])
        Xs  = self.scalers[node_id].transform(row)

        if_pred  = int(self.if_models[node_id].predict(Xs)[0])        # -1=anomaly 1=normal
        if_score = float(self.if_models[node_id].score_samples(Xs)[0]) # more negative = worse
        anomaly  = if_pred == -1

        result: dict = {
            "node_id":        node_id,
            "anomaly":        anomaly,
            "if_score":       round(if_score, 4),
            "anomaly_type":   None,
            "anomaly_reason": [],
            "rf_confidence":  None,
        }

        if anomaly:
            if node_id in self.rf_models:
                prob = float(self.rf_models[node_id].predict_proba(Xs)[0][1])
                result["rf_confidence"] = round(prob, 4)

            reasons = self._explain(node_id, metrics)
            result["anomaly_reason"] = reasons
            if reasons:
                result["anomaly_type"] = (
                    reasons[0].replace("_high", "").replace("_low", "")
                )

        return result

    def _explain(self, node_id: str, metrics: dict) -> list[str]:
        """Return top-2 most deviant features (>2σ from healthy mean)."""
        stats = self.healthy_stats.get(node_id, {})
        z: dict[str, float] = {}
        for f in FEATURES:
            s    = stats.get(f, {})
            mean = s.get("mean", 0.0)
            std  = s.get("std",  1e-6)
            z[f] = (float(metrics.get(f, mean)) - mean) / std

        significant = [(f, zv) for f, zv in z.items() if abs(zv) > 2.0]
        significant.sort(key=lambda x: abs(x[1]), reverse=True)
        return [
            f"{f}_{'high' if zv > 0 else 'low'}"
            for f, zv in significant[:2]
        ]

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        with open(DETECTOR_PATH, "wb") as fh:
            pickle.dump({
                "scalers":       self.scalers,
                "if_models":     self.if_models,
                "rf_models":     self.rf_models,
                "healthy_stats": self.healthy_stats,
                "_trained":      self._trained,
            }, fh)
        logger.info(f"AnomalyDetector saved → {DETECTOR_PATH}")

    def load(self) -> bool:
        if not os.path.exists(DETECTOR_PATH):
            return False
        try:
            with open(DETECTOR_PATH, "rb") as fh:
                data = pickle.load(fh)
            self.scalers       = data["scalers"]
            self.if_models     = data["if_models"]
            self.rf_models     = data["rf_models"]
            self.healthy_stats = data["healthy_stats"]
            self._trained      = data.get("_trained", True)
            logger.info(f"AnomalyDetector loaded {len(self.if_models)} device models")
            return True
        except Exception as e:
            logger.warning(f"AnomalyDetector load failed: {e}")
            return False

    @property
    def trained(self) -> bool:
        return self._trained


# Module-level singleton — load saved model if it exists, no-op otherwise
detector = DeviceAnomalyDetector()
detector.load()
