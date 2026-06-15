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


def main(days: int):
    print("=" * 65)
    print("  HPE Digital Twin — ML Analytics Training Pipeline")
    print("=" * 65)
    print(f"  History window : {days} days\n")

    start = time.time()
    registry.bootstrap(days=days)
    elapsed = time.time() - start

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

    print(f"\n  Training summary:")
    for node_id, targets in registry.behavior_model.training_summary.items():
        scores = "  ".join(f"{t}:R²={v['r2']:.3f}" for t, v in targets.items())
        print(f"    {node_id:20s}  {scores}")

    print(f"\n  Total time: {elapsed:.1f}s")
    print("=" * 65)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    main(days=args.days)