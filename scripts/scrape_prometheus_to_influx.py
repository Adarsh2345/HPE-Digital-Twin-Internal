#!/usr/bin/env python3
"""
scripts/scrape_prometheus_to_influx.py

Scrapes real Prometheus metrics from http://168.144.91.25:9090/ and writes
them to InfluxDB for persistent time-series storage.

Prometheus label schema (set by the mock-exporter on each droplet):
  node metrics : node_telemetry_<field>{id, role, droplet, rack, instance, job}
  edge metrics : edge_telemetry_<field>{source, target, droplet, rack, instance, job}

Writes to the SAME measurements the simulation engine uses:
  node_telemetry  — same schema as write_snapshot_points(), source="prometheus_real"
  edge_telemetry  — same schema as write_snapshot_points(), source="prometheus_real"

This means the ML pipeline (history_fetcher, behavior_model, scenario_generator)
reads BOTH simulated and real data from a single Flux query.

Usage:
  python scripts/scrape_prometheus_to_influx.py              # continuous, 15s
  python scripts/scrape_prometheus_to_influx.py --once       # single pass
  python scripts/scrape_prometheus_to_influx.py --interval 30
"""
import sys, os, time, logging, argparse, datetime, requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config.settings import (
    INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Prometheus metric names exposed by the mock-exporter (port 9200) ───────
# Each metric already carries the computed value — no PromQL math needed.

NODE_METRICS = [
    "node_telemetry_cpu_percent",
    "node_telemetry_memory_percent",
    "node_telemetry_disk_iops",
    "node_telemetry_power_watts",
    "node_telemetry_temperature_celsius",
]

EDGE_METRICS = [
    "edge_telemetry_latency_ms",
    "edge_telemetry_bandwidth_mbps",
    "edge_telemetry_packet_loss_percent",
]

# Strip "node_telemetry_" prefix → InfluxDB field name
def _node_field(metric_name: str) -> str:
    return metric_name.replace("node_telemetry_", "")

def _edge_field(metric_name: str) -> str:
    return metric_name.replace("edge_telemetry_", "")


class PrometheusInfluxBridge:

    def __init__(self, prometheus_url: str, scrape_interval: int = 15):
        self.prometheus_url  = prometheus_url.rstrip("/")
        self.scrape_interval = scrape_interval

        self.influx = InfluxDBClient(
            url=INFLUXDB_URL, token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG, timeout=30000,
        )
        self.write_api = self.influx.write_api(write_options=SYNCHRONOUS)
        self.session   = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # ── Prometheus helpers ─────────────────────────────────────────────────

    def _query(self, metric: str) -> list[dict]:
        try:
            r = self.session.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": metric}, timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "success":
                return data["data"]["result"]
        except Exception as exc:
            logger.warning(f"Query failed [{metric}]: {exc}")
        return []

    def check_reachable(self) -> bool:
        try:
            return self.session.get(
                f"{self.prometheus_url}/-/healthy", timeout=5
            ).status_code == 200
        except Exception:
            return False

    # ── Node metric scrape → node_telemetry ───────────────────────────────

    def scrape_nodes(self, ts: datetime.datetime) -> list[Point]:
        """
        Query every node_telemetry_* metric, group by node `id`,
        write one Point per node to the `node_telemetry` measurement.
        """
        # Accumulate all fields per node id
        by_node: dict[str, dict] = {}

        for metric_name in NODE_METRICS:
            field = _node_field(metric_name)
            for result in self._query(metric_name):
                labels = result["metric"]
                node_id = labels.get("id", "")
                if not node_id:
                    continue
                try:
                    value = float(result["value"][1])
                    if value != value:          # NaN guard
                        continue
                except (ValueError, IndexError):
                    continue

                if node_id not in by_node:
                    by_node[node_id] = {
                        "role":    labels.get("role", "unknown"),
                        "droplet": labels.get("droplet", "unknown"),
                        "rack":    labels.get("rack", "unknown"),
                        "instance":labels.get("instance", ""),
                    }
                by_node[node_id][field] = value

        points = []
        for node_id, data in by_node.items():
            p = (
                Point("node_telemetry")
                .tag("id",      node_id)
                .tag("role",    data["role"])
                .tag("droplet", data["droplet"])
                .tag("subnet",  data["rack"])       # map rack → subnet tag slot
                .tag("source",  "prometheus_real")
                .time(ts, WritePrecision.NS)
            )
            has_field = False
            for field in ("cpu_percent", "memory_percent",
                          "temperature_celsius", "power_watts"):
                v = data.get(field)
                if v is not None:
                    p = p.field(field, float(v))
                    has_field = True
            if "disk_iops" in data:
                p = p.field("disk_iops", int(data["disk_iops"]))
                has_field = True
            if has_field:
                points.append(p)

        return points

    # ── Edge metric scrape → edge_telemetry ───────────────────────────────

    def scrape_edges(self, ts: datetime.datetime) -> list[Point]:
        """
        Query every edge_telemetry_* metric, group by (source, target),
        write one Point per edge to the `edge_telemetry` measurement.
        """
        by_edge: dict[tuple, dict] = {}

        for metric_name in EDGE_METRICS:
            field = _edge_field(metric_name)
            for result in self._query(metric_name):
                labels = result["metric"]
                src = labels.get("source", "")
                tgt = labels.get("target", "")
                if not src or not tgt:
                    continue
                try:
                    value = float(result["value"][1])
                    if value != value:
                        continue
                except (ValueError, IndexError):
                    continue

                key = (src, tgt)
                if key not in by_edge:
                    by_edge[key] = {
                        "droplet": labels.get("droplet", "unknown"),
                        "rack":    labels.get("rack", "unknown"),
                    }
                by_edge[key][field] = value

        points = []
        for (src, tgt), data in by_edge.items():
            p = (
                Point("edge_telemetry")
                .tag("source",  src)
                .tag("target",  tgt)
                .tag("droplet", data["droplet"])
                .tag("source_tag", "prometheus_real")
                .time(ts, WritePrecision.NS)
            )
            has_field = False
            for field in ("latency_ms", "bandwidth_mbps", "packet_loss_percent"):
                v = data.get(field)
                if v is not None:
                    p = p.field(field, float(v))
                    has_field = True
            if has_field:
                points.append(p)

        return points

    # ── Write ──────────────────────────────────────────────────────────────

    def _flush(self, points: list, label: str):
        if not points:
            return
        try:
            self.write_api.write(
                bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points
            )
            logger.info(f"  ✓ {label}: {len(points)} points written")
        except Exception as exc:
            logger.error(f"InfluxDB write failed [{label}]: {exc}")

    # ── Public interface ───────────────────────────────────────────────────

    def run_once(self) -> dict:
        now = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"Scraping {self.prometheus_url} at {now.strftime('%H:%M:%S')} UTC …")

        node_pts = self.scrape_nodes(now)
        edge_pts = self.scrape_edges(now)

        self._flush(node_pts, "node_telemetry")
        self._flush(edge_pts, "edge_telemetry")

        return {"nodes": len(node_pts), "edges": len(edge_pts)}

    def run_continuous(self):
        print("=" * 60)
        print("  HPE Digital Twin — Prometheus → InfluxDB Bridge")
        print("=" * 60)
        print(f"  Prometheus  : {self.prometheus_url}")
        print(f"  InfluxDB    : {INFLUXDB_URL} / {INFLUXDB_BUCKET}")
        print(f"  Interval    : {self.scrape_interval}s")
        print(f"  Node metrics: {NODE_METRICS}")
        print(f"  Edge metrics: {EDGE_METRICS}")
        print("=" * 60)

        if not self.check_reachable():
            logger.error(f"Prometheus not reachable at {self.prometheus_url}")
            return

        # Log discovered targets
        try:
            r = self.session.get(
                f"{self.prometheus_url}/api/v1/targets", timeout=8
            )
            active = r.json().get("data", {}).get("activeTargets", [])
            logger.info(f"  {len(active)} active scrape targets:")
            for t in active:
                lbl = t.get("labels", {})
                logger.info(f"    • {lbl.get('job')} — {lbl.get('instance')} [{lbl.get('rack')}]")
        except Exception:
            pass

        while True:
            try:
                counts = self.run_once()
                logger.info(
                    f"  Cycle done — nodes:{counts['nodes']}  edges:{counts['edges']}"
                )
            except Exception as exc:
                logger.error(f"Scrape cycle error: {exc}", exc_info=True)
            time.sleep(self.scrape_interval)

    def close(self):
        self.influx.close()
        self.session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Prometheus mock-exporter metrics into InfluxDB"
    )
    parser.add_argument(
        "--prometheus-url",
        default=os.getenv("PROMETHEUS_URL", "http://168.144.91.25:9090"),
    )
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    bridge = PrometheusInfluxBridge(args.prometheus_url, args.interval)
    try:
        if args.once:
            counts = bridge.run_once()
            print(f"\nDone — node_telemetry: {counts['nodes']} points | "
                  f"edge_telemetry: {counts['edges']} points")
        else:
            bridge.run_continuous()
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
