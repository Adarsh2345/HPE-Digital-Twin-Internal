#!/usr/bin/env python3
"""
run.py
Top-level entry point for the HPE Digital Twin Platform.
Automatically ensures Docker core services (Redis, Neo4j) are running and fully active on startup.
"""
import sys
import asyncio
import logging
import subprocess
import os
import socket
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run")

def ensure_docker_services():
    """Starts Redis and Neo4j via docker-compose and blocks until healthchecks pass."""
    compose_path = os.path.join("docker", "docker-compose.yml")
    if not os.path.exists(compose_path):
        logger.warning(f"Docker Compose file not found at {compose_path}. Skipping auto-start.")
        return

    logger.info("🐳 Orchestrating Docker infrastructure layers (Redis + Neo4j)...")
    logger.info("⏳ Launching containers and waiting for engines to fully initialize...")
    try:
        # The '--wait' flag forces docker-compose to block until the healthcheck passes!
        subprocess.run(
            ["docker", "compose", "-f", compose_path, "up", "-d", "--wait"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logger.info("✅ Redis and Neo4j stack verified operational, healthy, and ready!")
    except Exception as e:
        logger.error(f"❌ Failed to spin up Docker services automatically: {e}")
        logger.warning("Ensure Docker Desktop/Daemon is running. Proceeding with application boot...")
def run_server():
    import uvicorn
    from config.settings import API_HOST, API_PORT, DEBUG
    logger.info(f"Starting API server on http://{API_HOST}:{API_PORT}")
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="info",
    )

def run_bootstrap_only():
    from core.orchestrator import orchestrator
    orchestrator.bootstrap()
    topo = orchestrator.get_topology_dict()
    logger.info(f"Bootstrap complete — {len(topo.get('nodes', []))} nodes loaded")

async def run_demo():
    from core.orchestrator import orchestrator
    from core.graph.graph_serializer import graph_to_dict

    orchestrator.bootstrap()
    logger.info("Running first telemetry tick...")
    await orchestrator._tick()

    G = orchestrator.get_derived_graph()
    graph_data = graph_to_dict(G)

    print("\n" + "═" * 60)
    print("  HPE DIGITAL TWIN — DEMO REPORT")
    print("═" * 60)
    print(f"  Nodes: {len(graph_data.get('nodes', []))}")
    print(f"  Edges: {len(graph_data.get('edges', []))}")
    print("═" * 60)

if __name__ == "__main__":
    # Intercept and run infrastructure setup first with readiness checks
    ensure_docker_services()

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--bootstrap":
        run_bootstrap_only()
    elif mode == "--demo":
        asyncio.run(run_demo())
    else:
        run_server()