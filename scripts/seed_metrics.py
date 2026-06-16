#!/usr/bin/env python3
"""
scripts/seed_metrics.py
Runs several telemetry ticks and prints a live dashboard to stdout.
"""
import sys, os, asyncio, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.orchestrator import orchestrator


async def main(ticks: int, chaos: bool):
    orchestrator.bootstrap()

    if chaos:
        orchestrator.chaos_engine.enable(scenario="full")
        print("🔥 Chaos mode ENABLED\n")

    for i in range(ticks):
        await orchestrator._tick()
        G = orchestrator.get_derived_graph()

        print(f"\n{'─'*60}")
        print(f"  Tick #{i+1}/{ticks}  {time.strftime('%H:%M:%S')}  "
              f"{'[CHAOS]' if orchestrator.chaos_engine.is_active else '[HEALTHY]'}")
        print(f"{'─'*60}")
        for n in G.nodes:
            node = G.nodes[n]
            m = node.get("metrics", {})
            state = node.get("state", "?")
            icon = {"healthy": "✅", "warning": "⚠️ ", "critical": "❌"} .get(state, "?")
            cpu = m.get("cpu_percent", 0)
            mem = m.get("memory_percent", 0)
            print(f"  {icon} {n:20s} CPU={cpu:5.1f}%  MEM={mem:5.1f}%  [{state}]")

        if i < ticks - 1:
            print(f"\n  Next tick in 12s... (Ctrl+C to stop)")
            await asyncio.sleep(12)

    print("\n  ✓ Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed and display telemetry ticks")
    parser.add_argument("--chaos", action="store_true", help="Enable chaos mode")
    parser.add_argument("--ticks", type=int, default=3, help="Number of ticks to run")
    args = parser.parse_args()
    asyncio.run(main(ticks=args.ticks, chaos=args.chaos))
