import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8000
print(f"[+] Launching Droplet-2 (Server-1 Compute Node) NORMAL Exporter on port {PORT}...")

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage')
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage')
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second')
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts')
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data')

def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))

start_http_server(PORT)

while True:
    cpu  = gen_gauss(45.0, 6.0, 15.0, 75.0)
    mem  = gen_gauss(55.0, 4.0, 45.0, 70.0)
    iops = gen_gauss(210.0, 25.0, 100.0, 350.0)
    pwr  = gen_gauss(290.0, 15.0, 250.0, 340.0)
    temp = gen_gauss(46.0, 3.0, 38.0, 58.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    time.sleep(3)