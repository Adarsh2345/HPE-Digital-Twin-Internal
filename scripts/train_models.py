#!/usr/bin/env python3
"""
scripts/train_models.py
Trains all RandomForest models and runs the full analytics pipeline.
Usage:
    python scripts/train_models.py
    python scripts/train_models.py --days 7
"""
import sys, os, argparse, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics.model_registry import registry


def main(days: int, train_anomaly: bool = True, chaos_snapshots: int = 3000):
    print("=" * 65)
    print("  HPE Digital Twin — ML Analytics Training Pipeline")
    print("=" * 65)
    print(f"  History window : {days} days\n")

    start = time.time()

    # Bootstrap orchestrator once — loads topology (sets initial_graph for
    # chaos data generation in Phase 2) AND trains all analytics models.
    from core.orchestrator import orchestrator
    orchestrator.bootstrap()

    # --- Phase 1 outputs (models already trained by orchestrator.bootstrap) ---
    elapsed_phase1 = time.time() - start

    print(f"\n  Discovered scenarios (k={registry.scenario_gen.best_k}):")
    for s in registry.get_scenarios():
        m = s.get("metrics", {})
        print(
            f"    [{s['name']:16s}]  "
            f"CPU={m.get('cpu_percent', 0):5.1f}%  "
            f"MEM={m.get('memory_percent', 0):5.1f}%  "
            f"IOPS={m.get('disk_iops', 0):6.0f}  "
            f"BW={m.get('bandwidth_mbps', 0):5.0f}Mbps  "
            f"LAT={m.get('latency_ms', 0):5.1f}ms  "
            f"PWR={m.get('power_watts', 0):5.0f}W  "
            f"({s.get('cluster_size', 0)} pts)"
        )

    print(f"\n  Behavior model R² scores:")
    for node_id, targets in registry.behavior_model.training_summary.items():
        scores = "  ".join(f"{t}:R²={v['r2']:.3f}" for t, v in targets.items())
        print(f"    {node_id:35s}  {scores}")

    print(f"\n  Phase 1 elapsed: {elapsed_phase1:.1f}s")

    # --- Phase 2: per-device Isolation Forest + RF Classifier ---
    if train_anomaly:
        print("\n" + "-" * 65)
        print("  Phase 2 — Device-level Anomaly Detector (IF + RF)")
        print("-" * 65)
        print(f"  Raw history window : 7 days  |  Chaos snapshots: {chaos_snapshots}")

        # orchestrator already bootstrapped above — initial_graph is set
        from core.analytics.anomaly_detector import DeviceAnomalyDetector
        ad = DeviceAnomalyDetector()
        t2 = time.time()
        summary = ad.train(days=7, chaos_snapshots=chaos_snapshots)
        elapsed_phase2 = time.time() - t2

        print(f"\n  Devices trained : {summary['devices_trained']}")
        print(f"  Devices skipped : {summary['devices_skipped']}")
        print(f"  Phase 2 elapsed : {elapsed_phase2:.1f}s")
        print(f"  Model saved     → models/anomaly_detector.pkl")

    total = time.time() - start
    print(f"\n  Total time: {total:.1f}s")
    print("=" * 65)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days",            type=int,  default=30)
    p.add_argument("--chaos-snapshots", type=int,  default=3000)
    p.add_argument("--no-anomaly",      action="store_true",
                   help="Skip anomaly detector training (phase 2)")
    args = p.parse_args()
    main(
        days=args.days,
        train_anomaly=not args.no_anomaly,
        chaos_snapshots=args.chaos_snapshots,
    )