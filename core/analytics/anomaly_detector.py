"""
core/analytics/anomaly_detector.py

Two-stage anomaly detection:

  Stage 1 — Isolation Forest (unsupervised)
    Trained ONLY on healthy data from node_telemetry / node_telemetry_real.
    Outputs: is_anomaly (bool) + raw anomaly_score (float, higher = worse).

  Stage 2 — Random Forest Classifier (supervised)
    Trained on labeled anomaly_training_data (injected by inject_anomaly_windows.py).
    Outputs: anomaly_type (cpu_spike / memory_pressure / …) + confidence.

The IF never sees anomaly labels — it stays honest to the unsupervised
principle and generalises to anomaly patterns it was never shown.
The RF Classifier fires ONLY when the IF already flagged an anomaly.
"""
import os
import pickle
import logging
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

logger = logging.getLogger(__name__)

MODEL_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "anomaly_detector.pkl")

# Feature columns shared by both stages.
# Real Prometheus node metrics only expose these 5 fields — network is an
# edge-level concept (edge_telemetry_bandwidth_mbps/latency_ms/packet_loss_percent),
# there is no per-node rx/tx in the live schema, so it's excluded here.
FEATURE_COLS = [
    "cpu_percent",
    "memory_percent",
    "disk_iops",
    "temperature_celsius",
    "power_watts",
]

ANOMALY_TYPES = [
    "none",
    "cpu_spike",
    "memory_pressure",
    "disk_saturation",
    "thermal_anomaly",
    "network_saturation",
    "cascading_failure",
]

# Metric → anomaly type heuristic used when RF confidence is low
# (threshold, anomaly_type) — first metric that exceeds its threshold wins
METRIC_TYPE_HINTS = [
    ("cpu_percent",          80.0, "cpu_spike"),
    ("memory_percent",       82.0, "memory_pressure"),
    ("disk_iops",          3000.0, "disk_saturation"),
    ("temperature_celsius",  72.0, "thermal_anomaly"),
    ("power_watts",         380.0, "thermal_anomaly"),
]

# Roles that are monitoring/infra helpers — skip remediation for these
SKIP_REMEDIATION_ROLES = {"container-metrics", "monitoring", "exporter"}

# Coarse role groups for per-group Isolation Forest training.
# Storage controllers run a structurally higher disk_iops baseline than
# compute/network nodes — a single global IF flags them as outliers on
# every tick even when healthy. Training one IF per group means each
# node is judged against peers with the same operating profile.
ROLE_GROUPS = {
    "compute-node":         "compute",
    "storage-controller":   "storage",
    "object-storage":       "storage",
    "storage-tor":          "network",
    "tor-router":           "network",
    "spine-switch":         "network",
    "middleware":           "service",
    "graph-database":       "service",
    "infrastructure-docs":  "service",
    "metrics-exporter":     "monitoring",
    "metrics-collector":    "monitoring",
    "metrics-dashboard":    "monitoring",
    "container-metrics":    "monitoring",
}
DEFAULT_ROLE_GROUP = "default"
MIN_GROUP_SAMPLES = 20


def _load_node_role_map() -> dict:
    """node_id -> role, read straight from the infrastructure YAML (no live telemetry needed)."""
    try:
        from config.settings import INFRASTRUCTURE_YAML
        from core.parser.yaml_parser import YAMLParser
        from core.parser.topology_loader import TopologyLoader

        parser = YAMLParser(INFRASTRUCTURE_YAML)
        parser.load()
        topology = TopologyLoader(parser).load_topology()
        return {n["id"]: n.get("role", "") for n in topology["nodes"]}
    except Exception as exc:
        logger.warning(f"AnomalyDetector: could not load role map ({exc}) — using single global model")
        return {}


