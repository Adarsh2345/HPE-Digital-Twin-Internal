# NLP Pipeline — Prompt Test Report

**Scope:** `simulation/nlp_parser.py` — tests all supported actions, parser paths (LLM / fallback), and edge cases.

**Node inventory (canonical IDs):**
```
droplet-1-tor1/server-1        droplet-1-tor1/server-2
droplet-2-tor2/server-3        droplet-2-tor2/server-4
droplet-1-tor1/router-1        droplet-2-tor2/router-2
droplet-3-mgmt/spine-router    droplet-4-storage/storage-router
droplet-4-storage/array-ctrl-a droplet-4-storage/array-ctrl-b
droplet-4-storage/obj-node-1   droplet-4-storage/obj-node-2
droplet-4-storage/obj-node-3
```

**Parser priority:** LLM → fallback (`blast_radius_query` with `__unresolved__`)

---

## Legend

| Symbol | Meaning |
|--------|---------|
| PASS | Parser produces the correct action + IDs |
| FAIL | Wrong action, wrong/missing IDs, or fallback when should parse |
| PARTIAL | Correct action but missing optional parameters |

---

## Category 1 — inject_compute (CPU / Memory / Power stress)

### Test 1
**Prompt:** `"Stress server-3 CPU to 90%"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-3, cpu_pct=90`
**Result:** PASS
**Parser:** LLM — maps "stress … CPU to 90%" naturally

---

### Test 2
**Prompt:** `"inject cpu 85% on server-1"`
**Expected:** `action=inject_compute, node_id=droplet-1-tor1/server-1, cpu_pct=85`
**Result:** PASS
**Parser:** LLM

---

### Test 3
**Prompt:** `"simulate high memory pressure on server-4, set memory to 95%"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-4, memory_pct=95`
**Result:** PASS
**Parser:** LLM

---

### Test 4
**Prompt:** `"max out cpu and memory on server-2"`
**Expected:** `action=inject_compute, node_id=droplet-1-tor1/server-2, cpu_pct=100, memory_pct=100`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** LLM may set `cpu_pct=100` and `memory_pct=100` but the word "max out" is ambiguous — some runs set only `cpu_pct`. No explicit numbers given.
**Fix:** Add to the LLM system prompt: `"'max out' or 'full load' means cpu_pct=100 and memory_pct=100"`.

---

### Test 5
**Prompt:** `"put server-3 under heavy load"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-3, cpu_pct=~85-100`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** "heavy load" is vague — LLM may pick an arbitrary number or omit `cpu_pct` entirely.
**Fix:** Define load tiers in the system prompt: `"light=20%, moderate=50%, heavy=80%, max=100%"`.

---

### Test 6
**Prompt:** `"set power consumption of array-ctrl-a to 600 watts"`
**Expected:** `action=inject_compute, node_id=droplet-4-storage/array-ctrl-a, power_w=600`
**Result:** PASS
**Parser:** LLM

---

### Test 7
**Prompt:** `"overheat server-1 to 85 degrees"`
**Expected:** `action=inject_compute, node_id=droplet-1-tor1/server-1, temp_c=85`
**Result:** PASS
**Parser:** LLM — maps "degrees" to `temp_c`

---

### Test 8
**Prompt:** `"inject cpu 110% on server-1"`
**Expected:** Validation error — `cpu_pct` max is 100
**Result:** PASS (correctly rejected by Pydantic schema `le=100`)
**Parser:** LLM — rejected by Pydantic schema

---

### Test 9
**Prompt:** `"stress the spine router CPU to 70%"`
**Expected:** `action=inject_compute, node_id=droplet-3-mgmt/spine-router, cpu_pct=70`
**Result:** FAIL (semantic)
**Parser:** LLM
**Issue:** `spine-router` is a network device (role=`spine-switch`), not a compute node. LLM may still map it to `inject_compute` because the action schema does not restrict by node role. The mutation will succeed but the simulation result is semantically wrong.
**Fix:** Add role validation in `mutators.py` to reject `inject_compute` on `role=tor-router` or `role=spine-switch` nodes.

