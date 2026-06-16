import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8001
print(f"[+] Launching Droplet-3 (Management Node) ANOMALY Exporter on port {PORT}...")

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage')
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage')
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second')
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts')
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data')

def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))

start_http_server(PORT)

while True:
    cpu  = gen_gauss(91.0, 3.0, 80.0, 100.0)
    mem  = gen_gauss(97.0, 1.0, 92.0, 99.9)
    iops = gen_gauss(950.0, 90.0, 700.0, 1300.0)
    pwr  = gen_gauss(390.0, 20.0, 320.0, 450.0)
    temp = gen_gauss(79.0, 4.0, 65.0, 95.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    time.sleep(3)