SCENARIOS = {
    "thermal_spike": {"cpu_pct": 55, "memory_pct": 50, "temp_c": 95, "power_w": 360, "net_io_mbps": 180},
    "power_surge": {"cpu_pct": 60, "memory_pct": 55, "temp_c": 65, "power_w": 900, "net_io_mbps": 200},
    "memory_leak": {"cpu_pct": 45, "memory_pct": 99, "temp_c": 55, "power_w": 260, "net_io_mbps": 100},
    "cpu_runaway": {"cpu_pct": 100, "memory_pct": 65, "temp_c": 82, "power_w": 500, "net_io_mbps": 150},
    "network_anomaly": {"cpu_pct": 35, "memory_pct": 45, "temp_c": 45, "power_w": 180, "net_io_mbps": 5000},
}
