# Codebase Map — Every File Explained

A folder-by-folder, file-by-file guide to what each piece of the HPE Digital Twin does.
Use this to understand someone else's code, onboard a new team member, or navigate a bug.

---

## Root Level

| File | What it does |
|---|---|
| `run.py` | **Start here.** Ensures Docker (Redis + Neo4j) is up, then launches the FastAPI server via uvicorn on port 5000 |
| `ui.html` | Single-file frontend UI — no build step, open directly in browser. Has Live Metrics, Simulate, Anomaly, Chaos, NLP, and Reports tabs with a live pipeline animation panel |
| `.env` | Local environment overrides (not committed). Must set `PROMETHEUS_URL=http://localhost:9090` for local dev + Gemini credentials |
| `.gitignore` | Ignores venv, pycache, `.env`. Has `!models/anomaly_detector.pkl` exception so the trained model IS committed |
| `requirements.txt` | Python dependencies |

---

## `api/` — FastAPI Application Layer

The HTTP surface. Nothing here contains business logic — it only validates requests, calls core modules, and returns responses.

### `api/main.py`
Registers all route routers with the FastAPI app. Starts the background telemetry loop on startup. Configures CORS. The `app` object uvicorn imports.

### `api/models/requests.py`
Pydantic request models — `SimulationRequest`, `ChaosRequest`, etc. Defines what JSON shapes the API accepts and validates.

### `api/routes/`

| File | Endpoint(s) | What it does |
|---|---|---|
| `topology.py` | `GET /api/v1/topology` `/nodes` `/edges` | Returns the current graph topology as JSON. Nodes = devices, edges = connections |
| `telemetry.py` | `GET /api/v1/telemetry` `/telemetry/status` | Returns the latest derived state snapshot — all 26 nodes with metrics and HEALTHY/WARNING/CRITICAL states |
| `simulation.py` | `POST /api/v1/simulate` `GET /simulate/actions` | Runs a what-if simulation: clone graph → mutate → project → validate → recommend. Also lists all supported actions |
| `analytics.py` | `GET /analytics/profiles` `/scenarios` `/correlations` `POST /anomaly/train` `POST /anomaly/detect/{id}` | Analytics endpoints. The anomaly detect endpoint runs the full IF + RF + alert pipeline for one node |
| `metrics_resolve.py` | `POST /api/v1/metrics/resolve` | NLP endpoint. Takes plain English text, parses with Gemini, runs the full simulation pipeline, returns structured result |
| `chaos.py` | `POST /api/v1/chaos/enable` `/disable` `GET /chaos/status` | Toggles chaos mode in Redis. Chaos injects extreme metrics on the next telemetry tick |
| `reports.py` | `GET /api/v1/reports/health` `/validate` `/summary` `/node/{id}` | Pre-built report views aggregating topology + telemetry + validation state |

---

## `core/` — Business Logic

Everything the platform actually does.

### `core/orchestrator.py`
**The brain.** Bootstraps the entire system on startup and runs the 12-second heartbeat loop. Holds references to every subsystem. Exposes `get_derived_graph()` (NetworkX object for simulation) and `get_derived_state()` (dict for the API).

### `core/parser/`

| File | What it does |
|---|---|
| `yaml_parser.py` | Reads `infrastructure/infrastructure.yaml` into a Python dict. Validates required fields |
| `topology_loader.py` | Converts the parsed YAML dict into a structured topology object (nodes list + edges list) that the graph builder understands |

### `core/graph/`

| File | What it does |
|---|---|
| `topology_builder.py` | Takes the topology object and builds the initial NetworkX `DiGraph`. Every node gets attributes: `role`, `ip`, `subnet`, `droplet`, `metrics={}`. Edges get `state`, `metrics={}` |
| `derived_state_builder.py` | Takes a live telemetry snapshot and the base graph. Merges metrics into node/edge attributes. Derives `HEALTHY`/`WARNING`/`CRITICAL` state based on thresholds |
| `graph_serializer.py` | `graph_to_dict()` → serialize NetworkX graph to JSON-safe dict. `dict_to_graph()` → deserialize back. Used everywhere the graph needs to cross an API boundary |
| `state_builder.py` | Lower-level helper — builds the initial node state dict from topology YAML fields |

