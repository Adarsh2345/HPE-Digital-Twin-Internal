import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8001
print(f"[+] Launching Droplet-1 (ToR-1 Router) ANOMALY Exporter on port {PORT}...")

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage')
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage')
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second')
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts')
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data')

LATENCY_GAUGE = Gauge('latency_ms', 'Network layer delay', ['source', 'target'])
LOSS_GAUGE = Gauge('packet_loss_percent', 'Network data integrity degradation', ['source', 'target'])
BW_GAUGE = Gauge('bandwidth_mbps', 'Network throughput allocation', ['source', 'target'])

def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))

start_http_server(PORT)

while True:
    cpu  = gen_gauss(94.5, 2.5, 85.0, 100.0)
    mem  = gen_gauss(91.0, 4.0, 80.0, 99.0)
    iops = gen_gauss(850.0, 120.0, 500.0, 1200.0)
    pwr  = gen_gauss(480.0, 35.0, 400.0, 550.0)
    temp = gen_gauss(84.5, 6.0, 70.0, 105.0)

    lat_1, loss_1, bw_1 = gen_gauss(340.0, 85.0, 150.0, 999.0), gen_gauss(14.5, 4.5, 5.0, 45.0), gen_gauss(22.0, 8.0, 2.0, 50.0)
    lat_2, loss_2, bw_2 = gen_gauss(180.0, 40.0, 90.0, 500.0), gen_gauss(8.2, 2.1, 3.0, 20.0), gen_gauss(110.0, 25.0, 40.0, 300.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    
    LATENCY_GAUGE.labels(source="server-1", target="router-1").set(lat_1)
    LOSS_GAUGE.labels(source="server-1", target="router-1").set(loss_1)
    BW_GAUGE.labels(source="server-1", target="router-1").set(bw_1)

    LATENCY_GAUGE.labels(source="router-1", target="spine-router").set(lat_2)
    LOSS_GAUGE.labels(source="router-1", target="spine-router").set(loss_2)
    BW_GAUGE.labels(source="router-1", target="spine-router").set(bw_2)

    time.sleep(3)