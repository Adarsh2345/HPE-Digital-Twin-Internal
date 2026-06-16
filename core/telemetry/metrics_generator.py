"""
core/telemetry/metrics_generator.py
Generates realistic Prometheus-style metrics using Gaussian (Normal) distribution.
Healthy state: CPU 24.5%–42%, chaos state: latency up to 320ms etc.
"""
import random
import time
from config import settings
from config.constants import NODE_ROLES


def _gaussian_clamp(mean: float, std: float, lo: float = 0.0, hi: float = 100.0) -> float:
    val = random.gauss(mean, std)
    return max(lo, min(hi, val))


class MetricsGenerator:
    def __init__(self, chaos_mode: bool = False):
        self.chaos_mode = chaos_mode

    def generate_node_metrics(self, node: dict) -> dict:
        role = node.get("role", "")
        if role in (NODE_ROLES["TOR_ROUTER"], NODE_ROLES["SPINE"]):
            return self._router_metrics()
        if role in (NODE_ROLES["NETBOX"], NODE_ROLES["NEO4J"], NODE_ROLES["MIDDLEWARE"]):
            return self._service_metrics()
        return self._compute_metrics()

    def generate_edge_metrics(self, source: str, target: str) -> dict:
        if self.chaos_mode:
            latency = _gaussian_clamp(
                settings.LATENCY_CHAOS_MEAN,
                settings.LATENCY_CHAOS_STD,
                lo=50.0,
                hi=settings.LATENCY_CHAOS_MAX,
            )
            packet_loss = _gaussian_clamp(
                settings.PACKET_LOSS_CHAOS_MEAN,
                settings.PACKET_LOSS_CHAOS_STD,
                lo=0.0,
                hi=20.0,
            )
            bandwidth_mbps = _gaussian_clamp(200, 80, lo=10.0, hi=1000.0)
        else:
            latency = _gaussian_clamp(
                settings.LATENCY_HEALTHY_MEAN,
                settings.LATENCY_HEALTHY_STD,
                lo=1.0,
                hi=50.0,
            )
            packet_loss = _gaussian_clamp(
                settings.PACKET_LOSS_HEALTHY_MEAN,
                settings.PACKET_LOSS_HEALTHY_STD,
                lo=0.0,
                hi=1.0,
            )
            bandwidth_mbps = _gaussian_clamp(800, 100, lo=400.0, hi=1000.0)

        return {
            "latency_ms": round(latency, 2),
            "packet_loss_percent": round(packet_loss, 3),
            "bandwidth_mbps": round(bandwidth_mbps, 1),
            "timestamp": time.time(),
        }

    def _compute_metrics(self) -> dict:
        if self.chaos_mode:
            cpu = _gaussian_clamp(settings.CPU_CHAOS_MEAN, settings.CPU_CHAOS_STD, lo=40.0, hi=100.0)
            mem = _gaussian_clamp(settings.MEMORY_CHAOS_MEAN, settings.MEMORY_CHAOS_STD, lo=50.0, hi=100.0)
            iops = _gaussian_clamp(settings.IOPS_CHAOS_MEAN, settings.IOPS_CHAOS_STD, lo=1000.0, hi=6000.0)
            power = _gaussian_clamp(settings.POWER_CHAOS_MEAN, settings.POWER_CHAOS_STD, lo=150.0, hi=500.0)
        else:
            cpu = _gaussian_clamp(settings.CPU_HEALTHY_MEAN, settings.CPU_HEALTHY_STD,
                                  lo=settings.CPU_HEALTHY_MIN, hi=settings.CPU_HEALTHY_MAX)
            mem = _gaussian_clamp(settings.MEMORY_HEALTHY_MEAN, settings.MEMORY_HEALTHY_STD, lo=20.0, hi=70.0)
            iops = _gaussian_clamp(settings.IOPS_HEALTHY_MEAN, settings.IOPS_HEALTHY_STD, lo=200.0, hi=2000.0)
            power = _gaussian_clamp(settings.POWER_PER_NODE_MEAN, settings.POWER_PER_NODE_STD, lo=100.0, hi=300.0)

        return {
            "cpu_percent": round(cpu, 2),
            "memory_percent": round(mem, 2),
            "disk_iops": round(iops),
            "power_watts": round(power, 1),
            "network_rx_mbps": round(_gaussian_clamp(120, 40, lo=10, hi=500), 1),
            "network_tx_mbps": round(_gaussian_clamp(80, 30, lo=5, hi=400), 1),
            "temperature_celsius": round(_gaussian_clamp(45 if not self.chaos_mode else 72, 5, lo=25, hi=90), 1),
            "timestamp": time.time(),
        }

    def _router_metrics(self) -> dict:
        base = self._compute_metrics()
        base["cpu_percent"] = round(_gaussian_clamp(
            12 if not self.chaos_mode else 55,
            5 if not self.chaos_mode else 15,
            lo=2, hi=95
        ), 2)
        base["routing_table_entries"] = random.randint(50, 500)
        base["bgp_sessions_active"] = random.randint(1, 8)
        return base

    def _service_metrics(self) -> dict:
        base = self._compute_metrics()
        base["request_rate_rps"] = round(_gaussian_clamp(
            50 if not self.chaos_mode else 200, 20, lo=5, hi=1000
        ), 1)
        base["error_rate_percent"] = round(_gaussian_clamp(
            0.1 if not self.chaos_mode else 5.0, 0.05, lo=0.0, hi=20.0
        ), 3)
        return base

    def generate_full_snapshot(self, nodes: list[dict], edges: list[dict]) -> dict:
        node_metrics = {}
        for node in nodes:
            node_metrics[node["id"]] = self.generate_node_metrics(node)

        edge_metrics = {}
        for edge in edges:
            key = f"{edge['source']}->{edge['target']}"
            edge_metrics[key] = self.generate_edge_metrics(edge["source"], edge["target"])

        return {
            "nodes": node_metrics,
            "edges": edge_metrics,
            "generated_at": time.time(),
            "chaos_mode": self.chaos_mode,
        }