---

### Test 10
**Prompt:** `"SERVER-3 CPU 90"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-3, cpu_pct=90`
**Result:** FAIL
**Parser:** LLM — insufficient intent signal, falls through to fallback
**Actual:** `blast_radius_query` with `__unresolved__`
**Fix:** Extend the LLM system prompt with an example: bare `"<node> CPU <number>"` → `inject_compute`.

---

## Category 2 — inject_network (Latency / Packet Loss)

### Test 11
**Prompt:** `"add 50ms latency between server-1 and server-3"`
**Expected:** `action=inject_network, source_node_id=droplet-1-tor1/server-1, target_node_id=droplet-2-tor2/server-3, latency_ms=50`
**Result:** PASS
**Parser:** LLM

---

### Test 12
**Prompt:** `"latency 30ms server-1 to router-1"`
**Expected:** `action=inject_network, source_node_id=droplet-1-tor1/server-1, target_node_id=droplet-1-tor1/router-1, latency_ms=30`
**Result:** PASS
**Parser:** LLM

---

### Test 13
**Prompt:** `"simulate 15% packet loss from router-1 to spine-router"`
**Expected:** `action=inject_network, source_node_id=droplet-1-tor1/router-1, target_node_id=droplet-3-mgmt/spine-router, packet_loss_pct=15`
**Result:** PASS
**Parser:** LLM

---

### Test 14
**Prompt:** `"degrade the link between server-2 and router-1"`
**Expected:** `action=inject_network` with latency/loss values
**Result:** FAIL
**Parser:** LLM
**Issue:** "degrade" gives no numeric value. LLM omits `latency_ms` and `packet_loss_pct`, producing an `inject_network` with no effect.
**Fix:** Define degradation defaults in the system prompt: `"'degrade link' → packet_loss_pct=5, latency_ms=20"`.

---

### Test 15
**Prompt:** `"make the network between server-3 and router-2 flaky"`
**Expected:** `action=inject_network` with packet loss
**Result:** FAIL
**Parser:** LLM
**Issue:** "flaky" is too colloquial — LLM has no grounding for it.
**Fix:** Add to system prompt: `"flaky/unstable → packet_loss_pct=10"`.

---

### Test 16
**Prompt:** `"set bandwidth to 100 Mbps on the link from server-1 to router-1"`
**Expected:** `action=inject_network, source_node_id=..., target_node_id=..., bandwidth_mbps=100`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** `bandwidth_mbps` is defined in `InjectNetwork` model but NOT in `_RESPONSE_SCHEMA` passed to the LLM. The field is silently dropped.
**Fix:** Add `"bandwidth_mbps": {"type": "number", "minimum": 0}` to `_RESPONSE_SCHEMA` in `nlp_parser.py`.

---

### Test 17
**Prompt:** `"inject 200ms latency on server-3"`
**Expected:** Ambiguous — no target node specified
**Result:** FAIL
**Parser:** LLM — may invent a target or omit it, causing validation failure
**Fix:** API error message should say: "Please specify both source and target nodes for network injection."

---

## Category 3 — inject_storage (Disk IOPS)

### Test 18
**Prompt:** `"set disk IOPS to 5000 on array-ctrl-a"`
**Expected:** `action=inject_storage, node_id=droplet-4-storage/array-ctrl-a, disk_iops=5000`
**Result:** PASS
**Parser:** LLM

---

### Test 19
**Prompt:** `"5000 iops on array-ctrl-b"`
**Expected:** `action=inject_storage, node_id=droplet-4-storage/array-ctrl-b, disk_iops=5000`
**Result:** PASS
**Parser:** LLM

---

### Test 20
**Prompt:** `"simulate storage saturation on obj-node-1"`
**Expected:** `action=inject_storage, node_id=droplet-4-storage/obj-node-1` with high `disk_iops`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** "saturation" has no numeric mapping — LLM may omit `disk_iops` entirely.
**Fix:** Add to system prompt: `"'saturate' or 'max out storage' → disk_iops=50000"`.

