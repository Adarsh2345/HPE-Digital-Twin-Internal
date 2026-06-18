import copy
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from core.analytics.anomaly_detector import DeviceAnomalyDetector
from core.graph.topology_builder import TopologyBuilder
from core.parser.topology_loader import TopologyLoader
from core.parser.yaml_parser import YAMLParser
from core.telemetry.chaos_engine import ChaosEngine
from schema.models import TopologyValidationError
from schema.yaml_validator import load_and_validate
from simulation.audit import AuditStore
from simulation.blast_radius import compute_blast_radius
from simulation.engine import SimulationEngine
from simulation.models import Severity, normalize_request
from simulation.nlp_parser import parse_request
from simulation.report import render_html, render_pdf
from simulation.validators import validate_all_constraints

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "infrastructure" / "infrastructure.yaml"


def graph():
    parser = YAMLParser(str(YAML_PATH))
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


def test_current_yaml_validates_and_canonical_ids_are_unique():
    schema = load_and_validate(YAML_PATH)
    assert sum(len(records) for records in schema.containers.values()) == 26
    built = graph()
    assert built.number_of_nodes() == 26
    exporters = [node for node, data in built.nodes(data=True) if data["display_name"] == "node-exporter"]
    assert len(exporters) == 4
    assert len(set(exporters)) == 4


def test_invalid_link_is_structured(tmp_path):
    text = YAML_PATH.read_text().replace('target: "server-1"', 'target: "missing"', 1)
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(TopologyValidationError) as exc:
        load_and_validate(path)
    assert exc.value.errors[0]["code"] == "LINK_ENDPOINT_NOT_FOUND"
    assert exc.value.errors[0]["path"].startswith("links[")


def test_request_normalizer_rejects_missing_params():
    with pytest.raises(Exception):
        normalize_request({"action": "move_server", "params": {}})


def test_live_headroom_catches_static_pass_live_fail():
    candidate = graph()
    target = "droplet-1-tor1/server-1"
    candidate.nodes[target]["metrics"]["temperature_celsius"] = 90
    findings = validate_all_constraints(candidate, {target})
    assert any(v.code == "LIVE_THERMAL_DANGER" and v.severity == Severity.HARD_BLOCK for v in findings)


def test_projection_hard_block_denies_and_live_graph_is_unchanged():
    live = graph()
    before = copy.deepcopy(nx.node_link_data(live, edges="edges"))
    request = normalize_request({
        "action": "inject_network",
        "params": {
            "source_node": "router-1", "target_node": "server-1",
            "latency_ms": 149, "packet_loss_percent": .1,
        },
        "projection_steps": 2,
    })
    result = SimulationEngine().run(live, request)
    assert result.allowed is False
    assert any(v.projected and v.code == "NETWORK_LATENCY_EXCEEDED" for v in result.projected_violations)
    assert before == nx.node_link_data(live, edges="edges")


def test_blast_radius_excludes_failed_and_handles_cycle():
    candidate = nx.DiGraph()
    candidate.add_nodes_from([
        ("pdu", {"node_type": "pdu"}), ("server", {"node_type": "server"}),
        ("workload", {"node_type": "workload"}),
    ])
    candidate.add_edge("server", "pdu", edge_type="powered_by")
    candidate.add_edge("workload", "server", edge_type="hosted_on")
    candidate.add_edge("server", "workload", edge_type="depends_on")
    result = compute_blast_radius(candidate, "pdu")
    affected = {item for values in result.affected_by_type.values() for item in values}
    assert "pdu" not in affected
    assert {"server", "workload"} <= affected


def test_denied_placement_returns_hard_block_free_alternative():
    live = graph()
    for node_id, data in live.nodes(data=True):
        data["metrics"]["power_watts"] = 230 if data.get("droplet") == "droplet-1-tor1" else 20
    request = normalize_request({
        "action": "add_compute", "target_router_id": "router-1",
        "target_rack_id": "droplet-1-tor1", "node_id": "new-server",
        "max_power_w": 500, "projection_steps": 1,
    })
    result = SimulationEngine().run(live, request)
    assert not result.allowed
    assert result.alternatives
    assert all(item.target != "droplet-1-tor1" for item in result.alternatives)


