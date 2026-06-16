#!/usr/bin/env python3
"""
scripts/inject_anomaly_windows.py

Injects labeled synthetic anomaly windows into InfluxDB alongside healthy
baseline data to build a supervised training dataset for anomaly detection
and the recommendation engine.

Writes to measurement: anomaly_training_data
  - Normal windows  → anomaly=false, anomaly_type=none
  - Anomaly windows → anomaly=true,  anomaly_type=<type>, severity=<level>

Anomaly types:
  cpu_spike          — runaway process / compute storm
  memory_pressure    — memory leak / large allocation
  disk_saturation    — IOPS near capacity limit
  thermal_anomaly    — cooling failure / high ambient temp
  network_saturation — bandwidth exhaustion / packet loss
  cascading_failure  — multi-metric degradation spreading across nodes

Usage:
  # Backfill 7 days of mixed normal + anomaly data
  python scripts/inject_anomaly_windows.py --days 7

  # Backfill with higher anomaly ratio for imbalanced datasets
  python scripts/inject_anomaly_windows.py --days 7 --anomaly-ratio 0.25

  # Inject a single live anomaly event right now (for demo/testing)
  python scripts/inject_anomaly_windows.py --live --anomaly-type cpu_spike

  # List available anomaly types
  python scripts/inject_anomaly_windows.py --list-types
"""
import sys
import os
import math
import random
import logging
import argparse
import datetime

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

INTERVAL_SECONDS = 12   # matches live tick rate and Prometheus scrape interval
BATCH_SIZE = 1000       # points per InfluxDB write call

# ── Topology nodes (from infrastructure.yaml) ──────────────────────────────
NODES = [
    {"id": "server-1",      "role": "compute-node",       "droplet": "droplet-1-tor1", "ip": "10.10.1.11"},
    {"id": "server-2",      "role": "compute-node",       "droplet": "droplet-1-tor1", "ip": "10.10.1.12"},
    {"id": "server-3",      "role": "compute-node",       "droplet": "droplet-2-tor2", "ip": "10.10.2.11"},
    {"id": "server-4",      "role": "compute-node",       "droplet": "droplet-2-tor2", "ip": "10.10.2.12"},
    {"id": "router-1",      "role": "tor-router",         "droplet": "droplet-1-tor1", "ip": "10.10.1.1"},
    {"id": "router-2",      "role": "tor-router",         "droplet": "droplet-2-tor2", "ip": "10.10.2.1"},
    {"id": "spine-router",  "role": "spine-switch",       "droplet": "droplet-3-mgmt", "ip": "10.10.3.1"},
    {"id": "storage-router","role": "storage-tor",        "droplet": "droplet-4-storage","ip": "10.10.4.1"},
    {"id": "array-ctrl-a",  "role": "storage-controller", "droplet": "droplet-4-storage","ip": "10.10.4.11"},
    {"id": "array-ctrl-b",  "role": "storage-controller", "droplet": "droplet-4-storage","ip": "10.10.4.12"},
    {"id": "obj-node-1",    "role": "object-storage",     "droplet": "droplet-4-storage","ip": "10.10.4.21"},
    {"id": "obj-node-2",    "role": "object-storage",     "droplet": "droplet-4-storage","ip": "10.10.4.22"},
    {"id": "obj-node-3",    "role": "object-storage",     "droplet": "droplet-4-storage","ip": "10.10.4.23"},
    {"id": "netbox",        "role": "infrastructure-docs","droplet": "droplet-3-mgmt", "ip": "10.10.3.11"},
    {"id": "neo4j",         "role": "graph-database",     "droplet": "droplet-3-mgmt", "ip": "10.10.3.12"},
    {"id": "python-app",    "role": "middleware",          "droplet": "droplet-3-mgmt", "ip": "10.10.3.13"},
]

NODE_BY_ID = {n["id"]: n for n in NODES}

