# HPE Digital Twin

HPE Digital Twin is a private-cloud infrastructure modelling and simulation platform. It represents racks, routers, compute nodes, storage services, management components, topology links, and telemetry as a software twin so teams can inspect current state, run what-if simulations, validate capacity constraints, and reason about operational risk before making changes.

This README is written for a newcomer. It summarizes the current project direction from the `sowmithra/test-ui` branch analysis and notes the runnable layout currently present on `main`.

## What The System Does

At a high level, the platform:

- Loads infrastructure definitions from structured configuration.
- Builds an in-memory topology graph.
- Scrapes or generates telemetry for compute, storage, network, and power signals.
- Derives live node/link health from that telemetry.
- Exposes topology, telemetry, reports, simulation, chaos, and analytics APIs.
- Provides a frontend dashboard for topology exploration and operational workflows.
- Runs isolated what-if simulations without mutating the live graph.
- Validates proposed changes against power, rack, compute, storage, and network constraints.
- Produces recommendations when a change is risky or denied.

## Architecture Overview

The target application is organized around a central orchestrator:

```text
Infrastructure YAML
  -> parser / loader
  -> NetworkX topology graph
  -> telemetry scraper / processor
  -> derived live graph
  -> API routes
  -> frontend pages
```

The orchestrator is responsible for:

1. Loading the infrastructure source of truth.
2. Building the initial topology graph.
3. Connecting optional persistence services such as Redis, Neo4j, and InfluxDB.
4. Starting a background telemetry loop.
5. Updating the derived graph with latest metrics and health state.
6. Serving that state to API routes.

## Main Runtime Components

The complete system uses:

| Area | Technology |
| --- | --- |
| API | FastAPI, Uvicorn |
| Graph model | NetworkX |
| Validation | Pydantic, custom constraint validators |
| Telemetry | Prometheus-style metrics, mock exporters |
| Cache | Redis |
| Graph persistence | Neo4j |
| Time-series storage | InfluxDB |
| Analytics | NumPy, scikit-learn |
| Frontend | React, Vite, TypeScript |
| Topology UI | React Flow |

## Running The Baseline On Main

Install dependencies:

```bash
cd digital-twin-core
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start supporting services if needed:

```bash
docker compose up -d
```

Run the baseline API:

```bash
uvicorn src.api.main:app --reload
```

The exact routes available on `main` depend on the baseline API implementation under `digital-twin-core/src/api/`.

## Running The Full FastAPI/React System

In the fuller implementation from the analysed branch, the backend is started from the repository root:

```bash
pip install -r requirements.txt
docker compose -f docker/docker-compose.yml up -d --wait
python run.py
```

The backend runs on:

```text
http://localhost:5000
```

Useful URLs:

```text
http://localhost:5000/health
http://localhost:5000/docs
http://localhost:5000/api/v1/topology
http://localhost:5000/api/v1/telemetry/status
```

The frontend is started with:

```bash
cd frontend
npm install
npm run dev
```

It runs on:

```text
http://localhost:3002
```

## Environment Variables

Common runtime settings in the full implementation:

```text
PROMETHEUS_URL=http://localhost:9090
API_HOST=0.0.0.0
API_PORT=5000
TELEMETRY_INTERVAL=12
REDIS_HOST=localhost
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
INFLUXDB_URL=http://localhost:8086
INFLUXDB_ORG=hpe-digital-twin-org
INFLUXDB_BUCKET=telemetry_bucket
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

For local telemetry, set:

```text
PROMETHEUS_URL=http://localhost:9090
```

Without a Gemini key, natural-language parsing should fall back to deterministic or rule-based handling depending on the branch implementation.

## Key API Areas

The full system exposes APIs under `/api/v1`:

| Area | Prefix | Purpose |
| --- | --- | --- |
| Topology | `/api/v1/topology` | Full graph, node list, edges, node details |
| Telemetry | `/api/v1/telemetry` | Latest metrics and orchestrator tick status |
| Simulation | `/api/v1/simulate` | Isolated what-if simulation |
| Natural language | `/api/v1/metrics/resolve` | Convert text intent into simulation request |
| Chaos | `/api/v1/chaos` | Toggle synthetic degraded telemetry |
| Reports | `/api/v1/reports` | Health, validation, node and summary reports |
| Analytics | `/api/v1/analytics` | Profiles, scenarios, correlations, anomaly APIs |

