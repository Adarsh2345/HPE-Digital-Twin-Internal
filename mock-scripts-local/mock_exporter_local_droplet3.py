"""
mock-scripts-local/mock_exporter_local_droplet3.py
Local per-device exporter for droplet-3-mgmt.
See mock_exporter_local_droplet1.py for rationale.
"""
import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 9102
DROPLET = "droplet-3-mgmt"
print(f"[+] Launching {DROPLET} LOCAL per-device Exporter on port {PORT}...")

DEVICES = [
    {"id": "netbox", "role": "infrastructure-docs"},
    {"id": "neo4j", "role": "graph-database"},
    {"id": "python-app", "role": "middleware"},
    {"id": "spine-router", "role": "spine-switch"},
    {"id": "prometheus", "role": "metrics-collector"},
    {"id": "grafana", "role": "metrics-dashboard"},
    {"id": "node-exporter", "role": "metrics-exporter"},
    {"id": "cadvisor", "role": "container-metrics"},
]

# spine-router uplinks all terminate elsewhere (router-1, router-2,
# storage-router), so this droplet "owns" all three spine edges.
EDGES = [
    ("spine-router", "router-1"),
    ("spine-router", "router-2"),
    ("spine-router", "storage-router"),
]

SERVICE_ROLES = {"infrastructure-docs", "graph-database", "middleware",
                  "metrics-collector", "metrics-dashboard"}
ROUTER_ROLES = {"spine-switch"}

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage', ['id', 'droplet', 'role'])
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage', ['id', 'droplet', 'role'])
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second', ['id', 'droplet', 'role'])
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts', ['id', 'droplet', 'role'])
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data', ['id', 'droplet', 'role'])

LATENCY_GAUGE = Gauge('latency_ms', 'Network layer delay', ['source', 'target'])
LOSS_GAUGE = Gauge('packet_loss_percent', 'Network data integrity degradation', ['source', 'target'])
BW_GAUGE = Gauge('bandwidth_mbps', 'Network throughput allocation', ['source', 'target'])


def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))


def device_metrics(role: str):
    if role in ROUTER_ROLES:
        return {
            "cpu": gen_gauss(12.0, 5.0, 2.0, 95.0),
            "mem": gen_gauss(45.0, 10.0, 20.0, 70.0),
            "iops": gen_gauss(800.0, 150.0, 200.0, 2000.0),
            "pwr": gen_gauss(180.0, 30.0, 100.0, 300.0),
            "temp": gen_gauss(45.0, 5.0, 25.0, 90.0),
        }
    return {
        "cpu": gen_gauss(33.0, 8.0, 24.5, 42.0),
        "mem": gen_gauss(45.0, 10.0, 20.0, 70.0),
        "iops": gen_gauss(800.0, 150.0, 200.0, 2000.0),
        "pwr": gen_gauss(180.0, 30.0, 100.0, 300.0),
        "temp": gen_gauss(45.0, 5.0, 25.0, 90.0),
    }


start_http_server(PORT)

while True:
    for dev in DEVICES:
        m = device_metrics(dev["role"])
        labels = (dev["id"], DROPLET, dev["role"])
        CPU_GAUGE.labels(*labels).set(m["cpu"])
        MEM_GAUGE.labels(*labels).set(m["mem"])
        IOPS_GAUGE.labels(*labels).set(m["iops"])
        POWER_GAUGE.labels(*labels).set(m["pwr"])
        TEMP_GAUGE.labels(*labels).set(m["temp"])

    for source, target in EDGES:
        lat = gen_gauss(12.0, 3.0, 1.0, 50.0)
        loss = gen_gauss(0.05, 0.02, 0.0, 1.0)
        bw = gen_gauss(800.0, 100.0, 400.0, 1000.0)
        LATENCY_GAUGE.labels(source=source, target=target).set(lat)
        LOSS_GAUGE.labels(source=source, target=target).set(loss)
        BW_GAUGE.labels(source=source, target=target).set(bw)

    time.sleep(3)