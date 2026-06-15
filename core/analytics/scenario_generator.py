"""
core/analytics/scenario_generator.py
Phase 3: Auto-KMeans Scenario Discovery.
Tries k=2..6, selects best by silhouette score.
Features include compute, network, storage, hour, and day dimensions.
"""
import numpy as np
import logging
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from integrations.influxdb.history_fetcher import HistoryFetcher

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "cpu_percent", "memory_percent", "disk_iops",
    "bandwidth_mbps", "latency_ms", "power_watts",
    "hour_of_day", "day_of_week",
]

SCENARIO_FALLBACK = [
    {
        "name": "normal",
        "label": "Normal (off-peak)",
        "cluster_size": 0,
        "metrics": {
            "cpu_percent": 33, "memory_percent": 45, "disk_iops": 800,
            "bandwidth_mbps": 500, "latency_ms": 12, "power_watts": 180,
        },
    },
    {
        "name": "business_peak",
        "label": "Business hours peak",
        "cluster_size": 0,
        "metrics": {
            "cpu_percent": 60, "memory_percent": 65, "disk_iops": 2000,
            "bandwidth_mbps": 800, "latency_ms": 35, "power_watts": 240,
        },
    },
    {
        "name": "night_batch",
        "label": "Night batch",
        "cluster_size": 0,
        "metrics": {
            "cpu_percent": 85, "memory_percent": 78, "disk_iops": 3200,
            "bandwidth_mbps": 300, "latency_ms": 20, "power_watts": 290,
        },
    },
    {
        "name": "weekend",
        "label": "Weekend idle",
        "cluster_size": 0,
        "metrics": {
            "cpu_percent": 20, "memory_percent": 30, "disk_iops": 400,
            "bandwidth_mbps": 100, "latency_ms": 8, "power_watts": 150,
        },
    },
]

SCENARIO_NAMES = ["normal", "business_peak", "night_batch", "weekend", "burst", "maintenance"]


class ScenarioGenerator:
    def __init__(self, k_min: int = 2, k_max: int = 6):
        self.k_min = k_min
        self.k_max = k_max
        self.scenarios: list[dict] = []
        self.best_k: int = 0
        self.fetcher = HistoryFetcher()

    def generate(self, days: int = 30) -> list[dict]:
        matrix, timestamps = self.fetcher.fetch_flat_matrix_with_time(
            days=days, metrics=FEATURE_COLS
        )

        if matrix is None or len(matrix) < self.k_max + 1:
            logger.warning("Insufficient data for clustering — using static fallback scenarios")
            self.scenarios = SCENARIO_FALLBACK
            return self.scenarios

        scaler = StandardScaler()
        X = scaler.fit_transform(matrix)

        # Auto-select k via silhouette score
        best_k, best_score, best_labels, best_centers = self._select_k(X)
        self.best_k = best_k
        logger.info(f"ScenarioGenerator: selected k={best_k} (silhouette={best_score:.3f})")

        centroids_orig = scaler.inverse_transform(best_centers)

        # Sort clusters by mean CPU ascending
        cpu_idx = FEATURE_COLS.index("cpu_percent")
        order = np.argsort(centroids_orig[:, cpu_idx])

        self.scenarios = []
        for rank, cluster_idx in enumerate(order):
            centroid = centroids_orig[cluster_idx]
            name = SCENARIO_NAMES[rank] if rank < len(SCENARIO_NAMES) else f"cluster_{rank}"
            scenario = {
                "name": name,
                "label": name.replace("_", " ").title(),
                "cluster_size": int(np.sum(best_labels == cluster_idx)),
                "silhouette": round(best_score, 3),
                "metrics": {
                    col: round(float(centroid[i]), 2)
                    for i, col in enumerate(FEATURE_COLS)
                    if col not in ("hour_of_day", "day_of_week")
                },
                "hour_centroid":  round(float(centroid[FEATURE_COLS.index("hour_of_day")]), 1),
                "day_centroid":   round(float(centroid[FEATURE_COLS.index("day_of_week")]), 1),
            }
            self.scenarios.append(scenario)

        logger.info(f"ScenarioGenerator: {len(self.scenarios)} scenarios discovered")
        return self.scenarios

    def _select_k(self, X: np.ndarray):
        best_k     = self.k_min
        best_score = -1.0
        best_labels  = None
        best_centers = None

        for k in range(self.k_min, self.k_max + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X)
            try:
                score = silhouette_score(X, labels, sample_size=min(5000, len(X)))
            except Exception:
                score = 0.0
            logger.debug(f"  k={k} silhouette={score:.3f}")
            if score > best_score:
                best_score   = score
                best_k       = k
                best_labels  = labels
                best_centers = km.cluster_centers_

        return best_k, best_score, best_labels, best_centers

    def get_scenarios(self) -> list[dict]:
        return self.scenarios if self.scenarios else SCENARIO_FALLBACK