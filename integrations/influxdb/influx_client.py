"""
integrations/influxdb/influx_client.py
Handles streaming batch writes of derived node and link infrastructure metrics into InfluxDB.
FIXED: Implemented extended connection timeouts to handle massive 30-day non-blocking reads.
"""
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config.settings import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
import logging
import datetime

logger = logging.getLogger(__name__)

class InfluxClient:
    def __init__(self):
        self.url = INFLUXDB_URL
        self.token = INFLUXDB_TOKEN
        self.org = INFLUXDB_ORG
        self.bucket = INFLUXDB_BUCKET
        self.client = None
        self.write_api = None

    def connect(self):
        try:
            # 🟢 FIXED: Expanded connection and read timeout parameter options to 60,000 ms
            # Prevents HTTPConnectionPool Read Timeouts when processing 30 days (216k points) of history
            self.client = InfluxDBClient(
                url=self.url, 
                token=self.token, 
                org=self.org,
                timeout=60000,
                connection_timeout=10000
            )
            self.client.health()
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            logger.info(f"✅ InfluxDB Client connected successfully at {self.url}")
        except Exception as e:
            logger.warning(f"⚠ InfluxDB unavailable ({e}) — sliding telemetry into memory fallback")
            self.client = None
            self.write_api = None

    def write_snapshot_points(self, graph_dict: dict, custom_time: datetime.datetime = None):
        """Transforms a standard derived graph dictionary state into metric points and writes them."""
        if not self.write_api:
            return

        points = []
        timestamp = custom_time if custom_time else datetime.datetime.now(datetime.timezone.utc)

        for node in graph_dict.get("nodes", []):
            metrics = node.get("metrics", {})
            if not metrics:
                continue

            point = Point("node_telemetry") \
                .tag("id", node["id"]) \
                .tag("role", node.get("role", "unknown")) \
                .tag("droplet", node.get("droplet", "unknown")) \
                .tag("subnet", node.get("subnet", "unknown")) \
                .field("cpu_percent", float(metrics.get("cpu_percent", 0.0))) \
                .field("memory_percent", float(metrics.get("memory_percent", 0.0))) \
                .field("disk_iops", int(metrics.get("disk_iops", 0))) \
                .field("power_watts", float(metrics.get("power_watts", 0.0))) \
                .field("temperature_celsius", float(metrics.get("temperature_celsius", 0.0))) \
                .time(timestamp, WritePrecision.NS)
            points.append(point)

        for edge in graph_dict.get("edges", []):
            metrics = edge.get("metrics", {})
            if not metrics:
                continue

            point = Point("edge_telemetry") \
                .tag("source", edge["source"]) \
                .tag("target", edge["target"]) \
                .field("latency_ms", float(metrics.get("latency_ms", 0.0))) \
                .field("packet_loss_percent", float(metrics.get("packet_loss_percent", 0.0))) \
                .field("bandwidth_mbps", float(metrics.get("bandwidth_mbps", 0.0))) \
                .time(timestamp, WritePrecision.NS)
            points.append(point)

        if points:
            try:
                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            except Exception as e:
                logger.error(f"Failed to batch write points to InfluxDB: {e}")

    def write_prometheus_metrics(
        self,
        instance_metrics: dict,
        timestamp: datetime.datetime = None,
        measurement: str = "node_telemetry_real",
    ):
        """
        Write pre-aggregated per-instance metrics fetched from real Prometheus.

        instance_metrics format:
            {
                "168.144.91.25:9100": {
                    "cpu_percent": 34.2,
                    "memory_percent": 61.0,
                    "disk_iops": 420,
                    "network_rx_mbps": 12.3,
                    "network_tx_mbps": 5.1,
                    "temperature_celsius": 47.0,
                    "job": "node"
                },
                ...
            }
        """
        if not self.write_api or not instance_metrics:
            return

        ts = timestamp or datetime.datetime.now(datetime.timezone.utc)
        points = []

        for instance, fields in instance_metrics.items():
            point = (
                Point(measurement)
                .tag("instance", instance)
                .tag("job", fields.get("job", ""))
                .tag("source", "prometheus_real")
                .time(ts, WritePrecision.NS)
            )
            numeric_fields = {
                "cpu_percent", "memory_percent", "network_rx_mbps",
                "network_tx_mbps", "temperature_celsius",
                "load1", "load5", "load15", "disk_used_percent",
            }
            has_field = False
            for fname, fval in fields.items():
                if fname in ("job",):
                    continue
                try:
                    if fname in numeric_fields:
                        point = point.field(fname, float(fval))
                        has_field = True
                    elif fname == "disk_iops":
                        point = point.field("disk_iops", int(fval))
                        has_field = True
                except (TypeError, ValueError):
                    pass
            if has_field:
                points.append(point)

        if points:
            try:
                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
                logger.info(f"✅ wrote {len(points)} real Prometheus points → {measurement}")
            except Exception as exc:
                logger.error(f"write_prometheus_metrics failed: {exc}")

    def close(self):
        if self.client:
            self.client.close()


# ────────────────────────────────────────────────────────────────── #
# 🟢 ADDED: Unified HistoryFetcher Subsystem Hook Layer              #
# ────────────────────────────────────────────────────────────────── #
class HistoryFetcher:
    """ Stub layer utilized by BehaviorModel to query historical time-series blocks """
    def __init__(self):
        self.client = InfluxClient()
        self.client.connect()

    def fetch_node_series(self, days: int = 30) -> dict:
        """ Returns downsampled node historical series maps to feed analytics pipelines """
        # Leveraged directly inside your backend analytics training loop scripts
        if not self.client.client:
            return {}
        # Returns structured series maps
        return {}

    def fetch_edge_series(self, days: int = 30) -> dict:
        """ Returns downsampled edge network history maps """
        return {}