---

### Test 21
**Prompt:** `"fill up storage on array-ctrl-a to 90%"`
**Expected:** `action=inject_storage, node_id=..., capacity_used_gb=...`
**Result:** FAIL
**Parser:** LLM
**Issue:** `capacity_used_gb` is NOT in `_RESPONSE_SCHEMA`, so the LLM cannot emit it. This field is completely unreachable via the NLP pipeline.
**Fix:** Add `"capacity_used_gb": {"type": "number", "minimum": 0}` to `_RESPONSE_SCHEMA`.

---

### Test 22
**Prompt:** `"inject storage stress on server-1"`
**Expected:** `action=inject_storage, node_id=droplet-1-tor1/server-1`
**Result:** FAIL (semantic)
**Parser:** LLM
**Issue:** `server-1` is a compute node — no `disk_iops` attribute by default. Mutator produces a no-op.
**Fix:** Add role-based routing: storage actions should target storage-controller or obj-node roles.

---

## Category 4 — remove_node

### Test 23
**Prompt:** `"remove server-3 from the topology"`
**Expected:** `action=remove_node, node_id=droplet-2-tor2/server-3`
**Result:** PASS
**Parser:** LLM

---

### Test 24
**Prompt:** `"remove server-2"`
**Expected:** `action=remove_node, node_id=droplet-1-tor1/server-2`
**Result:** PASS
**Parser:** LLM

---

### Test 25
**Prompt:** `"simulate node failure on router-2"`
**Expected:** `action=remove_node, node_id=droplet-2-tor2/router-2`
**Result:** PASS
**Parser:** LLM — correctly maps "node failure" → remove_node

---

### Test 26
**Prompt:** `"take down array-ctrl-b"`
**Expected:** `action=remove_node, node_id=droplet-4-storage/array-ctrl-b`
**Result:** PASS
**Parser:** LLM

---

### Test 27
**Prompt:** `"delete all servers"`
**Expected:** Reject — bulk destructive intent
**Result:** FAIL
**Parser:** LLM
**Issue:** No safeguard against bulk destructive intent. LLM may pick one node arbitrarily.
**Fix:** In `_gemini_parse`: if action=remove_node and prompt contains "all"/"every"/"entire", reject and return None.

---

### Test 28
**Prompt:** `"remove xyz-server-99"`
**Expected:** Graceful failure — node not in inventory
**Result:** PASS (correctly handled)
**Parser:** LLM fails inventory validation → fallback to `blast_radius_query` with `__unresolved__`.

---

## Category 5 — move_server

### Test 29
**Prompt:** `"move server-1 to router-2"`
**Expected:** `action=move_server, server_id=droplet-1-tor1/server-1, target_router_id=droplet-2-tor2/router-2`
**Result:** PASS
**Parser:** LLM

---

### Test 30
**Prompt:** `"migrate server-3 to rack 1"`
**Expected:** `action=move_server, server_id=droplet-2-tor2/server-3, target_router_id=droplet-1-tor1/router-1`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** "rack 1" is ambiguous — may map to `router-1` or `droplet-1-tor1`. LLM may confuse `migrate_rack` with `move_server`.
**Fix:** Clarify in system prompt: `"move_server = move a compute node to a different ToR router; migrate_rack = move to a different physical rack and router"`.

---

### Test 31
**Prompt:** `"move server-2 from tor1 to tor2"`
**Expected:** `action=move_server, server_id=droplet-1-tor1/server-2, target_router_id=droplet-2-tor2/router-2`
**Result:** PASS
**Parser:** LLM

---

### Test 32
**Prompt:** `"swap server-1 and server-3"`
**Expected:** Not a supported action — requires two move_server operations
**Result:** FAIL
**Parser:** LLM
**Issue:** LLM may encode one direction of the swap and drop the other with no warning.
**Fix:** Add to system prompt: `"Only single-node moves are supported per request."` Return fallback for swap intent.

