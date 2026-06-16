#!/usr/bin/env python3
"""
scripts/seed_influx_history.py
Generates and backfills 30 days of historical telemetry mock metrics at 12-second intervals.
Total Points Generated: ~216,000 snapshots points written synchronously in hourly blocks.
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import orchestrator
from core.telemetry.metrics_generator import MetricsGenerator

def main():
    print("============================================================")
    print("⚡ HPE DIGITAL TWIN — INFLUXDB 30-DAY HISTORICAL BACKFILL   ")
    print("============================================================")
    
    # Initialize metadata configuration mappings
    orchestrator.bootstrap()
    
    if not orchestrator.influx_client or not orchestrator.influx_client.write_api:
        print("❌ Error: InfluxDB write API layer is unreachable. Ensure the container is healthy.")
        return

    # Extract static architectural components
    nodes = [{"id": n, **orchestrator.initial_graph.nodes[n]} for n in orchestrator.initial_graph.nodes]
    edges = [{"source": u, "target": v, **orchestrator.initial_graph.edges[u, v]} for u, v in orchestrator.initial_graph.edges]
    
    generator = MetricsGenerator(chaos_mode=False)
    
    interval_seconds = 12
    days_to_seed = 30
    total_seconds = days_to_seed * 24 * 60 * 60
    total_ticks = total_seconds // interval_seconds
    
    now = datetime.datetime.now(datetime.timezone.utc)
    start_time = now - datetime.timedelta(days=days_to_seed)
    
    print(f"👉 Seeding chronological data window starting: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"👉 Total baseline intervals to compile: {total_ticks:,} points")
    print("🚀 Streaming data chunks down to time-series channels...")

    from core.graph.graph_serializer import graph_to_dict
    from influxdb_client import Point, WritePrecision

    BATCH_SIZE = 1000
    batch: list[Point] = []

    def flush(points: list[Point]):
        if not points:
            return
        orchestrator.influx_client.write_api.write(
            bucket=orchestrator.influx_client.bucket,
            org=orchestrator.influx_client.org,
            record=points,
        )

    for tick in range(total_ticks):
        current_tick_time = start_time + datetime.timedelta(seconds=tick * interval_seconds)

        # Build clean Gaussian curve metrics for this historical timestamp marker
        raw_snapshot = generator.generate_full_snapshot(nodes, edges)
        processed = orchestrator.processor.process(raw_snapshot)

        derived_graph = orchestrator.state_builder.build_derived_state(orchestrator.initial_graph, processed)
        graph_dict = graph_to_dict(derived_graph)

        for node in graph_dict.get("nodes", []):
            metrics = node.get("metrics", {})
            if not metrics:
                continue
            point = (
                Point("node_telemetry")
                .tag("id", node["id"])
                .tag("role", node.get("role", "unknown"))
                .tag("droplet", node.get("droplet", "unknown"))
                .tag("subnet", node.get("subnet", "unknown"))
                .field("cpu_percent", float(metrics.get("cpu_percent", 0.0)))
                .field("memory_percent", float(metrics.get("memory_percent", 0.0)))
                .field("disk_iops", int(metrics.get("disk_iops", 0)))
                .field("power_watts", float(metrics.get("power_watts", 0.0)))
                .field("temperature_celsius", float(metrics.get("temperature_celsius", 0.0)))
                .time(current_tick_time, WritePrecision.NS)
            )
            batch.append(point)

        for edge in graph_dict.get("edges", []):
            metrics = edge.get("metrics", {})
            if not metrics:
                continue
            point = (
                Point("edge_telemetry")
                .tag("source", edge["source"])
                .tag("target", edge["target"])
                .field("latency_ms", float(metrics.get("latency_ms", 0.0)))
                .field("packet_loss_percent", float(metrics.get("packet_loss_percent", 0.0)))
                .field("bandwidth_mbps", float(metrics.get("bandwidth_mbps", 0.0)))
                .time(current_tick_time, WritePrecision.NS)
            )
            batch.append(point)

        if len(batch) >= BATCH_SIZE:
            flush(batch)
            batch = []

        if tick % 20000 == 0 and tick > 0:
            progress_percent = (tick / total_ticks) * 100
            print(f"   Processed {tick:,}/{total_ticks:,} intervals ({progress_percent:.1f}% synchronized)...")

    flush(batch)

    print("\n============================================================")
    print("✅ Success! InfluxDB time-series backfill permanently saved.")
    print("============================================================")

if __name__ == "__main__":
    main()