Example simulation request:

```json
{
  "action": "inject_compute",
  "params": {
    "node_id": "droplet-1-tor1/server-1",
    "cpu_percent": 92,
    "memory_percent": 88,
    "power_watts": 310
  },
  "projection_steps": 5
}
```

## Simulation Model

Simulations are designed to be safe. The system clones the current graph, applies the requested change to the clone, projects future metrics, validates the result, and returns a decision report.

Supported actions in the fuller branch include:

| Action | Meaning |
| --- | --- |
| `move_server` | Move a compute node to another ToR router |
| `add_compute` | Add a compute node under a rack/router |
| `remove_node` | Remove/decommission a node |
| `inject_compute` | Inject CPU, memory, and power stress |
| `inject_network` | Inject latency and packet-loss on a link |
| `inject_storage` | Inject disk IOPS pressure |
| `migrate_rack` | Move a node between racks |

Simulation responses include:

- Verdict and allow/deny status.
- Reasons and warnings.
- Recommendations.
- Mutation summary.
- Projected graph.
- Future projections.
- Tier/constraint results.
- Scenario and impact results where enabled.

## Validation Model

The system validates both live state and simulated future state.

Important constraint areas:

- Rack U-space.
- Power envelope.
- Compute CPU/memory headroom.
- Storage IOPS and capacity.
- Network latency, packet loss, and bandwidth.
- Future projected breaches.

The important idea is that a proposed change should not be approved only because static inventory says there is enough capacity. The system should also account for live telemetry and projected risk.

## Telemetry And Chaos

Telemetry is gathered from Prometheus-compatible sources or mock exporters. A background loop updates the derived graph on a fixed interval.

Chaos mode can inject degraded telemetry so the system can demonstrate failure handling. Depending on branch, scenarios may include:

- Compute saturation.
- Storage IOPS pressure.
- Thermal rise.
- Network latency.
- Packet loss.
- PDU/router/storage-controller style failures.

Chaos affects telemetry; simulation affects only cloned graph state.

## Frontend Pages

The React/Vite frontend in the fuller implementation includes:

| Route | Purpose |
| --- | --- |
| `/` | Dashboard overview |
| `/topology` | Interactive infrastructure graph |
| `/simulation` | Form-driven what-if simulation |
| `/prompt` | Natural-language simulation assistant |
| `/drift` | Validation/drift view |
| `/anomaly` | Anomaly training and detection workflows |
| `/analytics` | Behavior profiles, scenarios, correlations |
| `/reports` | Health, validation, and summary reports |

## Testing

For the fuller Python backend:

```bash
pytest tests/
```

Useful test areas:

- Graph construction.
- YAML/schema parsing.
- Simulation mutations.
- Constraint validators.
- Natural-language parser.
- API contracts.
- Unified simulation features.

## Common Gotchas

- `main` and feature branches may not have identical layouts.
- The most complete FastAPI/React implementation is represented by the analysed `sowmithra/test-ui` branch.
- Graph node IDs often use canonical composite IDs such as `droplet-1-tor1/server-1`.
- Prometheus labels may use short names like `server-1`, so metric adapters must map short names to graph IDs.
- Redis, Neo4j, and InfluxDB are useful but should not prevent the backend from starting if unavailable.
- Simulation changes are isolated unless a separate live-apply route is explicitly used.
- A missing LLM key should not break core simulation flows.

## Recommended First Reading Path

For new contributors:

1. Read this README.
2. Inspect `digital-twin-core/src/` on `main`.
3. Compare the fuller branch implementation for `api/`, `core/`, `simulation/`, and `frontend/`.
4. Start with topology loading and graph construction.
5. Then follow telemetry into derived state.
6. Finally study simulation, validation, and recommendation flow.
