"""
integrations/influxdb/history_fetcher.py
Pulls historical time-series from InfluxDB for the ML pipeline.
Falls back to correlated synthetic data when InfluxDB is offline.
FIXED: Implemented extended connection timeouts and downsampled aggregation intervals.
"""

import logging
import time as time_mod
import numpy as np
from config.settings import (
    INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET,
    CPU_HEALTHY_MEAN, CPU_HEALTHY_STD,
    MEMORY_HEALTHY_MEAN, MEMORY_HEALTHY_STD,
    IOPS_HEALTHY_MEAN, IOPS_HEALTHY_STD,
    POWER_PER_NODE_MEAN, POWER_PER_NODE_STD,
    LATENCY_HEALTHY_MEAN, LATENCY_HEALTHY_STD,
)

logger = logging.getLogger(__name__)

COMPUTE_NODES = ["server-1", "server-2", "server-3", "server-4", "array-ctrl-a", "array-ctrl-b"]
ROUTER_NODES = ["router-1", "router-2", "spine-router", "storage-router"]
SERVICE_NODES = ["neo4j", "python-app", "netbox"]
ALL_NODES = COMPUTE_NODES + ROUTER_NODES + SERVICE_NODES

KNOWN_EDGES = [
    "spine-router->router-1",
    "spine-router->router-2",
    "spine-router->storage-router",
    "router-1->server-1",
    "router-1->server-2",
    "router-2->server-3",
    "router-2->server-4",
    "storage-router->array-ctrl-a",
    "storage-router->array-ctrl-b",
]


