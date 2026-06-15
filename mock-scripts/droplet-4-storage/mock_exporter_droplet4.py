#!/usr/bin/env python3
import random
import time
from prometheus_client import start_http_server, Gauge, Counter

NODES = [
    {"id": "storage-router", "role": "storage-tor"},
    {"id": "array-ctrl-a",   "role": "storage-controller"},
    {"id": "array-ctrl-b",   "role": "storage-controller"},
    {"id": "obj-node-1",     "role": "object-storage"},
    {"id": "obj-node-2",     "role": "object-storage"},
    {"id": "obj-node-3",     "role": "object-storage"},
]

ROLE_PARAMS = {
    "storage-tor": {
        "cpu_idle_ratio":  (0.78, 0.07),
        "temp_celsius":    (37.0, 2.0),
        "power_watts":     (90.0, 12.0),
    },
    "storage-controller": {
        "cpu_idle_ratio":  (0.55, 0.12),
        "temp_celsius":    (46.0, 4.0),
        "power_watts":     (220.0, 25.0),
    },
    "object-storage": {
        "cpu_idle_ratio":  (0.60, 0.10),
        "temp_celsius":    (42.0, 3.0),
        "power_watts":     (150.0, 18.0),
    },
}

cpu_seconds  = Counter("node_cpu_seconds_total", "CPU time spent per mode", ["id", "cpu", "mode"])
mem_total    = Gauge("node_memory_MemTotal_bytes", "Total RAM bytes", ["id"])
mem_avail    = Gauge("node_memory_MemAvailable_bytes", "Available RAM bytes", ["id"])
temp         = Gauge("node_hwmon_temp_celsius", "Core temperature Celsius", ["id", "chip", "sensor"])
power        = Gauge("node_power_watts", "Power usage Watts", ["id"])
disk_reads   = Counter("node_disk_reads_completed_total", "Disk reads total", ["id", "device"])
disk_writes  = Counter("node_disk_writes_completed_total", "Disk writes total", ["id", "device"])
disk_io_time = Counter("node_disk_io_time_seconds_total", "Disk IO time total", ["id", "device"])

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def is_anomaly_window():
    current_time = time.localtime()
    return current_time.tm_hour % 2 == 0 and 0 <= current_time.tm_min < 5

def update_metrics():
    anomaly_active = is_anomaly_window()
    
    for node in NODES:
        nid    = node["id"]
        role   = node["role"]
        params = ROLE_PARAMS[role]

        multiplier = 1.45 if (anomaly_active and role == "storage-controller") else 1.0

        idle_ratio = clamp(random.gauss(*params["cpu_idle_ratio"]) / multiplier, 0.01, 0.99)
        busy_ratio = 1.0 - idle_ratio
        cpu_seconds.labels(id=nid, cpu="0", mode="idle").inc(12 * idle_ratio)
        cpu_seconds.labels(id=nid, cpu="0", mode="user").inc(12 * busy_ratio * 0.70)
        cpu_seconds.labels(id=nid, cpu="0", mode="system").inc(12 * busy_ratio * 0.30)

        mem_tot = 3.44e10 if role == "storage-controller" else 1.72e10
        avail_ratio = clamp(random.gauss(0.40, 0.08) / multiplier, 0.05, 0.95)
        mem_total.labels(id=nid).set(mem_tot)
        mem_avail.labels(id=nid).set(mem_tot * avail_ratio)

        t = clamp(random.gauss(*params["temp_celsius"]) * multiplier, 25.0, 95.0)
        temp.labels(id=nid, chip="platform_coretemp_0", sensor="core_0").set(t)

        p = clamp(random.gauss(*params["power_watts"]) * multiplier, 20.0, 500.0)
        power.labels(id=nid).set(p)

        if role in ["storage-controller", "object-storage"]:
            disk_reads.labels(id=nid, device="sda").inc(max(0, int(random.gauss(1500, 300) * multiplier)))
            disk_writes.labels(id=nid, device="sda").inc(max(0, int(random.gauss(1200, 200) * multiplier)))
            disk_io_time.labels(id=nid, device="sda").inc(max(0, random.gauss(0.6, 0.1) * multiplier))

if __name__ == "__main__":
    start_http_server(9200)
    print("[droplet-4-storage] Exporter running on port 9200")
    while True:
        try:
            update_metrics()
        except Exception:
            pass
        time.sleep(12)