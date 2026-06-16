import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8001
print(f"[+] Launching Droplet-4 (Storage Router) ANOMALY Exporter on port {PORT}...")

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
    cpu  = gen_gauss(96.0, 2.0, 88.0, 100.0)
    mem  = gen_gauss(88.0, 5.0, 75.0, 98.0)
    iops = gen_gauss(1800.0, 250.0, 1200.0, 2500.0)
    pwr  = gen_gauss(540.0, 40.0, 450.0, 650.0)
    temp = gen_gauss(89.0, 5.0, 75.0, 102.0)

    lat, loss, bw = gen_gauss(410.0, 95.0, 200.0, 999.0), gen_gauss(19.5, 5.0, 8.0, 60.0), gen_gauss(12.0, 4.0, 1.0, 35.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    
    LATENCY_GAUGE.labels(source="storage-router", target="spine-router").set(lat)
    LOSS_GAUGE.labels(source="storage-router", target="spine-router").set(loss)
    BW_GAUGE.labels(source="storage-router", target="spine-router").set(bw)

    time.sleep(3)