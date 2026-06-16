#!/usr/bin/env python3
"""
scripts/bootstrap.py
One-shot bootstrap: parse YAML, build graph, print summary.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser.yaml_parser import YAMLParser
from core.parser.topology_loader import TopologyLoader
from core.graph.topology_builder import TopologyBuilder
from config.settings import INFRASTRUCTURE_YAML


def main():
    print("═" * 50)
    print("  HPE Digital Twin — Bootstrap")
    print("═" * 50)

    parser = YAMLParser(INFRASTRUCTURE_YAML)
    parser.load()
    print(f"  Site: {parser.site.get('name')} ({parser.site.get('region')})")
    print(f"  Droplets: {len(parser.droplets)}")

    loader = TopologyLoader(parser)
    topo = loader.load_topology()

    builder = TopologyBuilder()
    G = builder.build(topo)

    print(f"\n  Graph Nodes ({G.number_of_nodes()}):")
    for n in G.nodes:
        node = G.nodes[n]
        print(f"    {n:20s} | role={node.get('role','?'):20s} | ip={node.get('ip','')}")

    print("═" * 50)
    print("  Bootstrap complete ✓")


if __name__ == "__main__":
    main()
