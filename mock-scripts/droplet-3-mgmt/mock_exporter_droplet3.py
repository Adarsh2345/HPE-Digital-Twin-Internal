"""
mock_exporter.py — Droplet-3 (droplet-3-mgmt)
Nodes covered: spine-router, netbox, neo4j, python-app, prometheus, grafana

Runs an HTTP server on port 9200.
Prometheus scrapes http://localhost:9200/metrics (self-scrape) every 15 seconds.
Generates Gaussian random metrics per node and serves them in Prometheus
text exposition format.
"""

import random
import time
from prometheus_client import start_http_server, Gauge, Counter

# ── Nodes on this droplet ────────────────────────────────────────────────────
NODES = [
    {"id": "spine-router", "role": "spine-switch"},
    {"id": "netbox",       "role": "management-service"},
    {"id": "neo4j",        "role": "management-service"},
    {"id": "python-app",   "role": "management-service"},
    {"id": "prometheus",   "role": "management-service"},
    {"id": "grafana",      "role": "management-service"},
]

# Network interfaces per node — from infrastructure.yaml
NODE_INTERFACES = {
    "spine-router": ["eth0", "eth1", "eth2"],
    "netbox":       ["eth0"],
    "neo4j":        ["eth0"],
    "python-app":   ["eth0"],
    "prometheus":   ["eth0"],
    "grafana":      ["eth0"],
}

# Disk devices per node
# Management services write logs/data — model with a single sda disk
NODE_DISKS = {
    "neo4j":      ["sda"],   # graph database — active disk I/O
    "python-app": ["sda"],
    "prometheus": ["sda"],   # TSDB writes heavily to disk
}

# ── Gaussian parameters per role ─────────────────────────────────────────────
ROLE_PARAMS = {
    "spine-switch": {
        "cpu_idle_ratio":  (0.80, 0.06),   # spine switch — mostly forwarding, light CPU
        "mem_total":       1.72e10,         # 16 GB RAM
        "mem_avail_ratio": (0.65, 0.05),
        "temp_celsius":    (36.0, 2.0),
        "power_watts":     (120.0, 15.0),
    },
    "management-service": {
        "cpu_idle_ratio":  (0.70, 0.10),   # services vary in load
        "mem_total":       4.29e9,          # 4 GB RAM (mgmt droplet is s-1vcpu-2gb → model 4GB for containers)
        "mem_avail_ratio": (0.50, 0.10),
        "temp_celsius":    (40.0, 3.0),
        "power_watts":     (60.0, 8.0),
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
    for node in NODES:
        nid    = node["id"]
        role   = node["role"]
        params = ROLE_PARAMS[role]

        # ── CPU ──────────────────────────────────────────────────────────────
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
            rx_bytes = max(0, random.gauss(200e6, 50e6))
            drops    = max(0, int(random.gauss(0.5, 2.0)))
            net_rx_bytes.labels(id=nid, device=iface).inc(rx_bytes)
            net_rx_drops.labels(id=nid, device=iface).inc(drops)

        # ── Disk I/O ─────────────────────────────────────────────────────────
        for disk in NODE_DISKS.get(nid, []):
            r = max(0, int(random.gauss(600, 120)))
            w = max(0, int(random.gauss(300, 80)))
            disk_reads.labels(id=nid,  device=disk).inc(r)
            disk_writes.labels(id=nid, device=disk).inc(w)
            disk_io_time.labels(id=nid, device=disk).inc(max(0, random.gauss(0.6, 0.12)))


if __name__ == "__main__":
    start_http_server(9200)
    print("[droplet-3-mgmt] Mock exporter running on port 9200")
    print("Nodes: spine-router, netbox, neo4j, python-app, prometheus, grafana")
    while True:
        update_metrics()
        time.sleep(12)
