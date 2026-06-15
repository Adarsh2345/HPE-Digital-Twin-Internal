"""
mock_exporter.py — Droplet-4 (droplet-4-storage)
Nodes covered: storage-router, array-ctrl-a, array-ctrl-b,
               obj-node-1, obj-node-2, obj-node-3

Runs an HTTP server on port 9200.
Prometheus scrapes http://<droplet-4-ip>:9200/metrics every 15 seconds.
Generates Gaussian random metrics per node and serves them in Prometheus
text exposition format.

Storage controllers emit SAS + NVMe disk metrics matching the docx
sample payloads exactly. Object nodes emit S3 traffic patterns.
"""

import random
import time
from prometheus_client import start_http_server, Gauge, Counter

# ── Nodes on this droplet ────────────────────────────────────────────────────
NODES = [
    {"id": "storage-router", "role": "storage-tor"},
    {"id": "array-ctrl-a",   "role": "storage-controller"},
    {"id": "array-ctrl-b",   "role": "storage-controller"},
    {"id": "obj-node-1",     "role": "object-storage"},
    {"id": "obj-node-2",     "role": "object-storage"},
    {"id": "obj-node-3",     "role": "object-storage"},
]

# Network interfaces per node — from infrastructure.yaml
# storage-router has 8 interfaces (eth0–eth7) as declared in YAML
NODE_INTERFACES = {
    "storage-router": ["eth0", "eth1", "eth2", "eth3", "eth4", "eth5", "eth6", "eth7"],
    "array-ctrl-a":   ["eth0", "eth1"],   # dual host ports (25gbase-t)
    "array-ctrl-b":   ["eth0", "eth1"],   # dual host ports (25gbase-t)
    "obj-node-1":     ["eth0"],            # 10gbase-t data port
    "obj-node-2":     ["eth0"],
    "obj-node-3":     ["eth0"],
}

# Disk devices per node
# Controllers: both NVMe (fast block pool) and SAS (backend shelf) — matches docx exactly
# Object nodes: local disk for erasure-coded object data
NODE_DISKS = {
    "array-ctrl-a": [("nvme0n1", "nvme"), ("sas0", "sas")],
    "array-ctrl-b": [("nvme0n1", "nvme"), ("sas0", "sas")],
    "obj-node-1":   [("sda",     "hdd")],
    "obj-node-2":   [("sda",     "hdd")],
    "obj-node-3":   [("sda",     "hdd")],
}

# ── Gaussian parameters per role ─────────────────────────────────────────────
ROLE_PARAMS = {
    "storage-tor": {
        "cpu_idle_ratio":  (0.78, 0.07),
        "mem_total":       8.59e9,          # 8 GB
        "mem_avail_ratio": (0.62, 0.06),
        "temp_celsius":    (37.0, 2.0),
        "power_watts":     (90.0, 12.0),
    },
    "storage-controller": {
        "cpu_idle_ratio":  (0.55, 0.12),   # controllers work harder
        "mem_total":       3.44e10,         # 32 GB — controllers are memory-heavy
        "mem_avail_ratio": (0.35, 0.10),
        "temp_celsius":    (46.0, 4.0),
        "power_watts":     (220.0, 25.0),
    },
    "object-storage": {
        "cpu_idle_ratio":  (0.60, 0.10),
        "mem_total":       1.72e10,         # 16 GB
        "mem_avail_ratio": (0.40, 0.08),
        "temp_celsius":    (42.0, 3.0),
        "power_watts":     (150.0, 18.0),
    },
}

# Disk IOPS parameters by device type
# (reads_mean, reads_sigma, writes_mean, writes_sigma, io_time_mean, io_time_sigma)
DISK_IOPS_PARAMS = {
    "nvme": (5000, 800,  2500, 500,  1.2, 0.20),   # fast NVMe pool
    "sas":  (1200, 200,   800, 150,  2.5, 0.40),   # SAS backend shelves
    "hdd":  ( 600, 120,   350,  80,  3.8, 0.60),   # spinning disk in MinIO nodes
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
        # Storage nodes push higher traffic — controllers at 25GbE, objects at 10GbE
        for iface in NODE_INTERFACES.get(nid, []):
            if role == "storage-controller":
                rx_bytes = max(0, random.gauss(1.5e9, 300e6))  # ~1.5 GB/tick on 25GbE
            elif role == "object-storage":
                rx_bytes = max(0, random.gauss(600e6, 100e6))   # ~600 MB/tick on 10GbE
            else:
                rx_bytes = max(0, random.gauss(200e6, 50e6))    # storage-tor general
            drops = max(0, int(random.gauss(0.2, 1.0)))         # storage fabric is clean
            net_rx_bytes.labels(id=nid, device=iface).inc(rx_bytes)
            net_rx_drops.labels(id=nid, device=iface).inc(drops)

        # ── Disk I/O ─────────────────────────────────────────────────────────
        # NODE_DISKS entries are tuples: (device_name, device_type)
        for disk_name, disk_type in NODE_DISKS.get(nid, []):
            rm, rs, wm, ws, tm, ts = DISK_IOPS_PARAMS[disk_type]
            r = max(0, int(random.gauss(rm, rs)))
            w = max(0, int(random.gauss(wm, ws)))
            io_t = max(0, random.gauss(tm, ts))
            disk_reads.labels(id=nid,  device=disk_name).inc(r)
            disk_writes.labels(id=nid, device=disk_name).inc(w)
            disk_io_time.labels(id=nid, device=disk_name).inc(io_t)


if __name__ == "__main__":
    start_http_server(9200)
    print("[droplet-4-storage] Mock exporter running on port 9200")
    print("Nodes: storage-router, array-ctrl-a, array-ctrl-b, obj-node-1, obj-node-2, obj-node-3")
    while True:
        update_metrics()
        time.sleep(12)