### `core/telemetry/`

| File | What it does |
|---|---|
| `prometheus_telemetry_adapter.py` | **Core telemetry bridge.** Fires PromQL queries to Prometheus, disambiguates bare device names to composite IDs using `(droplet, name)` tuples. Returns `{"nodes":{...}, "edges":{...}}` |
| `prometheus_scraper.py` | Thin wrapper that holds `prometheus_url` from settings, calls the adapter. Falls back to MetricsGenerator if Prometheus is unreachable |
| `metrics_generator.py` | Generates synthetic Gaussian metrics. Used as: (1) fallback when Prometheus is down, (2) chaos training data source for the RF classifier |
| `chaos_engine.py` | Reads Redis `digital_twin:chaos_mode` key. When active, overwrites snapshot metrics with extreme values before they enter the processing pipeline |
| `telemetry_processor.py` | Maintains rolling average windows (last ~50 samples) per node. Adds `rolling_avg_cpu`, `rolling_avg_memory`, and a simple `anomaly_detected` flag (|current - avg| > 25%) |

### `core/simulation/`

| File | What it does |
|---|---|
| `simulator.py` | Orchestrates the full simulation: (1) clone graph, (2) apply mutator, (3) run BehaviorModel projection N steps. Returns `{success, clone_id, projected_graph, projections, mutation_summary}` |
| `clone_manager.py` | Creates isolated deep copies of the NetworkX graph using `copy.deepcopy()`. Each simulation runs on its own clone so the live graph is never modified |
| `mutators.py` | Implements every topology mutation: `move_server` (reroute edge), `add_compute` (add node), `remove_node` (delete node), `inject_compute/network/storage` (set metric values), `migrate_rack` (combined move + tag update) |
| `future_predictor.py` | Wraps `BehaviorModel`. Runs N-step projection: predicts future metric values at each step using the trained RF regressor. Populates the `projections` list returned by the simulator |
| `impact_analyzer.py` | Graph traversal after mutation. Computes traffic redistribution deltas — which downstream nodes see increased load. Feeds `impact_predictions` in the simulation response |

### `core/analytics/`

| File | What it does |
|---|---|
| `anomaly_detector.py` | **Per-device two-stage ML pipeline.** Trains one IsolationForest + one RandomForestClassifier + one StandardScaler per device from InfluxDB history. `detect()` runs a live snapshot through both stages and returns `if_score`, `rf_confidence`, `anomaly_type` |
| `alert_pipeline.py` | **Single entry point for live anomaly evaluation.** Combines threshold_checker + anomaly_detector + RecommendationEngine into one call. Returns a unified `alert_level` + `recommendations` envelope |
| `threshold_checker.py` | Pure rule-based metric checks (CPU > 85% = CRITICAL, etc.) against `config/constants.py` thresholds. Runs first — no ML involved. Always catches hard violations even if the model isn't loaded |
| `behavior_model.py` | RandomForest regressor trained on healthy InfluxDB history. Predicts future metric values for N-step projection in simulation. NOT used in anomaly detection |
| `historical_analyzer.py` | Queries InfluxDB for full metric history. Computes P50/P90/P95/P99 profiles per node and edge. Detects night-batch patterns and weekend-idle patterns |
| `model_registry.py` | Bootstraps and holds references to all analytics models (HistoricalAnalyzer, ScenarioGenerator, BehaviorModel, AnomalyDetector). Single `registry` singleton used everywhere |
| `scenario_generator.py` | K-means clustering on historical metric vectors. Discovers distinct workload patterns (e.g., "normal daytime", "batch overnight"). Exposes `GET /analytics/scenarios` |
| `impact_predictor.py` | Predicts downstream impact of topology changes. Used by ImpactAnalyzer |

