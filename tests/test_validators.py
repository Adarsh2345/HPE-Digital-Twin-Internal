import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import networkx as nx

from core.validation.validator_engine import ValidatorEngine
from core.validation.power_validator import PowerValidator
from core.validation.network_validator import NetworkValidator


def _make_graph(cpu=35, mem=45, power=180, latency=10, iops=800):
    G = nx.DiGraph()
    G.add_node("server-1", role="compute-node", subnet="subnet-1-tor1", droplet="droplet-1-tor1",
               metrics={"cpu_percent": cpu, "memory_percent": mem, "power_watts": power, "disk_iops": iops})
    G.add_node("router-1", role="tor-router", subnet="subnet-1-tor1", droplet="droplet-1-tor1",
               metrics={"cpu_percent": 10, "memory_percent": 20, "power_watts": 80, "disk_iops": 200})
    G.add_edge("router-1", "server-1", metrics={"latency_ms": latency, "packet_loss_percent": 0.01})
    return G


def test_healthy_graph_passes():
    G = _make_graph()
    engine = ValidatorEngine()
    result = engine.validate(G)
    assert result["allowed"] is True
    assert len(result["reasons"]) == 0


def test_high_cpu_triggers_violation():
    G = _make_graph(cpu=97)
    engine = ValidatorEngine()
    result = engine.validate(G)
    assert result["allowed"] is False
    assert any("Compute Overload" in r for r in result["reasons"])


def test_power_breach():
    G = nx.DiGraph()
    for i in range(10):
        G.add_node(f"s{i}", role="compute-node", subnet="subnet-1-tor1", droplet="d1",
                   metrics={"cpu_percent": 30, "memory_percent": 40, "power_watts": 200, "disk_iops": 500})
    pv = PowerValidator()
    result = pv.validate(G)
    assert result["passed"] is False


def test_network_sla_breach():
    G = _make_graph(latency=200)
    nv = NetworkValidator()
    result = nv.validate(G)
    assert result["passed"] is False
    assert any("SLA Breach" in v for v in result["violations"])


def test_healthy_network():
    G = _make_graph(latency=8)
    nv = NetworkValidator()
    result = nv.validate(G)
    assert result["passed"] is True
