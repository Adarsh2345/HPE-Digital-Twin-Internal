# HPE Digital Twin — Frontend Dashboard

React + Vite dashboard matching the Infrastructure Command Center UI. All data comes from the FastAPI backend — no mock data.

## Prerequisites

- Node.js 18+
- Backend running on port 5000 (`python run.py` from project root)

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3002**

## Environment

Copy `.env.example` to `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | (empty) | Leave empty in dev — Vite proxies `/api` to :5000 |
| `VITE_GRAFANA_URL` | `http://localhost:3000` | Grafana iframe embed |
| `VITE_PROMETHEUS_URL` | `http://localhost:9090` | Sidebar link |
| `VITE_INFLUXDB_URL` | `http://localhost:8086` | Sidebar link |

## Pages & APIs

| Route | APIs Used |
|-------|-----------|
| `/` Dashboard | `/api/v1/topology/nodes`, `/api/v1/telemetry`, `/api/v1/reports/health` |
| `/topology` | `/api/v1/topology`, `/api/v1/topology/node/{id}`, `/api/v1/telemetry/{id}` |
| `/simulation` | `/api/v1/simulate/actions`, `POST /api/v1/simulate` |
| `/drift` | `/api/v1/reports/validate` |
| `/approvals` | **No backend API** — shows empty state |
| `/observability` | `/api/v1/telemetry`, `/api/v1/analytics/anomaly/*` |
| `/analytics` | `/api/v1/analytics/profiles`, `/scenarios`, `/correlations/{id}` |
| `/reports` | `/api/v1/reports/health`, `/validate`, `/summary` |

## Production Build

```bash
npm run build
```

Served at `http://localhost:5000/app` when `frontend/dist` exists and backend is running.
