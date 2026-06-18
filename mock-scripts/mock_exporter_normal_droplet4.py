import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8000
print(f"[+] Launching Droplet-4 (Storage Router) NORMAL Exporter on port {PORT}...")

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
    cpu  = gen_gauss(40.0, 6.0, 20.0, 65.0)
    mem  = gen_gauss(45.0, 4.0, 35.0, 60.0)
    iops = gen_gauss(450.0, 40.0, 300.0, 600.0)
    pwr  = gen_gauss(310.0, 15.0, 270.0, 360.0)
    temp = gen_gauss(45.0, 2.5, 38.0, 55.0)

    lat, loss, bw = gen_gauss(3.1, 0.5, 1.0, 6.0), gen_gauss(0.01, 0.005, 0.0, 0.04), gen_gauss(850.0, 50.0, 700.0, 980.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    
    LATENCY_GAUGE.labels(source="storage-router", target="spine-router").set(lat)
    LOSS_GAUGE.labels(source="storage-router", target="spine-router").set(loss)
    BW_GAUGE.labels(source="storage-router", target="spine-router").set(bw)

    time.sleep(3)