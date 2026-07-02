# HPE Digital Twin — API Endpoint Reference

**Base URL:** `http://localhost:5000`

---

## Table of Contents

1. [Simulation Endpoints](#1-simulation-endpoints)
2. [NLP / Prompt Endpoint](#2-nlp--prompt-endpoint)
3. [Chaos Endpoints](#3-chaos-endpoints)
4. [Reports Endpoints](#4-reports-endpoints)
5. [Telemetry Endpoints](#5-telemetry-endpoints)
6. [Topology Endpoints](#6-topology-endpoints)
7. [Analytics Endpoints](#7-analytics-endpoints)
8. [Quick Reference Table](#8-quick-reference-table)

---

## 1. Simulation Endpoints

### `POST /api/v1/simulate`

Runs a full what-if simulation against a sandboxed RCU clone of the live graph.

**Pipeline phases:**
- **Phase 3** — Clone live graph → apply mutation → compute metric projections
- **Phase 4** — 4-tier constraint validation on the projected state
- **Phase 5** — Recommendation report generation (LLM context injected on failure)

**Request Body:**
```json
{
  "action": "<action_name>",
  "params": { ... },
  "projection_steps": 3
}
```

`projection_steps` controls how many future ticks the BehaviorModel forecasts (range: 1–10, default: 3).

---

### Supported Actions

#### `move_server` — Move compute node to a different ToR switch

Clips the existing network edge, creates a new edge to the target router, and updates subnet assignments.

```json
{
  "action": "move_server",
  "params": {
    "server_id": "droplet-1-tor1/server-1",
    "target_router_id": "droplet-2-tor2/router-2"
  },
  "projection_steps": 3
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `server_id` | string | Yes | Composite ID of the node to move |
| `target_router_id` | string | Yes | Destination ToR router composite ID |

Constraints checked: `power_envelope`, `rack_u_space`, `compute_overload`, `network_sla`

---

#### `add_compute` — Provision a new compute blade in a rack

Validates rack U-space and power headroom before inserting the new node into the graph.

```json
{
  "action": "add_compute",
  "params": {
    "node_id": "server-5",
    "target_router_id": "droplet-1-tor1/router-1",
    "target_rack_id": "droplet-1-tor1",
    "ip": "10.10.1.13"
  },
  "projection_steps": 3
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | No | Unique ID for the new node |
| `target_router_id` | string | Yes | Parent ToR router composite ID |
| `target_rack_id` | string | Yes | Parent rack / droplet ID |
| `ip` | string | No | Static IP in the ToR subnet |
| `role` | string | No | Node role (default: `compute-node`) |
| `u_size` | int | No | Rack units consumed (default: 1) |
| `max_power_w` | float | No | Max power draw in watts (default: 500) |
| `nics` | int | No | Number of NICs (default: 1) |

Constraints checked: `rack_u_space`, `power_envelope`, `compute_overload`

---

#### `remove_node` — Decommission a node from topology

Removes a node and all its edges, then validates remaining capacity is sufficient.

```json
{
  "action": "remove_node",
  "params": {
    "node_id": "droplet-2-tor2/server-4"
  },
  "projection_steps": 3
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | Yes | Composite ID of the node to remove |

Constraints checked: `compute_overload`, `power_envelope`

---

#### `inject_compute` — Inject CPU / memory / power stress

Stamps elevated metric values directly onto a node to simulate batch job peaks, VM migration load, or runaway processes. The BehaviorModel projections are overridden with the injected values so the validator sees the true breach.

```json
{
  "action": "inject_compute",
  "params": {
    "node_id": "droplet-1-tor1/server-1",
    "cpu_percent": 92.0,
    "memory_percent": 88.0,
    "power_watts": 310.0
  },
  "projection_steps": 5
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | Yes | Target compute node |
| `cpu_percent` | float | No | Simulated CPU load (0–100) |
| `memory_percent` | float | No | Simulated memory load (0–100) |
| `power_watts` | float | No | Simulated power draw per node |

**Breach thresholds:**

| Metric | Warning | Critical | Hard Limit |
|---|---|---|---|
| CPU | >70% | >85% | 95% |
| Memory | >75% | >90% | 95% |
| Power (subnet total) | >1200 W | — | 1400 W |

Constraints checked: `compute_overload`, `power_envelope`, `future_cpu_projection`

---

#### `inject_network` — Inject latency / packet loss on a BGP link

Degrades a specific network edge to simulate NIC flap, MTU mismatch, or congested spine path.

```json
{
  "action": "inject_network",
  "params": {
    "source_node_id": "droplet-3-mgmt/spine-router",
    "target_node_id": "droplet-1-tor1/router-1",
    "latency_ms": 160.0,
    "packet_loss_percent": 6.5
  },
  "projection_steps": 3
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source_node_id` | string | Yes | Link source (e.g. `spine-router`, `router-1`) |
| `target_node_id` | string | Yes | Link target (e.g. `router-1`, `server-1`) |
| `latency_ms` | float | No | Injected latency in milliseconds |
| `packet_loss_percent` | float | No | Injected packet loss (0–100) |
| `bandwidth_mbps` | float | No | Injected bandwidth cap |

**Breach thresholds:**

| Metric | Warning | SLA Breach |
|---|---|---|
| Latency | >100 ms | >150 ms |
| Packet Loss | >2% | >5% |

Constraints checked: `network_sla`, `packet_loss`, `future_latency_projection`

---

#### `inject_storage` — Inject elevated disk IOPS

Simulates storage network path congestion or heavy full-table indexing scans.

```json
{
  "action": "inject_storage",
  "params": {
    "node_id": "droplet-1-tor1/server-2",
    "disk_iops": 3900
  },
  "projection_steps": 5
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | Yes | Target node (compute-node, middleware, or graph-database) |
| `disk_iops` | float | No | Injected IOPS value |
| `capacity_used_gb` | float | No | Injected storage capacity used |

**Breach thresholds:**

| Metric | Warning | Hard Limit (NVMe) |
|---|---|---|
| Disk IOPS | >3000 | >4000 |

Constraints checked: `storage_iops`, `future_iops_projection`

---

#### `migrate_rack` — Cross-droplet rack migration

Atomically moves a node to a different physical rack and ToR switch. Updates network edges and the droplet metadata tag.

```json
{
  "action": "migrate_rack",
  "params": {
    "node_id": "droplet-1-tor1/server-1",
    "target_rack_id": "droplet-2-tor2",
    "target_router_id": "droplet-2-tor2/router-2"
  },
  "projection_steps": 3
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | Yes | Node to migrate |
| `target_rack_id` | string | Yes | Destination rack / droplet |
| `target_router_id` | string | Yes | Destination ToR router |

Constraints checked: `rack_u_space`, `power_envelope`, `network_sla`

---

### Simulation Response

All actions return the same response shape:

```json
{
  "allowed": true,
  "reasons": [],
  "warnings": ["CPU projection exceeds 80% within 2 ticks"],
  "recommendation": "Consider distributing load across server-2 and server-3.",
  "clone_id": "uuid-string",
  "projected_graph": {
    "nodes": [ ... ],
    "edges": [ ... ]
  },
  "projections": [
    { "step": 1, "node_id": "...", "cpu_percent": 93.1, ... },
    ...
  ],
  "tier_results": {
    "power":   { "allowed": true,  "reasons": [] },
    "rack":    { "allowed": true,  "reasons": [] },
    "compute": { "allowed": false, "reasons": ["CPU exceeds critical threshold"] },
    "network": { "allowed": true,  "reasons": [] }
  },
  "scenario_results": [],
  "impact_predictions": {}
}
```

| Field | Description |
|---|---|
| `allowed` | `true` if all 4 constraint tiers passed |
| `reasons` | Hard violations that caused `allowed: false` |
| `warnings` | Non-blocking issues |
| `recommendation` | Human-readable remediation advice |
| `clone_id` | UUID of the sandboxed graph clone used |
| `projected_graph` | Full serialized graph after mutation |
| `projections` | Per-step metric forecast from BehaviorModel |
| `tier_results` | Per-tier pass/fail breakdown |
| `scenario_results` | KMeans workload scenario matches |
| `impact_predictions` | ML impact forecast from ScenarioGenerator |

---

### `GET /api/v1/simulate/actions`

Returns the full catalog of supported actions with parameter specs and examples. Used by the frontend Simulation page to build the action dropdown.

**No request body required.**

---

## 2. NLP / Prompt Endpoint

### `POST /api/v1/metrics/resolve`

Same 3-phase simulation pipeline as `/simulate`, but triggered via natural language text. Gemini parses the intent and resolves entity IDs against the live inventory before running the pipeline.

**Natural language request:**
```json
{
  "request_text": "move server-1 to router-2"
}
```

**Structured fallback (same schema as /simulate):**
```json
{
  "action": "inject_compute",
  "params": {
    "node_id": "droplet-1-tor1/server-1",
    "cpu_percent": 95.0
  }
}
```

**Response** — same shape as `/simulate` plus `parser_metadata`:
```json
{
  "parser_metadata": {
    "request_text": "move server-1 to router-2",
    "parser_used": "gemini",
    "action": "move_server"
  },
  "allowed": true,
  "reasons": [],
  ...
}
```

| `parser_used` value | Meaning |
|---|---|
| `gemini` | Gemini successfully parsed and resolved all entities |
| `rule` | Rule-based fallback parser matched a known pattern |
| `form` | Structured payload was passed directly (no NLP needed) |
| `fallback` | Both parsers failed → request rejected with 422 |

**Error — NLP resolution failed (HTTP 422):**
```json
{
  "detail": [{
    "code": "NLP_REQUEST_UNRESOLVED",
    "path": "request_text",
    "message": "Request text could not be mapped safely or mapped parameters did not match active inventory."
  }]
}
```

**Common causes of NLP failure:**
- Missing required field (e.g. `add_compute` needs `target_rack_id` but none was mentioned)
- Device name not present in live inventory (graph node IDs)
- Gemini returns an action type not in the supported 8-action set
- Ambiguous intent that maps to no recognized action

---

## 3. Chaos Endpoints

### `POST /api/v1/chaos/enable`

Activates chaos mode. While active, every Prometheus scrape tick corrupts live metrics with random noise to simulate a stressed or degrading infrastructure.

**Request Body:**
```json
{
  "nodes": ["droplet-1-tor1/server-1", "droplet-2-tor2/server-3"],
  "scenario": "full"
}
```

| Parameter | Type | Description |
|---|---|---|
| `nodes` | array | Node IDs to affect. Pass `[]` to affect all nodes |
| `scenario` | string | Chaos scenario name (default: `"full"`) |

**Response:**
```json
{
  "message": "🔥 Chaos mode ENABLED",
  "active": true,
  "nodes": ["droplet-1-tor1/server-1"],
  "scenario": "full"
}
```

---

### `POST /api/v1/chaos/disable`

Deactivates chaos mode. Metrics return to healthy baseline on the next Prometheus scrape tick.

**No request body required.**

**Response:**
```json
{
  "message": "✅ Chaos mode DISABLED — system returning to healthy baseline",
  "active": false
}
```

---

### `GET /api/v1/chaos/status`

Returns the current chaos state.

**Response:**
```json
{
  "active": false,
  "nodes": [],
  "scenario": null
}
```

---

### `POST /api/v1/chaos/toggle`

Toggles chaos on if off, off if on. Convenience endpoint for the dashboard toggle button.

**Response:**
```json
{
  "message": "Chaos enabled",
  "active": true
}
```

---

## 4. Reports Endpoints

### `GET /api/v1/reports/health`

Returns overall system health derived from the current live graph node states.

**Response:**
```json
{
  "timestamp": "2026-06-22T10:00:00Z",
  "overall_health": "healthy",
  "state_counts": { "healthy": 26 },
  "critical_nodes": [],
  "warning_nodes": [],
  "chaos_active": false,
  "tick_count": 24
}
```

`overall_health` is `"critical"` if any node is critical, `"warning"` if any node is in warning state, otherwise `"healthy"`.

---

### `GET /api/v1/reports/validate`

Runs the full 4-tier `ValidatorEngine` against the **current live graph** (not a simulation clone). This is the endpoint the **Drift Detection page polls every 8 seconds**.

**Response:**
```json
{
  "timestamp": "2026-06-22T10:00:00Z",
  "allowed": true,
  "reasons": [],
  "warnings": [],
  "tier_results": {
    "power":   { "allowed": true, "reasons": [] },
    "rack":    { "allowed": true, "reasons": [] },
    "compute": { "allowed": true, "reasons": [] },
    "network": { "allowed": true, "reasons": [] }
  }
}
```

---

### `GET /api/v1/reports/node/{node_id}`

Per-node telemetry report with last 10 history points.

**Path parameter:** `node_id` — composite topology ID (e.g. `droplet-1-tor1/server-1`)

**Response:**
```json
{
  "timestamp": "2026-06-22T10:00:00Z",
  "node": {
    "id": "droplet-1-tor1/server-1",
    "role": "compute-node",
    "state": "healthy",
    "metrics": { "cpu_percent": 30.1, "memory_percent": 43.2, ... }
  },
  "history_points": 24,
  "history": [ ... ]
}
```

---

### `GET /api/v1/reports/summary`

Combined full-system dump: orchestrator status + 4-tier validation result + full serialized graph.

---

## 5. Telemetry Endpoints

### `GET /api/v1/telemetry`

Live snapshot of all 26 nodes and 13 edges with their current state and metrics dict.

**Response:**
```json
{
  "nodes": {
    "droplet-1-tor1/server-1": {
      "state": "healthy",
      "metrics": { "cpu_percent": 30.1, "memory_percent": 43.2, "power_watts": 185.0, ... }
    },
    ...
  },
  "edges": {
    "droplet-3-mgmt/spine-router->droplet-1-tor1/router-1": {
      "state": "active",
      "metrics": { "latency_ms": 4.2, "bandwidth_mbps": 612.0, ... }
    },
    ...
  },
  "chaos_active": false,
  "tick_count": 24
}
```

---

### `GET /api/v1/telemetry/status`

Orchestrator tick count and uptime.

**Response:**
```json
{
  "tick_count": 24,
  "uptime_seconds": 192,
  "chaos_active": false
}
```

---

### `GET /api/v1/telemetry/{node_id}`

Single node detail: state, all metrics, rolling average CPU, anomaly flag, and last 5 history points.

**Path parameter:** `node_id` — composite topology ID

**Response:**
```json
{
  "node_id": "droplet-1-tor1/server-1",
  "state": "healthy",
  "metrics": {
    "cpu_percent": 30.1,
    "memory_percent": 43.2,
    "power_watts": 185.0,
    "disk_iops": 890,
    "temperature_celsius": 51.2,
    "rolling_avg_cpu": 28.7
  },
  "rolling_avg_cpu": 28.7,
  "anomaly_detected": false,
  "history_count": 24,
  "recent_history": [ ... ]
}
```

---

## 6. Topology Endpoints

### `GET /api/v1/topology`

Full graph serialized — all 26 nodes and 13 edges with every attribute. Used by the Topology page to render the network diagram.

---

### `GET /api/v1/topology/nodes`

Flat list of all 26 nodes with their full attribute dictionaries.

**Response:**
```json
[
  {
    "id": "droplet-1-tor1/server-1",
    "role": "compute-node",
    "state": "healthy",
    "droplet": "droplet-1-tor1",
    "metrics": { ... }
  },
  ...
]
```

---

### `GET /api/v1/topology/node/{node_id}`

Single node detail including its neighbor list.

**Path parameter:** `node_id` — composite topology ID

**Response:**
```json
{
  "id": "droplet-1-tor1/server-1",
  "role": "compute-node",
  "state": "healthy",
  "metrics": { ... },
  "neighbors": ["droplet-1-tor1/router-1"]
}
```

---

### `GET /api/v1/topology/role/{role}`

Filter and return all nodes matching a given role.

**Available roles:** `compute-node`, `tor-switch`, `spine-switch`, `storage-controller`, `middleware`, `graph-database`

---

### `GET /api/v1/topology/edges`

All 13 edges with source, target, and edge attributes (latency, bandwidth, state).

**Response:**
```json
[
  {
    "source": "droplet-3-mgmt/spine-router",
    "target": "droplet-1-tor1/router-1",
    "state": "active",
    "metrics": { "latency_ms": 4.2, "bandwidth_mbps": 612.0, "packet_loss_percent": 0.04 }
  },
  ...
]
```

---

## 7. Analytics Endpoints

### `GET /api/v1/analytics/profiles`

All node P50/P90/P95/P99 statistical profiles computed from 30-day InfluxDB history.

**Response:**
```json
{
  "ready": true,
  "node_profiles": {
    "droplet-1-tor1/server-1": {
      "cpu_p50": 28.3,
      "cpu_p90": 61.2,
      "cpu_p95": 74.1,
      "cpu_p99": 88.5,
      ...
    }
  },
  "edge_profiles": { ... }
}
```

---

### `GET /api/v1/analytics/profile/{node_id}`

Single node profile plus detected behavioral patterns.

**Response includes extra fields:**
```json
{
  "night_batch_detected": true,
  "weekend_idle_detected": false,
  ...profile fields...
}
```

---

### `GET /api/v1/analytics/edge/{edge_key}`

Edge network profile (latency/bandwidth percentiles). Key format: `spine-router->router-1`

---

### `GET /api/v1/analytics/scenarios`

KMeans-discovered workload clusters from 30-day InfluxDB history.

**Response:**
```json
{
  "scenarios": [
    {
      "label": "Business Hours Peak",
      "centroid": { "cpu_percent": 62.3, "memory_percent": 71.1, ... },
      "size": 1420
    },
    ...
  ],
  "best_k": 3,
  "source": "kmeans"
}
```

---

### `GET /api/v1/analytics/correlations/{node_id}`

Metric correlation pairs for a node — e.g. how strongly CPU load correlates with power draw.

**Response:**
```json
{
  "node_id": "droplet-1-tor1/server-1",
  "correlations": {
    "cpu_vs_power": 0.87,
    "cpu_vs_memory": 0.63,
    "cpu_vs_temperature": 0.79
  }
}
```

---

### `POST /api/v1/analytics/retrain?days=30`

Re-runs the full analytics training pipeline:
- **BehaviorModel** (Random Forest Regressor) — per node, per metric
- **ScenarioGenerator** (KMeans clustering, k=2–6 with silhouette scoring)

**Query parameter:** `days` — number of days of InfluxDB history to use (default: 30)

**Response:**
```json
{
  "message": "Retraining complete",
  "scenarios": 3,
  "best_k": 3
}
```

---

### `GET /api/v1/analytics/anomaly/status`

Shows whether the two-stage anomaly detector models are trained and which devices have per-device models.

**Response:**
```json
{
  "trained": true,
  "if_devices": ["droplet-1-tor1/server-1", "droplet-2-tor2/server-3", ...],
  "rf_devices": ["droplet-1-tor1/server-1", "droplet-2-tor2/server-3", ...],
  "model_path": "models/anomaly_detector.pkl"
}
```

---

### `POST /api/v1/analytics/anomaly/train?days=7&chaos_snapshots=3000`

Trains (or retrains) the two-stage anomaly detector:
1. **Isolation Forest** — unsupervised outlier detection on 7-day raw InfluxDB history
2. **Random Forest Classifier** — binary classifier (normal / anomaly) trained on healthy + synthetic chaos snapshots

| Query Parameter | Default | Description |
|---|---|---|
| `days` | 7 | Days of raw InfluxDB history to train IF on |
| `chaos_snapshots` | 3000 | Number of synthetic chaos data points for RF training |

**Response:**
```json
{
  "status": "trained",
  "devices_trained": 26,
  "if_contamination": 0.05,
  "rf_accuracy": 0.97
}
```

---

### `POST /api/v1/analytics/anomaly/detect/{node_id}`

Scores a live metric snapshot through the full alert pipeline (threshold check → Isolation Forest → RF Classifier).

**Path parameter:** `node_id` — composite topology ID (e.g. `droplet-1-tor1/server-1`)

**Request Body:**
```json
{
  "metrics": {
    "cpu_percent": 91.0,
    "memory_percent": 87.0,
    "power_watts": 295.0,
    "disk_iops": 1200,
    "temperature_celsius": 72.0
  }
}
```

**Response:**
```json
{
  "node_id": "droplet-1-tor1/server-1",
  "anomaly_detected": true,
  "if_score": -0.31,
  "rf_confidence": 0.94,
  "alert_level": "critical",
  "triggered_thresholds": ["cpu_percent > 85%"],
  "recommendation": "Redistribute workload or investigate runaway process."
}
```

**Error — model not trained (HTTP 503):**
```json
{
  "detail": "Anomaly detector not trained. POST /anomaly/train first."
}
```

---

## 8. Quick Reference Table

| Endpoint | Method | Used By | Polling Interval |
|---|---|---|---|
| `/api/v1/simulate` | POST | Simulation page | On demand |
| `/api/v1/simulate/actions` | GET | Simulation page dropdown | On load |
| `/api/v1/metrics/resolve` | POST | Prompt Assistant page | On demand |
| `/api/v1/chaos/enable` | POST | Dashboard chaos toggle | On demand |
| `/api/v1/chaos/disable` | POST | Dashboard chaos toggle | On demand |
| `/api/v1/chaos/status` | GET | Dashboard status card | — |
| `/api/v1/chaos/toggle` | POST | Dashboard toggle button | On demand |
| `/api/v1/reports/health` | GET | Dashboard health cards | ~5s |
| `/api/v1/reports/validate` | GET | Drift Detection page | 8s |
| `/api/v1/reports/node/{id}` | GET | Node detail view | On demand |
| `/api/v1/reports/summary` | GET | Debug / export | On demand |
| `/api/v1/telemetry` | GET | Dashboard / Topology | ~5s |
| `/api/v1/telemetry/status` | GET | Dashboard tick counter | ~5s |
| `/api/v1/telemetry/{node_id}` | GET | Node detail panel | On demand |
| `/api/v1/topology` | GET | Topology page | On load |
| `/api/v1/topology/nodes` | GET | Node search / list | On load |
| `/api/v1/topology/node/{id}` | GET | Node detail | On demand |
| `/api/v1/topology/role/{role}` | GET | Filtered node views | On demand |
| `/api/v1/topology/edges` | GET | Topology page | On load |
| `/api/v1/analytics/profiles` | GET | Analytics dashboard | On load |
| `/api/v1/analytics/profile/{id}` | GET | Node profile panel | On demand |
| `/api/v1/analytics/scenarios` | GET | Scenario explorer | On load |
| `/api/v1/analytics/retrain` | POST | Admin / maintenance | Manual |
| `/api/v1/analytics/anomaly/status` | GET | Anomaly Detection page | On load |
| `/api/v1/analytics/anomaly/train` | POST | Anomaly Detection page | Manual |
| `/api/v1/analytics/anomaly/detect/{id}` | POST | Anomaly Detection page | On demand |

---

## Node ID Format

All node IDs in this API use the composite format:

```
<droplet-id>/<node-name>
```

**Examples:**
- `droplet-1-tor1/server-1` — server-1 in rack droplet-1-tor1
- `droplet-2-tor2/router-2` — router-2 in rack droplet-2-tor2
- `droplet-3-mgmt/spine-router` — spine router in management droplet

The droplet prefix identifies which physical rack/pod the node belongs to.

---

## 4-Tier Validation Reference

Every simulation and live validate call runs through all four tiers:

| Tier | What It Checks | Hard Limits |
|---|---|---|
| **Power** | Total subnet power draw | >1400 W per subnet |
| **Rack** | Available U-space in target rack | Exceeds rack capacity |
| **Compute** | CPU and memory headroom | CPU >95%, Memory >95% |
| **Network** | Link latency and packet loss SLA | Latency >150ms, Loss >5% |