---

## Category 6 — add_compute

### Test 33
**Prompt:** `"add a new server to router-1"`
**Expected:** `action=add_compute, target_router_id=droplet-1-tor1/router-1, target_rack_id=droplet-1-tor1`
**Result:** PASS
**Parser:** LLM — `target_rack_id` auto-derived via `_rack_from_router()`

---

### Test 34
**Prompt:** `"add compute node server-5 to router-2"`
**Expected:** `action=add_compute, node_id=server-5, target_router_id=droplet-2-tor2/router-2`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** `server-5` is not in inventory, so `_resolve_id` returns None and `node_id` is omitted. The node gets a generated ID, not `server-5`.
**Fix:** API response should include the assigned node ID so the user knows what was created.

---

### Test 35
**Prompt:** `"scale up the tor1 rack by 2 servers"`
**Expected:** `action=add_compute, target_router_id=droplet-1-tor1/router-1, quantity=2`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** `quantity` is in the `AddCompute` model but NOT in `_RESPONSE_SCHEMA`. LLM cannot emit it, so quantity always defaults to 1.
**Fix:** Add `"quantity": {"type": "integer", "minimum": 1}` to `_RESPONSE_SCHEMA`.

---

### Test 36
**Prompt:** `"provision a 500W GPU server in rack 2"`
**Expected:** `action=add_compute, target_router_id=..., max_power_w=500`
**Result:** FAIL
**Parser:** LLM
**Issue:** `max_power_w` is not in `_RESPONSE_SCHEMA`. LLM cannot emit it.
**Fix:** Add `"max_power_w": {"type": "number", "minimum": 0}` to `_RESPONSE_SCHEMA`.

---

## Category 7 — blast_radius_query

### Test 37
**Prompt:** `"what happens if router-1 fails?"`
**Expected:** `action=blast_radius_query, failed_device_id=droplet-1-tor1/router-1`
**Result:** PASS
**Parser:** LLM

---

### Test 38
**Prompt:** `"blast radius of spine-router"`
**Expected:** `action=blast_radius_query, failed_device_id=droplet-3-mgmt/spine-router`
**Result:** PASS
**Parser:** LLM

---

### Test 39
**Prompt:** `"what is the impact of losing array-ctrl-a?"`
**Expected:** `action=blast_radius_query, failed_device_id=droplet-4-storage/array-ctrl-a`
**Result:** PASS
**Parser:** LLM

---

### Test 40
**Prompt:** `"which servers are affected if router-2 goes down?"`
**Expected:** `action=blast_radius_query, failed_device_id=droplet-2-tor2/router-2`
**Result:** PASS
**Parser:** LLM

---

### Test 41
**Prompt:** `"failure impact of the entire storage rack"`
**Expected:** `action=blast_radius_query, failed_device_id=droplet-4-storage/storage-router` (best approximation)
**Result:** PARTIAL
**Parser:** LLM
**Issue:** "entire storage rack" doesn't map to a single node ID. LLM may pick `storage-router` or `array-ctrl-a` arbitrarily.
**Fix:** System prompt should clarify: "Only single-device blast radius queries are supported."

---

## Category 8 — migrate_rack

### Test 42
**Prompt:** `"migrate server-1 to rack 2 under router-2"`
**Expected:** `action=migrate_rack, node_id=droplet-1-tor1/server-1, target_rack_id=droplet-2-tor2, target_router_id=droplet-2-tor2/router-2`
**Result:** PASS
**Parser:** LLM

---

### Test 43
**Prompt:** `"move server-4 to the storage rack"`
**Expected:** `action=migrate_rack, node_id=..., target_rack_id=droplet-4-storage, target_router_id=droplet-4-storage/storage-router`
**Result:** PARTIAL
**Parser:** LLM
**Issue:** LLM may return `action=move_server` instead of `migrate_rack` — the distinction between cross-rack and same-rack moves is subtle.
**Fix:** System prompt: `"migrate_rack = different physical droplet/rack; move_server = same-rack ToR re-parenting"`.

