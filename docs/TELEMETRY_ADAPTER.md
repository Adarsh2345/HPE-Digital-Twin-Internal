# Telemetry Adapter & Data Pipeline

How raw metrics travel from physical exporters all the way into the Digital Twin graph — and how the 12-second heartbeat loop keeps everything in sync.

---

## The Big Picture

```
Mock Exporters (4 droplets)          Real Infrastructure
  node-exporter :9100-9103      OR   actual servers / routers
  cadvisor, prometheus, etc.
          │
          │  scrape every 12s
          ▼
    Prometheus :9090
    (stores time-series,
     answers PromQL queries)
          │
          │  PromQL GET /api/v1/query
          ▼
  prometheus_telemetry_adapter.py
  (translates bare names → composite IDs)
          │
          ▼
  prometheus_scraper.py
  (calls the adapter, returns snapshot dict)
          │
          ▼
  chaos_engine.py  (optional: inject synthetic faults)
          │
          ▼
  telemetry_processor.py
  (rolling averages, simple anomaly flag)
          │
          ▼
  derived_state_builder.py
  (merges metrics into NetworkX graph, assigns HEALTHY/WARNING/CRITICAL)
          │
          ├──► Redis   (latest snapshot cache)
          ├──► InfluxDB (time-series history)
          └──► Neo4j   (graph snapshot per tick)

          │
          ▼
  GET /api/v1/telemetry  → UI, anomaly scanner, simulation baseline
```

---

## Component 1 — Prometheus Telemetry Adapter

**File:** `core/telemetry/prometheus_telemetry_adapter.py`  
**Function:** `fetch_snapshot(prometheus_url, graph_node_ids) → dict`

### The ID Collision Problem

Prometheus receives metrics from all 4 droplets. Each droplet has a `node-exporter`, a `cadvisor`, etc. Prometheus only sees the bare device name as a label (`id="node-exporter"`), not the droplet it came from.

Without disambiguation:
```
droplet-1-tor1/node-exporter  ←─┐
droplet-2-tor2/node-exporter  ←─┼── all collapse to "node-exporter" → only 1 gets metrics
droplet-3-mgmt/node-exporter  ←─┘
```

### The Fix: Two-Map Lookup

```python
# Built once from the 26-node topology inventory:

by_droplet_and_name = {
    ("droplet-1-tor1", "node-exporter"): "droplet-1-tor1/node-exporter",
    ("droplet-2-tor2", "node-exporter"): "droplet-2-tor2/node-exporter",
    ("droplet-3-mgmt", "node-exporter"): "droplet-3-mgmt/node-exporter",
    ("droplet-1-tor1", "server-1"):      "droplet-1-tor1/server-1",
    ...  # 26 entries total
}

bare_to_full = {
    "server-1": "droplet-1-tor1/server-1",  # first encountered wins
    "router-1": "droplet-1-tor1/router-1",
    ...
}

def resolve(name, droplet):
    if droplet and (droplet, name) in by_droplet_and_name:
        return by_droplet_and_name[(droplet, name)]   # exact match
    return bare_to_full.get(name)                      # fallback
```

Prometheus metric labels include both `id` (device name) and `droplet` (which rack it came from). The adapter reads both and resolves the composite ID precisely.

### Node Metrics Fetched

For each of these 5 fields, one PromQL query is fired:

| Field | PromQL query |
|---|---|
| `cpu_percent` | `cpu_percent` |
| `memory_percent` | `memory_percent` |
| `disk_iops` | `disk_iops` |
| `power_watts` | `power_watts` |
| `temperature_celsius` | `temperature_celsius` |

Each query returns a list of `{metric: {id, droplet, role, ...}, value: [timestamp, "45.2"]}` objects from Prometheus. The adapter resolves the composite ID and stores the float value.

### Edge Metrics Fetched

For each of these 3 fields, one PromQL query is fired:

| Field | PromQL query | Labels needed |
|---|---|---|
| `latency_ms` | `latency_ms` | `source`, `target`, `droplet` |
| `packet_loss_percent` | `packet_loss_percent` | `source`, `target`, `droplet` |
| `bandwidth_mbps` | `bandwidth_mbps` | `source`, `target`, `droplet` |

Edge key format: `"droplet-1-tor1/server-1->droplet-1-tor1/router-1"`

### Output Shape

```python
{
    "nodes": {
        "droplet-1-tor1/server-1": {
            "role":                "compute-node",
            "droplet":             "droplet-1-tor1",
            "cpu_percent":         45.2,
            "memory_percent":      62.1,
            "disk_iops":           1250.5,
            "power_watts":         215.3,
            "temperature_celsius": 48.5,
        },
        ...  # all 26 nodes
    },
    "edges": {
        "droplet-1-tor1/server-1->droplet-1-tor1/router-1": {
            "latency_ms":           12.4,
            "packet_loss_percent":  0.08,
            "bandwidth_mbps":       850.0,
        },
        ...  # all 13+ edges
    }
}
```

