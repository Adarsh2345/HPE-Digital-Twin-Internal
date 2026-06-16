"""
config/constants.py
System-wide architectural threshold definitions, node states, and role registries.
Extended to fully support the production Storage Rack and Monitoring planes.
"""

NODE_STATES = {
    "HEALTHY": "healthy",
    "WARNING": "warning",
    "CRITICAL": "critical",
    "UNKNOWN": "unknown",
    "OFFLINE": "offline",
}

EDGE_STATES = {
    "ACTIVE": "active",
    "DEGRADED": "degraded",
    "DOWN": "down",
}

NODE_ROLES = {
    "COMPUTE": "compute-node",
    "TOR_ROUTER": "tor-router",
    "SPINE": "spine-switch",
    "NETBOX": "infrastructure-docs",
    "NEO4J": "graph-database",
    "MIDDLEWARE": "middleware",
    # 🟢 ADDED: Core production roles from your new storage rack blueprint
    "STORAGE_TOR": "storage-tor",
    "STORAGE_CONTROLLER": "storage-controller",
    "OBJECT_STORAGE": "object-storage",
    "METRICS_COLLECTOR": "metrics-collector",
    "METRICS_EXPORTER": "metrics-exporter",
    "CONTAINER_METRICS": "container-metrics",
}

WARNING_THRESHOLDS = {
    "cpu": 70.0,
    "memory": 75.0,
    "latency_ms": 100.0,
    "packet_loss": 2.0,
    "iops": 3000,
    "power_watts": 1200.0,
}

CRITICAL_THRESHOLDS = {
    "cpu": 85.0,
    "memory": 90.0,
    "latency_ms": 150.0,
    "packet_loss": 5.0,
    "iops": 4000,
    "power_watts": 1400.0,
}

REDIS_KEYS = {
    "DERIVED_STATE": "digital_twin:derived_state",
    "CHAOS_MODE": "digital_twin:chaos_mode",
    "TOPOLOGY": "digital_twin:topology",
    "METRICS_HISTORY": "digital_twin:metrics_history",
}

API_VERSION = "v1"
APP_NAME = "HPE Digital Twin Platform"