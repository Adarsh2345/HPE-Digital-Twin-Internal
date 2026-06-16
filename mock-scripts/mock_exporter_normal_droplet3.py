import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8000
print(f"[+] Launching Droplet-3 (Management Node) NORMAL Exporter on port {PORT}...")

CPU_GAUGE = Gauge('cpu_percent', 'CPU consumption percentage')
MEM_GAUGE = Gauge('memory_percent', 'Memory consumption percentage')
IOPS_GAUGE = Gauge('disk_iops', 'Disk Input/Output operations per second')
POWER_GAUGE = Gauge('power_watts', 'Power consumption in Watts')
TEMP_GAUGE = Gauge('temperature_celsius', 'Thermal core data')

def gen_gauss(mean, std_dev, min_val, max_val):
    return max(min_val, min(max_val, random.gauss(mean, std_dev)))

start_http_server(PORT)

while True:
    cpu  = gen_gauss(25.0, 4.0, 10.0, 45.0)
    mem  = gen_gauss(65.0, 2.0, 55.0, 75.0)
    iops = gen_gauss(90.0, 10.0, 50.0, 150.0)
    pwr  = gen_gauss(180.0, 8.0, 150.0, 210.0)
    temp = gen_gauss(38.0, 1.5, 32.0, 45.0)

    CPU_GAUGE.set(cpu)
    MEM_GAUGE.set(mem)
    IOPS_GAUGE.set(iops)
    POWER_GAUGE.set(pwr)
    TEMP_GAUGE.set(temp)
    time.sleep(3)