#!/bin/bash
# ============================================================
# setup-exporter.sh — Run ON the droplet
# Usage: bash setup-exporter.sh <droplet-name>
# Example: bash setup-exporter.sh droplet-1-tor1
# ============================================================
set -e
D="${1:?Usage: $0 <droplet-name>}"

echo "=== Setting up exporter for $D ==="

# Kill existing on 9200
fuser -k 9200/tcp 2>/dev/null || true
sleep 1

mkdir -p /opt/device-exporter

# Generate config
python3 -c "
import json,sys
DB={
'droplet-1-tor1':{'d':[{'id':'server-1','role':'compute-node'},{'id':'server-2','role':'compute-node'},{'id':'router-1','role':'tor-router'},{'id':'node-exporter','role':'metrics-exporter'},{'id':'cadvisor','role':'container-metrics'}],'e':[['router-1','server-1'],['router-1','server-2']]},
'droplet-2-tor2':{'d':[{'id':'server-3','role':'compute-node'},{'id':'server-4','role':'compute-node'},{'id':'router-2','role':'tor-router'},{'id':'node-exporter','role':'metrics-exporter'},{'id':'cadvisor','role':'container-metrics'}],'e':[['router-2','server-3'],['router-2','server-4']]},
'droplet-3-mgmt':{'d':[{'id':'netbox','role':'infrastructure-docs'},{'id':'neo4j','role':'graph-database'},{'id':'python-app','role':'middleware'},{'id':'spine-router','role':'spine-switch'},{'id':'prometheus','role':'metrics-collector'},{'id':'grafana','role':'metrics-dashboard'},{'id':'node-exporter','role':'metrics-exporter'},{'id':'cadvisor','role':'container-metrics'}],'e':[['spine-router','router-1'],['spine-router','router-2'],['spine-router','storage-router']]},
'droplet-4-storage':{'d':[{'id':'storage-router','role':'storage-tor'},{'id':'array-ctrl-a','role':'storage-controller'},{'id':'array-ctrl-b','role':'storage-controller'},{'id':'obj-node-1','role':'object-storage'},{'id':'obj-node-2','role':'object-storage'},{'id':'obj-node-3','role':'object-storage'},{'id':'node-exporter','role':'metrics-exporter'},{'id':'cadvisor','role':'container-metrics'}],'e':[['storage-router','array-ctrl-a'],['storage-router','array-ctrl-b'],['storage-router','obj-node-1'],['storage-router','obj-node-2'],['storage-router','obj-node-3'],['array-ctrl-a','array-ctrl-b']]}
}
if '$D' not in DB:print(f'ERROR: unknown droplet '$D);sys.exit(1)
c={'droplet':'$D','devices':DB['$D']['d'],'edges':DB['$D']['e']}
open('/opt/device-exporter/config.json','w').write(json.dumps(c,indent=2))
print(f'Config: {len(c[\"devices\"])} devices, {len(c[\"edges\"])} edges')
"

# Write exporter
cat > /opt/device-exporter/device_exporter.py << 'PYEOF'
import json,random,time
from prometheus_client import Gauge,start_http_server
PORT=9200
with open("/opt/device-exporter/config.json") as f: cfg=json.load(f)
DN=cfg["droplet"];DV=cfg["devices"];ED=cfg["edges"]
RR={"tor-router","spine-switch","storage-tor"};SR={"storage-controller","object-storage"}
CG=Gauge("cpu_percent","CPU",["id","droplet","role"]);MG=Gauge("memory_percent","Mem",["id","droplet","role"])
IG=Gauge("disk_iops","IOPS",["id","droplet","role"]);PG=Gauge("power_watts","Pwr",["id","droplet","role"])
TG=Gauge("temperature_celsius","Tmp",["id","droplet","role"])
LG=Gauge("latency_ms","Lat",["source","target"]);QG=Gauge("packet_loss_percent","Loss",["source","target"])
BG=Gauge("bandwidth_mbps","Bw",["source","target"])
def g(m,s,a,b):return max(a,min(b,random.gauss(m,s)))
def sv(r):
    if r in RR:return g(12,5,2,95),g(45,10,20,70),g(800,150,200,2000),g(180,30,100,300),g(45,5,25,90)
    if r in SR:return g(33,8,24.5,42),g(45,10,20,70),g(1400,250,400,4000),g(180,30,100,300),g(45,5,25,90)
    return g(33,8,24.5,42),g(45,10,20,70),g(800,150,200,2000),g(180,30,100,300),g(45,5,25,90)
start_http_server(PORT);print(f"[+] {DN} exporter on :{PORT}")
while True:
    for d in DV:
        c,m,i,p,t=sv(d["role"]);CG.labels(d["id"],DN,d["role"]).set(c);MG.labels(d["id"],DN,d["role"]).set(m)
        IG.labels(d["id"],DN,d["role"]).set(i);PG.labels(d["id"],DN,d["role"]).set(p);TG.labels(d["id"],DN,d["role"]).set(t)
    for a,b in ED:LG.labels(a,b).set(g(12,3,1,50));QG.labels(a,b).set(g(0.05,0.02,0,1));BG.labels(a,b).set(g(800,100,400,1000))
    time.sleep(3)
PYEOF

chmod 755 /opt/device-exporter/device_exporter.py

# Install dep
pip3 install --break-system-packages prometheus_client 2>/dev/null || pip3 install --user prometheus_client 2>/dev/null || { apt-get update -qq && apt-get install -y -qq python3-prometheus-client; }
python3 -c "import prometheus_client" && echo "[OK] dep ready" || { echo "FATAL: pip failed"; exit 1; }

# Systemd
cat > /etc/systemd/system/device-exporter.service << 'SVCEOF'
[Unit]
Description=HPE Digital Twin Device Exporter
After=docker.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/device-exporter/device_exporter.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now device-exporter
sleep 2

echo "=== RESULT ==="
systemctl is-active device-exporter && echo "Service: RUNNING" || echo "Service: FAILED"
curl -s localhost:9200/metrics | grep "^cpu_percent" | head -3
echo "=============="
