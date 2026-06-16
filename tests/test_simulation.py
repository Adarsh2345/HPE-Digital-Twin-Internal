import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser.yaml_parser import YAMLParser
from core.parser.topology_loader import TopologyLoader
from core.graph.topology_builder import TopologyBuilder
from core.simulation.simulator import Simulator
from core.simulation.mutators import TopologyMutator
from core.simulation.clone_manager import CloneManager
from core.simulation.future_predictor import FuturePredictor

YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "infrastructure", "infrastructure.yaml")


def _build():
    p = YAMLParser(YAML_PATH)
    p.load()
    loader = TopologyLoader(p)
    topo = loader.load_topology()
    builder = TopologyBuilder()
    return builder.build(topo)


def test_rcu_clone_isolates():
    G = _build()
    cm = CloneManager()
    clone_id, clone = cm.create_clone(G)
    clone.remove_node("droplet-1-tor1/server-1")
    assert "droplet-1-tor1/server-1" in G.nodes
    assert "droplet-1-tor1/server-1" not in clone.nodes


def test_move_server():
    G = _build()
    cm = CloneManager()
    _, clone = cm.create_clone(G)
    mutator = TopologyMutator()
    result = mutator.move_server(clone, "droplet-1-tor1/server-1", "droplet-2-tor2/router-2")
    assert result["success"]
    assert clone.has_edge("droplet-2-tor2/router-2", "droplet-1-tor1/server-1")


def test_add_compute():
    G = _build()
    _, clone = CloneManager().create_clone(G)
    mutator = TopologyMutator()
    result = mutator.add_compute_node(clone, "server-99", "droplet-1-tor1/router-1", ip="10.10.1.99")
    assert result["success"]
    assert "server-99" in clone.nodes


def test_future_projection():
    G = _build()
    for n in G.nodes:
        G.nodes[n]["metrics"] = {"cpu_percent": 40, "memory_percent": 50, "disk_iops": 800, "power_watts": 180}
    for u, v in G.edges:
        G.edges[u, v]["metrics"] = {"latency_ms": 12, "packet_loss_percent": 0.05}
    predictor = FuturePredictor()
    projections = predictor.project(G, steps=3)
    assert len(projections) == 3
    for i in range(1, 3):
        assert projections[i]["nodes"].get("droplet-1-tor1/server-1", {}).get("cpu_percent", 0) >= \
               projections[i-1]["nodes"].get("droplet-1-tor1/server-1", {}).get("cpu_percent", 0)


def test_full_simulator():
    G = _build()
    for n in G.nodes:
        G.nodes[n]["metrics"] = {"cpu_percent": 35, "memory_percent": 45, "disk_iops": 700, "power_watts": 160}
    for u, v in G.edges:
        G.edges[u, v]["metrics"] = {"latency_ms": 10, "packet_loss_percent": 0.02}
    sim = Simulator()
    result = sim.run(G, "move_server", {"server_id": "droplet-1-tor1/server-1", "target_router": "droplet-2-tor2/router-2"})
    assert result["success"]
    assert "projected_graph" in result
    assert len(result["projections"]) == 3