class HistoryFetcher:
    def __init__(self):
        self._client = None
        self._connect()

    def _connect(self):
        try:
            from influxdb_client import InfluxDBClient
            # 🟢 FIXED: Extended connection and read timeouts to 60 seconds (60,000 ms)
            # Prevents client drops when loading a full 30-day historical time-series dataset
            self._client = InfluxDBClient(
                url=INFLUXDB_URL, 
                token=INFLUXDB_TOKEN, 
                org=INFLUXDB_ORG,
                timeout=60000,
                connection_timeout=10000
            )
            self._client.health()
            logger.info("HistoryFetcher: InfluxDB OK")
        except Exception as e:
            logger.warning(f"HistoryFetcher: InfluxDB unavailable ({e}) — using synthetic data")
            self._client = None

    # ==================================================================
    # Node Series Handling
    # ==================================================================
    def fetch_node_series(self, days: int = 30) -> dict[str, dict]:
        if self._client:
            result = self._influx_node_series(days)
            if result:
                return result
        return self._synthetic_node_series(days)

    def _influx_node_series(self, days: int) -> dict:
        q_api = self._client.query_api()
        # 🟢 FIXED: Added aggregateWindow() downsampling directly on the InfluxDB side.
        # This condenses the dataset into clean 1-hour mean intervals before returning to Python,
        # dramatically cutting query payload size and accelerating ML ingestion speeds.
        flux = f"""
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r._measurement == "node_telemetry")
          |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time","id"], columnKey:["_field"], valueColumn:"_value")
        """
        result: dict[str, dict] = {}
        try:
            for table in q_api.query(flux):
                for rec in table.records:
                    nid = rec.values.get("id", "")
                    if nid not in result:
                        result[nid] = {"timestamps": []}
                    
                    ts = rec.get_time()
                    result[nid]["timestamps"].append(ts.timestamp() if ts else 0)
                    
                    metrics_keys = ["cpu_percent", "memory_percent", "disk_iops", "power_watts", "temperature_celsius"]
                    for m in metrics_keys:
                        v = rec.values.get(m)
                        if v is not None:
                            result[nid].setdefault(m, []).append(float(v))
        except Exception as e:
            logger.warning(f"InfluxDB node query failed: {e}")
            return {}

        # Compute time-of-day features from timestamps — needed by ScenarioGenerator
        for data in result.values():
            ts_list = data.get("timestamps", [])
            data["hour_of_day"] = [float(int(t % 86400 // 3600)) for t in ts_list]
            data["day_of_week"]  = [float(int((t // 86400) % 7)) for t in ts_list]

        # Join edge telemetry — add global-mean bandwidth/latency to each node so
        # fetch_flat_matrix_with_time has all 8 features ScenarioGenerator expects.
        try:
            edge_series = self._influx_edge_series(days)
            all_bw  = [d.get("bandwidth_mbps", []) for d in edge_series.values() if d.get("bandwidth_mbps")]
            all_lat = [d.get("latency_ms", []) for d in edge_series.values() if d.get("latency_ms")]
            
            if all_bw and all_lat:
                min_len  = min(min(len(s) for s in all_bw), min(len(s) for s in all_lat))
                mean_bw  = np.mean([s[:min_len] for s in all_bw], axis=0).tolist()
                mean_lat = np.mean([s[:min_len] for s in all_lat], axis=0).tolist()
                
                for data in result.values():
                    n = len(data.get("timestamps", []))
                    # Align lengths: repeat last value if node series is longer
                    data["bandwidth_mbps"] = (mean_bw + [mean_bw[-1]] * max(0, n - min_len))[:n]
                    data["latency_ms"]     = (mean_lat + [mean_lat[-1]] * max(0, n - min_len))[:n]
        except Exception as e:
            logger.debug(f"Edge join for node series skipped: {e}")

        return result

    def _synthetic_node_series(self, days: int) -> dict:
        """Correlated Gaussian synthetic data with day/night patterns."""
        rng = np.random.default_rng(seed=42)
        interval_s = 300  # 5-minute samples
        n = min(days * 24 * 12, 8640)
        now_ts = time_mod.time()
        timestamps = [now_ts - (n - i) * interval_s for i in range(n)]

        result = {}
        for node in ALL_NODES:
            is_router  = node in ROUTER_NODES
            is_storage = node in ["array-ctrl-a", "array-ctrl-b"]

            # Hour-of-day pattern: business hours higher CPU
            hour_arr = np.array([(int(t % 86400 // 3600)) for t in timestamps], dtype=float)
            biz_mask   = ((hour_arr >= 9) & (hour_arr < 18)).astype(float)
            night_mask = ((hour_arr >= 22) | (hour_arr < 2)).astype(float)
            day_arr    = np.array([int((t // 86400) % 7) for t in timestamps], dtype=float)
            weekend_mask = (day_arr >= 5).astype(float)

            cpu_base = (
                8.0 if is_router
                else CPU_HEALTHY_MEAN + biz_mask * 25 + night_mask * 30 - weekend_mask * 20
            )
            cpu = np.clip(rng.normal(cpu_base, CPU_HEALTHY_STD, n), 0, 100)

            mem_base = MEMORY_HEALTHY_MEAN + cpu * 0.35
            mem = np.clip(rng.normal(mem_base, MEMORY_HEALTHY_STD, n), 0, 100)

            iops_base = (IOPS_HEALTHY_MEAN * (1.5 if is_storage else 1.0) + cpu * 25 + night_mask * 1500)
            iops = np.clip(rng.normal(iops_base, IOPS_HEALTHY_STD, n), 0, 10000)

            power_base = POWER_PER_NODE_MEAN + cpu * 1.5
            power = np.clip(rng.normal(power_base, POWER_PER_NODE_STD, n), 50, 600)

            bw = np.clip(rng.normal(500 + biz_mask * 200 - weekend_mask * 300, 80, n), 0, 1000)
            latency = np.clip(rng.normal(LATENCY_HEALTHY_MEAN + bw * 0.01, LATENCY_HEALTHY_STD, n), 0.5, 200)

            result[node] = {
                "timestamps": timestamps,
                "cpu_percent": list(cpu),
                "memory_percent": list(mem),
                "disk_iops": list(iops),
                "power_watts": list(power),
                "bandwidth_mbps": list(bw),
                "latency_ms": list(latency),
                "packet_loss_percent": list(np.clip(rng.normal(0.05, 0.02, n), 0, 5)),
                "temperature_celsius": list(np.clip(rng.normal(45 + cpu * 0.2, 3, n), 25, 90)),
                "hour_of_day": list(hour_arr),
                "day_of_week": list(day_arr),
            }
        return result

    def fetch_node_series_raw(self, days: int = 7) -> dict[str, dict]:
        """
        Non-aggregated node telemetry for Isolation Forest training.
        Uses raw 12-second-interval points so training variance matches
        live single-point readings — avoids the false-anomaly problem
        that arises when IF is trained on 1h-mean aggregates (which
        crush std by ~17x, making normal live readings look like outliers).
        """
        if self._client:
            result = self._influx_node_series_raw(days)
            if result:
                return result
        return self._synthetic_node_series(days)

    def _influx_node_series_raw(self, days: int) -> dict:
        q_api = self._client.query_api()
        flux = f"""
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r._measurement == "node_telemetry")
          |> pivot(rowKey:["_time","id"], columnKey:["_field"], valueColumn:"_value")
        """
        result: dict[str, dict] = {}
        try:
            for table in q_api.query(flux):
                for rec in table.records:
                    nid = rec.values.get("id", "")
                    if not nid:
                        continue
                    if nid not in result:
                        result[nid] = {"timestamps": []}
                    
                    ts = rec.get_time()
                    result[nid]["timestamps"].append(ts.timestamp() if ts else 0)
                    
                    metrics_keys = ["cpu_percent", "memory_percent", "disk_iops", "power_watts", "temperature_celsius"]
                    for m in metrics_keys:
                        v = rec.values.get(m)
                        if v is not None:
                            result[nid].setdefault(m, []).append(float(v))
        except Exception as e:
            logger.warning(f"InfluxDB raw node query failed: {e}")
            return {}
        return result

    # ==================================================================
    # Edge Series Handling
    # ==================================================================
    def fetch_edge_series(self, days: int = 30) -> dict[str, dict]:
        if self._client:
            result = self._influx_edge_series(days)
            if result:
                return result
        return self._synthetic_edge_series(days)

    def _influx_edge_series(self, days: int) -> dict:
        q_api = self._client.query_api()
        # 🟢 FIXED: Added aggregateWindow() downsampling to the edge network interface query
        flux = f"""
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r._measurement == "edge_telemetry")
          |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time","source","target"], columnKey:["_field"], valueColumn:"_value")
        """
        result: dict[str, dict] = {}
        try:
            for table in q_api.query(flux):
                for rec in table.records:
                    src = rec.values.get("source", "")
                    tgt = rec.values.get("target", "")
                    key = f"{src}->{tgt}"
                    if key not in result:
                        result[key] = {"timestamps": []}
                    
                    ts = rec.get_time()
                    result[key]["timestamps"].append(ts.timestamp() if ts else 0)
                    
                    for m in ["latency_ms", "packet_loss_percent", "bandwidth_mbps"]:
                        v = rec.values.get(m)
                        if v is not None:
                            result[key].setdefault(m, []).append(float(v))
        except Exception as e:
            logger.warning(f"InfluxDB edge query failed: {e}")
            return {}
        return result

    def _synthetic_edge_series(self, days: int) -> dict:
        rng = np.random.default_rng(seed=99)
        n = min(days * 24 * 12, 8640)
        now_ts = time_mod.time()
        timestamps = [now_ts - (n - i) * 300 for i in range(n)]
        result = {}
        for edge_key in KNOWN_EDGES:
            bw   = np.clip(rng.normal(600, 100, n), 50, 1000)
            lat  = np.clip(rng.normal(LATENCY_HEALTHY_MEAN + bw * 0.005, LATENCY_HEALTHY_STD, n), 0.5, 200)
            loss = np.clip(rng.normal(0.05, 0.02, n), 0, 5)
            result[edge_key] = {
                "timestamps": timestamps,
                "latency_ms": list(lat),
                "packet_loss_percent": list(loss),
                "bandwidth_mbps": list(bw),
            }
        return result

    # ==================================================================
    # Flat Processing Interface for ML Pipelines
    # ==================================================================
    def fetch_flat_matrix_with_time(self, days: int = 30, metrics: list[str] = None) -> tuple:
        metrics = metrics or [
            "cpu_percent", "memory_percent", "disk_iops",
            "bandwidth_mbps", "latency_ms", "power_watts",
            "hour_of_day", "day_of_week"
        ]
        series = self.fetch_node_series(days)
        rows, timestamps = [], []
        
        for node_id, data in series.items():
            n = min(len(data.get(m, [])) for m in metrics if data.get(m))
            if n < 10:
                continue
            
            ts_list = data.get("timestamps", [None] * n)
            for i in range(n):
                row = []
                ok = True
                for m in metrics:
                    vals = data.get(m, [])
                    if i < len(vals):
                        row.append(float(vals[i]))
                    else:
                        ok = False
                        break
                if ok and len(row) == len(metrics):
                    rows.append(row)
                    timestamps.append(ts_list[i] if i < len(ts_list) else None)
                    
        if not rows:
            return None, []
        return np.array(rows, dtype=float), timestamps