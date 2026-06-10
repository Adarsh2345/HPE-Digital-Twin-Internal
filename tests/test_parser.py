import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser.yaml_parser import YAMLParser
from core.parser.topology_loader import TopologyLoader

YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "infrastructure", "infrastructure.yaml")


def test_yaml_loads():
    p = YAMLParser(YAML_PATH)
    raw = p.load()
    assert "site" in raw
    assert "droplets" in raw
    assert "containers" in raw
    assert "links" in raw


def test_node_count():
    p = YAMLParser(YAML_PATH)
    p.load()
    nodes = p.get_all_nodes()
    assert len(nodes) == 10


def test_links():
    p = YAMLParser(YAML_PATH)
    p.load()
    links = p.links
    assert len(links) == 6


def test_topology_loader():
    p = YAMLParser(YAML_PATH)
    p.load()
    loader = TopologyLoader(p)
    topo = loader.load_topology()
    assert len(topo["nodes"]) == 10
    assert len(topo["edges"]) == 6
    node_ids = [n["id"] for n in topo["nodes"]]
    assert "spine-router" in node_ids
    assert "server-1" in node_ids