### `core/validation/`

The 4-tier constraint system. Each validator is independent; `ValidatorEngine` runs all of them.

| File | What it does |
|---|---|
| `validator_engine.py` | Runs all validators in sequence. Aggregates `reasons` (violations) and `warnings`. Returns `{allowed, reasons, warnings, tier_results}` |
| `compute_validator.py` | Checks `cpu_percent ≥ 95%` and `memory_percent ≥ 95%` on compute-node roles. Fires per-node |
| `power_validator.py` | Groups nodes by subnet. Sums total power watts across all nodes in the subnet. Flags if total > 1400W (CRITICAL) or > 1200W (WARNING) |
| `rack_validator.py` | Checks U-space (physical rack slot) availability. Each droplet has a fixed U-capacity; counts occupied slots after mutation |
| `network_validator.py` | Checks edge `latency_ms ≥ 150ms` and `packet_loss_percent ≥ 5%`. Also validates projected SLA breaches from future_predictor output |

### `core/recommendations/`

| File | What it does |
|---|---|
| `recommendation_engine.py` | Wraps remediation_rules + optional Gemini LLM call. `generate_report()` takes validation result, calls rule engine for base recs, then calls `gemini_client.enhance_recommendations()` if context is provided. Returns the full simulation/alert report dict |
| `remediation_rules.py` | List of `{trigger_keyword, template}` dicts. `generate_remediation(reasons)` does keyword substring matching and fills templates. Rules cover: Power Envelope Breach, Rack U-Space Breach, Compute Overload, Storage IOPS Breach, Network SLA Breach, Packet Loss Breach |

### `core/llm/`

| File | What it does |
|---|---|
| `__init__.py` | Empty — makes `core/llm/` a Python package |
| `gemini_client.py` | HTTP client for Gemini recommendation enhancement. `enhance_recommendations(context, base_recs, action)` builds a z-score-aware prompt (actual metric values vs healthy baseline), calls Gemini `generateContent` API, parses the JSON array response. Falls back to `base_recs` on any error |

---

## `simulation/` — NLP Simulation Models

| File | What it does |
|---|---|
| `nlp_parser.py` | Sends natural language text to Gemini with a strict JSON schema. Resolves short IDs to composite graph IDs. Falls back to `blast_radius_query` if Gemini fails. Full details in `docs/NLP_PARSER_ENGINE.md` |
| `models.py` | `SimulationRequest` Pydantic model — the canonical shape of a parsed simulation intent. `normalize_request()` handles field name aliases from Gemini |

---

## `config/`

| File | What it does |
|---|---|
| `settings.py` | All runtime configuration loaded from environment / `.env`. Prometheus URL, InfluxDB credentials, Neo4j credentials, Redis config, Gemini credentials, API port, telemetry interval, power/compute/network limits |
| `constants.py` | Static values that don't change at runtime: `NODE_ROLES`, `NODE_STATES`, `EDGE_STATES`, `WARNING_THRESHOLDS`, `CRITICAL_THRESHOLDS`, `REDIS_KEYS` |

---

## `integrations/` — External Service Clients

### `integrations/influxdb/`

| File | What it does |
|---|---|
| `influx_client.py` | Wraps InfluxDB Python SDK. `write_node_metrics()` and `write_edge_metrics()` write time-series points every tick. `connect()` verifies the bucket exists |
| `history_fetcher.py` | Reads historical metric series from InfluxDB. `fetch_node_series_raw(days=7)` returns per-device per-feature time series arrays. Used by the anomaly detector for training data |

### `integrations/neo4j/`

