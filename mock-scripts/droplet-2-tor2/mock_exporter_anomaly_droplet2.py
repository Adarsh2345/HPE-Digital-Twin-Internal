import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8001
print(f"[+] Launching Droplet-2 (Server-1 Compute Node) ANOMALY Exporter on port {PORT}...")

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage')
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage')
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second')
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts')
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data')

def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))

start_http_server(PORT)

while True:
    cpu  = gen_gauss(98.2, 1.1, 90.0, 100.0)
    mem  = gen_gauss(96.5, 2.0, 88.0, 99.5)
    iops = gen_gauss(1400.0, 180.0, 900.0, 2000.0)
    pwr  = gen_gauss(580.0, 45.0, 480.0, 680.0)
    temp = gen_gauss(92.0, 4.0, 80.0, 110.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    time.sleep(3)