

A high-fidelity, real-time Digital Twin platform engineered to parse infrastructure layouts, model spine-and-leaf network topologies as directional graphs, scrape live Prometheus telemetry simulation loops, and visualize physical-to-historic data assets.

The system leverages a dual-layer storage strategy (**Redis** for real-time sub-millisecond caching and **Neo4j** for historical timeline state-tracking graphs) to monitor performance anomalies and execute deterministic chaos engineering stress tests.

---

## 🏗️ System Architecture & Data Flow

```text
  [ infrastructure.yaml ]
            │
            ▼ (Phase 1 Bootstrap)
   [ NetworkX Topology ] ───(Sync Layout Once)───► [ Neo4j: BaseNode Graph ]
            │
            ▼ (Phase 2: 12s Heartbeat Loop)
  [ Metrics Generator ] ◄───(Interceptors)──────── [ Chaos Mesh Engine ]
 (Gaussian Distribution)
            │
     (Enriched JSON)
            ▼
 [ DerivedStateBuilder ]
            ├───(Cache Flattened State)──────────► [ Redis Cache Layer ]
            └───(Stream Telemetry Snapshots)─────► [ Neo4j: LiveState & Snapshots ]
```

### Phase 1: Bootstrap

On startup, the platform reads `infrastructure.yaml` via a custom loader to compile an in-memory structural wireframe using NetworkX. This static topology is instantly written to Neo4j as permanent `:BaseNode` assets connected via `:WIRED_TO` relationships.

### Phase 2: 12s Telemetry Loop

Every 12 seconds, an asynchronous telemetry harvester triggers. It scrapes metrics from a role-aware generator, enriches and flattens data variables, computes automated infrastructure health states, and streams transactional updates concurrently to Redis and Neo4j.

---

## 📂 Project Workspace Layout

```plaintext
privatetwin/
├── config/
│   ├── constants.py
│   │   # Static system states, threshold definitions & Redis keys
│   └── settings.py
│       # Port bindings, credentials, and environmental settings
│
├── core/
│   ├── graph/
│   │   ├── derived_state_builder.py
│   │   │   # Merges metrics, handles health checks, flattens payloads
│   │   └── topology_builder.py
│   │       # Converts YAML structural wireframes into NetworkX objects
│   │
│   ├── telemetry/
│   │   ├── metrics_generator.py
│   │   │   # Statistical simulation engine (Gaussian curve modeling)
│   │   └── chaos_engine.py
│   │       # Fault injection manager and state context register
│   │
│   └── orchestrator.py
│       # Central engine singleton directing bootstrap sequences & timers
│
├── docker/
│   └── docker-compose.yml
│       # Native container definitions (Redis Stack + Neo4j Engine)
│
├── integrations/
│   └── neo4j/
│       └── neo4j_client.py
│           # High-performance Cypher transaction mutations
│
├── infrastructure/
│   └── infrastructure.yaml
│       # Source-of-Truth definition for the spine-and-leaf cluster
│
└── run.py
    # Unified platform runner with embedded Docker health check hooks
```

---

## 📊 Telemetry Simulation Engine (Interview Talking Points)

Unlike basic simulators that rely on arbitrary uniform randomness (`random.randint`), this platform implements statistical realism and topology-aware dependency modeling.

### 🔹 Role-Specific Gaussian Distribution

Metrics are generated using a normal distribution function governed by a localized mean (μ) and standard deviation (σ). This ensures that components naturally hover around their realistic operational profiles.

Examples:

* Core switches idle with low processor overhead (~10%)
* Compute nodes handle higher baselines (~35%)

### 🔹 Deterministic Chaos Mesh

The system features an advanced Fault-Injection interface.

Triggering the chaos endpoint alters the core application state context within Redis. On the following heartbeat cycle, the simulator intercepts this context and programmatically switches out the standard Gaussian curve for an anomalous, right-skewed stress profile:

* CPU utilization spikes beyond 90%
* Temperatures increase sharply
* Artificial packet loss is injected across target network edges

This validates downstream monitoring and anomaly-detection pipelines.

---

## 🛠️ Installation & Getting Started

### Prerequisites

* Linux / WSL2 Environment
* Python 3.11+
* Docker & Docker Compose

### 1. Environment Setup

Clone the repository, create a virtual environment, and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Booting the Platform

Run the master startup script.

The script uses Docker health checks to block application initialization until Neo4j has completed startup and authentication handshakes.

```bash
./.venv/bin/python run.py
```

---

## 🔍 Graph Queries (Neo4j Browser)

Open Neo4j Browser:

```text
http://localhost:7474
```

### View Clean Master Network (Latest Metrics Only)

This query isolates the newest telemetry tick and hides all historical state snapshots.

```cypher
MATCH (l:LiveState)
WITH max(toInteger(l.tick)) AS latestTick

MATCH (b:BaseNode)
OPTIONAL MATCH (b)-[wired:WIRED_TO]->(target:BaseNode)
OPTIONAL MATCH (b)-[current:CURRENT_METRICS]->(latestMetrics:LiveState)
WHERE toInteger(latestMetrics.tick) = latestTick

RETURN b, wired, target, current, latestMetrics
```

### Database Clean Reset

Flush all nodes, relationships, and tracking history.

```cypher
MATCH (n)
DETACH DELETE n
```
