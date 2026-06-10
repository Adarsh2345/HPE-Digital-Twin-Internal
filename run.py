#!/usr/bin/env python3
"""
run.py
Top-level entry point for the HPE Digital Twin Platform.
"""
import sys
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run")


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
    from core.validation.validator_engine import ValidatorEngine
    from core.graph.graph_serializer import graph_to_dict

    orchestrator.bootstrap()
    logger.info("Running first telemetry tick...")
    await orchestrator._tick()

    G = orchestrator.get_derived_graph()
    validator = ValidatorEngine()
    result = validator.validate(G)
    graph_data = graph_to_dict(G)

    print("\n" + "═" * 60)
    print("  HPE DIGITAL TWIN — DEMO REPORT")
    print("═" * 60)
    print(f"  Nodes: {len(graph_data.get('nodes', []))}")
    print(f"  Edges: {len(graph_data.get('edges', []))}")
    print(f"  Validation: {'✅ PASS' if result['allowed'] else '❌ FAIL'}")
    if result["reasons"]:
        print("  Violations:")
        for r in result["reasons"]:
            print(f"     • {r}")
    if result["warnings"]:
        print("  Warnings:")
        for w in result["warnings"]:
            print(f"     ⚠ {w}")
    print("═" * 60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--bootstrap":
        run_bootstrap_only()
    elif mode == "--demo":
        asyncio.run(run_demo())
    else:
        run_server()
