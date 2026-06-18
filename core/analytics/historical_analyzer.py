"""
core/analytics/historical_analyzer.py
Phase 2: Full HistoricalPatternAnalyzer.
Steps: Percentile → Hourly Behavior → Daily Pattern → Correlation Analysis.
Covers compute (CPU/memory/power), network (latency/bandwidth/loss), storage (IOPS).
"""
import numpy as np
import logging
from integrations.influxdb.history_fetcher import HistoryFetcher

logger = logging.getLogger(__name__)

COMPUTE_METRICS  = ["cpu_percent", "memory_percent", "power_watts", "temperature_celsius"]
NETWORK_METRICS  = ["latency_ms", "bandwidth_mbps", "packet_loss_percent"]
STORAGE_METRICS  = ["disk_iops"]
ALL_NODE_METRICS = COMPUTE_METRICS + STORAGE_METRICS
ALL_EDGE_METRICS = NETWORK_METRICS

CORRELATION_PAIRS = [
    ("cpu_percent",    "memory_percent"),
    ("cpu_percent",    "power_watts"),
    ("cpu_percent",    "disk_iops"),
    ("bandwidth_mbps", "latency_ms"),
    ("bandwidth_mbps", "packet_loss_percent"),
]

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class HistoricalPatternAnalyzer:
    def __init__(self):
        self.fetcher = HistoryFetcher()
        self.profiles: dict = {}         # node_id → full profile
        self.edge_profiles: dict = {}    # edge_key → full profile
        self.correlations: dict = {}     # node_id → correlation pairs

    def analyze(self, days: int = 30) -> dict:
        """Run all 4 analysis steps and return merged profiles."""
        node_series = self.fetcher.fetch_node_series(days=days)
        edge_series = self.fetcher.fetch_edge_series(days=days)

        for node_id, series in node_series.items():
            self.profiles[node_id] = self._build_node_profile(node_id, series)

        for edge_key, series in edge_series.items():
            self.edge_profiles[edge_key] = self._build_edge_profile(edge_key, series)

        logger.info(
            f"HistoricalPatternAnalyzer: {len(self.profiles)} node profiles, "
            f"{len(self.edge_profiles)} edge profiles"
        )
        return {"profiles": self.profiles, "edge_profiles": self.edge_profiles}

    # ------------------------------------------------------------------ #
    # Step 2.1 — Percentile Analysis                                       #
    # ------------------------------------------------------------------ #
    def _percentile_profile(self, values: list) -> dict:
        if not values:
            return {}
        arr = np.array(values, dtype=float)
        return {
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p90": round(float(np.percentile(arr, 90)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "max": round(float(arr.max()), 2),
            "mean": round(float(arr.mean()), 2),
            "samples": len(arr),
        }

    # ------------------------------------------------------------------ #
    # Step 2.2 — Hourly Behavior Analysis                                  #
    # ------------------------------------------------------------------ #
    def _hourly_profile(self, values: list, timestamps: list) -> dict:
        """Returns mean value per hour-of-day (0-23)."""
        hourly: dict[int, list] = {h: [] for h in range(24)}
        for ts, v in zip(timestamps, values):
            hour = int(ts % 86400 // 3600)
            hourly[hour].append(v)
        return {
            str(h): round(float(np.mean(vals)), 2) if vals else 0.0
            for h, vals in hourly.items()
        }

    # ------------------------------------------------------------------ #
    # Step 2.3 — Daily Pattern Analysis                                    #
    # ------------------------------------------------------------------ #
    def _daily_profile(self, values: list, timestamps: list) -> dict:
        """Returns mean value per day-of-week (Mon–Sun)."""
        daily: dict[int, list] = {d: [] for d in range(7)}
        for ts, v in zip(timestamps, values):
            day = int((ts // 86400) % 7)
            daily[day].append(v)
        return {
            DAYS_OF_WEEK[d]: round(float(np.mean(vals)), 2) if vals else 0.0
            for d, vals in daily.items()
        }

    # ------------------------------------------------------------------ #
    # Step 2.4 — Correlation Analysis                                      #
    # ------------------------------------------------------------------ #
    def _correlation_profile(self, series: dict) -> dict:
        correlations = {}
        for m1, m2 in CORRELATION_PAIRS:
            v1 = series.get(m1, [])
            v2 = series.get(m2, [])
            n = min(len(v1), len(v2))
            if n < 10:
                continue
            try:
                r = float(np.corrcoef(v1[:n], v2[:n])[0, 1])
                key = f"{m1}_vs_{m2}"
                correlations[key] = round(r, 3) if not np.isnan(r) else 0.0
            except Exception:
                pass
        return correlations

    # ------------------------------------------------------------------ #
    # Node profile builder                                                  #
    # ------------------------------------------------------------------ #
    def _build_node_profile(self, node_id: str, series: dict) -> dict:
        timestamps = series.get("timestamps", [])
        profile = {"node_id": node_id, "compute": {}, "storage": {}, "hourly": {}, "daily": {}}

        for metric in COMPUTE_METRICS + STORAGE_METRICS:
            values = series.get(metric, [])
            if not values:
                continue
            group = "storage" if metric in STORAGE_METRICS else "compute"
            profile[group][metric] = self._percentile_profile(values)

            if timestamps and metric == "cpu_percent":
                profile["hourly"]["cpu_percent"] = self._hourly_profile(values, timestamps)
                profile["daily"]["cpu_percent"]  = self._daily_profile(values, timestamps)
            if timestamps and metric == "power_watts":
                profile["hourly"]["power_watts"] = self._hourly_profile(values, timestamps)

        profile["correlations"] = self._correlation_profile(series)
        return profile

    # ------------------------------------------------------------------ #
    # Edge profile builder (network metrics)                               #
    # ------------------------------------------------------------------ #
    def _build_edge_profile(self, edge_key: str, series: dict) -> dict:
        timestamps = series.get("timestamps", [])
        profile = {"edge_key": edge_key, "network": {}, "hourly": {}}

        for metric in ALL_EDGE_METRICS:
            values = series.get(metric, [])
            if not values:
                continue
            profile["network"][metric] = self._percentile_profile(values)
            if timestamps and metric == "latency_ms":
                profile["hourly"]["latency_ms"] = self._hourly_profile(values, timestamps)

        return profile

    # ------------------------------------------------------------------ #
    # Public accessors                                                      #
    # ------------------------------------------------------------------ #
    def get_profile(self, node_id: str) -> dict:
        return self.profiles.get(node_id, {})

    def get_edge_profile(self, edge_key: str) -> dict:
        return self.edge_profiles.get(edge_key, {})

    def get_scenario_bounds(self, node_id: str, metric: str) -> dict:
        domain = "storage" if metric in STORAGE_METRICS else "compute"
        p = self.profiles.get(node_id, {}).get(domain, {}).get(metric, {})
        if not p:
            return {}
        return {
            "normal":        p.get("p50", 0),
            "business_peak": p.get("p90", 0),
            "night_batch":   p.get("p95", 0),
            "worst_case":    p.get("p99", 0),
        }

    def detect_night_batch(self, node_id: str) -> bool:
        """Returns True if hourly CPU shows a consistent spike in hours 22-2."""
        hourly = self.profiles.get(node_id, {}).get("hourly", {}).get("cpu_percent", {})
        if not hourly:
            return False
        night_hours = [22, 23, 0, 1, 2]
        day_hours   = [9, 10, 11, 14, 15, 16]
        night_avg = np.mean([hourly.get(str(h), 0) for h in night_hours])
        day_avg   = np.mean([hourly.get(str(h), 0) for h in day_hours])
        return float(night_avg) > float(day_avg) * 1.3

    def detect_weekend_idle(self, node_id: str) -> bool:
        """Returns True if Sat/Sun CPU is significantly lower than weekday."""
        daily = self.profiles.get(node_id, {}).get("daily", {}).get("cpu_percent", {})
        if not daily:
            return False
        weekday_avg = np.mean([daily.get(d, 0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]])
        weekend_avg = np.mean([daily.get(d, 0) for d in ["Sat", "Sun"]])
        return float(weekend_avg) < float(weekday_avg) * 0.5