# ── Anomaly profiles ────────────────────────────────────────────────────────
# Each profile defines which nodes can be affected, duration, severity,
# and the peak metric values to reach at intensity=1.0.
ANOMALY_PROFILES: dict[str, dict] = {
    "cpu_spike": {
        "description": "Runaway process or compute storm — CPU surges to 85-99%",
        "severity": "high",
        "duration_range_min": (5, 30),
        "shape": "spike",            # fast rise, sustained, fast drop
        "eligible_roles": {"compute-node", "tor-router", "spine-switch", "middleware"},
        "max_nodes": 3,
        "peak": {
            "cpu_percent":          (85.0, 99.0),
            "memory_percent":       (55.0, 78.0),
            "temperature_celsius":  (66.0, 82.0),
            "disk_iops":            (500,  1200),
            "network_rx_mbps":      (200.0, 600.0),
            "network_tx_mbps":      (180.0, 500.0),
        },
    },
    "memory_pressure": {
        "description": "Memory leak or large allocation — memory climbs to 90%+",
        "severity": "high",
        "duration_range_min": (15, 60),
        "shape": "gradual_rise",     # slow linear rise then slow drop
        "eligible_roles": {"compute-node", "graph-database", "middleware", "object-storage"},
        "max_nodes": 2,
        "peak": {
            "cpu_percent":          (40.0, 65.0),
            "memory_percent":       (88.0, 98.0),
            "temperature_celsius":  (52.0, 65.0),
            "disk_iops":            (800,  2000),
            "network_rx_mbps":      (50.0, 150.0),
            "network_tx_mbps":      (40.0, 120.0),
        },
    },
    "disk_saturation": {
        "description": "IOPS near capacity — disk queue depth overflows",
        "severity": "critical",
        "duration_range_min": (10, 45),
        "shape": "sustained",        # sudden jump, stays high, sudden drop
        "eligible_roles": {"compute-node", "storage-controller", "object-storage"},
        "max_nodes": 2,
        "peak": {
            "cpu_percent":          (55.0, 80.0),
            "memory_percent":       (60.0, 80.0),
            "temperature_celsius":  (55.0, 70.0),
            "disk_iops":            (3500, 5800),
            "network_rx_mbps":      (300.0, 900.0),
            "network_tx_mbps":      (250.0, 800.0),
        },
    },
    "thermal_anomaly": {
        "description": "Cooling failure or high ambient temperature — node overheating",
        "severity": "critical",
        "duration_range_min": (20, 90),
        "shape": "gradual_rise",
        "eligible_roles": {"compute-node", "storage-controller", "tor-router"},
        "max_nodes": 2,
        "peak": {
            "cpu_percent":          (45.0, 70.0),   # throttled
            "memory_percent":       (40.0, 65.0),
            "temperature_celsius":  (78.0, 92.0),
            "disk_iops":            (300,  800),
            "network_rx_mbps":      (50.0, 200.0),
            "network_tx_mbps":      (40.0, 180.0),
        },
    },
    "network_saturation": {
        "description": "Bandwidth exhaustion or microbursts — high latency and loss",
        "severity": "medium",
        "duration_range_min": (5, 25),
        "shape": "oscillating",      # alternates between high and medium
        "eligible_roles": {"tor-router", "spine-switch", "storage-tor"},
        "max_nodes": 2,
        "peak": {
            "cpu_percent":          (60.0, 85.0),
            "memory_percent":       (40.0, 65.0),
            "temperature_celsius":  (50.0, 65.0),
            "disk_iops":            (200,  600),
            "network_rx_mbps":      (850.0, 999.0),
            "network_tx_mbps":      (800.0, 990.0),
        },
    },
    "cascading_failure": {
        "description": "Multi-metric degradation spreading across linked nodes",
        "severity": "critical",
        "duration_range_min": (20, 60),
        "shape": "cascading",        # starts on 1 node, spreads over time
        "eligible_roles": {"compute-node", "tor-router", "spine-switch", "storage-controller"},
        "max_nodes": 5,
        "peak": {
            "cpu_percent":          (75.0, 97.0),
            "memory_percent":       (80.0, 96.0),
            "temperature_celsius":  (68.0, 85.0),
            "disk_iops":            (2500, 5000),
            "network_rx_mbps":      (700.0, 980.0),
            "network_tx_mbps":      (650.0, 950.0),
        },
    },
}