---

## Component 2 — Prometheus Scraper

**File:** `core/telemetry/prometheus_scraper.py`

Thin wrapper around the adapter. Holds the `prometheus_url` from settings and calls `fetch_snapshot()`. If Prometheus is unreachable, it falls back to `MetricsGenerator` (synthetic metrics) so the UI never goes blank.

---

## Component 3 — Metrics Generator (Fallback / Chaos Source)

**File:** `core/telemetry/metrics_generator.py`

Used in two scenarios:
1. **Prometheus unreachable** — generates realistic synthetic data so the system keeps running
2. **Chaos mode training** — generates 3,000 extreme-value snapshots per device for the RF Classifier

Metrics are drawn from Gaussian distributions:

**Healthy mode:**
| Metric | Mean | Std |
|---|---|---|
| cpu_percent | ~35% | ±12% |
| memory_percent | ~50% | ±15% |
| disk_iops | ~1200 | ±400 |
| power_watts | ~200W | ±50W |
| latency_ms | ~15ms | ±8ms |

**Chaos mode** (`chaos_mode=True`):
| Metric | Range |
|---|---|
| cpu_percent | 80–99% |
| memory_percent | 85–98% |
| disk_iops | 3500–5000 |
| power_watts | 280–400W |
| latency_ms | 50–320ms |
| packet_loss_percent | 1–20% |

---

## Component 4 — Chaos Engine

**File:** `core/telemetry/chaos_engine.py`

Activated via `POST /api/v1/chaos/enable`. Reads the Redis key `digital_twin:chaos_mode`.

When active during a tick, it overwrites the Prometheus snapshot with extreme metric values before the data enters the processing pipeline. The downstream anomaly detector, threshold checker, and UI all see the injected fault — exactly as if the real hardware was under stress.

**Scenarios available:**
- `full` — all metrics
- `compute` — CPU + memory only
- `network` — latency + packet loss only
- `storage` — IOPS only
- `thermal_rise`, `pdu_failure`, `tor_failure`, `storage_controller_failure`

---

## Component 5 — Telemetry Processor

**File:** `core/telemetry/telemetry_processor.py`

Runs after scrape/chaos. Does two things:

**1. Rolling Averages**  
Keeps a sliding window (last ~50 samples) per node. Calculates:
- `rolling_avg_cpu`
- `rolling_avg_memory`

These smooth out single-point spikes and are stored alongside the raw metrics.

**2. Simple Anomaly Flag**  
Rule: `|current_cpu - rolling_avg_cpu| > 25%` → sets `anomaly_detected: True` on the node.

This is NOT the ML anomaly detector — it's a cheap, zero-latency first pass that the UI uses for the `⚠ yes` column in the Live Metrics table.

---

## Component 6 — Derived State Builder

**File:** `core/graph/derived_state_builder.py`

Takes the enriched snapshot and the base NetworkX graph. Produces the `derived_graph` — the live view of the infrastructure.

**For nodes:**
```
metrics from snapshot injected into graph.nodes[node_id]["metrics"]

state derived from thresholds:
  cpu_percent ≥ 85%  OR  memory_percent ≥ 90%  →  CRITICAL
  cpu_percent ≥ 70%  OR  memory_percent ≥ 75%  →  WARNING
  power_watts ≥ 1200W                           →  WARNING
  power_watts ≥ 1400W                           →  CRITICAL
  else                                          →  HEALTHY
```

**For edges:**
```
latency_ms ≥ 150ms  OR  packet_loss_percent ≥ 5%  →  DOWN
latency_ms ≥ 100ms  OR  packet_loss_percent ≥ 2%  →  DEGRADED
else                                              →  ACTIVE
```

---

## The 12-Second Heartbeat Loop

**File:** `core/orchestrator.py`  
**Method:** `_tick()`  
**Interval:** `TELEMETRY_INTERVAL_SECONDS` (default 12s, set in `.env`)