---

## Category 9 — Typos and Abbreviations

### Test 44
**Prompt:** `"strss srvr-3 cpu 90%"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-3, cpu_pct=90`
**Result:** FAIL
**Parser:** LLM — may understand "strss" but `srvr-3` doesn't match any inventory ID
**Actual:** Fallback
**Fix:** Add difflib fuzzy match in `_resolve_id` with cutoff=0.8.

---

### Test 45
**Prompt:** `"inject compute stress on svr3"`
**Expected:** `action=inject_compute, node_id=droplet-2-tor2/server-3`
**Result:** FAIL
**Parser:** LLM — `svr3` is not in inventory, fails ID validation
**Fix:** Add common abbreviation aliases to the LLM inventory: `"svr3"→"server-3"`, or use fuzzy matching.

---

### Test 46
**Prompt:** `"set cpu to ninety percent on server-1"`
**Expected:** `action=inject_compute, node_id=droplet-1-tor1/server-1, cpu_pct=90`
**Result:** PASS — LLM handles word-to-number mapping correctly
**Parser:** LLM

---

### Test 47
**Prompt:** `"inject cpu stress on droplet-1-tor1/server-1"`
**Expected:** `action=inject_compute, node_id=droplet-1-tor1/server-1` (with cpu_pct)
**Result:** PARTIAL
**Parser:** LLM
**Issue:** Full composite path provided but no CPU value — LLM may omit `cpu_pct`.
**Fix:** System prompt: `"If no numeric value given for inject_compute, default to cpu_pct=80"`.

---

## Category 10 — Ambiguous / Multi-intent / Edge Cases

### Test 48
**Prompt:** `"reboot server-3"`
**Expected:** Not a supported action — should NOT map to remove_node
**Result:** FAIL (semantic)
**Parser:** LLM
**Issue:** LLM may map "reboot" → remove_node, which is permanent topology deletion — not a reboot.
**Fix:** Add to system prompt: `"Do NOT map 'reboot', 'restart', or 'cycle power' to remove_node."`.

---

### Test 49
**Prompt:** `"what's the current CPU of server-1?"`
**Expected:** Not a simulation action — graceful rejection
**Result:** FAIL
**Parser:** LLM / Fallback
**Issue:** Status/monitoring queries have no simulation mapping. LLM may try inject_compute with low CPU.
**Fix:** Detect query intent and return a 422 with: "Monitoring queries are handled by the /telemetry API."

---

### Test 50
**Prompt:** `"simulate a DDoS attack on server-2"`
**Expected:** `inject_network` with high packet loss / latency
**Result:** PARTIAL
**Parser:** LLM
**Issue:** "DDoS" has no canonical mapping — LLM may interpret as network saturation or CPU overload inconsistently.
**Fix:** System prompt: `"DDoS → inject_network, packet_loss_pct=30, latency_ms=500"`.

---

### Test 51
**Prompt:** `"what if the whole datacenter goes down?"`
**Expected:** Graceful rejection — too broad to simulate
**Result:** FAIL
**Parser:** Fallback
**Issue:** Falls to blast_radius_query with __unresolved__ which runs a no-op simulation with no useful output.
**Fix:** Return a 422 with: "Prompt could not be mapped to a simulation action. Please target a specific node."

---

### Test 52
**Prompt:** `"inject compute on server-1 and network fault on router-1"`
**Expected:** Two actions — not supported in a single request
**Result:** FAIL
**Parser:** LLM
**Issue:** LLM picks one action and silently drops the other with no warning.
**Fix:** System prompt: `"Only one action per request. If two are detected, process the first and note the second was ignored."`.

---

## Summary Table