def test_branch_anomaly_detector_flags_synthetic_outlier():
    detector = DeviceAnomalyDetector()
    rng = np.random.default_rng(seed=42)
    healthy = rng.normal(
        loc=[35, 45, 700, 180, 45],
        scale=[3, 4, 80, 20, 2],
        size=(200, 5),
    )
    chaos = rng.normal(
        loc=[95, 92, 5500, 450, 90],
        scale=[2, 2, 150, 20, 1],
        size=(200, 5),
    )
    detector._train_device("node-a", healthy, chaos)

    normal = detector.detect("node-a", {
        "cpu_percent": 36, "memory_percent": 44, "disk_iops": 720,
        "power_watts": 185, "temperature_celsius": 45,
    })
    anomalous = detector.detect("node-a", {
        "cpu_percent": 98, "memory_percent": 93, "disk_iops": 5800,
        "power_watts": 470, "temperature_celsius": 91,
    })
    assert normal["anomaly"] is False
    assert anomalous["anomaly"] is True
    assert anomalous["rf_confidence"] is not None
    assert anomalous["anomaly_reason"]


def test_report_html_escapes_and_pdf_generates():
    request = normalize_request({
        "action": "blast_radius_query", "failed_device_id": "spine-router",
        "request_text": "<script>alert(1)</script>",
    })
    result = SimulationEngine().run(graph(), request)
    html = render_html(result)
    assert "<script>" not in html
    assert "Current Violations" in html
    pdf = render_pdf(result)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_rule_parser_works_without_provider(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_PARSER", "false")
    request = parse_request("Add 2 DL360 servers to droplet-1-tor1 using router-1")
    assert request.action == "add_compute"
    assert request.quantity == 2
    assert request.parser_used == "rule_based"


@pytest.mark.parametrize(("text", "action"), [
    ("Remove server-1", "remove_node"),
    ("Move server-1 to router-2", "move_server"),
    ("Migrate server-1 to droplet-2-tor2 using router-2", "migrate_rack"),
    ("Set CPU on server-1 to 92 and memory to 88", "inject_compute"),
    ("Set latency from router-1 to server-1 to 160", "inject_network"),
    ("Set server-1 to 5000 IOPS", "inject_storage"),
    ("Show blast radius if spine-router fails", "blast_radius_query"),
])
def test_rule_parser_all_actions(text, action):
    assert parse_request(text).action == action


def test_parser_safe_fallback_and_gemini_failure(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_PARSER", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    request = parse_request("unstructured request with no known inventory")
    assert request.parser_used == "fallback"


def test_ambiguous_add_rack_request_falls_back_safely(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_PARSER", "false")
    request = parse_request("ADD rack to server 1")
    assert request.parser_used == "fallback"
    with pytest.raises(ValueError, match="could not be resolved safely"):
        SimulationEngine().run(graph(), request)


def test_rule_parser_normalizes_spoken_numeric_ids():
    request = parse_request("Move server 1 to router 2")
    assert request.action == "move_server"
    assert request.server_id == "server-1"
    assert request.target_router_id == "router-2"


def test_rule_parser_extracts_metrics_around_inventory_ids():
    compute = parse_request("Set CPU on server-1 to 92 and memory to 88")
    assert compute.action == "inject_compute"
    assert compute.cpu_pct == 92
    assert compute.memory_pct == 88

    network = parse_request("Set latency from router-1 to server-1 to 160")
    assert network.action == "inject_network"
    assert network.latency_ms == 160


def test_empty_target_identifiers_are_rejected():
    with pytest.raises(Exception):
        normalize_request({
            "action": "add_compute",
            "target_router_id": "",
            "target_rack_id": "",
        })


def test_gemini_retry_policy_and_25_flash_configuration(monkeypatch):
    from google.genai import types
    from simulation.nlp_parser import _generation_config, _http_options

    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "9")
    options = _http_options(types)
    assert options.timeout == 10_000
    assert options.retry_options.attempts == 3
    assert 503 in options.retry_options.http_status_codes
    assert 429 not in options.retry_options.http_status_codes

    config = _generation_config(types, "gemini-2.5-flash")
    assert config.thinking_config.thinking_budget == 0
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 512


def test_audit_persists_and_approval_never_executes(tmp_path):
    request = normalize_request({"action": "blast_radius_query", "failed_device_id": "spine-router"})
    result = SimulationEngine().run(graph(), request)
    store = AuditStore(tmp_path / "audit.sqlite")
    store.save(request, result, render_html(result))
    fetched = store.get(result.sim_id)
    assert fetched["result"]["sim_id"] == result.sim_id
    decided = store.decide(result.sim_id, "APPROVED", "operator")
    assert decided["approval_status"] == "APPROVED"


def test_targeted_chaos_changes_only_target():
    engine = ChaosEngine()
    snapshot = {
        "nodes": {"a": {"cpu_percent": 10}, "b": {"cpu_percent": 10}},
        "edges": {}, "generated_at": 1,
    }
    engine.enable(["a"], "compute_saturation")
    changed = engine.apply(snapshot, nx.DiGraph())
    assert changed["nodes"]["a"]["cpu_percent"] == 98
    assert changed["nodes"]["b"]["cpu_percent"] == 10
    engine.disable()
    assert engine.apply(snapshot, nx.DiGraph())["nodes"] == snapshot["nodes"]


@pytest.mark.parametrize("payload", [
    {"action": "move_server", "server_id": "server-1", "target_router_id": "router-2"},
    {"action": "remove_node", "node_id": "server-1"},
    {"action": "inject_storage", "node_id": "server-1", "disk_iops": 4500, "capacity_used_gb": 95},
    {"action": "migrate_rack", "node_id": "server-1", "target_rack_id": "droplet-2-tor2", "target_router_id": "router-2"},
])
def test_engine_supports_remaining_mutations(payload):
    result = SimulationEngine().run(graph(), normalize_request(payload))
    assert result.mutation_summary["success"]
    assert result.model_dump(mode="json")["action"] == payload["action"]


def test_validator_warning_and_capacity_boundaries():
    candidate = graph()
    node = "droplet-1-tor1/server-1"
    candidate.nodes[node]["metrics"].update(
        cpu_percent=81, memory_percent=86, temperature_celsius=76,
        disk_iops=3000, capacity_used_gb=86,
    )
    candidate.nodes[node]["capacity"].update(iops=4000, capacity_gb=100)
    findings = validate_all_constraints(candidate, {node})
    codes = {item.code for item in findings}
    assert {"LIVE_CPU_HIGH", "LIVE_MEMORY_HIGH", "LIVE_TEMP_HIGH", "STORAGE_IOPS_WARNING", "STORAGE_CAPACITY_WARNING"} <= codes


def test_validator_hard_compute_storage_and_bandwidth_boundaries():
    candidate = graph()
    node = "droplet-1-tor1/server-1"
    candidate.nodes[node]["metrics"].update(cpu_percent=95, memory_percent=95, disk_iops=4000, capacity_used_gb=101)
    candidate.nodes[node]["capacity"].update(iops=4000, capacity_gb=100)
    source = "droplet-1-tor1/router-1"
    candidate.edges[source, node]["metrics"]["bandwidth_mbps"] = 1001
    candidate.edges[source, node]["capacity"] = {"bandwidth_mbps": 1000}
    findings = validate_all_constraints(candidate, {node, source})
    codes = {item.code for item in findings if item.severity == Severity.HARD_BLOCK}
    assert {"LIVE_CPU_HIGH", "LIVE_MEMORY_HIGH", "STORAGE_IOPS_EXCEEDED", "STORAGE_CAPACITY_EXCEEDED", "BANDWIDTH_EXCEEDED"} <= codes


def test_blast_radius_unknown_and_truncation():
    candidate = nx.DiGraph()
    candidate.add_edges_from((f"n{i}", f"n{i+1}", {"edge_type": "network_link"}) for i in range(10))
    assert compute_blast_radius(candidate, "missing").affected_count == 0
    assert compute_blast_radius(candidate, "n0", max_nodes=3).truncated


def test_audit_rejects_invalid_transition(tmp_path):
    request = normalize_request({"action": "blast_radius_query", "failed_device_id": "spine-router"})
    result = SimulationEngine().run(graph(), request)
    store = AuditStore(tmp_path / "audit.sqlite")
    store.save(request, result)
    store.decide(result.sim_id, "REJECTED", "operator")
    with pytest.raises(ValueError):
        store.decide(result.sim_id, "APPROVED", "operator")
    assert store.list(limit=1)[0]["sim_id"] == result.sim_id
