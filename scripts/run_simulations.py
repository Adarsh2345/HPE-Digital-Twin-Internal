#!/usr/bin/env python3
"""
scripts/run_simulations.py
Standalone CLI runner for all simulation scenarios.

Runs every scenario type against the live graph without needing the
HTTP server. Engineers can execute this directly to validate changes.

Usage:
    python scripts/run_simulations.py                    # run all scenarios
    python scripts/run_simulations.py --scenario compute # run one category
    python scripts/run_simulations.py --list             # list all scenarios

Categories: topology | compute | network | storage | all (default)
"""
import sys
import os
import asyncio
import argparse
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import orchestrator
from core.simulation.simulator import Simulator
from core.validation.validator_engine import ValidatorEngine
from core.recommendations.recommendation_engine import RecommendationEngine
from core.graph.graph_serializer import dict_to_graph

# ── Colour helpers ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def pass_label(): return f"{GREEN}PASS ✅{RESET}"
def fail_label(): return f"{RED}FAIL ❌{RESET}"
def warn_label(): return f"{YELLOW}WARN ⚠{RESET}"

# ── All simulation scenarios ────────────────────────────────────────────────
ALL_SCENARIOS = [

    # ── Topology ────────────────────────────────────────────────────────────
    {
        "id": "move_server_1_to_tor2",
        "category": "topology",
        "label": "Move server-1 from ToR1 to ToR2",
        "description": "Validates power, rack U-space, and SLA on target subnet after migration.",
        "action": "move_server",
        "params": {"server_id": "server-1", "target_router": "router-2"},
        "projection_steps": 3,
    },
    {
        "id": "add_compute_server5",
        "category": "topology",
        "label": "Add new compute blade server-5 under ToR1",
        "description": "Checks rack U-space (+1U) and power envelope (+~180W) on subnet-1-tor1.",
        "action": "add_compute",
        "params": {"node_id": "server-5", "router_id": "router-1", "ip": "10.10.1.13"},
        "projection_steps": 3,
    },
    {
        "id": "add_compute_server6_tor2",
        "category": "topology",
        "label": "Add new compute blade server-6 under ToR2",
        "description": "Validates second subnet capacity before provisioning.",
        "action": "add_compute",
        "params": {"node_id": "server-6", "router_id": "router-2", "ip": "10.10.2.13"},
        "projection_steps": 3,
    },
    {
        "id": "remove_server4",
        "category": "topology",
        "label": "Decommission server-4",
        "description": "Validates remaining compute capacity after blade removal.",
        "action": "remove_node",
        "params": {"node_id": "server-4"},
        "projection_steps": 3,
    },
    {
        "id": "migrate_rack_server2",
        "category": "topology",
        "label": "Rack migration: server-2 to droplet-2-tor2",
        "description": "Full rack migration — updates droplet tag and rewires ToR edge.",
        "action": "migrate_rack",
        "params": {
            "node_id": "server-2",
            "target_droplet": "droplet-2-tor2",
            "target_router": "router-2",
        },
        "projection_steps": 3,
    },

    # ── Compute ─────────────────────────────────────────────────────────────
    {
        "id": "inject_cpu_warning",
        "category": "compute",
        "label": "CPU warning-level stress on server-1 (60%)",
        "description": "CPU in warning band (70-85% window under projection). Expects clean pass with notice flags.",
        "action": "inject_compute",
        "params": {
            "node_id": "server-1",
            "cpu_percent": 60.0,
            "memory_percent": 55.0,
            "power_watts": 220.0,
        },
        "projection_steps": 3,
    },
    {
        "id": "inject_cpu_critical",
        "category": "compute",
        "label": "CPU critical breach on server-1 (96%)",
        "description": "CPU above 95% limit. Expect hard compute violation + remediation.",
        "action": "inject_compute",
        "params": {
            "node_id": "server-1",
            "cpu_percent": 96.0,
            "memory_percent": 60.0,
            "power_watts": 240.0,
        },
        "projection_steps": 5,
    },
    {
        "id": "inject_memory_critical",
        "category": "compute",
        "label": "Memory critical breach on server-2 (96%)",
        "description": "Memory above 95% limit — simulates in-memory DB or VM ballooning.",
        "action": "inject_compute",
        "params": {
            "node_id": "server-2",
            "cpu_percent": 45.0,
            "memory_percent": 96.0,
            "power_watts": 200.0,
        },
        "projection_steps": 5,
    },
    {
        "id": "inject_power_breach",
        "category": "compute",
        "label": "Power envelope breach — high-draw workload on server-3 (420W)",
        "description": "Single-node high power draw that pushes subnet over 1400W total.",
        "action": "inject_compute",
        "params": {
            "node_id": "server-3",
            "cpu_percent": 85.0,
            "memory_percent": 70.0,
            "power_watts": 420.0,
        },
        "projection_steps": 3,
    },
    {
        "id": "inject_compute_future_breach",
        "category": "compute",
        "label": "Near-limit CPU that breaches on projected step 3 (88%)",
        "description": "CPU starts at 88% — clean now but projects past 95% in 2 steps (×1.05/step).",
        "action": "inject_compute",
        "params": {
            "node_id": "server-1",
            "cpu_percent": 88.0,
            "memory_percent": 50.0,
            "power_watts": 200.0,
        },
        "projection_steps": 5,
    },

    # ── Network ─────────────────────────────────────────────────────────────
    {
        "id": "inject_latency_warning",
        "category": "network",
        "label": "Network latency warning on spine->router-1 (120ms)",
        "description": "Latency in warning band (100-150ms). No SLA violation yet.",
        "action": "inject_network",
        "params": {
            "source_node": "spine-router",
            "target_node": "router-1",
            "latency_ms": 120.0,
            "packet_loss_percent": 0.5,
        },
        "projection_steps": 3,
    },
    {
        "id": "inject_latency_sla_breach",
        "category": "network",
        "label": "Network SLA breach on spine->router-1 (160ms)",
        "description": "Latency above 150ms SLA hard limit. Expect BGP path recommendation.",
        "action": "inject_network",
        "params": {
            "source_node": "spine-router",
            "target_node": "router-1",
            "latency_ms": 160.0,
            "packet_loss_percent": 1.0,
        },
        "projection_steps": 3,
    },
    {
        "id": "inject_packet_loss_breach",
        "category": "network",
        "label": "Packet loss breach on router-2->server-3 (7%)",
        "description": "Packet loss above 5% threshold — simulates NIC flap or MTU mismatch.",
        "action": "inject_network",
        "params": {
            "source_node": "router-2",
            "target_node": "server-3",
            "latency_ms": 25.0,
            "packet_loss_percent": 7.0,
        },
        "projection_steps": 3,
    },
    {
        "id": "inject_combined_network_failure",
        "category": "network",
        "label": "Combined latency + packet loss (200ms, 8%) on spine->router-2",
        "description": "Both SLA and packet loss breached simultaneously on spine uplink.",
        "action": "inject_network",
        "params": {
            "source_node": "spine-router",
            "target_node": "router-2",
            "latency_ms": 200.0,
            "packet_loss_percent": 8.0,
        },
        "projection_steps": 5,
    },

    # ── Storage ─────────────────────────────────────────────────────────────
    {
        "id": "inject_iops_warning",
        "category": "storage",
        "label": "IOPS warning on server-1 (3100 IOPS)",
        "description": "IOPS in warning band (75-100% of 4000 limit). No hard breach.",
        "action": "inject_storage",
        "params": {"node_id": "server-1", "disk_iops": 3100},
        "projection_steps": 5,
    },
    {
        "id": "inject_iops_breach",
        "category": "storage",
        "label": "IOPS hard breach on server-2 (4050 IOPS)",
        "description": "IOPS above NVMe 4000 limit. Expect storage violation + caching recommendation.",
        "action": "inject_storage",
        "params": {"node_id": "server-2", "disk_iops": 4050},
        "projection_steps": 5,
    },
    {
        "id": "inject_iops_neo4j",
        "category": "storage",
        "label": "IOPS near-limit on neo4j (3800 IOPS) — full-scan workload",
        "description": "Neo4j graph-database under full-index-scan load approaching NVMe ceiling.",
        "action": "inject_storage",
        "params": {"node_id": "neo4j", "disk_iops": 3800},
        "projection_steps": 5,
    },
    {
        "id": "inject_iops_future_breach",
        "category": "storage",
        "label": "IOPS that projects past limit at step 2 (3500 IOPS base)",
        "description": "3500 IOPS clean now — projects to 4200 at step 2 (×1.10/step).",
        "action": "inject_storage",
        "params": {"node_id": "server-3", "disk_iops": 3500},
        "projection_steps": 5,
    },
]

