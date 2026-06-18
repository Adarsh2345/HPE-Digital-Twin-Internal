# HPE Digital Twin Internal

HPE Digital Twin Internal is a local-first infrastructure digital twin platform for modeling, observing, validating, and simulating private-cloud infrastructure. It reads a declarative topology, builds a graph representation of the environment, pulls live telemetry from Prometheus, stores state in supporting data systems, and exposes a React dashboard plus FastAPI APIs for operations, analytics, reports, and what-if simulations.

The project is designed for demo, review, and development workflows where the complete stack can run on one machine using Docker Compose.

## What This Project Does

- Builds an infrastructure topology graph from `infrastructure/infrastructure.yaml`.
- Runs a FastAPI backend that owns orchestration, telemetry, validation, simulation, analytics, and reports.
- Runs a React + Vite frontend dashboard for topology, telemetry, simulation, analytics, drift, and reports.
- Uses local Docker containers for Redis, Neo4j, InfluxDB, Prometheus, and mock Prometheus exporters.
- Generates synthetic server, router, network, power, temperature, and storage metrics for local testing.
- Runs a background telemetry loop every 12 seconds.
- Supports sandboxed what-if simulations such as moving servers, adding compute, injecting CPU/network/storage stress, removing nodes, and migrating racks.
- Supports natural-language simulation requests through `/api/v1/metrics/resolve` when Gemini is configured.

## High-Level Architecture

```text
infrastructure/infrastructure.yaml
        |
        v
Backend Orchestrator
        |
        +--> Builds NetworkX topology graph
        +--> Syncs baseline topology to Neo4j
        +--> Scrapes Prometheus every 12 seconds
        +--> Applies chaos mode when enabled
        +--> Processes telemetry and derives node/link state
        +--> Caches latest state in Redis
        +--> Writes time-series snapshots to InfluxDB
        +--> Serves APIs to the frontend

Docker Local Telemetry Stack
        |
        +--> mock-exporter-droplet1 :9100
        +--> mock-exporter-droplet2 :9101
        +--> mock-exporter-droplet3 :9102
        +--> mock-exporter-droplet4 :9103
        +--> Prometheus :9090 scrapes all exporters

Frontend Dashboard
        |
        +--> Vite dev server :3002
        +--> Calls FastAPI backend :5000
```

## Repository Structure

```text
api/                    FastAPI app, route handlers, request/response models
config/                 Runtime settings and constants
core/                   Orchestrator, graph, telemetry, validation, analytics, simulation logic
docker/                 Local Docker Compose stack and Prometheus config
frontend/               React + Vite dashboard
infrastructure/         Source infrastructure topology YAML
integrations/           Redis, Neo4j, InfluxDB, NetBox integration clients
mock-scripts/           Remote-style mock exporters
mock-scripts-local/     Local Prometheus exporters used by Docker Compose
models/                 Trained/generated analytics model artifacts
schema/                 YAML and domain schema validation
scripts/                Bootstrap, seed, train, sync, and simulation helper scripts
simulation/             Natural-language parser and simulation request models
tests/                  Parser, graph, validator, and simulation tests
terraform-pipeline/     Terraform and cloud-init files for real cloud infrastructure
```

## Main Runtime Components

### Backend

The backend is a FastAPI app served by `run.py`. On startup it:

1. Starts Docker services through `docker/docker-compose.yml` when possible.
2. Loads settings from the root `.env`.
3. Bootstraps the orchestrator.
4. Parses the infrastructure YAML.
5. Builds the base topology graph.
6. Connects to Redis, Neo4j, InfluxDB, and Prometheus.
7. Starts the 12-second telemetry loop.

Backend URL:

```text
http://localhost:5000
```

API docs:

```text
http://localhost:5000/docs
```

### Frontend

The frontend is a React + Vite app in `frontend/`.

Development UI:

```text
http://localhost:3002
```

Production build is served by the backend at:

```text
http://localhost:5000/app
```

after running:

```powershell
cd frontend
npm run build
```

### Docker Services

`docker/docker-compose.yml` starts:

| Service | Purpose | URL / Port |
| --- | --- | --- |
| `twin-redis` | Latest derived-state cache | `localhost:6379` |
| `twin-neo4j` | Topology and live metric graph store | `http://localhost:7474`, Bolt `7687` |
| `twin-influxdb` | Time-series telemetry storage | `http://localhost:8086` |
| `mock-exporter-droplet1` | Local metrics exporter | `localhost:9100` |
| `mock-exporter-droplet2` | Local metrics exporter | `localhost:9101` |
| `mock-exporter-droplet3` | Local metrics exporter | `localhost:9102` |
| `mock-exporter-droplet4` | Local metrics exporter | `localhost:9103` |
| `twin-prometheus-local` | Scrapes local exporters | `http://localhost:9090` |