# ── Healthy baseline ranges (normal operating conditions) ──────────────────
HEALTHY_BASELINE = {
    "compute-node":       {"cpu": (24.5, 42.0), "mem": (30.0, 65.0), "iops": (200, 1500),  "temp": (38.0, 52.0), "rx": (20.0, 200.0),  "tx": (15.0, 160.0)},
    "tor-router":         {"cpu": (5.0,  20.0), "mem": (20.0, 40.0), "iops": (50,  200),   "temp": (35.0, 48.0), "rx": (100.0, 500.0), "tx": (90.0, 450.0)},
    "spine-switch":       {"cpu": (8.0,  25.0), "mem": (25.0, 45.0), "iops": (30,  150),   "temp": (36.0, 50.0), "rx": (200.0, 700.0), "tx": (180.0, 650.0)},
    "storage-tor":        {"cpu": (5.0,  18.0), "mem": (20.0, 38.0), "iops": (100, 400),   "temp": (35.0, 48.0), "rx": (150.0, 600.0), "tx": (140.0, 550.0)},
    "storage-controller": {"cpu": (20.0, 50.0), "mem": (40.0, 70.0), "iops": (500, 2500),  "temp": (42.0, 58.0), "rx": (100.0, 400.0), "tx": (90.0, 380.0)},
    "object-storage":     {"cpu": (15.0, 45.0), "mem": (35.0, 65.0), "iops": (300, 1800),  "temp": (40.0, 55.0), "rx": (80.0, 300.0),  "tx": (75.0, 280.0)},
    "graph-database":     {"cpu": (10.0, 35.0), "mem": (45.0, 75.0), "iops": (150, 800),   "temp": (38.0, 52.0), "rx": (20.0, 100.0),  "tx": (18.0, 90.0)},
    "middleware":         {"cpu": (15.0, 40.0), "mem": (35.0, 65.0), "iops": (100, 500),   "temp": (38.0, 52.0), "rx": (30.0, 120.0),  "tx": (25.0, 100.0)},
    "infrastructure-docs":{"cpu": (8.0,  25.0), "mem": (30.0, 55.0), "iops": (50,  200),   "temp": (36.0, 48.0), "rx": (10.0, 60.0),   "tx": (8.0, 50.0)},
    "metrics-collector":  {"cpu": (10.0, 30.0), "mem": (30.0, 55.0), "iops": (80,  300),   "temp": (36.0, 48.0), "rx": (20.0, 80.0),   "tx": (15.0, 70.0)},
    "metrics-dashboard":  {"cpu": (8.0,  22.0), "mem": (28.0, 50.0), "iops": (50,  200),   "temp": (35.0, 47.0), "rx": (10.0, 50.0),   "tx": (8.0, 45.0)},
}
_DEFAULT_BASELINE = {"cpu": (25.0, 45.0), "mem": (35.0, 60.0), "iops": (200, 1000), "temp": (38.0, 52.0), "rx": (20.0, 150.0), "tx": (15.0, 120.0)}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _gauss(lo: float, hi: float, skew: float = 0.5) -> float:
    """Gaussian sample within [lo, hi]; skew controls center (0=lo, 1=hi)."""
    mean = lo + (hi - lo) * skew
    std  = (hi - lo) / 6.0
    return max(lo, min(hi, random.gauss(mean, std)))


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b at position t ∈ [0, 1]."""
    return a + (b - a) * t


def _intensity_for_shape(shape: str, t: float, jitter: float = 0.05) -> float:
    """
    Return anomaly intensity in [0, 1] for time position t ∈ [0, 1].
    t=0 is start of anomaly window, t=1 is end.
    """
    j = random.uniform(-jitter, jitter)
    if shape == "spike":
        # fast rise (10%), sustained peak (80%), fast drop (10%)
        if t < 0.10:
            return _lerp(0.0, 1.0, t / 0.10) + j
        elif t < 0.90:
            return 1.0 + j
        else:
            return _lerp(1.0, 0.0, (t - 0.90) / 0.10) + j

    elif shape == "gradual_rise":
        # slow rise (40%), peak (20%), slow recovery (40%)
        if t < 0.40:
            return _lerp(0.0, 1.0, t / 0.40) + j
        elif t < 0.60:
            return 1.0 + j
        else:
            return _lerp(1.0, 0.0, (t - 0.60) / 0.40) + j

    elif shape == "sustained":
        # instant jump, stays high, instant drop
        if t < 0.05:
            return _lerp(0.0, 1.0, t / 0.05) + j
        elif t < 0.95:
            return 1.0 + j
        else:
            return _lerp(1.0, 0.0, (t - 0.95) / 0.05) + j

    elif shape == "oscillating":
        # oscillates between 0.4 and 1.0 with sine wave
        base = 0.7 + 0.3 * math.sin(t * math.pi * 8)
        return max(0.0, min(1.0, base + j))

    elif shape == "cascading":
        # similar to gradual_rise but applies to different nodes at different t offsets
        # (offset is handled in the caller)
        if t < 0.30:
            return _lerp(0.0, 1.0, t / 0.30) + j
        elif t < 0.70:
            return 1.0 + j
        else:
            return _lerp(1.0, 0.0, (t - 0.70) / 0.30) + j

    return 0.0


class AnomalyInjector:
    def __init__(self):
        self.client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
            timeout=60000,
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.org = INFLUXDB_ORG
        self.bucket = INFLUXDB_BUCKET

    # ── Metric generation ──────────────────────────────────────────────────

    def _healthy_metrics(self, node: dict) -> dict:
        b = HEALTHY_BASELINE.get(node["role"], _DEFAULT_BASELINE)
        return {
            "cpu_percent":          round(_gauss(*b["cpu"]),  2),
            "memory_percent":       round(_gauss(*b["mem"]),  2),
            "disk_iops":            int(_gauss(*b["iops"])),
            "temperature_celsius":  round(_gauss(*b["temp"]), 1),
            "network_rx_mbps":      round(_gauss(*b["rx"]),   1),
            "network_tx_mbps":      round(_gauss(*b["tx"]),   1),
            "power_watts":          round(_gauss(120.0, 280.0), 1),
        }

    def _anomaly_metrics(self, node: dict, profile: dict, intensity: float) -> dict:
        """Interpolate between healthy baseline and anomaly peak at given intensity."""
        b = HEALTHY_BASELINE.get(node["role"], _DEFAULT_BASELINE)
        pk = profile["peak"]

        def interpolate(healthy_range, peak_range, i):
            healthy_mid = (healthy_range[0] + healthy_range[1]) / 2
            peak_val = _gauss(*peak_range)
            return round(_lerp(healthy_mid, peak_val, i) + random.gauss(0, 0.5), 2)

        cpu  = interpolate(b["cpu"],  pk["cpu_percent"],         intensity)
        mem  = interpolate(b["mem"],  pk["memory_percent"],      intensity)
        temp = interpolate(b["temp"], pk["temperature_celsius"],  intensity)
        rx   = interpolate(b["rx"],   pk["network_rx_mbps"],     intensity)
        tx   = interpolate(b["tx"],   pk["network_tx_mbps"],     intensity)
        iops_lo, iops_hi = pk["disk_iops"]
        iops_peak = random.randint(iops_lo, iops_hi)
        iops_base = (b["iops"][0] + b["iops"][1]) / 2
        iops = int(_lerp(iops_base, iops_peak, intensity))

        return {
            "cpu_percent":         max(0.0, min(100.0, cpu)),
            "memory_percent":      max(0.0, min(100.0, mem)),
            "disk_iops":           max(0, iops),
            "temperature_celsius": max(20.0, min(95.0, temp)),
            "network_rx_mbps":     max(0.0, rx),
            "network_tx_mbps":     max(0.0, tx),
            "power_watts":         round(_gauss(120.0, 280.0) + intensity * 100, 1),
        }

    # ── Point builder ──────────────────────────────────────────────────────

    def _build_point(
        self,
        node: dict,
        metrics: dict,
        timestamp: datetime.datetime,
        is_anomaly: bool,
        anomaly_type: str,
        severity: str,
    ) -> Point:
        p = (
            Point("anomaly_training_data")
            .tag("node_id",      node["id"])
            .tag("role",         node["role"])
            .tag("droplet",      node["droplet"])
            .tag("anomaly",      "true" if is_anomaly else "false")
            .tag("anomaly_type", anomaly_type)
            .tag("severity",     severity)
            .time(timestamp, WritePrecision.NS)
        )
        for field, value in metrics.items():
            if isinstance(value, int):
                p = p.field(field, value)
            else:
                p = p.field(field, float(value))
        return p

    # ── Batch writer ───────────────────────────────────────────────────────

    def _flush_batch(self, points: list, label: str = ""):
        if not points:
            return
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=points)
        except Exception as exc:
            logger.error(f"InfluxDB write failed [{label}]: {exc}")

    # ── Anomaly window generator ───────────────────────────────────────────

    def _select_affected_nodes(self, profile: dict) -> list[dict]:
        eligible = [
            n for n in NODES if n["role"] in profile["eligible_roles"]
        ]
        if not eligible:
            return random.sample(NODES, 1)
        n = random.randint(1, min(profile["max_nodes"], len(eligible)))
        return random.sample(eligible, n)

    def _generate_anomaly_window(
        self,
        anomaly_type: str,
        start_time: datetime.datetime,
        duration_minutes: int,
    ) -> list[Point]:
        profile  = ANOMALY_PROFILES[anomaly_type]
        shape    = profile["shape"]
        severity = profile["severity"]
        affected = self._select_affected_nodes(profile)
        affected_ids = {n["id"] for n in affected}
        total_ticks = (duration_minutes * 60) // INTERVAL_SECONDS
        points = []

        for tick in range(total_ticks):
            ts = start_time + datetime.timedelta(seconds=tick * INTERVAL_SECONDS)
            t  = tick / max(total_ticks - 1, 1)   # normalised position in window [0,1]

            for node in NODES:
                if node["id"] in affected_ids:
                    # For cascading, nodes get delayed onset based on their position
                    if shape == "cascading":
                        node_idx = list(affected_ids).index(node["id"])
                        delay    = node_idx / len(affected_ids) * 0.4  # stagger up to 40% of window
                        t_adj    = max(0.0, t - delay) / (1.0 - delay) if delay < 1 else t
                        intensity = max(0.0, min(1.0, _intensity_for_shape(shape, t_adj)))
                    else:
                        intensity = max(0.0, min(1.0, _intensity_for_shape(shape, t)))

                    metrics = self._anomaly_metrics(node, profile, intensity)
                    is_anomaly = intensity > 0.15   # below 15% intensity looks healthy
                    points.append(self._build_point(
                        node, metrics, ts,
                        is_anomaly=is_anomaly,
                        anomaly_type=anomaly_type if is_anomaly else "none",
                        severity=severity if is_anomaly else "none",
                    ))
                else:
                    # Unaffected nodes get healthy metrics
                    metrics = self._healthy_metrics(node)
                    points.append(self._build_point(
                        node, metrics, ts,
                        is_anomaly=False,
                        anomaly_type="none",
                        severity="none",
                    ))

        return points

    def _generate_normal_window(
        self,
        start_time: datetime.datetime,
        duration_minutes: int,
    ) -> list[Point]:
        total_ticks = (duration_minutes * 60) // INTERVAL_SECONDS
        points = []
        for tick in range(total_ticks):
            ts = start_time + datetime.timedelta(seconds=tick * INTERVAL_SECONDS)
            for node in NODES:
                metrics = self._healthy_metrics(node)
                points.append(self._build_point(
                    node, metrics, ts,
                    is_anomaly=False,
                    anomaly_type="none",
                    severity="none",
                ))
        return points

    # ── Public: historical backfill ────────────────────────────────────────

    def inject_historical(self, days: int = 7, anomaly_ratio: float = 0.20):
        """
        Backfill `days` of mixed normal + anomaly data into InfluxDB.
        anomaly_ratio controls what fraction of time contains anomalies.
        """
        print("=" * 64)
        print("  HPE Digital Twin — Anomaly Training Data Injector")
        print("=" * 64)
        print(f"  Days to fill   : {days}")
        print(f"  Anomaly ratio  : {anomaly_ratio * 100:.0f}%")
        print(f"  Nodes          : {len(NODES)}")
        print(f"  Interval       : {INTERVAL_SECONDS}s")
        print(f"  Anomaly types  : {list(ANOMALY_PROFILES.keys())}")
        print("=" * 64)

        now       = datetime.datetime.now(datetime.timezone.utc)
        cursor    = now - datetime.timedelta(days=days)
        end_time  = now

        anomaly_types = list(ANOMALY_PROFILES.keys())
        total_points  = 0
        window_num    = 0
        batch: list   = []

        while cursor < end_time:
            window_num += 1
            is_anomaly_window = random.random() < anomaly_ratio

            if is_anomaly_window:
                a_type   = random.choice(anomaly_types)
                profile  = ANOMALY_PROFILES[a_type]
                lo, hi   = profile["duration_range_min"]
                duration = random.randint(lo, hi)
                label    = f"[ANOMALY:{a_type}] {duration}min"
                points   = self._generate_anomaly_window(a_type, cursor, duration)
            else:
                duration = random.randint(20, 60)   # normal windows: 20-60 min
                label    = f"[NORMAL] {duration}min"
                points   = self._generate_normal_window(cursor, duration)

            batch.extend(points)
            total_points += len(points)

            # Flush when batch is large enough
            if len(batch) >= BATCH_SIZE:
                self._flush_batch(batch, label=label)
                batch = []

            cursor += datetime.timedelta(minutes=duration)

            if window_num % 20 == 0:
                progress = (cursor - (now - datetime.timedelta(days=days))).total_seconds()
                total    = days * 86400
                pct      = min(100.0, progress / total * 100)
                logger.info(
                    f"  Progress: {pct:.1f}%  |  Windows: {window_num}  |  "
                    f"Points: {total_points:,}  |  {label}"
                )

        # flush remainder
        if batch:
            self._flush_batch(batch, "final-batch")

        print("\n" + "=" * 64)
        print(f"  ✅ Injection complete!")
        print(f"     Windows written : {window_num}")
        print(f"     Total points    : {total_points:,}")
        print(f"     Measurement     : anomaly_training_data")
        print("=" * 64)

    # ── Public: live single anomaly injection ──────────────────────────────

    def inject_live(self, anomaly_type: str, duration_minutes: int = None):
        """
        Inject a single anomaly window starting right now.
        Useful for testing the detection pipeline in real time.
        """
        if anomaly_type not in ANOMALY_PROFILES:
            print(f"Unknown anomaly type '{anomaly_type}'. Use --list-types to see options.")
            return

        profile = ANOMALY_PROFILES[anomaly_type]
        lo, hi  = profile["duration_range_min"]
        if duration_minutes is None:
            duration_minutes = random.randint(lo, hi)

        now = datetime.datetime.now(datetime.timezone.utc)
        print(f"\n  Injecting live anomaly: {anomaly_type}")
        print(f"  Description : {profile['description']}")
        print(f"  Duration    : {duration_minutes} minutes")
        print(f"  Severity    : {profile['severity']}")
        print(f"  Start time  : {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

        points = self._generate_anomaly_window(anomaly_type, now, duration_minutes)
        self._flush_batch(points, label=f"live:{anomaly_type}")

        anomaly_pts = sum(1 for p in points if "true" in str(p))
        print(f"  ✅ Written {len(points)} points ({duration_minutes} min of data) to InfluxDB")
        print(f"     Measurement: anomaly_training_data")
        print(f"     Tag anomaly=true covers {profile['severity']}-severity windows")

    def close(self):
        self.client.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inject labeled anomaly windows into InfluxDB for ML training"
    )
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--live",
        action="store_true",
        help="Inject a single anomaly event starting right now",
    )
    mode.add_argument(
        "--list-types",
        action="store_true",
        help="Print available anomaly types and exit",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days of historical data to backfill (default: 7)",
    )
    parser.add_argument(
        "--anomaly-ratio",
        type=float,
        default=0.20,
        help="Fraction of time windows that contain anomalies 0.0-1.0 (default: 0.20)",
    )
    parser.add_argument(
        "--anomaly-type",
        default=None,
        choices=list(ANOMALY_PROFILES.keys()),
        help="Anomaly type for --live mode (default: random)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Duration in minutes for --live mode (default: random from profile)",
    )
    args = parser.parse_args()

    if args.list_types:
        print("\nAvailable anomaly types:\n")
        for name, profile in ANOMALY_PROFILES.items():
            print(f"  {name:<22} [{profile['severity']:>8}]  {profile['description']}")
        print()
        return

    injector = AnomalyInjector()
    try:
        if args.live:
            a_type = args.anomaly_type or random.choice(list(ANOMALY_PROFILES.keys()))
            injector.inject_live(a_type, duration_minutes=args.duration)
        else:
            injector.inject_historical(
                days=args.days,
                anomaly_ratio=args.anomaly_ratio,
            )
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        injector.close()


if __name__ == "__main__":
    main()