CATEGORIES = ["topology", "compute", "network", "storage"]


# ── Core runner ─────────────────────────────────────────────────────────────

def run_scenario(scenario: dict, G, simulator: Simulator,
                 validator: ValidatorEngine,
                 recommender: RecommendationEngine) -> dict:
    """Run one scenario and return a structured result dict."""
    sim_result = simulator.run(
        G,
        action=scenario["action"],
        params=scenario["params"],
        projection_steps=scenario.get("projection_steps", 3),
    )

    if not sim_result["success"]:
        return {
            "id": scenario["id"],
            "label": scenario["label"],
            "success": False,
            "error": str(sim_result.get("mutation", {}).get("error", "Unknown error")),
            "allowed": False,
            "violations": [],
            "warnings": [],
            "recommendations": [],
            "projections": 0,
        }

    projected_graph = dict_to_graph(sim_result["projected_graph"])
    projections = sim_result["projections"]
    validation = validator.validate(projected_graph, projections)

    report = recommender.generate_report(
        action=scenario["action"],
        params=scenario["params"],
        validation_result=validation,
        mutation_result=sim_result["mutation"],
        projections=projections,
    )

    return {
        "id": scenario["id"],
        "label": scenario["label"],
        "success": True,
        "allowed": validation["allowed"],
        "violations": validation.get("reasons", []),
        "warnings": validation.get("warnings", []),
        "recommendations": report.get("recommendations", []),
        "future_violations": _collect_future(validation.get("tier_results", {})),
        "projections": len(projections),
        "clone_id": sim_result["clone_id"],
    }


