"""
mock_exporter.py — Droplet-1 (droplet-1-tor1)
Nodes covered: server-1, server-2, router-1

Runs an HTTP server on port 9200.
Prometheus scrapes http://<droplet-1-ip>:9200/metrics every 15 seconds.
Generates Gaussian random metrics per node and serves them in Prometheus
text exposition format.
"""

import random
import time
from prometheus_client import start_http_server, Gauge, Counter

# ── Nodes on this droplet ────────────────────────────────────────────────────
NODES = [
    {"id": "server-1", "role": "compute-node"},
    {"id": "server-2", "role": "compute-node"},
    {"id": "router-1", "role": "tor-router"},
]

# Network interfaces per node — from infrastructure.yaml
NODE_INTERFACES = {
    "server-1": ["eth0"],
    "server-2": ["eth0"],
    "router-1": ["eth0", "eth1", "eth2"],
}

# Disk devices per node (only compute nodes have disks)
NODE_DISKS = {
    "server-1": ["sda"],
    "server-2": ["sda"],
}

# ── Gaussian parameters per role ─────────────────────────────────────────────
# (mean, sigma) — idle_ratio: fraction of CPU time idle (higher = less busy)
ROLE_PARAMS = {
    "compute-node": {
        "cpu_idle_ratio":  (0.55, 0.10),   # ~45% CPU used on average
        "mem_total":       4.29e10,         # 40 GB RAM (fixed hardware spec)
        "mem_avail_ratio": (0.40, 0.08),    # fraction of total RAM available
        "temp_celsius":    (44.0, 3.0),
        "power_watts":     (180.0, 20.0),
    },
    "tor-router": {
        "cpu_idle_ratio":  (0.75, 0.08),   # routers run lighter
        "mem_total":       8.59e9,          # 8 GB RAM
        "mem_avail_ratio": (0.60, 0.06),
        "temp_celsius":    (38.0, 2.5),
        "power_watts":     (80.0, 10.0),
    },
}

# ── Prometheus metric registry objects ───────────────────────────────────────
cpu_seconds  = Counter("node_cpu_seconds_total",
                       "CPU time spent per mode",
                       ["id", "cpu", "mode"])

mem_total    = Gauge("node_memory_MemTotal_bytes",
                     "Total RAM in bytes", ["id"])

mem_avail    = Gauge("node_memory_MemAvailable_bytes",
                     "Available RAM in bytes", ["id"])

temp         = Gauge("node_hwmon_temp_celsius",
                     "Core temperature in Celsius",
                     ["id", "chip", "sensor"])

power        = Gauge("node_power_watts",
                     "Power draw in watts", ["id"])

net_rx_bytes = Counter("node_network_receive_bytes_total",
                       "Network bytes received", ["id", "device"])

net_rx_drops = Counter("node_network_receive_drop_total",
                       "Packets dropped on receive", ["id", "device"])

disk_reads   = Counter("node_disk_reads_completed_total",
                       "Disk read operations completed", ["id", "device"])

disk_writes  = Counter("node_disk_writes_completed_total",
                       "Disk write operations completed", ["id", "device"])

disk_io_time = Counter("node_disk_io_time_seconds_total",
                       "Time spent on disk I/O", ["id", "device"])


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def update_metrics():
    """
    Called every 12 seconds.
    Generates fresh Gaussian values for every node and updates
    the Prometheus metric objects. Prometheus reads the latest
    values when it scrapes /metrics.
    """
    for node in NODES:
        nid    = node["id"]
        role   = node["role"]
        params = ROLE_PARAMS[role]

        # ── CPU ──────────────────────────────────────────────────────────────
        # Counters increment by 12 seconds worth of CPU time each tick.
        # This mirrors how real node-exporter accumulates CPU counters.
        idle_ratio = clamp(random.gauss(*params["cpu_idle_ratio"]), 0.05, 0.99)
        busy_ratio = 1.0 - idle_ratio
        cpu_seconds.labels(id=nid, cpu="0", mode="idle").inc(12 * idle_ratio)
        cpu_seconds.labels(id=nid, cpu="0", mode="user").inc(12 * busy_ratio * 0.70)
        cpu_seconds.labels(id=nid, cpu="0", mode="system").inc(12 * busy_ratio * 0.20)
        cpu_seconds.labels(id=nid, cpu="0", mode="iowait").inc(12 * busy_ratio * 0.10)

        # ── Memory ───────────────────────────────────────────────────────────
        mem_tot     = params["mem_total"]
        avail_ratio = clamp(random.gauss(*params["mem_avail_ratio"]), 0.10, 0.95)
        mem_total.labels(id=nid).set(mem_tot)
        mem_avail.labels(id=nid).set(mem_tot * avail_ratio)

        # ── Temperature ──────────────────────────────────────────────────────
        t = clamp(random.gauss(*params["temp_celsius"]), 25.0, 85.0)
        temp.labels(id=nid, chip="platform_coretemp_0", sensor="core_0").set(t)

        # ── Power ────────────────────────────────────────────────────────────
        p = clamp(random.gauss(*params["power_watts"]), 20.0, 400.0)
        power.labels(id=nid).set(p)

        # ── Network interfaces ────────────────────────────────────────────────
        for iface in NODE_INTERFACES.get(nid, []):
            rx_bytes = max(0, random.gauss(200e6, 50e6))   # ~200 MB per 12s tick
            drops    = max(0, int(random.gauss(0.5, 2.0)))
            net_rx_bytes.labels(id=nid, device=iface).inc(rx_bytes)
            net_rx_drops.labels(id=nid, device=iface).inc(drops)

        # ── Disk I/O ─────────────────────────────────────────────────────────
        for disk in NODE_DISKS.get(nid, []):
            r = max(0, int(random.gauss(800, 150)))
            w = max(0, int(random.gauss(400, 100)))
            disk_reads.labels(id=nid,  device=disk).inc(r)
            disk_writes.labels(id=nid, device=disk).inc(w)
            disk_io_time.labels(id=nid, device=disk).inc(max(0, random.gauss(0.8, 0.15)))


if __name__ == "__main__":
    start_http_server(9200)
    print("[droplet-1-tor1] Mock exporter running on port 9200")
    print("Nodes: server-1, server-2, router-1")
    while True:
        update_metrics()
        time.sleep(12)