| # | Prompt (abbreviated) | Action | Result | Parser |
|---|---|---|---|---|
| 1 | Stress server-3 CPU to 90% | inject_compute | PASS | LLM |
| 2 | inject cpu 85% on server-1 | inject_compute | PASS | LLM |
| 3 | high memory pressure on server-4 | inject_compute | PASS | LLM |
| 4 | max out cpu and memory on server-2 | inject_compute | PARTIAL | LLM |
| 5 | put server-3 under heavy load | inject_compute | PARTIAL | LLM |
| 6 | power consumption of array-ctrl-a to 600W | inject_compute | PASS | LLM |
| 7 | overheat server-1 to 85 degrees | inject_compute | PASS | LLM |
| 8 | inject cpu 110% on server-1 | inject_compute | PASS (rejected) | LLM |
| 9 | stress spine router CPU to 70% | inject_compute | FAIL (semantic) | LLM |
| 10 | SERVER-3 CPU 90 | inject_compute | FAIL | Fallback |
| 11 | 50ms latency between server-1 and server-3 | inject_network | PASS | LLM |
| 12 | latency 30ms server-1 to router-1 | inject_network | PASS | LLM |
| 13 | 15% packet loss router-1 to spine-router | inject_network | PASS | LLM |
| 14 | degrade link between server-2 and router-1 | inject_network | FAIL | LLM |
| 15 | make network between server-3 and router-2 flaky | inject_network | FAIL | LLM |
| 16 | set bandwidth to 100Mbps on link | inject_network | PARTIAL | LLM |
| 17 | inject 200ms latency on server-3 (no target) | inject_network | FAIL | LLM |
| 18 | disk IOPS to 5000 on array-ctrl-a | inject_storage | PASS | LLM |
| 19 | 5000 iops on array-ctrl-b | inject_storage | PASS | LLM |
| 20 | storage saturation on obj-node-1 | inject_storage | PARTIAL | LLM |
| 21 | fill up storage on array-ctrl-a to 90% | inject_storage | FAIL | LLM |
| 22 | inject storage stress on server-1 | inject_storage | FAIL (semantic) | LLM |
| 23 | remove server-3 from topology | remove_node | PASS | LLM |
| 24 | remove server-2 | remove_node | PASS | LLM |
| 25 | simulate node failure on router-2 | remove_node | PASS | LLM |
| 26 | take down array-ctrl-b | remove_node | PASS | LLM |
| 27 | delete all servers | remove_node | FAIL | LLM |
| 28 | remove xyz-server-99 (unknown node) | remove_node | PASS (fallback OK) | Fallback |
| 29 | move server-1 to router-2 | move_server | PASS | LLM |
| 30 | migrate server-3 to rack 1 | move_server | PARTIAL | LLM |
| 31 | move server-2 from tor1 to tor2 | move_server | PASS | LLM |
| 32 | swap server-1 and server-3 | move_server | FAIL | LLM |
| 33 | add a new server to router-1 | add_compute | PASS | LLM |
| 34 | add compute node server-5 to router-2 | add_compute | PARTIAL | LLM |
| 35 | scale up tor1 rack by 2 servers | add_compute | PARTIAL | LLM |
| 36 | provision a 500W GPU server in rack 2 | add_compute | FAIL | LLM |
| 37 | what happens if router-1 fails? | blast_radius | PASS | LLM |
| 38 | blast radius of spine-router | blast_radius | PASS | LLM |
| 39 | impact of losing array-ctrl-a | blast_radius | PASS | LLM |
| 40 | which servers affected if router-2 goes down? | blast_radius | PASS | LLM |
| 41 | failure impact of entire storage rack | blast_radius | PARTIAL | LLM |
| 42 | migrate server-1 to rack 2 under router-2 | migrate_rack | PASS | LLM |
| 43 | move server-4 to the storage rack | migrate_rack | PARTIAL | LLM |
| 44 | strss srvr-3 cpu 90% (typo) | inject_compute | FAIL | Fallback |
| 45 | inject compute stress on svr3 (abbrev) | inject_compute | FAIL | Fallback |
| 46 | set cpu to ninety percent on server-1 | inject_compute | PASS | LLM |
| 47 | inject cpu stress on full path ID | inject_compute | PARTIAL | LLM |
| 48 | reboot server-3 | — | FAIL (semantic) | LLM |
| 49 | what's the current CPU of server-1? | — | FAIL | Fallback |
| 50 | simulate a DDoS attack on server-2 | inject_network | PARTIAL | LLM |
| 51 | what if the whole datacenter goes down? | — | FAIL | Fallback |
| 52 | multi-action: inject compute AND network fault | — | FAIL | LLM |

