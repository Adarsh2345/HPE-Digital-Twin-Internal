#!/usr/bin/env python3
import random
import time
from prometheus_client import start_http_server, Gauge, Counter

NODES = [
    {"id": "spine-router", "role": "spine-switch"},
    {"id": "netbox",       "role": "management-service"},
    {"id": "neo4j",        "role": "management-service"},
    {"id": "python-app",   "role": "management-service"},
    {"id": "prometheus",   "role": "management-service"},
    {"id": "grafana",      "role": "management-service"},
]

ROLE_PARAMS = {
    "spine-switch": {
        "cpu_idle_ratio":  (0.80, 0.06),
        "temp_celsius":    (36.0, 2.0),
        "power_watts":     (120.0, 15.0),
    },
    "management-service": {
        "cpu_idle_ratio":  (0.70, 0.10),
        "temp_celsius":    (40.0, 3.0),
        "power_watts":     (60.0, 8.0),
    },
}

cpu_seconds = Counter("node_cpu_seconds_total", "CPU time spent per mode", ["id", "cpu", "mode"])
mem_total   = Gauge("node_memory_MemTotal_bytes", "Total RAM bytes", ["id"])
mem_avail   = Gauge("node_memory_MemAvailable_bytes", "Available RAM bytes", ["id"])
temp        = Gauge("node_hwmon_temp_celsius", "Core temperature Celsius", ["id", "chip", "sensor"])
power       = Gauge("node_power_watts", "Power usage Watts", ["id"])

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

        multiplier = 1.35 if (anomaly_active and role == "management-service") else 1.0

        idle_ratio = clamp(random.gauss(*params["cpu_idle_ratio"]) / multiplier, 0.01, 0.99)
        busy_ratio = 1.0 - idle_ratio
        cpu_seconds.labels(id=nid, cpu="0", mode="idle").inc(12 * idle_ratio)
        cpu_seconds.labels(id=nid, cpu="0", mode="user").inc(12 * busy_ratio * 0.70)
        cpu_seconds.labels(id=nid, cpu="0", mode="system").inc(12 * busy_ratio * 0.30)

        mem_tot = 1.72e10 if role == "spine-switch" else 4.29e9
        avail_ratio = clamp(random.gauss(0.50, 0.10) / multiplier, 0.05, 0.95)
        mem_total.labels(id=nid).set(mem_tot)
        mem_avail.labels(id=nid).set(mem_tot * avail_ratio)

        t = clamp(random.gauss(*params["temp_celsius"]) * multiplier, 25.0, 95.0)
        temp.labels(id=nid, chip="platform_coretemp_0", sensor="core_0").set(t)

        p = clamp(random.gauss(*params["power_watts"]) * multiplier, 20.0, 500.0)
        power.labels(id=nid).set(p)

if __name__ == "__main__":
    start_http_server(9200)
    print("[droplet-3-mgmt] Exporter running on port 9200")
    while True:
        try:
            update_metrics()
        except Exception:
            pass
        time.sleep(12)