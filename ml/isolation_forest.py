from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURES = ("cpu_pct", "memory_pct", "temp_c", "power_w", "net_io_mbps")
MODEL_LABEL = "Anomaly Detection — Synthetic Baseline Demo"


class SyntheticIsolationForest:
    def __init__(self, random_state: int = 42, threshold: float = .65):
        self.random_state = random_state
        self.threshold = threshold
        self._model = None
        self._scaler = None

    def _ensure_trained(self):
        if self._model is not None:
            return
        rng = np.random.default_rng(self.random_state)
        profiles = [
            (45, 55, 48, 220, 180), (60, 70, 55, 310, 250),
            (15, 25, 35, 90, 40), (35, 45, 43, 170, 320),
            (50, 50, 50, 240, 200),
        ]
        samples = np.vstack([rng.normal(profile, (8, 8, 3, 25, 35), size=(120, 5)) for profile in profiles])
        samples[:, :2] = np.clip(samples[:, :2], 0, 100)
        self._scaler = StandardScaler().fit(samples)
        self._model = IsolationForest(
            n_estimators=50,
            contamination=.05,
            random_state=self.random_state,
            n_jobs=1,
        ).fit(self._scaler.transform(samples))

    def score_one(self, metrics: dict) -> dict:
        return self.score_batch([metrics])[0]

    def score_batch(self, rows: list[dict]) -> list[dict]:
        self._ensure_trained()
        matrix = np.array([[float(row[name]) for name in FEATURES] for row in rows])
        raw = self._model.decision_function(self._scaler.transform(matrix))
        scores = np.clip((.2 - raw) / .4, 0, 1)
        return [{
            "anomaly_score": round(float(score), 4),
            "anomaly_detected": bool(score >= self.threshold),
            "anomaly_model": "isolation_forest_synthetic_v1",
            "anomaly_label": MODEL_LABEL,
        } for score in scores]