class AnomalyDetector:
    """
    Wraps both ML stages.  Call train() once after data is available,
    then detect() / detect_all() on every tick.
    """

    def __init__(self, contamination: float = 0.08):
        os.makedirs(MODEL_DIR, exist_ok=True)
        self.contamination = contamination

        # Stage 1 — one IsolationForest + scaler per role group
        self.if_models:  dict[str, IsolationForest] = {}
        self.if_scalers: dict[str, StandardScaler]  = {}

        # Stage 2
        self.clf:        RandomForestClassifier = None
        self.clf_scaler: StandardScaler         = None

        self._trained = False

    # ── Training ───────────────────────────────────────────────────────────

    def train(self, days: int = 7) -> dict:
        from integrations.influxdb.history_fetcher import HistoryFetcher
        fetcher = HistoryFetcher()

        summary = {}
        summary["isolation_forest"] = self._train_if(fetcher, days)
        summary["classifier"]       = self._train_clf(fetcher, days)

        self._trained = True
        self._save()
        logger.info(f"AnomalyDetector training complete: {summary}")
        return summary

    def _train_if(self, fetcher, days: int) -> dict:
        """Isolation Forest — healthy data only, one model per role group."""
        node_series = fetcher.fetch_node_series_raw(days=days)
        role_map = _load_node_role_map()

        rows_by_group: dict[str, list] = {}
        for node_id, series in node_series.items():
            group = ROLE_GROUPS.get(role_map.get(node_id, ""), DEFAULT_ROLE_GROUP)
            n = len(series.get("cpu_percent", []))
            for i in range(n):
                row = [float(series.get(col, [0.0] * (i + 1))[i]
                             if i < len(series.get(col, [])) else 0.0)
                       for col in FEATURE_COLS]
                rows_by_group.setdefault(group, []).append(row)

        total_rows = sum(len(r) for r in rows_by_group.values())
        if total_rows < 20:
            logger.warning(f"IF: only {total_rows} healthy samples — skipping")
            return {"status": "insufficient_data", "samples": total_rows}

        # Groups too small to train their own model fall back into "default"
        pooled: dict[str, list] = {}
        for group, rows in rows_by_group.items():
            target = group if len(rows) >= MIN_GROUP_SAMPLES else DEFAULT_ROLE_GROUP
            pooled.setdefault(target, []).extend(rows)

        self.if_models  = {}
        self.if_scalers = {}
        group_summary = {}

        for group, rows in pooled.items():
            X = np.array(rows, dtype=float)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            scaler = StandardScaler()
            Xs = scaler.fit_transform(X)

            model = IsolationForest(
                contamination=self.contamination,
                n_estimators=200,
                max_samples="auto",
                random_state=42,
                n_jobs=-1,
            )
            model.fit(Xs)

            preds = model.predict(Xs)
            detected_rate = float((preds == -1).mean())

            self.if_models[group]  = model
            self.if_scalers[group] = scaler
            group_summary[group] = {"samples": len(rows), "detected_anomaly_rate": round(detected_rate, 3)}
            logger.info(f"IF[{group}] trained: {len(rows)} samples, detected_rate={detected_rate:.3f}")

        return {"status": "trained", "samples": total_rows, "groups": group_summary}

    def _train_clf(self, fetcher, days: int) -> dict:
        """RF Classifier — labeled anomaly_training_data."""
        labeled = fetcher.fetch_anomaly_training_data(days=days)
        X_raw = labeled.get("X", [])
        y_raw = labeled.get("y", [])

        if len(X_raw) < 20:
            logger.warning(f"Classifier: only {len(X_raw)} labeled samples — skipping")
            return {"status": "insufficient_data", "samples": len(X_raw)}

        X = np.array(X_raw, dtype=float)
        y = np.array(y_raw)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        self.clf_scaler = StandardScaler()
        Xs = self.clf_scaler.fit_transform(X)

        self.clf = RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        )
        self.clf.fit(Xs, y)

        try:
            scores = cross_val_score(self.clf, Xs, y, cv=3, scoring="f1_macro", n_jobs=-1)
            f1 = float(scores.mean())
        except Exception:
            f1 = 0.0

        classes = list(set(y))
        logger.info(f"RF Classifier trained: {len(X)} samples, classes={classes}, F1={f1:.3f}")
        return {"status": "trained", "samples": len(X), "f1_macro": round(f1, 3), "classes": classes}

    # ── Inference ──────────────────────────────────────────────────────────

    def detect(self, node_id: str, metrics: dict, role: str = "") -> dict:
        """
        Run both stages on a single node's current metric dict.
        Loads from disk if not already trained in memory.
        `role` selects which per-group Isolation Forest to score against.
        """
        if not self._trained:
            if not self.load():
                return self._null_result(node_id)

        if not self.if_models:
            return self._null_result(node_id)

        group = ROLE_GROUPS.get(role, DEFAULT_ROLE_GROUP)
        if group not in self.if_models:
            group = DEFAULT_ROLE_GROUP
        if group not in self.if_models:
            # No default model either (e.g. every group met MIN_GROUP_SAMPLES) — use any available model
            group = next(iter(self.if_models))

        if_model  = self.if_models[group]
        if_scaler = self.if_scalers[group]

        row = np.array([[metrics.get(col, 0.0) for col in FEATURE_COLS]], dtype=float)
        row = np.nan_to_num(row, nan=0.0, posinf=0.0, neginf=0.0)
        row_s = if_scaler.transform(row)

        # IF: -1 = anomaly, +1 = normal
        pred  = int(if_model.predict(row_s)[0])
        # score_samples returns negative values; negate so higher = more anomalous
        score = float(-if_model.score_samples(row_s)[0])

        is_anomaly   = pred == -1
        anomaly_type = "none"
        confidence   = 0.0

        if is_anomaly and self.clf is not None:
            row_cs  = self.clf_scaler.transform(row)
            proba   = self.clf.predict_proba(row_cs)[0]
            classes = self.clf.classes_

            top_idx      = int(proba.argmax())
            anomaly_type = str(classes[top_idx])
            confidence   = float(proba[top_idx])

            # If RF picked "none" with low confidence, try the runner-up class
            if anomaly_type == "none" and confidence < 0.6:
                for idx in proba.argsort()[::-1]:
                    if classes[idx] != "none":
                        if float(proba[idx]) > 0.2:
                            anomaly_type = str(classes[idx])
                            confidence   = float(proba[idx])
                        break

            # Last resort: infer from which metric is most elevated
            if anomaly_type == "none":
                inferred = self._infer_type_from_metrics(metrics)
                if inferred:
                    anomaly_type = inferred
                    confidence   = max(confidence, 0.30)

        return {
            "node_id":      node_id,
            "is_anomaly":   is_anomaly,
            "anomaly_score": round(score, 4),
            "anomaly_type": anomaly_type,
            "confidence":   round(confidence, 3),
            "source":       "isolation_forest",
        }

    def detect_all(self, derived_graph) -> list[dict]:
        """
        Run detect() on every infrastructure node in the derived graph.
        Skips monitoring/exporter nodes (cadvisor, etc.) that can't be remediated.
        Returns only nodes where is_anomaly=True.
        """
        results = []
        for node_id in derived_graph.nodes:
            node = derived_graph.nodes[node_id]
            role = node.get("role", "")
            if role in SKIP_REMEDIATION_ROLES:
                continue
            metrics = node.get("metrics", {})
            if not metrics:
                continue
            result = self.detect(node_id, metrics, role=role)
            if result["is_anomaly"]:
                result["role"] = role
                results.append(result)
        return results

    def _infer_type_from_metrics(self, metrics: dict) -> str:
        """Return the anomaly type suggested by the highest threshold breach."""
        best_type  = ""
        best_ratio = 0.0
        for col, threshold, atype in METRIC_TYPE_HINTS:
            val = float(metrics.get(col, 0.0))
            if val > threshold:
                ratio = val / threshold
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_type  = atype
        return best_type

    # ── Persistence ────────────────────────────────────────────────────────

    def _save(self):
        payload = {
            "if_models":   self.if_models,
            "if_scalers":  self.if_scalers,
            "clf":         self.clf,
            "clf_scaler":  self.clf_scaler,
            "contamination": self.contamination,
        }
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(payload, f)
        logger.info(f"AnomalyDetector saved → {MODEL_PATH}")

    def load(self) -> bool:
        if not os.path.exists(MODEL_PATH):
            logger.warning("AnomalyDetector: no saved model found — train first")
            return False
        try:
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.if_models   = data.get("if_models", {})
            self.if_scalers  = data.get("if_scalers", {})
            self.clf         = data.get("clf")
            self.clf_scaler  = data.get("clf_scaler")
            self.contamination = data.get("contamination", 0.08)
            self._trained    = True
            logger.info("AnomalyDetector loaded from disk")
            return True
        except Exception as exc:
            logger.warning(f"AnomalyDetector load failed: {exc}")
            return False

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _null_result(node_id: str) -> dict:
        return {
            "node_id":       node_id,
            "is_anomaly":    False,
            "anomaly_score": 0.0,
            "anomaly_type":  "none",
            "confidence":    0.0,
            "source":        "not_trained",
        }
