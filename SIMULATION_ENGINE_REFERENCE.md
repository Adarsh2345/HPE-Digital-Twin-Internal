# HPE Digital Twin — Simulation Engine Reference

> Everything that happens from the moment a user submits a query to the moment a result is returned.

---

## Table of Contents

1. [Big Picture — How It All Fits Together](#1-big-picture)
2. [Step 1 — NLP Parsing (Gemini)](#2-step-1--nlp-parsing-gemini)
3. [Step 2 — API Entry Points](#3-step-2--api-entry-points)
4. [Step 3 — Graph Cloning (Safe Sandbox)](#4-step-3--graph-cloning-safe-sandbox)
5. [Step 4 — Topology Mutations](#5-step-4--topology-mutations)
6. [Step 5 — Impact Analysis](#6-step-5--impact-analysis)
7. [Step 6 — Future Projection](#7-step-6--future-projection)
8. [Step 7 — Scenario Testing](#8-step-7--scenario-testing)
9. [Step 8 — Validation (4 Tiers)](#9-step-8--validation-4-tiers)
10. [Step 9 — Recommendations](#10-step-9--recommendations)
11. [Step 10 — Final Response](#11-step-10--final-response)
12. [Request Types Reference](#12-request-types-reference)
13. [Simulation Models & Data Structures](#13-simulation-models--data-structures)
14. [Key Source Files](#14-key-source-files)

---

## 1. Big Picture

The simulation engine lets a user ask questions like:

> *"What happens if I move server-1 to router-2?"*
> *"Add a new compute node under router-1"*
> *"What's the blast radius if router-1 fails?"*

The system takes that natural language input, figures out what the user wants, safely simulates the change on a copy of the live infrastructure graph, predicts how metrics will evolve over time, tests the result under different operational scenarios, validates it against capacity constraints, and returns a detailed report — all without touching the real running system.

### End-to-End Flow

```
User Query (text or structured JSON)
            │
            ▼
    [1] NLP Parser (Gemini AI)
        Understands intent → extracts action + parameters
            │
            ▼
    [2] API Route
        /api/v1/metrics/resolve  OR  /api/v1/simulate
            │
            ▼
    [3] Clone Manager
        Deep-copies the live graph → safe sandbox
            │
            ▼
    [4] Mutator
        Applies the requested change to the clone
            │
            ▼
    [5] Impact Analyzer
        Calculates traffic deltas → predicts metric changes
            │
            ▼
    [6] Future Predictor
        Projects metrics 3–10 steps into the future
            │
            ▼
    [7] Scenario Loop
        Tests result under: normal / peak / night_batch / weekend
            │
            ▼
    [8] Validator (4 Tiers)
        Checks power, rack space, compute, storage, network limits
            │
            ▼
    [9] Recommendation Engine
        Generates actionable fixes for any violations
            │
            ▼
    [10] Response
         Verdict (PASS/FAIL) + full report returned to user
```

---

## 2. Step 1 — NLP Parsing (Gemini)

**File:** `simulation/nlp_parser.py`

This is the first thing that runs when a user types a natural language query.

### What It Does

1. Takes the user's raw text (e.g. *"move server-1 to router-2"*)
2. Builds a list of all known node IDs from the live topology (inventory)
3. Sends the text + inventory to **Gemini AI** with a structured prompt
4. Gemini returns a JSON object describing the action and parameters
5. The parser cleans up and validates the response

### What Gemini Returns

Gemini always returns a flat JSON with an `action` field and action-specific fields:

```json
{
  "action": "move_server",
  "server_id": "server-1",
  "target_router_id": "router-2"
}
```

### Supported Actions Gemini Can Identify

| Action | What It Means |
|--------|--------------|
| `move_server` | Move a server from one router to another |
| `add_compute` | Add a new compute node to the topology |
| `remove_node` | Remove a node entirely |
| `inject_compute` | Simulate CPU/memory stress on a node |
| `inject_network` | Simulate latency/packet loss on a link |
| `inject_storage` | Simulate high disk IOPS on a node |
| `migrate_rack` | Move a node to a different droplet/rack |
| `blast_radius_query` | Show what breaks if a device fails |

### ID Resolution

Gemini often returns short names like `"server-1"`. The parser resolves these to full composite IDs:

```
"server-1"  →  "droplet-1-tor1/server-1"
"router-2"  →  "droplet-2-tor2/router-2"
```

This matching is done against the full inventory of graph node IDs.

### Gemini Configuration

| Setting | Value |
|---------|-------|
| Model | `gemini-2.5-flash` (configurable via `GEMINI_MODEL`) |
| Temperature | `0` (deterministic output) |
| Max tokens | `512` |
| Timeout | `15 seconds` |
| Retries | `3 attempts` |
| Response format | Enforced JSON schema |

### Fallback

If Gemini fails, times out, or returns something unresolvable, the parser falls back to:

```json
{
  "action": "blast_radius_query",
  "failed_device_id": "__unresolved__"
}
```

The API then returns a `422 NLP_REQUEST_UNRESOLVED` error to the user.

### Post-Processing Fixes

The parser automatically handles common Gemini inconsistencies:
- Strips markdown code fences (` ```json ... ``` `)
- Flattens nested `"parameters"` or `"params"` keys to the top level
- Fixes known typos (e.g. `"destination_id"` → `"target_router_id"`)

---

## 3. Step 2 — API Entry Points

**File:** `api/routes/simulation.py`, `api/routes/metrics_resolve.py`

Two routes can trigger a simulation:

### Route 1: `/api/v1/metrics/resolve` (NLP First)

- Accepts natural language text: `{"request_text": "move server-1 to router-2"}`
- Runs Gemini parsing first, then full simulation pipeline
- Best for UI / conversational use

### Route 2: `/api/v1/simulate` (Structured)

- Accepts a structured JSON body directly
- Skips NLP parsing
- Best for programmatic use

### Request Body Structure

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

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | One of the 8 supported actions |
| `params` | dict | Action-specific parameters |
| `projection_steps` | int (1–10) | How many steps into the future to project |

### Before Calling the Simulator

The route performs **key remapping** to ensure parameter names are consistent:

```
target_router_id  →  target_router
target_rack_id    →  target_droplet
server_id         →  server
source_node_id    →  source_node
target_node_id    →  target_node
```

This handles differences between what Gemini returns and what the mutator expects.

---

## 4. Step 3 — Graph Cloning (Safe Sandbox)

**File:** `core/simulation/clone_manager.py`

Before anything is changed, the live graph is cloned.

### Why Clone?

The live infrastructure graph is running in production — the orchestrator ticks every 12 seconds updating it with real metrics. If mutations were applied directly to it, they would corrupt the live state and affect real monitoring.

Cloning creates a **completely independent copy** (sandbox) that can be freely mutated, broken, and discarded without any impact on the live system.

### How It Works

```
Live Graph (production)
      │
      │  copy.deepcopy()
      ▼
Clone Graph (sandbox)  ←── all mutations happen here
      │
      │  released after simulation
      ▼
   (discarded)
```

1. A `clone_id` is generated (first 8 chars of a UUID, e.g. `"a3f9b21c"`)
2. The entire NetworkX graph is deep-copied — every node, edge, and attribute
3. The clone is stored in memory under the `clone_id`
4. After simulation completes, the clone is released from memory

### Clone Lifecycle

```
create_clone()  →  apply mutations  →  run analysis  →  release_clone()
```

---

## 5. Step 4 — Topology Mutations

**File:** `core/simulation/mutators.py`

This is where the actual change is applied to the cloned graph. The mutator receives the `action` and `params`, and dispatches to the correct mutation function.

### Structural Mutations (change the topology)

#### `move_server`

Moves a server from its current router to a new one.

```
Before:  router-1 → server-1
After:   router-2 → server-1
```

What happens internally:
- All edges from old router(s) to the server are removed
- The server's subnet is updated to match the new router's subnet
- A new edge is added from `target_router → server`

Returns: `{server, old_routers[], new_router, old_subnet, new_subnet}`

---

#### `add_compute`

Adds a brand new compute node to the graph.

```
Before:  router-1 → server-1, server-2
After:   router-1 → server-1, server-2, new-server
```

What happens internally:
- A new node is created with attributes: `id, name, role, ip, image, droplet, subnet, state="healthy", metrics={}`
- An edge is added from `router → new_node`

Returns: `{node_id, router, subnet}`

---

#### `remove_node`

Removes a node from the graph entirely.

```
Before:  router-1 → server-1
After:   router-1  (server-1 gone, edge also gone)
```

NetworkX automatically removes all edges connected to the node when the node is removed.

Returns: `{removed: node_id}`

---

#### `migrate_rack`

Moves a node from one rack (droplet) to another.

```
Before:  droplet-1-tor1 / server-1 connected to router-1
After:   droplet-2-tor2 / server-1 connected to router-2
```

Internally calls `move_server` for edge rewiring, then updates the `droplet` metadata tag.

Returns: `{node_id, old_droplet, new_droplet, new_router, ...}`

---

### Metric Injection Mutations (stress testing, no topology change)

These don't change the graph structure — they inject specific metric values to simulate a stressed or degraded state.

#### `inject_compute`

Forces specific CPU/memory/power values onto a node.

```
Before:  server-1  →  cpu=33%, memory=45%, power=180W
After:   server-1  →  cpu=92%, memory=75%, power=280W  [injected=true]
```

Default injected values: `cpu=92%, memory=75%, power=280W`

---

#### `inject_network`

Forces specific latency/packet loss values onto a link.

```
Before:  router-1 → server-1  →  latency=12ms, packet_loss=0.05%
After:   router-1 → server-1  →  latency=160ms, packet_loss=0.5%  [injected=true]
```

Default injected values: `latency=160ms, packet_loss=0.5%`

Creates the edge if it doesn't exist yet.

---

#### `inject_storage`

Forces a high IOPS value onto a storage node.

```
Before:  array-ctrl-a  →  disk_iops=800
After:   array-ctrl-a  →  disk_iops=3800  [injected=true]
```

Default injected value: `disk_iops=3800`

---

### Mutation Result

Every mutation returns a dict like:

```json
{
  "success": true,
  "action": "move_server",
  "server": "droplet-1-tor1/server-1",
  "old_routers": ["droplet-1-tor1/router-1"],
  "new_router": "droplet-2-tor2/router-2",
  "old_subnet": "subnet-1-tor1",
  "new_subnet": "subnet-2-tor2"
}
```

If the mutation fails (node not found, invalid params), `"success": false` and the clone is discarded.

---

## 6. Step 5 — Impact Analysis

**File:** `core/analytics/impact_analyzer.py`

After the mutation is applied, the impact analyzer figures out **which nodes are affected** and **by how much**.

### How It Works

1. Compares the graph before and after the mutation
2. Calculates a **traffic delta** (in Mbps) for each affected node
3. Feeds the new traffic load into the **BehaviorModel** to predict metric changes

### Traffic Delta Calculation (per action)

| Action | Affected Nodes | Delta |
|--------|---------------|-------|
| `move_server` | Old routers | −server_bandwidth |
| `move_server` | New router | +server_bandwidth |
| `move_server` | Spine switches | +server_bandwidth × 0.4 |
| `move_server` | Storage fabric | +server_bandwidth × 0.15 |
| `add_compute` | Target router | +300 Mbps |
| `add_compute` | Spine switches | +120 Mbps |
| `remove_node` | Old predecessors | −node_bandwidth |
| `inject_*` | Just the node itself | 0 (no traffic change) |

> The 0.4 and 0.15 multipliers model the reality that not all traffic from a moved server propagates all the way to the spine or storage — only a fraction does.

### Impact Prediction Output

For each affected node, the analyzer returns:

```json
{
  "droplet-1-tor1/router-1": {
    "traffic_delta_mbps": -250.0,
    "compute": {
      "cpu_percent": 28.5,
      "memory_percent": 40.1,
      "power_watts": 165.0
    },
    "network": {
      "latency_ms": 10.2,
      "packet_loss_percent": 0.04
    },
    "storage": {
      "disk_iops": 750
    }
  }
}
```

---

## 7. Step 6 — Future Projection

**File:** `core/simulation/future_predictor.py`

After the mutation and impact analysis, the system projects how metrics will evolve **step by step into the future**.

### How Many Steps?

Controlled by `projection_steps` in the request (1–10, default 3). Each step represents one telemetry tick (12 seconds in real time, but conceptually represents a future time point).

### Two Projection Modes

#### Mode 1: ML-Based (RandomForest BehaviorModel)

If the BehaviorModel has been trained (requires historical data), it uses a trained RandomForest to predict:

```
Inputs:   [cpu_percent, memory_percent, disk_iops, power_watts,
           latency_ms, bandwidth_mbps, hour_of_day, day_of_week]

Outputs:  [cpu_percent, memory_percent, power_watts,
           disk_iops, latency_ms, packet_loss_percent]
```

The bandwidth delta from the impact analyzer is added to the current bandwidth as the main driver of predicted change.

#### Mode 2: Linear Fallback

If the model is not trained, uses fixed degradation multipliers per step:

| Metric | Degradation per Step |
|--------|---------------------|
| CPU | × 1.05 (5% increase per step) |
| Memory | × 1.03 (3% increase per step) |
| Disk IOPS | × 1.10 (10% increase per step) |
| Power | × 1.05 (5% increase per step) |
| Latency | × 1.08 (8% increase per step, exponential) |
| Packet Loss | × 1.20 (20% increase per step) |

All values are clamped to valid ranges (0–100% for percentages, sensible ranges for others).

### Projection Output

```json
[
  {
    "step": 1,
    "nodes": {
      "droplet-1-tor1/server-1": {
        "cpu_percent": 35.2,
        "memory_percent": 47.1,
        "power_watts": 189.0,
        "disk_iops": 880
      }
    },
    "edges": {
      "droplet-1-tor1/router-1->droplet-1-tor1/server-1": {
        "latency_ms": 13.0,
        "packet_loss_percent": 0.06
      }
    }
  },
  { "step": 2, ... },
  { "step": 3, ... }
]
```

---

## 8. Step 7 — Scenario Testing

**File:** `core/analytics/scenario_generator.py`

The mutated graph is tested under multiple **operational scenarios** — different realistic load profiles that the infrastructure might experience.

### How Scenarios Are Discovered

The system runs **KMeans clustering** (k=2 to 6) on 30 days of historical InfluxDB data. Each cluster represents a distinct operational pattern. Silhouette scoring picks the best number of clusters.

### Default Scenarios (when insufficient historical data)

| Scenario | CPU | Memory | IOPS | Bandwidth | Latency | Power |
|----------|-----|--------|------|-----------|---------|-------|
| `normal` | 33% | 45% | 800 | 500 Mbps | 12ms | 180W |
| `business_peak` | 60% | 65% | 2000 | 800 Mbps | 35ms | 240W |
| `night_batch` | 85% | 78% | 3200 | 300 Mbps | 20ms | 290W |
| `weekend` | 20% | 30% | 400 | 100 Mbps | 8ms | 150W |

### What Happens Per Scenario

For each scenario:
1. The mutated graph is **deep-cloned again** (each scenario gets its own copy)
2. Scenario baseline metrics are applied to all compute/network/storage nodes
3. Impact analysis is run under that load
4. One projection step is calculated
5. The 4-tier validator checks it
6. Results are collected: `{scenario_name, status, violations, affected_nodes, predicted_state}`

This answers: *"Does this change hold up not just right now, but during peak load? During batch jobs overnight?"*

---

## 9. Step 8 — Validation (4 Tiers)

**File:** `core/validation/validator_engine.py` + `core/validation/*.py`

After mutation and projection, the resulting graph is validated against physical and operational constraints across 4 tiers.

### Tier 1: Power & Rack Space

**Power Validator** (`power_validator.py`)
- Sums `power_watts` across all nodes in the same subnet/rack
- Warning if total ≥ 1,190W (85% of 1,400W limit)
- Violation if total ≥ 1,400W

**Rack Validator** (`rack_validator.py`)
- Counts U-space occupied per droplet based on device roles
- Role-based form factors:

| Role | U-size |
|------|--------|
| compute-node | 1U |
| tor-router | 2U |
| spine-switch | 4U |
| storage-controller | 2U |
| object-storage | 2U |
| other | 1U |

- Violation if total U-space > 42U per droplet

---

### Tier 2: Compute

**Compute Validator** (`compute_validator.py`)
- Checks CPU and memory per node against capacity limits
- Warning if CPU ≥ 85% of 95% limit
- Violation if CPU ≥ 95%
- Same logic for memory

---

### Tier 3: Storage

**Storage Validator** (`storage_validator.py`)
- Checks `disk_iops` per node
- Warning if IOPS ≥ 4,000
- Violation if IOPS ≥ 8,000

---

### Tier 4: Network

**Network Validator** (`network_validator.py`)
- Checks `latency_ms` and `packet_loss_percent` per edge
- Violation if latency ≥ 150ms (SLA breach)
- Violation if packet loss ≥ 5%

---

### Overall Verdict

If any violation exists across any tier → `allowed: false` → **FAIL ❌**

If only warnings exist → `allowed: true` → **PASS ✅** (with warnings)

### Validation Result Structure

```json
{
  "allowed": false,
  "reasons": [
    "Power envelope exceeded in subnet-2-tor2: 1520W > 1400W limit"
  ],
  "warnings": [
    "CPU utilization on droplet-2-tor2/router-2 approaching capacity: 88%"
  ],
  "tier_results": {
    "power": { "violations": [...], "warnings": [...] },
    "rack": { "violations": [...], "warnings": [...] },
    "compute": { "violations": [...], "warnings": [...] },
    "storage": { "violations": [...], "warnings": [...] },
    "network": { "violations": [...], "warnings": [...] }
  }
}
```

---

## 10. Step 9 — Recommendations

**File:** `core/recommendations/recommendation_engine.py`
**File:** `core/recommendations/remediation_rules.py`

If the validation finds violations, the recommendation engine generates **specific, actionable fixes**.

### How It Works

Each violation message is scanned for trigger keywords. When a keyword matches, a pre-written remediation template is filled in with the relevant node/link name and added to the recommendations list.

### All Remediation Rules

| Trigger Keyword | Recommendation Template |
|----------------|------------------------|
| `power` / `watt` | *"Move heavy workload containers out of {subnet} to balance rack distribution into the alternate subnet."* |
| `u-space` / `rack` | *"Migrate lower-priority containers from {droplet} to a less utilised droplet to free U-space."* |
| `cpu` / `memory` / `compute` | *"Scale {node} workload horizontally — add a sibling compute node under the same ToR switch and redistribute processes."* |
| `iops` / `storage` | *"Attach an additional NVMe volume to {node} or enable read caching (Redis) to reduce raw disk IOPS pressure."* |
| `latency` / `sla` | *"Inspect FRRouting BGP path on {link} — consider enabling ECMP load-balancing or switching to an alternate spine route."* |
| `packet loss` | *"Check physical/virtual NIC on {link} — packet loss indicates a flapping link or MTU mismatch in the Docker bridge network."* |
| `projected` | *"Projected degradation on {node} will breach limits within the simulation horizon — consider live-migrating workloads before the next maintenance window."* |

Deduplication ensures only one recommendation per keyword type is generated even if multiple nodes trigger the same rule.

### Recommendation Report Output

```json
{
  "timestamp": "2026-06-17T10:30:00Z",
  "action": "move_server",
  "params": { "server_id": "...", "target_router_id": "..." },
  "allowed": false,
  "verdict": "FAIL ❌",
  "reasons": ["Power envelope exceeded in subnet-2-tor2: 1520W > 1400W limit"],
  "warnings": [],
  "recommendations": [
    "Move heavy workload containers out of subnet-2-tor2 to balance rack distribution into the alternate subnet."
  ],
  "tier_results": { ... },
  "mutation_summary": { ... },
  "projection_steps": 3
}
```

---

## 11. Step 10 — Final Response

The API assembles the complete response from all pipeline stages and returns it to the user.

### Full Response Structure

```json
{
  "success": true,
  "clone_id": "a3f9b21c",
  "action": "move_server",
  "params": { ... },
  "mutation": { ... },
  "projected_graph": {
    "nodes": [ ... ],
    "edges": [ ... ]
  },
  "projections": [
    { "step": 1, "nodes": { ... }, "edges": { ... } },
    { "step": 2, "nodes": { ... }, "edges": { ... } },
    { "step": 3, "nodes": { ... }, "edges": { ... } }
  ],
  "tier_results": {
    "power": { "violations": [], "warnings": [] },
    "rack": { "violations": [], "warnings": [] },
    "compute": { "violations": [], "warnings": [] },
    "storage": { "violations": [], "warnings": [] },
    "network": { "violations": [], "warnings": [] }
  },
  "scenario_results": [
    {
      "scenario": "business_peak",
      "status": "PASS",
      "violations": [],
      "affected_nodes": [ ... ],
      "predicted_state": { ... }
    }
  ],
  "impact_predictions": {
    "droplet-2-tor2/router-2": {
      "traffic_delta_mbps": 250.0,
      "compute": { "cpu_percent": 45.2, ... },
      "network": { "latency_ms": 18.5, ... },
      "storage": { "disk_iops": 820 }
    }
  },
  "report": {
    "verdict": "PASS ✅",
    "allowed": true,
    "reasons": [],
    "warnings": [ "CPU on router-2 approaching 70%" ],
    "recommendations": []
  }
}
```

---

## 12. Request Types Reference

### `move_server`
```json
{
  "action": "move_server",
  "server_id": "droplet-1-tor1/server-1",
  "target_router_id": "droplet-2-tor2/router-2"
}
```

### `add_compute`
```json
{
  "action": "add_compute",
  "node_id": "new-server-5",
  "target_router_id": "droplet-1-tor1/router-1",
  "target_rack_id": "droplet-1-tor1",
  "ip": "10.10.1.20",
  "role": "compute-node"
}
```

### `remove_node`
```json
{
  "action": "remove_node",
  "node_id": "droplet-1-tor1/server-2"
}
```

### `inject_compute`
```json
{
  "action": "inject_compute",
  "node_id": "droplet-1-tor1/server-1",
  "cpu_percent": 95.0,
  "memory_percent": 88.0,
  "power_watts": 310.0
}
```

### `inject_network`
```json
{
  "action": "inject_network",
  "source_node_id": "droplet-1-tor1/router-1",
  "target_node_id": "droplet-1-tor1/server-1",
  "latency_ms": 200.0,
  "packet_loss_percent": 8.0
}
```

### `inject_storage`
```json
{
  "action": "inject_storage",
  "node_id": "droplet-4-storage/array-ctrl-a",
  "disk_iops": 5500
}
```

### `migrate_rack`
```json
{
  "action": "migrate_rack",
  "node_id": "droplet-1-tor1/server-1",
  "target_rack_id": "droplet-2-tor2",
  "target_router_id": "droplet-2-tor2/router-2"
}
```

### `blast_radius_query`
```json
{
  "action": "blast_radius_query",
  "failed_device_id": "droplet-1-tor1/router-1"
}
```

---

## 13. Simulation Models & Data Structures

### The Graph (NetworkX DiGraph)

The entire infrastructure is represented as a directed graph.

**Node Attributes:**
```python
{
  "id":          "droplet-1-tor1/server-1",
  "name":        "server-1",
  "role":        "compute-node",
  "ip":          "10.10.1.11",
  "subnet":      "subnet-1-tor1",
  "droplet":     "droplet-1-tor1",
  "state":       "healthy",        # healthy / warning / critical
  "cpu":         33.0,             # flat property (%)
  "memory":      45.0,             # flat property (%)
  "metrics": {
    "cpu_percent":          33.0,
    "memory_percent":       45.0,
    "disk_iops":            800,
    "power_watts":          180.0,
    "temperature_celsius":  45.0,
    "rolling_avg_cpu":      32.5,
    "anomaly_detected":     false,
    "injected":             false   # true if from inject_* mutation
  }
}
```

**Edge Attributes:**
```python
{
  "state":         "active",       # active / degraded / down
  "latency":       12.0,           # flat property (ms)
  "packet_loss":   0.05,           # flat property (%)
  "metrics": {
    "latency_ms":            12.0,
    "packet_loss_percent":   0.05,
    "bandwidth_mbps":        800.0,
    "injected":              false
  }
}
```

### BehaviorModel (RandomForest)

Trained per-node, stored at `models/{node_id}__models.pkl`.

```
Inputs:   cpu_percent, memory_percent, disk_iops, power_watts,
          latency_ms, bandwidth_mbps, hour_of_day, day_of_week

Outputs:  cpu_percent, memory_percent, power_watts,
          disk_iops, latency_ms, packet_loss_percent
```

---

## 14. Key Source Files

| Component | File |
|-----------|------|
| NLP Parser | `simulation/nlp_parser.py` |
| Simulation Models | `simulation/models.py` |
| API — NLP Route | `api/routes/metrics_resolve.py` |
| API — Direct Route | `api/routes/simulation.py` |
| API Request Models | `api/models/requests.py` |
| Simulator (orchestrates all steps) | `core/simulation/simulator.py` |
| Clone Manager | `core/simulation/clone_manager.py` |
| Mutators | `core/simulation/mutators.py` |
| Future Predictor | `core/simulation/future_predictor.py` |
| Impact Analyzer | `core/analytics/impact_analyzer.py` |
| Scenario Generator | `core/analytics/scenario_generator.py` |
| Behavior Model | `core/analytics/behavior_model.py` |
| Validator Engine | `core/validation/validator_engine.py` |
| Power Validator | `core/validation/power_validator.py` |
| Rack Validator | `core/validation/rack_validator.py` |
| Compute Validator | `core/validation/compute_validator.py` |
| Storage Validator | `core/validation/storage_validator.py` |
| Network Validator | `core/validation/network_validator.py` |
| Recommendation Engine | `core/recommendations/recommendation_engine.py` |
| Remediation Rules | `core/recommendations/remediation_rules.py` |

---

*Generated for HPE Digital Twin Internal — 2026*
