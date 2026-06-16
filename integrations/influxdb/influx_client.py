"""
integrations/influxdb/influx_client.py
Handles streaming batch writes of derived node and link infrastructure metrics into InfluxDB.
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
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
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

    def close(self):
        if self.client:
            self.client.close()