## What `mock-scripts-local` Does

`mock-scripts-local/` contains four Python Prometheus exporters. Each exporter represents one local droplet and exposes synthetic per-device metrics.

The exporters generate:

- `cpu_percent`
- `memory_percent`
- `disk_iops`
- `power_watts`
- `temperature_celsius`
- `latency_ms`
- `packet_loss_percent`
- `bandwidth_mbps`

Prometheus reads `mock-scripts-local/prometheus.local.yml`, scrapes all four exporters every 12 seconds, and exposes query results at `http://localhost:9090`.

This lets the full project run locally without depending on real DigitalOcean droplets or real hardware telemetry.

## Local Environment Files

The backend reads the root `.env`.

```env
REDIS_HOST=localhost
REDIS_PORT=6379
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=my-super-secret-admin-token-12345
INFLUXDB_ORG=hpe-digital-twin-org
INFLUXDB_BUCKET=telemetry_bucket
PROMETHEUS_URL=http://localhost:9090
```

Optional Gemini configuration for natural-language simulation parsing:

```env
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
```

The frontend reads `frontend/.env`.

```env
VITE_API_BASE_URL=http://localhost:5000
VITE_GRAFANA_URL=http://localhost:3000
VITE_PROMETHEUS_URL=http://localhost:9090
VITE_INFLUXDB_URL=http://localhost:8086
```

Note: the current Docker Compose file does not start Grafana. `VITE_GRAFANA_URL` is reserved for when Grafana is added separately.

## Prerequisites

- Docker Desktop or Docker Engine
- Python 3.12 recommended
- Node.js 18+
- npm
- PowerShell on Windows

## Quick Start

From the repository root:

```powershell
docker compose -f docker/docker-compose.yml up -d --build --wait
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe run.py
```

If dependencies are not installed yet:

```powershell
pip install -r requirements.txt
```

Start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3002
```

## Full Local Workflow

1. Docker Compose starts Redis, Neo4j, InfluxDB, Prometheus, and the four local mock exporters.
2. Each mock exporter publishes Prometheus metrics for a simulated droplet.
3. Prometheus scrapes the exporters every 12 seconds.
4. `run.py` starts the FastAPI backend.
5. The orchestrator loads `infrastructure/infrastructure.yaml`.
6. The topology builder creates a NetworkX graph.
7. Neo4j receives the baseline topology.
8. The telemetry loop queries Prometheus.
9. Raw Prometheus labels are mapped to graph node IDs such as `droplet-1-tor1/server-1`.
10. Telemetry is processed into node and edge health states.
11. Redis receives latest derived state.
12. Neo4j receives live metric snapshots.
13. InfluxDB receives time-series points.
14. The frontend polls the backend APIs and renders the dashboard.
15. Simulations clone the current graph, mutate the clone, validate constraints, and return recommendations without changing the live graph.

## Important URLs

| Target | URL |
| --- | --- |
| Frontend UI | `http://localhost:3002` |
| Backend API | `http://localhost:5000` |
| API docs | `http://localhost:5000/docs` |
| Prometheus | `http://localhost:9090` |
| Neo4j browser | `http://localhost:7474` |
| InfluxDB | `http://localhost:8086` |
| Production frontend through backend | `http://localhost:5000/app` |

Neo4j login:

```text
Username: neo4j
Password: password
```

InfluxDB local setup:

```text
Username: admin
Password: password12345
Org: hpe-digital-twin-org
Bucket: telemetry_bucket
Token: my-super-secret-admin-token-12345
```

## API Overview

Root and health:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic app metadata and route hints |
| `GET` | `/health` | Backend health check |

Topology:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/topology` | Full derived topology graph |
| `GET` | `/api/v1/topology/nodes` | List all nodes |
| `GET` | `/api/v1/topology/node/{node_id}` | Single node detail |
| `GET` | `/api/v1/topology/role/{role}` | Nodes by role |
| `GET` | `/api/v1/topology/edges` | List all edges |

Telemetry:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/telemetry` | Latest telemetry for all nodes and edges |
| `GET` | `/api/v1/telemetry/status` | Orchestrator tick and connection status |
| `GET` | `/api/v1/telemetry/{node_id}` | Single node telemetry and recent history |

Simulation:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/simulate/actions` | Supported simulation actions |
| `POST` | `/api/v1/simulate` | Run structured what-if simulation |

Natural-language metrics and simulation resolution:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/metrics/resolve` | Parse natural language or structured payload, run sandbox simulation, validate, and return report |