| File | What it does |
|---|---|
| `neo4j_client.py` | Wraps the Neo4j Python driver. `save_base_topology()` writes the initial graph structure. `save_live_metrics()` snapshots derived state per tick. Enables graph queries and timeline replay |

### `integrations/redis/`

| File | What it does |
|---|---|
| `redis_client.py` | Wraps the Redis client. Stores `DERIVED_STATE` (latest snapshot JSON) and `CHAOS_MODE` (boolean flag). Optional — the system degrades gracefully if Redis is offline |

### `integrations/netbox/`

| File | What it does |
|---|---|
| `netbox_client.py` | Planned integration with NetBox IPAM/DCIM. Would allow the topology to be auto-populated from real datacenter inventory rather than YAML |

---

## `infrastructure/`

| File | What it does |
|---|---|
| `infrastructure.yaml` | **The source of truth for the topology.** Defines all 26 nodes (device ID, role, IP, subnet, droplet) and all edges (source → target). This is what the YAML parser loads on startup |

---

## `models/`

| File | What it does |
|---|---|
| `anomaly_detector.pkl` | **Tracked in git.** Single pickle file containing 26 per-device anomaly models. Each entry: `StandardScaler` + `IsolationForest` + `RandomForestClassifier` + `healthy_stats` dict. Loaded at startup; only needs retraining if topology or history changes significantly |
| `*_models.pkl` | Other per-device model files from a different architecture experiment. NOT loaded by the current codebase — can be ignored |

---

## `docs/`

| File | What it documents |
|---|---|
| `NLP_PARSER_ENGINE.md` | Full NLP flow: Gemini prompt, JSON schema, ID resolution, fallback, examples |
| `TELEMETRY_ADAPTER.md` | Full telemetry pipeline: Prometheus scrape → ID mapping → chaos → processing → InfluxDB |
| `ANOMALY_AND_RECOMMENDATIONS.md` | IF + RF anomaly pipeline and two-phase recommendation engine |
| `CODEBASE_MAP.md` | This file — every folder and file explained |

---

## `docker/`

| File | What it does |
|---|---|
| `docker-compose.yml` | Starts Redis + Neo4j. Run.py calls `docker compose up -d --wait` on startup to ensure these are healthy before the API starts |

---

## `mock-scripts/`

Scripts and configs for the 4 mock Prometheus exporters (one per droplet). They expose `/metrics` on ports 9100–9103 and simulate real hardware metric patterns with Gaussian noise.

---

## `tests/`

Unit tests for validators, graph serializer, mutators, and the alert pipeline. Run with `pytest`.

---

## `scripts/`

| File | What it does |
|---|---|
| `train_models.py` | Standalone script to train the anomaly detector from scratch. Calls `detector.train(days=7, chaos_snapshots=3000)` and saves the `.pkl`. Run this when you add new devices or have fresh enough InfluxDB history |
| `bootstrap.py` | Loads topology and prints a summary — used for quick sanity checks without starting the full server |

---

## How It All Connects — The Request Lifecycle

```
Browser (ui.html)
    │
    │  HTTP POST /api/v1/simulate
    ▼
api/routes/simulation.py
    │  validates SimulationRequest via Pydantic
    ▼
core/orchestrator.get_derived_graph()     ← live 26-node NetworkX graph
    │
    ▼
core/simulation/simulator.py
    ├── core/simulation/clone_manager.py   → isolated copy
    ├── core/simulation/mutators.py        → apply action
    └── core/simulation/future_predictor.py → N-step projection
    │
    ▼
core/validation/validator_engine.py
    ├── compute_validator.py
    ├── power_validator.py
    ├── rack_validator.py
    └── network_validator.py
    │
    ▼
core/recommendations/recommendation_engine.py
    ├── remediation_rules.py               → Phase 1: rule-based
    └── core/llm/gemini_client.py          → Phase 2: Gemini enhanced
    │
    ▼
HTTP response → ui.html pipeline panel animates each stage
```
