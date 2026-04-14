import requests
import time

BASE_URL = "http://localhost:8000"
HEADERS = {"X-Operator-Token": "test-operator-key-123"}

def run_simulation():
    print("--- 1. Registering HPE Server ---")
    server_data = {
        "asset_id": "srv-hpe-gen11-01",
        "asset_type": "server",
        "status": "ok",
        "temperature": 45.0,
        "cpu_utilization": 20.5,
        "timestamp": "2026-03-25T10:00:00Z"
    }
    res = requests.post(f"{BASE_URL}/ingest/asset", json=server_data, headers=HEADERS)
    print(res.json())
    
    print("\n--- 2. Registering Hypervisor (ESXi) ---")
    hypervisor_data = {
        "system_id": "esxi-01",
        "parent_asset_id": "srv-hpe-gen11-01",
        "system_type": "hypervisor",
        "status": "running",
        "memory_utilization": 40.0,
        "timestamp": "2026-03-25T10:00:05Z"
    }
    res = requests.post(f"{BASE_URL}/ingest/system", json=hypervisor_data, headers=HEADERS)
    print(res.json())

    print("\n--- 3. Registering VM ---")
    vm_data = {
        "system_id": "vm-app-01",
        "parent_asset_id": "esxi-01",
        "system_type": "vm",
        "status": "running",
        "memory_utilization": 80.0,
        "timestamp": "2026-03-25T10:00:10Z"
    }
    res = requests.post(f"{BASE_URL}/ingest/system", json=vm_data, headers=HEADERS)
    print(res.json())

    print("\n--- 4. SIMULATING SERVER OVERHEAT ---")
    time.sleep(2)
    overheat_data = {
        "asset_id": "srv-hpe-gen11-01",
        "asset_type": "server",
        "status": "critical",
        "temperature": 95.0,
        "cpu_utilization": 99.9,
        "timestamp": "2026-03-25T10:05:00Z"
    }
    res = requests.post(f"{BASE_URL}/ingest/asset", json=overheat_data, headers=HEADERS)
    print(res.json())

    print("\n--- 5. Checking Digital Twin Graph State ---")
    res = requests.get(f"{BASE_URL}/twin/nodes")
    print(res.json())

if __name__ == "__main__":
    run_simulation()