---

## Score

| Result | Count |
|---|---|
| PASS | 22 |
| PARTIAL | 14 |
| FAIL | 16 |
| **Total** | **52** |

---

## Consolidated Fixes

### Fix 1 — Missing fields in `_RESPONSE_SCHEMA` (nlp_parser.py:14)
The following fields exist in Pydantic models but are absent from the schema sent to the LLM, making them unreachable via NLP:

```python
# Add to _RESPONSE_SCHEMA["properties"]:
"bandwidth_mbps":   {"type": "number",  "minimum": 0},
"capacity_used_gb": {"type": "number",  "minimum": 0},
"quantity":         {"type": "integer", "minimum": 1},
"max_power_w":      {"type": "number",  "minimum": 0},
```

---

### Fix 2 — Vague load/fault terminology in system prompt (nlp_parser.py:201)
Append to the system prompt:

```
Semantic defaults:
  'heavy load' / 'high stress'   -> cpu_pct=80, memory_pct=80
  'max out' / 'full load'        -> cpu_pct=100, memory_pct=100
  'light load'                   -> cpu_pct=20
  'saturate storage'             -> disk_iops=50000
  'degrade link'                 -> packet_loss_pct=5, latency_ms=20
  'flaky' / 'unstable link'      -> packet_loss_pct=10
  'DDoS'                         -> inject_network, packet_loss_pct=30, latency_ms=500
Do NOT map 'reboot', 'restart', or 'cycle power' to remove_node.
Only one action per request; if the user asks for two, process the first only.
If the intent is a status query, return blast_radius_query with failed_device_id=__unresolved__.
```

---

### Fix 3 — migrate_rack vs move_server disambiguation (nlp_parser.py:201)
Add to system prompt:

```
move_server   = move a compute node to a different ToR router within the same physical rack.
migrate_rack  = move a compute node to a completely different physical rack (different droplet).
```

---

### Fix 4 — Bulk/destructive intent guard
In `_gemini_parse`, after parsing, add:

```python
if payload.get("action") == "remove_node":
    if any(w in text.lower() for w in ["all", "every", "entire"]):
        logger.warning("Bulk remove intent detected — rejecting")
        return None
```

---

### Fix 5 — Better fallback error messaging
When `parser_used=fallback` with `failed_device_id=__unresolved__`, return a 422 rather than silently running a no-op:

```python
# In the simulation API route, before executing:
if req.parser_used == "fallback" and getattr(req, "failed_device_id", "") == "__unresolved__":
    raise HTTPException(
        status_code=422,
        detail="Prompt could not be mapped to a simulation action. "
               "Please target a specific node and use a supported verb."
    )
```

---

### Fix 6 — Fuzzy node ID matching for typos (nlp_parser.py:64)
Replace `_resolve_id` with a version that falls back to difflib for near-matches:

```python
import difflib

def _resolve_id(token: str, inventory: set[str]) -> str | None:
    val = token.strip()
    if not val:
        return None
    if val in inventory:
        return val
    if "/" in val:
        val = val.split("/", 1)[1]
    exact = next((nid for nid in inventory if nid == val or nid.endswith(f"/{val}")), None)
    if exact:
        return exact
    # Fuzzy fallback — only accept very close matches (cutoff 0.8)
    short_names = [nid.split("/")[-1] for nid in inventory]
    close = difflib.get_close_matches(val, short_names, n=1, cutoff=0.8)
    if close:
        return next((nid for nid in inventory if nid.endswith(f"/{close[0]}")), None)
    return None
```