Chaos:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/chaos/enable` | Enable chaos mode |
| `POST` | `/api/v1/chaos/disable` | Disable chaos mode |
| `POST` | `/api/v1/chaos/toggle` | Toggle chaos mode |
| `GET` | `/api/v1/chaos/status` | Current chaos state |

Reports:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/reports/health` | Current system health summary |
| `GET` | `/api/v1/reports/validate` | Validate live state |
| `GET` | `/api/v1/reports/node/{node_id}` | Per-node report |
| `GET` | `/api/v1/reports/summary` | Full status, validation, and graph summary |

Analytics:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/analytics/profiles` | Node and edge metric profiles |
| `GET` | `/api/v1/analytics/profile/{node_id}` | Single node profile |
| `GET` | `/api/v1/analytics/edge/{edge_key}` | Single edge profile |
| `GET` | `/api/v1/analytics/scenarios` | Workload scenarios |
| `GET` | `/api/v1/analytics/correlations/{node_id}` | Metric correlations |
| `POST` | `/api/v1/analytics/retrain` | Rebuild analytics profiles |
| `GET` | `/api/v1/analytics/anomaly/status` | Anomaly detector status |
| `POST` | `/api/v1/analytics/anomaly/train` | Train anomaly detector |
| `POST` | `/api/v1/analytics/anomaly/detect/{node_id}` | Detect anomaly for one node snapshot |

## Example API Calls

Check backend health:

```powershell
Invoke-RestMethod http://localhost:5000/health
```

Check telemetry status:

```powershell
Invoke-RestMethod http://localhost:5000/api/v1/telemetry/status
```

Run a structured simulation:

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

Run a natural-language request:

```json
{
  "request_text": "inject CPU 92 percent on server-1"
}
```

Send it to:

```text
POST http://localhost:5000/api/v1/metrics/resolve
```

## Simulation Actions

Supported actions include:

- `move_server`
- `add_compute`
- `remove_node`
- `inject_compute`
- `inject_network`
- `inject_storage`
- `migrate_rack`
- `blast_radius_query` through the NLP model layer

The simulation engine uses a clone of the live graph. That means simulations do not directly mutate the current live topology.

## Validation and Recommendations

The validator checks infrastructure constraints such as:

- Rack capacity
- Power envelope
- Compute saturation
- Memory pressure
- Storage IOPS pressure
- Network latency SLA
- Packet loss
- Future projected risk

The recommendation engine turns validation results into an operational report with suggested remediation.

## Running Tests

```powershell
pytest
```

Key test areas:

- YAML parsing
- Topology graph building
- Constraint validators
- Simulation behavior

## Useful Scripts

| Script | Purpose |
| --- | --- |
| `scripts/bootstrap.py` | Bootstrap project data |
| `scripts/seed_metrics.py` | Seed sample metrics |
| `scripts/seed_influx_history.py` | Seed InfluxDB historical telemetry |
| `scripts/sync_to_neo4j.py` | Sync topology/graph data into Neo4j |
| `scripts/train_models.py` | Train analytics/anomaly models |
| `scripts/run_simulations.py` | Run simulation batches |

## Troubleshooting

If the backend starts but telemetry is empty:

- Confirm Prometheus is reachable at `http://localhost:9090`.
- Confirm mock exporters are running on ports `9100` to `9103`.
- Confirm root `.env` has `PROMETHEUS_URL=http://localhost:9090`.
- Check `/api/v1/telemetry/status` for connection status.

If Neo4j is not connected:

- Open `http://localhost:7474`.
- Login with `neo4j/password`.
- Confirm `NEO4J_URI=bolt://localhost:7687`.

If InfluxDB does not accept writes:

- Open `http://localhost:8086`.
- Confirm org, bucket, and token match `.env`.
- If data was already initialized with different credentials, recreate the Docker volume.

If the frontend cannot reach the backend:

- Confirm backend is running on `http://localhost:5000`.
- Confirm frontend is running on `http://localhost:3002`.
- Confirm `frontend/.env` contains `VITE_API_BASE_URL=http://localhost:5000`.

If natural-language parsing fails:

- Add `GEMINI_API_KEY` to the root `.env`.
- Use full commands with node names, for example: `move server-1 to router-2`.

## Stopping the Stack

```powershell
docker compose -f docker/docker-compose.yml down
```

To remove volumes as well:

```powershell
docker compose -f docker/docker-compose.yml down -v
```

Use `down -v` only when you are okay deleting local InfluxDB and Neo4j persisted data.

## Review Summary

For a project review, explain the system as:

1. A YAML-driven digital twin builds a graph of infrastructure.
2. Local Prometheus exporters simulate live server and network metrics.
3. Prometheus collects those metrics.
4. FastAPI orchestrates the topology, telemetry, persistence, validation, analytics, and simulations.
5. Redis stores latest state, Neo4j stores graph snapshots, and InfluxDB stores telemetry over time.
6. React displays the operational dashboard.
7. What-if simulations run safely on cloned graph state, validate constraints, and produce recommendations.

