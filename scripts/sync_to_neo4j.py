#!/usr/bin/env python3
"""
scripts/sync_to_neo4j.py
Bootstraps the infrastructure topology and pushes a live snapshot to Neo4j.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from core.orchestrator import orchestrator
from integrations.neo4j.neo4j_client import Neo4jClient
from core.graph.graph_serializer import graph_to_dict

def main():
    print("🔄 Initializing Digital Twin Orchestrator...")
    orchestrator.bootstrap()
    
    # Get the base graph structural map
    G = orchestrator.get_derived_graph()
    graph_dict = graph_to_dict(G)
    
    print(f"🚀 Connecting to Neo4j at {NEO4J_URI}...")
    neo4j_client = Neo4jClient(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    
    print("📤 Pushing topology nodes and structural states to Neo4j...")
    # Send a snapshot at tick 0
    neo4j_client.save_snapshot(graph_dict, tick=0)
    
    print("✅ Sync complete! Check your Neo4j Browser dashboard.")
    neo4j_client.close()

if __name__ == "__main__":
    main()
