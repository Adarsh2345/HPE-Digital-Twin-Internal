#!/usr/bin/env python3
import time
import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- ROUTE DATA THROUGH EXPLICIT INTERNAL VPC FABRIC BOUNDARIES ---
# --- ROUTE DATA THROUGH EXPLICIT INTERNAL VPC FABRIC BOUNDARIES ---
PROMETHEUS_API = "http://10.10.0.3:9090/api/v1/query"
INFLUXDB_URL = "http://10.10.0.3:8086"
INFLUXDB_TOKEN = "my-super-secret-admin-token-12345"
INFLUXDB_ORG = "hpe-digital-twin-org"
INFLUXDB_BUCKET = "telemetry_bucket"

def query_prometheus(promql_query):
    """Safely extracts a vector snapshot slice from the Prometheus API engine."""
    try:
        response = requests.get(PROMETHEUS_API, params={'query': promql_query}, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("status") == "success":
                return res_json.get("data", {}).get("result", [])
        return []
    except Exception as e:
        print(f"[-] Failed to execute PromQL query ({promql_query}): {e}")
        return []

def main():
    print(f"[*] Starting Direct Prometheus-to-InfluxDB Synchronization Bridge...")
    
    # Initialize connection handle safely using synchronous write properties
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    while True:
        print(f"\n[+] Executing telemetry loop scraping sync tick at {time.strftime('%X')}...")
        
        # 1. Fetch raw metric values using library-native name registers
        cpu_data   = query_prometheus("cpu_percent")
        mem_data   = query_prometheus("memory_percent")
        iops_data  = query_prometheus("disk_iops")
        power_data = query_prometheus("power_watts")
        temp_data  = query_prometheus("temperature_celsius")
        
        lat_data   = query_prometheus("latency_ms")
        loss_data  = query_prometheus("packet_loss_percent")
        bw_data    = query_prometheus("bandwidth_mbps")

        # 2. Harmonize Node Metrics into Moushmi's exact schema layout
        nodes_map = {}
        for item in cpu_data:
            metric = item.get("metric", {})
            nid = metric.get("id")
            role = metric.get("role")
            droplet = metric.get("droplet", "unknown")
            rack = metric.get("rack", "unknown")
            if nid:
                nodes_map[nid] = {
                    "id": nid, "role": role, "droplet": droplet, "rack": rack,
                    "cpu_percent": float(item.get("value", [0, 0])[1])
                }

        for item in mem_data:
            nid = item.get("metric", {}).get("id")
            if nid in nodes_map:
                nodes_map[nid]["memory_percent"] = float(item.get("value", [0, 0])[1])

        for item in iops_data:
            nid = item.get("metric", {}).get("id")
            if nid in nodes_map:
                nodes_map[nid]["disk_iops"] = float(item.get("value", [0, 0])[1])

        for item in power_data:
            nid = item.get("metric", {}).get("id")
            if nid in nodes_map:
                nodes_map[nid]["power_watts"] = float(item.get("value", [0, 0])[1])

        for item in temp_data:
            nid = item.get("metric", {}).get("id")
            if nid in nodes_map:
                nodes_map[nid]["temperature_celsius"] = float(item.get("value", [0, 0])[1])

        # Write Grouped Points to InfluxDB under 'node_telemetry' measurement
        for nid, fields in nodes_map.items():
            p = (Point("node_telemetry")
                 .tag("id", nid)
                 .tag("role", fields.get("role", "unknown"))
                 .tag("droplet", fields.get("droplet", "unknown"))
                 .tag("rack", fields.get("rack", "unknown"))
                 .field("cpu_percent", fields.get("cpu_percent", 0.0))
                 .field("memory_percent", fields.get("memory_percent", 0.0))
                 .field("disk_iops", fields.get("disk_iops", 0.0))
                 .field("power_watts", fields.get("power_watts", 0.0))
                 .field("temperature_celsius", fields.get("temperature_celsius", 0.0)))
            try:
                write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=p)
                print(f"[->] Synced node_telemetry point for logical target: {nid}")
            except Exception as e:
                print(f"[-] Failed to write node metrics for {nid} to InfluxDB: {e}")

        # 3. Harmonize Link Edge Metrics into Moushmi's exact schema layout
        for item in lat_data:
            metric = item.get("metric", {})
            src, tgt = metric.get("source"), metric.get("target")
            if src and tgt:
                lat_val = float(item.get("value", [0, 0])[1])
                
                loss_val = 0.0
                for l_item in loss_data:
                    m = l_item.get("metric", {})
                    if m.get("source") == src and m.get("target") == tgt:
                        loss_val = float(l_item.get("value", [0, 0])[1])
                
                bw_val = 1000.0
                for b_item in bw_data:
                    m = b_item.get("metric", {})
                    if m.get("source") == src and m.get("target") == tgt:
                        bw_val = float(b_item.get("value", [0, 0])[1])

                ep = (Point("edge_telemetry")
                      .tag("source", src)
                      .tag("target", tgt)
                      .field("latency_ms", lat_val)
                      .field("packet_loss_percent", loss_val)
                      .field("bandwidth_mbps", bw_val))
                try:
                    write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=ep)
                    print(f"[->] Synced edge_telemetry link route: {src} -> {tgt}")
                except Exception as e:
                    print(f"[-] Failed to write edge metrics for {src}->{tgt} to InfluxDB: {e}")

        time.sleep(12)

if __name__ == "__main__":
    main()