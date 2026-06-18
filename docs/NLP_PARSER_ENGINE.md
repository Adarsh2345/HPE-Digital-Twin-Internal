# NLP Parser Engine

Converts a plain-English infrastructure request into a structured simulation action — no keywords, no special syntax required from the user.

---

## What it does in one sentence

Takes a string like `"inject CPU 92% on server-1"` and returns a `SimulationRequest` object with `action="inject_compute"`, `node_id="droplet-1-tor1/server-1"`, `cpu_percent=92.0` — ready to feed directly into the simulation pipeline.

---

## Entry Point

**File:** `simulation/nlp_parser.py`  
**Function:** `parse_request(text, inventory_ids) → SimulationRequest`

Called by:  
**File:** `api/routes/metrics_resolve.py`  
**Endpoint:** `POST /api/v1/metrics/resolve`

---

## Full Flow: User Text → Simulation Result

```
User types natural language
        │
        ▼
POST /api/v1/metrics/resolve
        │
        ▼
orchestrator.get_topology_dict()
        │  gets the live 26-node inventory
        ▼
parse_request(text, inventory_ids)
        │
        ├─── GEMINI AVAILABLE? ──Yes──► _gemini_parse(text, inventory)
        │                                       │
        │                               Build short-name inventory
        │                               (server-1, router-1, etc.)
        │                                       │
        │                               Send system prompt to Gemini API
        │                               (google-genai SDK, model=gemini-2.5-flash)
        │                                       │
        │                               Receive JSON string response
        │                                       │
        │                               Strip markdown fences (```) if present
        │                                       │
        │                               json.loads() → flat dict
        │                                       │
        │                               Flatten nested params/parameters
        │                                       │
        │                               Resolve short IDs → composite IDs
        │                               e.g. "server-1" → "droplet-1-tor1/server-1"
        │                                       │
        │                               normalize_request() → SimulationRequest
        │                                       │
        │                               Validate all IDs exist in inventory
        │                                       │
        │                               Return SimulationRequest (parser_used="gemini")
        │
        └─── GEMINI UNAVAILABLE / FAILED ──►  _fallback(text)
                                                       │
                                              Return blast_radius_query
                                              (parser_used="fallback")
                                                       │
                                              API returns NLP_REQUEST_UNRESOLVED error

        │
        ▼ (from parse_request)
Extract action + params from SimulationRequest
        │
        ▼
Simulator.run(base_graph, action, params, projection_steps)
        │
        ▼
ValidatorEngine.validate(projected_graph, projections)
        │
        ▼
RecommendationEngine.generate_report(...)
        │
        ▼
JSON response: parser_metadata + simulation_report + projected_graph
```

---

## Gemini System Prompt (exact logic)

The prompt sent to Gemini is built at runtime in `_gemini_parse()`:

```
You are an infrastructure intent parser.
Return ONE flat JSON object only — no markdown, no code fences, no nesting under 'params'.
Do NOT invent node IDs; only use IDs from the inventory provided.
Use the short name (e.g. 'server-1') not the composite path.

Supported actions and their required fields:
  move_server       → server_id, target_router_id
  add_compute       → target_router_id, target_rack_id
  remove_node       → node_id
  inject_compute    → node_id, [cpu_pct, memory_pct, power_w]
  inject_network    → source_node_id, target_node_id, [latency_ms, packet_loss_pct]
  inject_storage    → node_id, [disk_iops]
  migrate_rack      → node_id, target_rack_id, target_router_id
  blast_radius_query → failed_device_id

Inventory (short names): [cadvisor, grafana, neo4j, node-exporter,
  obj-node-1, obj-node-2, obj-node-3, prometheus, router-1,
  router-2, server-1, server-2, server-3, server-4, spine-router,
  storage-router, array-ctrl-a, array-ctrl-b, ...]

Request: <user's text>
```

**Why temperature=0?**  
Deterministic output. Infrastructure operations must not produce random routing decisions.

**Why `thinking_budget=0` for gemini-2.5-flash?**  
Disables chain-of-thought reasoning. Faster response, no `<thinking>` tags leaking into the JSON output.

---

## Response Schema (Enforced by Gemini)

Gemini is constrained to return ONLY this shape — enforced via `response_json_schema`:

```json
{
  "action":           "move_server | add_compute | remove_node | inject_compute | inject_network | inject_storage | migrate_rack | blast_radius_query",
  "server_id":        "string",
  "target_router_id": "string",
  "target_rack_id":   "string",
  "node_id":          "string",
  "source_node_id":   "string",
  "target_node_id":   "string",
  "failed_device_id": "string",
  "quantity":         1,
  "cpu_pct":          0–100,
  "memory_pct":       0–100,
  "temp_c":           float,
  "power_w":          float ≥ 0,
  "latency_ms":       float ≥ 0,
  "packet_loss_pct":  0–100,
  "disk_iops":        float ≥ 0
}
```

`additionalProperties: false` — Gemini cannot invent fields outside this schema.

---

## Short ID → Composite ID Resolution

Gemini returns short names like `"server-1"`. The graph uses composite IDs like `"droplet-1-tor1/server-1"`. The resolver bridges this:

```python
# Build two lookup maps from the 26-node inventory:
by_droplet_and_name = {
    ("droplet-1-tor1", "server-1"): "droplet-1-tor1/server-1",
    ("droplet-2-tor2", "server-1"): "droplet-2-tor2/server-3",  # disambiguation
    ...
}
bare_to_full = {
    "server-1": "droplet-1-tor1/server-1",  # first encountered wins
    "router-1": "droplet-1-tor1/router-1",
    ...
}

