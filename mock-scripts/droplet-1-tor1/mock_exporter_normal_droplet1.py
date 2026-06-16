import time
import random
from prometheus_client import start_http_server, Gauge

PORT = 8000
print(f"[+] Launching Droplet-1 (ToR-1 Router) NORMAL Exporter on port {PORT}...")

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
    cpu  = gen_gauss(35.0, 5.0, 10.0, 60.0)
    mem  = gen_gauss(50.0, 3.0, 40.0, 65.0)
    iops = gen_gauss(120.0, 15.0, 80.0, 200.0)
    pwr  = gen_gauss(240.0, 10.0, 210.0, 280.0)
    temp = gen_gauss(42.0, 2.0, 35.0, 50.0)

    lat_1, loss_1, bw_1 = gen_gauss(4.2, 0.8, 1.5, 8.0), gen_gauss(0.02, 0.01, 0.0, 0.1), gen_gauss(650.0, 40.0, 500.0, 800.0)
    lat_2, loss_2, bw_2 = gen_gauss(2.1, 0.4, 1.0, 4.5), gen_gauss(0.01, 0.005, 0.0, 0.05), gen_gauss(920.0, 30.0, 850.0, 1000.0)

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