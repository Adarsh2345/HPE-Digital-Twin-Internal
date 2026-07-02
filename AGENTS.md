# AGENTS.md — HPE Digital Twin

## Project Overview

Python/FastAPI backend + React/Vite frontend. Builds a live infrastructure topology graph from YAML, scrapes Prometheus telemetry on a 12s loop, caches to Redis/Neo4j/InfluxDB, and provides NLP-driven what-if simulation via Google Gemini with regex fallback.

## Running

### Backend
```powershell
pip install -r requirements.txt
docker compose -f docker/docker-compose.yml up -d --wait   # Redis, Neo4j, InfluxDB, mock exporters, local Prometheus
python run.py
```
Server starts on `http://0.0.0.0:5000`. Docs at `/docs`.

Modes: `python run.py` (server), `python run.py --bootstrap` (graph only), `python run.py --demo` (one-shot validation demo).

### Frontend
```powershell
cd frontend && npm install && npm run dev
```
Opens at `http://localhost:3002`. Proxies `/api` to `:5000`. Production build served at `/app` when `frontend/dist` exists.

### Environment

Create `.env` at project root (gitignored):
```
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
```
Prometheus URL defaults to remote droplet (`168.144.91.25:9090`). For local mock stack, set `PROMETHEUS_URL=http://localhost:9090`.

## Architecture

- **Entry point**: `run.py` → `api/main.py` (FastAPI app) → `core/orchestrator.py` (singleton)
- **Orchestrator bootstrap**: YAML parse → topology graph build → Redis/Neo4j/InfluxDB connect → ML analytics bootstrap
- **Telemetry loop**: 12s async tick → Prometheus scrape → chaos engine → processor → derived state → cache to Redis + Neo4j + InfluxDB
- **API routes**: `api/routes/` — topology, telemetry, simulation, chaos, reports, analytics, metrics_resolve
- **NLP parser**: `simulation/nlp_parser.py` — Gemini → regex rules → fallback. 8 supported actions.
- **Infra YAML**: `infrastructure/infrastructure.yaml` parsed by `core/parser/yaml_parser.py`

## Key Gotchas

- **Prometheus label mismatch**: Prometheus uses bare names (`server-1`), topology graph uses composite IDs (`droplet-1-tor1/server-1`). `core/telemetry/prometheus_telemetry_adapter.py` builds the mapping. If metrics show 0.0 everywhere, check this first.
- **InfluxDB data is synthetic**: seeded via `seed_influx_history.py` (~216k points). No real streaming pipeline exists yet.
- **InfluxDB runs locally** in Docker, not on cloud droplets (cost saving).
- **`frontend/index.html`** is stale — built against old `/api/v1/simulate` response. Use `frontend/` React app instead.
- **`config/settings.py` has orphaned `SIMULATION_DB_PATH`** — unused, safe to remove.
- **Gemini fallback**: if `GEMINI_API_KEY` is unset, NLP parser falls back to regex rules then `blast_radius_query` with `parser_used=fallback`.

## Testing

```powershell
pytest tests/
```
Tests in `tests/`: `test_graph.py`, `test_parser.py`, `test_simulation.py`, `test_validators.py`.

## Docker Stack

| Service | Port | Purpose |
|---------|------|---------|
| Redis | 6379 | Caching layer |
| Neo4j | 7474/7687 | Graph database |
| InfluxDB | 8086 | Time-series storage |
| Local Prometheus | 9090 | Metrics (when using mock stack) |
| Mock exporters | 9100-9103 | Per-droplet telemetry |

