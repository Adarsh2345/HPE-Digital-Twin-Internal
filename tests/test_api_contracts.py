from pathlib import Path

from fastapi import HTTPException

from api.routes.impact import blast_radius
from api.routes.simulation import run_simulation
from core.graph.topology_builder import TopologyBuilder
from core.orchestrator import orchestrator
from core.parser.topology_loader import TopologyLoader
from core.parser.yaml_parser import YAMLParser


def graph():
    parser = YAMLParser(str(Path(__file__).resolve().parents[1] / "infrastructure" / "infrastructure.yaml"))
    parser.load()
    result = TopologyBuilder().build(TopologyLoader(parser).load_topology())
    for _, data in result.nodes(data=True):
        data["metrics"] = {
            "cpu_percent": 30, "memory_percent": 40, "power_watts": 100,
            "temperature_celsius": 45, "disk_iops": 500, "timestamp": 9999999999,
        }
    for _, _, data in result.edges(data=True):
        data["metrics"] = {"latency_ms": 10, "packet_loss_percent": .1}
    return result


def test_malformed_request_returns_structured_422():
    orchestrator.derived_graph = graph()
    try:
        run_simulation({"action": "move_server", "params": {}})
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail[0]["code"]
    else:
        raise AssertionError("malformed request was accepted")


def test_simulation_route_preserves_legacy_fields():
    orchestrator.derived_graph = graph()
    body = run_simulation({
        "action": "blast_radius_query",
        "params": {"failed_device_id": "spine-router"},
    })
    assert {
        "allowed", "verdict", "reasons", "warnings", "recommendations",
        "tier_results", "projected_graph", "clone_id",
    } <= set(body)


def test_blast_radius_endpoint_404():
    orchestrator.derived_graph = graph()
    try:
        blast_radius("unknown", 500)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown blast-radius target was accepted")
