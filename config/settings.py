import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

# Infrastructure
INFRASTRUCTURE_YAML = os.getenv("INFRASTRUCTURE_YAML", str(BASE_DIR / "infrastructure" / "infrastructure.yaml"))

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# NetBox
NETBOX_URL = os.getenv("NETBOX_URL", "http://localhost:8080")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")

# Prometheus
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://168.144.91.25:9090")

# Telemetry Loop
TELEMETRY_INTERVAL_SECONDS = int(os.getenv("TELEMETRY_INTERVAL", 12))

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 5000))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

# InfluxDB Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-admin-token-12345")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "hpe-digital-twin-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry_bucket")

# Optional natural-language parser
ENABLE_LLM_PARSER = os.getenv("ENABLE_LLM_PARSER", "false").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")
GEMINI_TIMEOUT_SECONDS = max(10.0, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10")))
GEMINI_RETRY_ATTEMPTS = min(
    3, max(1, int(os.getenv("GEMINI_RETRY_ATTEMPTS", "3")))
)

# Durable local simulation audit
SIMULATION_DB_PATH = os.getenv("SIMULATION_DB_PATH", "/tmp/hpe_digital_twin_simulations.sqlite3")


# Constraints
POWER_LIMIT_WATTS = float(os.getenv("POWER_LIMIT_WATTS", 1400.0))
RACK_U_LIMIT = int(os.getenv("RACK_U_LIMIT", 42))
CPU_CAPACITY_LIMIT = float(os.getenv("CPU_CAPACITY_LIMIT", 95.0))
MEMORY_CAPACITY_LIMIT = float(os.getenv("MEMORY_CAPACITY_LIMIT", 95.0))
STORAGE_IOPS_LIMIT = int(os.getenv("STORAGE_IOPS_LIMIT", 4000))
NETWORK_LATENCY_SLA_MS = float(os.getenv("NETWORK_LATENCY_SLA_MS", 150.0))

# Gaussian metrics - healthy state
CPU_HEALTHY_MEAN = 33.0
CPU_HEALTHY_STD = 8.0
CPU_HEALTHY_MIN = 24.5
CPU_HEALTHY_MAX = 42.0

MEMORY_HEALTHY_MEAN = 45.0
MEMORY_HEALTHY_STD = 10.0

LATENCY_HEALTHY_MEAN = 12.0
LATENCY_HEALTHY_STD = 3.0

PACKET_LOSS_HEALTHY_MEAN = 0.05
PACKET_LOSS_HEALTHY_STD = 0.02

IOPS_HEALTHY_MEAN = 800.0
IOPS_HEALTHY_STD = 150.0

POWER_PER_NODE_MEAN = 180.0
POWER_PER_NODE_STD = 30.0

# Gaussian metrics - chaos state
CPU_CHAOS_MEAN = 82.0
CPU_CHAOS_STD = 12.0

MEMORY_CHAOS_MEAN = 88.0
MEMORY_CHAOS_STD = 8.0

LATENCY_CHAOS_MEAN = 200.0
LATENCY_CHAOS_STD = 60.0

LATENCY_CHAOS_MAX = 320.0

PACKET_LOSS_CHAOS_MEAN = 5.0
PACKET_LOSS_CHAOS_STD = 2.0

IOPS_CHAOS_MEAN = 3500.0
IOPS_CHAOS_STD = 400.0

POWER_CHAOS_MEAN = 320.0
POWER_CHAOS_STD = 50.0
