# Anomaly Detection & Recommendation Pipeline

HPE Digital Twin — Per-device ML anomaly detection with two-phase recommendations (rule engine + Gemini LLM).

---

## Table of Contents

1. [Overview](#overview)
2. [Anomaly Detection Pipeline](#anomaly-detection-pipeline)
   - [Model Architecture](#model-architecture)
   - [Features Used](#features-used)
   - [Threshold Layer](#threshold-layer)
   - [Stage 1 — Isolation Forest](#stage-1--isolation-forest)
   - [Stage 2 — Random Forest Classifier](#stage-2--random-forest-classifier)
   - [Alert Level Logic](#alert-level-logic)
3. [Recommendation Pipeline](#recommendation-pipeline)
   - [Phase 1 — Rule Engine](#phase-1--rule-engine)
   - [Phase 2 — Gemini LLM Enhancement](#phase-2--gemini-llm-enhancement)
4. [Code Flow](#code-flow)
5. [UI Flow](#ui-flow)
6. [How We Tested with Chaos Mode](#how-we-tested-with-chaos-mode)
7. [Manual API Testing](#manual-api-testing)
8. [Thresholds Reference](#thresholds-reference)

---

## Overview

Every live telemetry tick produces a metrics snapshot per device. This snapshot is routed through a unified alert pipeline that:

1. Checks hard thresholds (fast, always runs)
2. Runs per-device ML anomaly detection (IsolationForest + Random Forest)
3. Generates rule-based remediation recommendations
4. Enhances recommendations with Gemini LLM using real metric context

The same recommendation engine is shared with the simulation pipeline — so whether a FAIL comes from a live anomaly or a what-if simulation, recommendations are generated identically.

---

## Anomaly Detection Pipeline

### Model Architecture

A single file `models/anomaly_detector.pkl` bundles **26 separate per-device models**, one for each node in the topology. Each device has its own:

| Object | Purpose |
|--------|---------|
| `StandardScaler` | Normalises live metrics against the device's own healthy baseline |
| `IsolationForest` | Unsupervised — flags statistically abnormal points |
| `RandomForestClassifier` | Supervised — estimates probability it is a real fault vs noise |
| `healthy_stats` dict | Per-feature mean/std for z-score explanation at inference |

All 26 are keyed by composite node ID (e.g. `droplet-1-tor1/server-1`) inside one pickle dict. This means:

- A node that runs warm by nature (high baseline CPU) will not be falsely flagged — it is compared only against its own history
- No cross-device contamination of thresholds

### Features Used

Five metrics are fed into every model:

```
cpu_percent, memory_percent, disk_iops, power_watts, temperature_celsius
```

Network metrics (`latency_ms`, `packet_loss_percent`) are handled exclusively by the threshold layer since they are edge-level metrics, not node-level.

### Threshold Layer

**File:** `core/analytics/threshold_checker.py`

Runs first on every request. Pure rule-based, no ML involved.

| Metric | WARNING | CRITICAL |
|--------|---------|----------|
| CPU % | ≥ 70% | ≥ 85% |
| Memory % | ≥ 75% | ≥ 90% |
| Latency ms | ≥ 100ms | ≥ 150ms |
| Disk IOPS | ≥ 3000 | ≥ 4000 |
| Power W | ≥ 1200W | ≥ 1400W |

A violation at CRITICAL immediately sets `alert_level = "critical"` before the ML layer even runs.

### Stage 1 — Isolation Forest

**File:** `core/analytics/anomaly_detector.py` — `_train_device()` / `detect()`

- Trained on scaled healthy InfluxDB history (7 days by default)
- `contamination=0.05` — by design ~5% of healthy readings will be flagged as false positives
- Returns `if_score` (more negative = more anomalous) and a binary `anomaly: true/false`
- `if_score` around -0.1 to 0.1 = normal; below -0.5 = genuine anomaly; below -0.7 = severe

**Important:** IF alone firing with a very low RF confidence (e.g. 2%) is expected noise, not a real fault. The RF layer is the signal to trust.

### Stage 2 — Random Forest Classifier

Only runs when Stage 1 flags an anomaly.

- Trained on healthy data (label=0) vs synthetic chaos snapshots (label=1)
- Chaos data is generated using `MetricsGenerator(chaos_mode=True)` — 3,000 synthetic high-stress snapshots per device
- Returns `rf_confidence` — probability the point is a real fault (0.0 to 1.0)

**Decision guide:**

| IF Score | RF Confidence | Interpretation |
|----------|---------------|----------------|
| > -0.2 | — | Normal, no anomaly |
| -0.3 to -0.5 | < 0.3 | Borderline — likely IF noise |
| -0.5 to -0.7 | 0.5–0.8 | Genuine warning |
| < -0.7 | > 0.9 | Severe anomaly / chaos-level fault |

### Alert Level Logic

**File:** `core/analytics/alert_pipeline.py` — `run_alert_pipeline()`

```
threshold.critical == True  →  alert_level = "critical"
threshold.any_warning       →  alert_level = "warning"
IF anomaly == True          →  escalates to at least "warning" (never downgrades)
alert_level == "normal"     →  no recommendations generated
```

The `anomaly_type` is derived from the top-2 most deviant features (> 2σ from healthy mean) — for example `disk_iops_high`, `cpu_percent_high`.

---

## Recommendation Pipeline

### Phase 1 — Rule Engine

**File:** `core/recommendations/remediation_rules.py`

The alert pipeline maps trigger names to keyword strings that match remediation rules:

```
cpu_percent trigger     →  "Compute Overload on <node>"
disk_iops trigger       →  "Storage IOPS Breach on <node>"
power_watts trigger     →  "Power Envelope Breach on <node>"
latency_ms trigger      →  "Network SLA Breach on <node>"
packet_loss trigger     →  "Packet Loss Breach on <node>"
```

These keyword strings are matched against `REMEDIATION_RULES` in `remediation_rules.py`. Each rule has a `trigger_keyword` and a `template` string. The matched template is filled with the node/link name extracted from the reason string.

Example output for a compute overload:
> *"Scale droplet-1-tor1/server-1 workload horizontally — add a sibling compute node under the same ToR switch and redistribute processes."*

### Phase 2 — Gemini LLM Enhancement

**File:** `core/llm/gemini_client.py`

After Phase 1 generates base recommendations, if `GEMINI_API_KEY` is set, the Gemini client enhances them with context-aware advice.

The prompt sent to Gemini includes:
- Node ID and role
- Alert level and triggers
- Per-metric values WITH z-scores vs the healthy baseline (e.g. `cpu_percent: 96.0 (healthy 42.3±8.1, z=+6.6σ)`)
- The Phase 1 rule-based recommendations (so Gemini augments rather than repeats)

Gemini returns exactly 3 concise, device-specific recommendations referencing actual metric values.

**Fallback behaviour:** If the API is unreachable, times out, returns an error, or returns unparseable JSON — Phase 1 rule-based recommendations are returned unchanged. The LLM layer never blocks the response.

```
Configuration (.env):
  GEMINI_API_KEY=<your key>
  GEMINI_MODEL=gemini-3.1-flash-lite
  GEMINI_TIMEOUT_SECONDS=15     (default)
  GEMINI_RETRY_ATTEMPTS=3       (default)
```

---

## Code Flow

### Anomaly detect request: `POST /api/v1/analytics/anomaly/detect/{node_id}`

```
api/routes/analytics.py
  └─ anomaly_detect(node_id, payload)
       └─ run_alert_pipeline(node_id, metrics)             [alert_pipeline.py]
            ├─ check_thresholds(node_id, metrics)          [threshold_checker.py]
            │    └─ returns violations/warnings vs constants.py thresholds
            ├─ detector.detect(node_id, metrics)           [anomaly_detector.py]
            │    ├─ scalers[node_id].transform(row)
            │    ├─ if_models[node_id].predict() + score_samples()
            │    ├─ rf_models[node_id].predict_proba()     (if IF flagged anomaly)
            │    └─ _explain() → top-2 deviant features (z-score >2σ)
            ├─ _triggers_to_reasons(triggers, node_id)
            │    └─ maps trigger names → keyword strings for rule matching
            └─ _rec.generate_report(action, params, validation, llm_context)
                 ├─ generate_remediation(reasons)          [remediation_rules.py]
                 │    └─ keyword match → fill template → Phase 1 recs
                 └─ gemini_client.enhance_recommendations() [gemini_client.py]
                      ├─ _build_prompt() with z-score table + base recs
                      ├─ _call() → POST generativelanguage.googleapis.com
                      ├─ _parse() → extract JSON array from response
                      └─ fallback to base_recs on any error
```

### Simulation FAIL path: `POST /api/v1/simulate`

```
api/routes/simulation.py
  └─ run_simulation(req)
       ├─ _simulator.run(base_graph, action, params)       [simulator.py]
       │    └─ BehaviorModel.predict() for projection
       ├─ [re-stamp injected metrics onto projected_graph]  ← fixes BehaviorModel overwrite bug
       ├─ _validator.validate(projected_graph, projections) [validator_engine.py]
       └─ _recommender.generate_report(..., llm_context)   [recommendation_engine.py]
            └─ same Phase 1 + Phase 2 path as above
```

### Model storage

```
models/anomaly_detector.pkl
  └─ dict {
       "scalers":       { node_id: StandardScaler, ... }   # 26 entries
       "if_models":     { node_id: IsolationForest, ... }  # 26 entries
       "rf_models":     { node_id: RandomForestClassifier, ... }
       "healthy_stats": { node_id: { feature: {mean, std} } }
       "_trained":      True
     }
```

---

## UI Flow

### Live Metrics → per-node inline scan

1. Open `ui.html` → **Live Metrics** tab
2. The page calls `GET /api/v1/telemetry` every 12 seconds — this returns current metrics for all 26 nodes pulled from InfluxDB (Prometheus data written by mock exporters)
3. Each node card shows CPU/Memory/Power bars
4. **Click any node card** → the UI immediately calls `POST /api/v1/analytics/anomaly/detect/{node_id}` with that node's current live metrics
5. The inline result shows: IF score, RF confidence, alert level badge, trigger chips, recommendations

### Anomaly Tab → Scan All Nodes

1. Switch to the **Anomaly** tab
2. Click **Scan All Nodes**
3. The UI:
   - Fetches telemetry for all nodes (`GET /api/v1/telemetry`)
   - Fires 26 parallel `POST /api/v1/analytics/anomaly/detect/{node_id}` calls with each node's live metrics
   - Renders result cards sorted: **CRITICAL** first → **WARNING** → **NORMAL**
4. Each card shows:
   - `IF Score` (e.g. -0.7176) — how far outside the normal distribution
   - `RF Confidence` (e.g. 1.00) — probability it is a genuine fault
   - Trigger chips (e.g. `cpu_percent`, `if_anomaly:disk_iops`)
   - Recommendations (Phase 1 rule text or Phase 2 Gemini-enhanced strings)

### Simulate Tab → FAIL with recommendations

1. Switch to the **Simulate** tab
2. Select **Scenario 4: Compute Stress Peak**
3. Set: `cpu_percent=96`, `memory_percent=96`, `power_watts=1450`
4. Click **Run Simulation**
5. Result panel shows `FAIL ❌` with violations and the LLM-enhanced recommendation strings

---

## How We Tested with Chaos Mode

### What chaos mode does

`MetricsGenerator(chaos_mode=True)` generates extreme synthetic metrics — high CPU (80–99%), high IOPS (3500–5000), high power, etc. When chaos mode is enabled via Redis, the live telemetry tick injects these values into InfluxDB instead of normal readings.

### Steps used during testing

```
1. Open Live Metrics tab → toggle Chaos Mode ON
2. Wait ~15 seconds for the next background tick (runs every 12s)
3. Go to Anomaly tab → click Scan All Nodes
4. Result: most compute nodes show CRITICAL / WARNING
   - if_score around -0.70 to -0.75
   - rf_confidence 0.95 to 1.00
   - Gemini recommendations referencing actual chaos-level metric values
5. Toggle Chaos Mode OFF → wait one tick → Scan All Nodes again
   - All nodes return to NORMAL, IF scores back to -0.05 to 0.10
```

### What the numbers mean under chaos

A scan during chaos mode produced (for `droplet-1-tor1/server-1`):
```json
{
  "alert_level": "critical",
  "triggers": ["cpu_percent", "memory_percent", "disk_iops", "if_anomaly:disk_iops"],
  "anomaly": {
    "if_score": -0.7176,
    "rf_confidence": 1.0,
    "anomaly_type": "disk_iops",
    "anomaly_reason": ["disk_iops_high", "cpu_percent_high"]
  },
  "recommendations": [
    "Immediately throttle non-critical background processes using cgroups to reduce CPU from 96.0% and alleviate the 4200 IOPS disk saturation.",
    "Execute 'iostat -x 1' and 'lsof' to identify the specific PID causing the disk IOPS spike and terminate runaway I/O threads.",
    "Implement proactive node-level monitoring alerts for disk queue depth to trigger automated workload migration before thermal thresholds exceed 78.0°C."
  ]
}
```

The IF score of -0.7176 and RF confidence of 1.0 confirm a genuine chaos-level fault, not background noise.

---

## Manual API Testing

### Check model status
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/v1/analytics/anomaly/status"
```

### Scan a single node — healthy values
```powershell
$body = '{"metrics": {"cpu_percent": 42.0, "memory_percent": 55.0, "disk_iops": 800, "power_watts": 180.0, "temperature_celsius": 45.0, "latency_ms": 4.0, "packet_loss_percent": 0.0}}'
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/v1/analytics/anomaly/detect/droplet-1-tor1%2Fserver-1" -ContentType "application/json" -Body $body
# Expected: alert_level = "normal", no recommendations
```

### Scan a single node — chaos-level values
```powershell
$body = '{"metrics": {"cpu_percent": 96.0, "memory_percent": 92.0, "disk_iops": 4200, "power_watts": 350.0, "temperature_celsius": 78.0, "latency_ms": 5.0, "packet_loss_percent": 0.1}}'
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/v1/analytics/anomaly/detect/droplet-1-tor1%2Fserver-1" -ContentType "application/json" -Body $body
# Expected: alert_level = "critical", if_score ~-0.72, rf_confidence ~1.0, Gemini recommendations
```

### Retrain models (after adding new history data)
```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/v1/analytics/anomaly/train?days=7&chaos_snapshots=3000"
```

### Run simulation FAIL (no chaos needed)
```powershell
$body = '{"action":"inject_compute","params":{"node_id":"droplet-1-tor1/server-1","cpu_percent":96,"memory_percent":96,"power_watts":1450},"projection_steps":3}'
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/v1/simulate" -ContentType "application/json" -Body $body
# Expected: verdict = "FAIL ❌", violations + LLM-enhanced recommendations
```

---

## Thresholds Reference

### Compute thresholds (`config/constants.py`)

| Metric | WARNING | CRITICAL |
|--------|---------|----------|
| `cpu_percent` | 70% | 85% |
| `memory_percent` | 75% | 90% |
| `disk_iops` | 3,000 | 4,000 |
| `power_watts` | 1,200 W | 1,400 W |
| `latency_ms` | 100 ms | 150 ms |

### Simulation validator limits

| Constraint | Limit |
|-----------|-------|
| CPU capacity | 95% |
| Memory capacity | 95% |
| Subnet total power | 1,400 W |
| Storage IOPS | 4,000 |
| Network latency SLA | 150 ms |

---

## Key Files

| File | Role |
|------|------|
| `core/analytics/anomaly_detector.py` | IsolationForest + RF Classifier per-device, train/detect/save/load |
| `core/analytics/threshold_checker.py` | Hard threshold rule checks (runs before ML) |
| `core/analytics/alert_pipeline.py` | Combines threshold + IF/RF + recommendations into one alert envelope |
| `core/recommendations/remediation_rules.py` | Keyword-matched rule templates (Phase 1) |
| `core/recommendations/recommendation_engine.py` | Wraps rule engine + Gemini LLM call |
| `core/llm/gemini_client.py` | Gemini HTTP client, prompt builder, response parser, fallback logic |
| `api/routes/analytics.py` | REST endpoints: `/anomaly/status`, `/anomaly/train`, `/anomaly/detect/{id}` |
| `api/routes/simulation.py` | Simulation FAIL path also routes through recommendation engine |
| `models/anomaly_detector.pkl` | Trained model bundle (26 devices, tracked in git) |
| `config/settings.py` | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS` |
| `.env` | Local overrides: `PROMETHEUS_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL` |
