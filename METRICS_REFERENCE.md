# HPE Digital Twin — Metrics Reference Document

---

## Table of Contents

1. [Node Metrics](#1-node-metrics)
2. [Edge / Network Metrics](#2-edge--network-metrics)
3. [Derived / Computed Metrics](#3-derived--computed-metrics)
4. [Gaussian Distribution Parameters](#4-gaussian-distribution-parameters)
5. [Capacity Limits](#5-capacity-limits-hard-ceilings)
6. [Warning & Critical Thresholds](#6-warning--critical-thresholds)
7. [ML Analytics Features](#7-ml-analytics-features)
8. [Where Metrics Are Stored](#8-where-metrics-are-stored)
9. [Data Flow End to End](#9-data-flow-end-to-end)
10. [Key Source Files](#10-key-source-files)

---

## 1. Node Metrics

Collected per device every 12 seconds via Prometheus scrape. Each device belongs to one of four droplets.

### 1.1 Compute Metrics

| Metric | Field Name | What It Measures |
|--------|------------|-----------------|
| CPU Usage | `cpu_percent` | How much of the processor is being used (%) |
| Memory Usage | `memory_percent` | How much RAM is being used (%) |
| Disk IOPS | `disk_iops` | Number of read/write operations per second on storage |
| Power Draw | `power_watts` | How many watts the device is consuming |
| Temperature | `temperature_celsius` | Core thermal reading in degrees Celsius |

### 1.2 Router-Specific Metrics

These only appear on `tor-router` and `spine-switch` devices.

| Metric | Field Name | What It Measures |
|--------|------------|-----------------|
| Routing Table Size | `routing_table_entries` | Number of network routes the router knows (50–500) |
| BGP Sessions | `bgp_sessions_active` | Number of active BGP peer connections (1–8) |

### 1.3 Network Interface Metrics (per node)

| Metric | Field Name | What It Measures |
|--------|------------|-----------------|
| Inbound Bandwidth | `network_rx_mbps` | Data being received by this node (Mbps) |
| Outbound Bandwidth | `network_tx_mbps` | Data being sent from this node (Mbps) |

### 1.4 Service Node Metrics

Only on service containers: `netbox`, `neo4j`, `python-app`, `grafana`, `prometheus`.

| Metric | Field Name | What It Measures |
|--------|------------|-----------------|
| Request Rate | `request_rate_rps` | Requests handled per second |
| Error Rate | `error_rate_percent` | Percentage of requests that fail |

---

## 2. Edge / Network Metrics

Collected per link (connection) between two nodes. Edge metrics describe the quality of the network path between them.

| Metric | Field Name | What It Measures | Unit |
|--------|------------|-----------------|------|
| Latency | `latency_ms` | Round-trip delay between two nodes | milliseconds |
| Packet Loss | `packet_loss_percent` | Percentage of packets dropped in transit | % |
| Bandwidth | `bandwidth_mbps` | Available throughput on the link | Mbps |

---

## 3. Derived / Computed Metrics

These are not scraped from Prometheus — they are calculated by the platform after each telemetry tick inside `core/telemetry/telemetry_processor.py`.

| Metric | Field Name | How It's Calculated | Window |
|--------|------------|---------------------|--------|
| Rolling CPU Average | `rolling_avg_cpu` | Average of the last 50 CPU readings for this node | ~10 minutes |
| Rolling Memory Average | `rolling_avg_memory` | Average of the last 50 memory readings for this node | ~10 minutes |
| Anomaly Flag | `anomaly_detected` | `true` if current CPU is > 25% above the recent 5-sample average | ~60 seconds |

> **Why rolling averages?** A single high reading can be a momentary spike. Rolling averages smooth out noise and give a more reliable picture of sustained load.

> **Why anomaly detection?** The 5-sample window catches sudden spikes fast (within one minute), while the 25% threshold avoids false alarms from normal fluctuation.

---

## 4. Gaussian Distribution Parameters

Every metric value is generated using a **Gaussian (Normal) distribution** — most values cluster near the mean, with fewer values at the extremes. Values are clamped to a min/max range.

### 4.1 Healthy State (Normal Operations)

```
Compute Nodes:
  CPU:         mean = 33.0%    std = 8.0     range: 24.5% – 42.0%
  Memory:      mean = 45.0%    std = 10.0    range: 20%   – 70%
  Disk IOPS:   mean = 800      std = 150     range: 200   – 2000
  Power:       mean = 180 W    std = 30      range: 100W  – 300W
  Temperature: mean = 45 °C    std = 5       range: 25°C  – 90°C

Storage Controllers (higher IOPS baseline):
  Disk IOPS:   mean = 1400     std = 250     range: 400   – 4000

TOR / Spine Routers (lower CPU baseline):
  CPU:         mean = 12.0%    std = 5.0     range: 2%    – 95%

Network Links:
  Latency:     mean = 12.0 ms  std = 3.0     range: 1ms   – 50ms
  Packet Loss: mean = 0.05%    std = 0.02    range: 0%    – 1%
  Bandwidth:   mean = 800 Mbps std = 100     range: 400   – 1000 Mbps
```

### 4.2 Chaos State (System Under Stress)

Chaos mode is manually triggered via `POST /chaos`. It shifts all distributions to simulate a heavily stressed infrastructure.

```
Compute Nodes:
  CPU:         mean = 82.0%    std = 12.0    clamp: 40%   – 100%
  Memory:      mean = 88.0%    std = 8.0     clamp: 50%   – 100%
  Disk IOPS:   mean = 3500     std = 400     clamp: 1000  – 6000
  Power:       mean = 320 W    std = 50      clamp: 150W  – 500W
  Temperature: mean = 72 °C    std = 5       range: 25°C  – 90°C

Network Links:
  Latency:     mean = 200 ms   std = 60      max: 320ms
  Packet Loss: mean = 5.0%     std = 2.0     clamp: 0%    – 20%
  Bandwidth:   mean = 200 Mbps std = 80      clamp: 10    – 1000 Mbps
```

---

## 5. Capacity Limits (Hard Ceilings)

These are the absolute maximum values the infrastructure is designed to support. Defined in `config/settings.py`.

| Resource | Hard Limit | Applies To |
|----------|-----------|------------|
| CPU | 95% | Per node |
| Memory | 95% | Per node |
| Disk IOPS | 8,000 | Per storage device |
| Network Latency SLA | 150 ms | Per link |
| Cabinet Power | 1,400 W | Per rack/droplet total |
| Rack Height | 42 U | Per droplet |

---

## 6. Warning & Critical Thresholds

Defined in `config/constants.py`. When a metric crosses these values, the node or edge changes health state.

| Metric | Warning Threshold | Critical Threshold | State Change |
|--------|------------------|--------------------|-------------|
| `cpu_percent` | ≥ 70% | ≥ 85% | healthy → warning → critical |
| `memory_percent` | ≥ 75% | ≥ 90% | healthy → warning → critical |
| `disk_iops` | ≥ 3,000 | ≥ 4,000 | healthy → warning → critical |
| `power_watts` | ≥ 1,200 W | ≥ 1,400 W | healthy → warning → critical |
| `latency_ms` | ≥ 100 ms | ≥ 150 ms | active → degraded → down |
| `packet_loss_percent` | ≥ 2% | ≥ 5% | active → degraded → down |

### Node Health States

| State | Meaning |
|-------|---------|
| `healthy` | All metrics below warning thresholds |
| `warning` | At least one metric at or above warning threshold |
| `critical` | At least one metric at or above critical threshold |

### Edge Health States

| State | Meaning |
|-------|---------|
| `active` | Latency and packet loss within normal bounds |
| `degraded` | Latency or packet loss at warning level |
| `down` | Latency or packet loss at critical level |

---

## 7. ML Analytics Features

The analytics pipeline uses historical metric data to train models and detect patterns.

### 7.1 Anomaly Detector (`core/analytics/`)

Uses **Isolation Forest** + **Random Forest Classifier** on these features:

```
cpu_percent
memory_percent
disk_iops
power_watts
temperature_celsius
```

A Z-score > 2.0 from the node's own historical mean/std is flagged as significant.

### 7.2 Behavior Model

Predicts future metric values from current readings:

```
Inputs:  cpu_percent, memory_percent, disk_iops, power_watts,
         latency_ms, bandwidth_mbps, hour_of_day, day_of_week

Targets (Compute):  cpu_percent, memory_percent, power_watts
Targets (Network):  latency_ms, packet_loss_percent
Targets (Storage):  disk_iops
```

### 7.3 Historical Analyzer

Computes statistical profiles per metric over 30 days:

```
Percentiles:  P50, P90, P95, P99, max, mean
Patterns:     hourly profiles (0–23h), day-of-week patterns (Mon–Sun)

Correlation pairs tracked:
  cpu_percent      ↔  memory_percent
  cpu_percent      ↔  power_watts
  cpu_percent      ↔  disk_iops
  bandwidth_mbps   ↔  latency_ms
  bandwidth_mbps   ↔  packet_loss_percent
```

---

## 8. Where Metrics Are Stored

### InfluxDB (Time-Series History — 30 Days)

**Measurement: `node_telemetry`**
```
Tags:   id, role, droplet, subnet
Fields: cpu_percent, memory_percent, disk_iops, power_watts, temperature_celsius
```

**Measurement: `edge_telemetry`**
```
Tags:   source, target
Fields: latency_ms, packet_loss_percent, bandwidth_mbps
```

> Currently holds ~232,000 data points per field per node across 30 days.

### Redis (Live Cache)

| Key | Contents |
|-----|----------|
| `digital_twin:derived_state` | Full latest graph snapshot (all node + edge metrics) |
| `digital_twin:chaos_mode` | Whether chaos mode is currently active |
| `digital_twin:topology` | Static topology structure |

### Neo4j (Graph Ledger)

- Stores the baseline topology as an immutable snapshot on startup
- Syncs the latest live metrics as graph node properties on every tick
- Enables graph traversal queries (e.g. impact propagation)

### In-Memory (Per Session)

- Rolling 50-sample history per node (used for `rolling_avg_*` and `anomaly_detected`)
- Lost on server restart

---

## 9. Data Flow End to End

```
┌─────────────────────────────────────────────────┐
│  Mock Exporters  (ports 9100–9103)              │
│  Emit Prometheus gauges every 3 seconds         │
│  Labels: id, droplet, role, source, target      │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Prometheus  (localhost:9090)                   │
│  Scrapes all 4 exporters every 12 seconds       │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  PrometheusTelemetryAdapter                     │
│  Maps bare names → composite IDs               │
│  e.g. "server-1" + "droplet-1-tor1"            │
│       → "droplet-1-tor1/server-1"              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  ChaosEngine                                    │
│  If chaos ON: distorts CPU, memory,             │
│  latency, packet loss to chaos-state values     │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  TelemetryProcessor                             │
│  Adds: rolling_avg_cpu, rolling_avg_memory,     │
│        anomaly_detected                         │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  DerivedStateBuilder                            │
│  Merges metrics into graph nodes/edges          │
│  Assigns: healthy / warning / critical state    │
└──────────┬──────────────────────────────────────┘
           │
     ┌─────┴──────┬──────────────┐
     ▼            ▼              ▼
  InfluxDB      Redis          Neo4j
 (history)    (live cache)  (graph ledger)
     │
     └─────────────────────────────┐
                                   ▼
                          REST API (port 5000)
                                   │
                                   ▼
                            UI  (ui.html)
```

---

## 10. Key Source Files

| Component | File |
|-----------|------|
| Thresholds & role constants | `config/constants.py` |
| Gaussian parameters & settings | `config/settings.py` |
| Metric simulation | `core/telemetry/metrics_generator.py` |
| Telemetry processing & anomaly | `core/telemetry/telemetry_processor.py` |
| Prometheus label mapping | `core/telemetry/prometheus_telemetry_adapter.py` |
| Prometheus scraper | `core/telemetry/prometheus_scraper.py` |
| Chaos distortion | `core/telemetry/chaos_engine.py` |
| Health state derivation | `core/graph/derived_state_builder.py` |
| InfluxDB write & read | `integrations/influxdb/influx_client.py` |
| Anomaly detection model | `core/analytics/` |
| Validation rules | `core/validation/` |
| Mock data exporters | `mock-scripts-local/` |
| Main orchestrator | `core/orchestrator.py` |

---

*Generated for HPE Digital Twin Internal — 2026*