def _collect_future(tier_results: dict) -> list[str]:
    out = []
    for tier in tier_results.values():
        out.extend(tier.get("future_violations", []))
    return out


def print_scenario_result(scenario: dict, result: dict, index: int, total: int):
    label = result["label"]
    verdict = pass_label() if result["allowed"] else fail_label()
    prefix = f"[{index}/{total}]"

    print(f"\n{BOLD}{prefix} {label}{RESET}")
    print(f"  Category  : {scenario['category']}")
    print(f"  Action    : {scenario['action']}")
    print(f"  Verdict   : {verdict}")
    print(f"  Projections: {result['projections']} steps")

    if not result["success"]:
        print(f"  {RED}Mutation error: {result['error']}{RESET}")
        return

    if result["violations"]:
        print(f"  {RED}Violations ({len(result['violations'])}):{RESET}")
        for v in result["violations"]:
            print(f"    • {v}")

    if result["future_violations"]:
        print(f"  {YELLOW}Future violations ({len(result['future_violations'])}):{RESET}")
        for fv in result["future_violations"]:
            print(f"    ↗ {fv}")

    if result["warnings"]:
        print(f"  {YELLOW}Warnings ({len(result['warnings'])}):{RESET}")
        for w in result["warnings"]:
            print(f"    ~ {w}")

    if result["recommendations"]:
        print(f"  {CYAN}Recommendations:{RESET}")
        for r in result["recommendations"]:
            print(f"    → {r}")

    if result["allowed"] and not result["warnings"] and not result["future_violations"]:
        print(f"  {GREEN}All constraint tiers cleared — change is safe to apply.{RESET}")


def print_summary(results: list[dict], elapsed: float):
    passed  = sum(1 for r in results if r["allowed"])
    failed  = sum(1 for r in results if not r["allowed"])
    errors  = sum(1 for r in results if not r["success"])
    total   = len(results)

    print("\n" + "═" * 60)
    print(f"  {BOLD}SIMULATION RUN SUMMARY{RESET}")
    print("═" * 60)
    print(f"  Total scenarios : {total}")
    print(f"  {GREEN}Passed          : {passed}{RESET}")
    print(f"  {RED}Failed (blocked): {failed}{RESET}")
    if errors:
        print(f"  {RED}Errors          : {errors}{RESET}")
    print(f"  Elapsed         : {elapsed:.2f}s")
    print("═" * 60)

    print(f"\n  {'ID':<40} {'VERDICT'}")
    print("  " + "─" * 55)
    for r in results:
        icon = pass_label() if r["allowed"] else fail_label()
        print(f"  {r['id']:<40} {icon}")
    print()


async def main(category: str = "all", list_only: bool = False):
    # ── List mode ───────────────────────────────────────────────────────
    if list_only:
        print(f"\n{BOLD}Available simulation scenarios:{RESET}\n")
        for cat in CATEGORIES:
            print(f"  {CYAN}{cat.upper()}{RESET}")
            for s in ALL_SCENARIOS:
                if s["category"] == cat:
                    print(f"    {s['id']:<42} {s['label']}")
        print()
        return

    # ── Filter by category ──────────────────────────────────────────────
    if category == "all":
        print(f"\n{BOLD}HPE Digital Twin — Full Simulation Suite{RESET}")
        scenarios = ALL_SCENARIOS
    else:
        scenarios = [s for s in ALL_SCENARIOS if s["category"] == category]
        if not scenarios:
            print(f"{RED}No scenarios found for category '{category}'{RESET}")
            print(f"Available: {', '.join(CATEGORIES + ['all'])}")
            sys.exit(1)

    # ── Bootstrap orchestrator ──────────────────────────────────────────
    print(f"Running {len(scenarios)} scenario(s) in category: {BOLD}{category}{RESET}\n")

    orchestrator.bootstrap()
    print("\nSeeding live infrastructure telemetry state metrics...")
    await orchestrator._tick()

    G = orchestrator.get_derived_graph()

    simulator  = Simulator()
    validator  = ValidatorEngine()
    recommender = RecommendationEngine()

    # ── Execute scenarios ───────────────────────────────────────────────
    results = []
    start_time = time.time()

    for i, scenario in enumerate(scenarios, 1):
        result = run_scenario(scenario, G, simulator, validator, recommender)
        results.append(result)
        print_scenario_result(scenario, result, i, len(scenarios))

    elapsed = time.time() - start_time
    print_summary(results, elapsed)

    # ── Optional: dump JSON results ─────────────────────────────────────
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"simulation_results_{category}_{int(time.time())}.json"
    )
    with open(out_path, "w") as f:
        json.dump({"category": category, "results": results, "elapsed_s": elapsed}, f, indent=2)
    print(f"  Full results log report saved to: {out_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HPE Digital Twin — Simulation Scenario Runner"
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=CATEGORIES + ["all"],
        help="Category of scenarios to run (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available scenarios without running them",
    )
    args = parser.parse_args()
    asyncio.run(main(category=args.scenario, list_only=args.list))