# Adarsh-nlp-metrics-pipeline — Branch Guide

## What this branch is

This branch is the **input layer** of the HPE Digital Twin system: it takes a
user's natural-language request, figures out which infrastructure node(s) it
refers to, and gathers real data about those nodes — both right now and over
the last 30 days.

It deliberately contains **no simulation engine**. No mutations, no
validation, no projections, no recommendations. That logic was removed on
purpose so a different simulation engine can be built on top of this
foundation without dragging along the old one.

---

## What's actually in this branch

### 1. NLP Parser — `simulation/nlp_parser.py`
Takes a plain-English prompt and turns it into a structured action using
Google Gemini (no regex/rule-based matching — that was removed because it
couldn't handle vague phrasing like "remove a server from the first rack").

- Reads `GEMINI_API_KEY` and `GEMINI_MODEL` from `.env`
- Forces Gemini to respond in strict JSON matching one of 8 known actions
  (`move_server`, `add_compute`, `remove_node`, `inject_compute`,
  `inject_network`, `inject_storage`, `migrate_rack`, `blast_radius_query`)
- `temperature=0` so the same prompt gives the same result every time

### 2. Request Schema — `simulation/models.py`
Pydantic models defining what each of the 8 actions looks like once parsed
(e.g. `InjectCompute` needs `node_id`, `cpu_pct`, etc.). This is what the
NLP parser returns — kept because the simulation engine you plug in next
will need a structured request, not raw text.

### 3. Live Current Metrics — Prometheus
- `core/telemetry/prometheus_scraper.py` — thin wrapper, called every 12s by
  the orchestrator's telemetry loop
- `core/telemetry/prometheus_telemetry_adapter.py` — does the real work:
  queries Prometheus on the management droplet, and **remaps bare node names
  to composite graph IDs**

**Important gotcha this branch already solved:** Prometheus labels nodes with
bare names like `"server-1"`, but the topology graph uses composite IDs like
`"droplet-1-tor1/server-1"`. The adapter builds a lookup table from the graph's
node list to bridge this — if you ever see metrics showing as `0.0`
everywhere, check this mapping first.

### 4. 30-Day History — InfluxDB
- `integrations/influxdb/influx_client.py` — has `get_node_history(node_id,
  days=30)`, which queries `telemetry_bucket` for one node and returns
  p50/p90/p95/max percentiles per metric
- **This is fetched on-demand only** — not on every 12s tick. It only runs
  when a `/metrics/resolve` request actually references a node. Don't wire
  it into the tick loop; that would hammer InfluxDB for no reason.
- InfluxDB itself runs locally via Docker (`docker/docker-compose.yml`), not
  on the cloud droplets — this was a deliberate choice to avoid extra
  DigitalOcean costs. It currently holds ~216,000 synthetic seeded points
  (see `seed_influx_history.py`) rather than real droplet history, since
  nothing has been continuously streaming real data into it yet.

### 5. The one API endpoint — `api/routes/metrics_resolve.py`
```
POST /api/v1/metrics/resolve
{ "request_text": "inject cpu 95 on server-1" }
```

Returns:
```json
{
  "action": "inject_compute",
  "parser_used": "gemini",
  "resolved_node_ids": ["droplet-1-tor1/server-1"],
  "current_snapshot": { "droplet-1-tor1/server-1": { "cpu_percent": 48.3, ... } },
  "historical_context": { "droplet-1-tor1/server-1": { "cpu_percent": {"p50": 33.0, "p90": 42.0, ...} } }
}
```

That's it. **No `allowed`, no `violations`, no `recommendations`, no
`blast_radius`** — those belonged to the old engine and are gone. Whoever
builds the next simulation engine should call this endpoint's logic (or
import `parse_request` + the metrics fetch directly) as the first step of
their pipeline, then take it from there.

### 6. Frontend — `frontend/index.html`
A single-file HTML/JS console (no build step) for manually testing prompts
against the API. Currently still points at the old `/api/v1/simulate`
response shape in its rendering code — **this needs updating** to match the
new `/api/v1/metrics/resolve` response shape (see "What's broken" below).

---

## What's broken / needs follow-up work

1. **`frontend/index.html` is stale.** It was built against the old
   `/api/v1/simulate` response (expects `verdict`, `violations`,
   `blast_radius`, etc.) which no longer exists. It needs to be rewritten to
   call `/api/v1/metrics/resolve` and just show `current_snapshot` +
   `historical_context`.

2. **InfluxDB history is synthetic, not real.** `seed_influx_history.py` was
   used to backfill fake-but-realistic 30-day data. If you want real
   history, you need `prometheus_to_influx.py` (or similar) running
   continuously to actually accumulate real Prometheus data over time. It
   currently exists but isn't running anywhere.

3. **No simulation engine.** This is intentional — that's the next thing to
   build or plug in. Whatever you build should:
   - Call `parse_request()` from `simulation/nlp_parser.py` to get a
     structured `SimulationRequest`
   - Use `orchestrator.get_derived_graph()` for the live topology graph
   - Use `orchestrator.influx_client.get_node_history()` for 30-day context
     on specific nodes
   - Then do whatever mutation/validation/decision logic your new engine
     needs

4. **`config/settings.py` still has `SIMULATION_DB_PATH`** — an orphaned
   setting left over from the deleted `simulation/audit.py`. Harmless but
   unused; safe to remove if you want to tidy up.

---

## How to run this branch

```powershell
git checkout Adarsh-nlp-metrics-pipeline
pip install -r requirements.txt
# Make sure Docker Desktop is running, then:
docker compose -f docker/docker-compose.yml up -d   # Redis, Neo4j, InfluxDB
python run.py
```

Add a `.env` file (gitignored, not committed) with:
```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
```

Test it:
```
http://localhost:5000/docs
```
Try `POST /api/v1/metrics/resolve` with `{"request_text": "what happens if router-1 fails"}`.

---

## Where the real Terraform infra lives

Unrelated to this branch's content, but worth knowing: the actual cloud
provisioning files (`main.tf`, `infrastructure.yaml`, cloud-init scripts)
were moved into `terraform-pipeline/` in an earlier commit on `Adarsh`, since
they don't need to run every time you work on the app code. The Prometheus
instance this branch talks to lives on `droplet-3-mgmt`, currently reachable
at the IP configured in `PROMETHEUS_URL` (`config/settings.py`).