```
Tick N (every 12 seconds):

 1. PrometheusScraper.scrape()
       ↓ calls fetch_snapshot() → adapter → Prometheus /api/v1/query
       ↓ returns {"nodes": {...}, "edges": {...}}

 2. ChaosEngine.apply(snapshot)       ← only if chaos_mode == True in Redis
       ↓ overwrites some metrics with extreme values

 3. TelemetryProcessor.process(snapshot)
       ↓ rolling_avg_cpu/memory, anomaly_detected flag

 4. DerivedStateBuilder.build(initial_graph, snapshot)
       ↓ merges metrics + derives HEALTHY/WARNING/CRITICAL state
       ↓ returns derived_graph (NetworkX DiGraph)

 5. _cache_to_redis(snapshot)         ← optional
       ↓ DERIVED_STATE key → JSON state dict

 6. _sync_to_influxdb()
       ↓ writes Point("node_telemetry") + Point("edge_telemetry")
       ↓ tags: id, role, droplet
       ↓ fields: cpu_percent, memory_percent, disk_iops, power_watts, temperature_celsius
       ↓ batch write via synchronous InfluxDB write API

 7. _sync_to_neo4j()
       ↓ graph_to_dict(derived_graph) → flattened attributes
       ↓ Neo4jClient.save_live_metrics(dict, tick=N)

 8. orchestrator.derived_graph = derived_graph   ← in-memory live state
    orchestrator._tick_count += 1
```

---

## How the API Gets Telemetry

**File:** `api/routes/telemetry.py`  
**Endpoint:** `GET /api/v1/telemetry`

```python
snap = orchestrator.get_derived_state()
# Returns the last computed derived_graph as a dict
# Includes: nodes{id, role, state, metrics{}}, edges{key, state, metrics{}}
```

The UI polls this every 4 seconds. The Anomaly scanner uses these metrics as input to the ML detector. The Simulation pipeline uses `orchestrator.get_derived_graph()` (the NetworkX object) as the base graph to clone.

---

## InfluxDB — Time-Series Storage

**File:** `integrations/influxdb/influx_client.py`

Every tick writes two types of points:

**node_telemetry measurement:**
```
tags:   id="droplet-1-tor1/server-1", role="compute-node", droplet="droplet-1-tor1"
fields: cpu_percent=45.2, memory_percent=62.1, disk_iops=1250.0,
        power_watts=215.3, temperature_celsius=48.5
```

**edge_telemetry measurement:**
```
tags:   source="droplet-1-tor1/server-1", target="droplet-1-tor1/router-1"
fields: latency_ms=12.4, packet_loss_percent=0.08, bandwidth_mbps=850.0
```

InfluxDB is what the Anomaly Detector trains on — `HistoryFetcher` queries the last 7 days of `node_telemetry` to build each device's healthy baseline.

---

## Mock Exporters (Local Dev Stack)

**Folder:** `mock-scripts/` or `docker/`

Four Docker containers simulate the four physical droplets:

| Container | Port | Simulates |
|---|---|---|
| mock-exporter-1 | 9100 | droplet-1-tor1 (servers + router) |
| mock-exporter-2 | 9101 | droplet-2-tor2 (servers + router) |
| mock-exporter-3 | 9102 | droplet-3-mgmt (spine, services) |
| mock-exporter-4 | 9103 | droplet-4-storage (storage rack) |

Each exposes `/metrics` in Prometheus exposition format. The local `twin-prometheus-local` container scrapes all four every 15 seconds.

---

## Configuration Reference

All in `config/settings.py`, overridable via `.env`:

| Setting | Default | Purpose |
|---|---|---|
| `PROMETHEUS_URL` | `http://168.144.91.25:9090` | Remote default — set to `http://localhost:9090` for local dev |
| `TELEMETRY_INTERVAL_SECONDS` | `12` | How often the heartbeat tick runs |
| `INFLUXDB_URL` | `http://localhost:8086` | Time-series storage |
| `INFLUXDB_TOKEN` | — | Auth token |
| `INFLUXDB_ORG` | — | Org name |
| `INFLUXDB_BUCKET` | — | Bucket name |

**Local dev `.env` minimum:**
```
PROMETHEUS_URL=http://localhost:9090
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
```

---

## Key Files Summary

| File | Role |
|---|---|
| `core/telemetry/prometheus_telemetry_adapter.py` | Maps bare Prometheus names → composite graph IDs, fires PromQL queries |
| `core/telemetry/prometheus_scraper.py` | Calls the adapter, holds `prometheus_url`, falls back to generator |
| `core/telemetry/metrics_generator.py` | Synthetic Gaussian metrics for dev/chaos/training |
| `core/telemetry/chaos_engine.py` | Injects extreme values when chaos mode is active |
| `core/telemetry/telemetry_processor.py` | Rolling averages, simple anomaly flag |
| `core/graph/derived_state_builder.py` | Merges metrics into graph, assigns node/edge states |
| `core/orchestrator.py` | 12s heartbeat loop orchestrating all the above |
| `integrations/influxdb/influx_client.py` | Writes metric points to InfluxDB |
| `integrations/influxdb/history_fetcher.py` | Reads 7-day history from InfluxDB for anomaly training |
| `api/routes/telemetry.py` | `GET /api/v1/telemetry` — serves latest snapshot to UI |
