import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser.yaml_parser import YAMLParser
from core.parser.topology_loader import TopologyLoader
from core.graph.topology_builder import TopologyBuilder
from core.graph.derived_state_builder import DerivedStateBuilder, derive_node_state, derive_edge_state
from core.graph.graph_utils import path_exists

YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "infrastructure", "infrastructure.yaml")


def _build():
    p = YAMLParser(YAML_PATH)
    p.load()
    loader = TopologyLoader(p)
    topo = loader.load_topology()
    builder = TopologyBuilder()
    return builder.build(topo)


def test_graph_builds():
    G = _build()
    assert G.number_of_nodes() == 26
    assert G.number_of_edges() == 13
    assert sum(data["link_count"] for _, _, data in G.edges(data=True)) == 15


def test_path_server1_to_server3():
    G = _build()
    assert path_exists(G, "droplet-3-mgmt/spine-router", "droplet-1-tor1/server-1")


def test_derive_node_state_healthy():
    metrics = {"cpu_percent": 30, "memory_percent": 40, "power_watts": 200}
    assert derive_node_state(metrics) == "healthy"


def test_derive_node_state_critical():
    metrics = {"cpu_percent": 96, "memory_percent": 50, "power_watts": 200}
    assert derive_node_state(metrics) == "critical"


def test_derive_edge_state_active():
    metrics = {"latency_ms": 10, "packet_loss_percent": 0.01}
    assert derive_edge_state(metrics) == "active"


def test_derive_edge_state_down():
    metrics = {"latency_ms": 200, "packet_loss_percent": 0.1}
    assert derive_edge_state(metrics) == "down"


def test_derived_state_builder():
    G = _build()
    ds = DerivedStateBuilder()
    snapshot = {
        "nodes": {"droplet-1-tor1/server-1": {"cpu_percent": 35, "memory_percent": 45, "power_watts": 180}},
        "edges": {"droplet-1-tor1/router-1->droplet-1-tor1/server-1": {"latency_ms": 8, "packet_loss_percent": 0.01}},
    }
    derived = ds.build_derived_state(G, snapshot)
    assert derived.nodes["droplet-1-tor1/server-1"]["state"] == "healthy"
    assert derived.nodes["droplet-1-tor1/server-1"]["metrics"]["cpu_percent"] == 35