# For each ID field in Gemini's response:
# 1. If it contains "/" → strip the droplet prefix, use the short part
# 2. Find the first inventory entry whose suffix matches
# 3. Replace with the full composite ID
```

**Example:**
- Gemini returns `node_id = "server-1"`
- Resolver finds `"droplet-1-tor1/server-1"` ends with `/server-1`
- Payload becomes `node_id = "droplet-1-tor1/server-1"`

---

## Field Name Normalisation (`normalize_request`)

**File:** `simulation/models.py`

Gemini might use slightly different field names. `normalize_request()` handles aliases:

| Gemini field | SimulationRequest field |
|---|---|
| `cpu_pct` | `cpu_percent` |
| `memory_pct` | `memory_percent` |
| `power_w` | `power_watts` |
| `packet_loss_pct` | `packet_loss_percent` |
| `target_router` | `target_router_id` |
| `destination_id` | `target_router_id` (move_server special case) |

Any nested `params` or `parameters` dict in the response is flattened before normalisation.

---

## Retry & Timeout Logic

```python
HttpOptions(
    timeout = GEMINI_TIMEOUT_SECONDS * 1000  # default 15s → 15000ms
    retry_options = HttpRetryOptions(
        attempts       = GEMINI_RETRY_ATTEMPTS  # default 3
        initial_delay  = 0.5s
        max_delay      = 2.0s
        exp_base       = 2       # exponential backoff: 0.5s → 1s → 2s
        jitter         = 0.5
        http_status_codes = [408, 500, 502, 503, 504]  # transient errors only
    )
)
```

404 and 400 errors are NOT retried — those mean the model name is wrong or the request is malformed.

---

## Fallback Behaviour

When Gemini is unavailable or fails:

```python
return normalize_request({
    "action": "blast_radius_query",
    "failed_device_id": "__unresolved__",
    "request_text": text,
    "parser_used": "fallback",
})
```

The `metrics_resolve` endpoint catches `failed_device_id == "__unresolved__"` and returns HTTP 422 with:
```json
{ "code": "NLP_REQUEST_UNRESOLVED", "detail": "Could not parse intent — try rephrasing" }
```

---

## Example Inputs and What Gemini Returns

| User types | Gemini returns |
|---|---|
| `move server-1 to router-2` | `{"action":"move_server","server_id":"server-1","target_router_id":"router-2"}` |
| `inject CPU 92% on server-1` | `{"action":"inject_compute","node_id":"server-1","cpu_pct":92}` |
| `remove server-4` | `{"action":"remove_node","node_id":"server-4"}` |
| `latency 160ms spine-router to router-1` | `{"action":"inject_network","source_node_id":"spine-router","target_node_id":"router-1","latency_ms":160}` |
| `3900 iops on server-2` | `{"action":"inject_storage","node_id":"server-2","disk_iops":3900}` |
| `migrate rack server-1 to droplet-2-tor2` | `{"action":"migrate_rack","node_id":"server-1","target_rack_id":"droplet-2-tor2"}` |

---

## What the API Returns

`POST /api/v1/metrics/resolve` response shape:

```json
{
  "parser_metadata": {
    "request_text": "inject CPU 92% on server-1",
    "parser_used": "gemini",
    "action": "inject_compute"
  },
  "simulation_report": {
    "allowed": false,
    "verdict": "FAIL ❌",
    "reasons": ["Compute Overload on droplet-1-tor1/server-1"],
    "recommendations": ["Scale workload horizontally..."]
  },
  "clone_id": "uuid-...",
  "projected_graph": { ... },
  "projections": [ ... ],
  "tier_results": { ... }
}
```

---

## Configuration

All in `config/settings.py`, overridable via `.env`:

| Setting | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `""` | Empty = NLP disabled, all requests fall back |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Which Gemini model to use |
| `GEMINI_TIMEOUT_SECONDS` | `15` | Per-request timeout |
| `GEMINI_RETRY_ATTEMPTS` | `3` | Retries on transient HTTP errors |

---

## Key Files

| File | Role |
|---|---|
| `simulation/nlp_parser.py` | Gemini call, ID resolution, fallback |
| `simulation/models.py` | `SimulationRequest` Pydantic model, `normalize_request()` |
| `api/routes/metrics_resolve.py` | REST endpoint, wires parser → simulator → validator |
| `config/settings.py` | `GEMINI_API_KEY`, `GEMINI_MODEL`, timeout, retries |
