#!/usr/bin/env python3
"""
device_exporter.py - Per-droplet Prometheus exporter.
Reads config from /opt/device-exporter/config.json
Emits cpu_percent, memory_percent, disk_iops, power_watts, temperature_celsius,
latency_ms, packet_loss_percent, bandwidth_mbps on port 9200.
"""
import json
import os
import random
import time

from prometheus_client import Gauge, start_http_server

PORT = 9200
CONFIG_PATH = "/opt/device-exporter/config.json"

ROUTER_ROLES = {"tor-router", "spine-switch", "storage-tor"}
STORAGE_ROLES = {"storage-controller", "object-storage"}

CPU  = Gauge("cpu_percent",         "CPU",       ["id", "droplet", "role"])
MEM  = Gauge("memory_percent",      "Memory",    ["id", "droplet", "role"])
IOPS = Gauge("disk_iops",           "Disk IOPS", ["id", "droplet", "role"])
PWR  = Gauge("power_watts",         "Watts",     ["id", "droplet", "role"])
TMP  = Gauge("temperature_celsius", "Celsius",   ["id", "droplet", "role"])
LAT  = Gauge("latency_ms",          "Latency",   ["source", "target"])
LOSS = Gauge("packet_loss_percent", "Loss",      ["source", "target"])
BW   = Gauge("bandwidth_mbps",      "Bandwidth", ["source", "target"])


def g(mu, sd, lo, hi):
    return max(lo, min(hi, random.gauss(mu, sd)))


def sample(role):
    if role in ROUTER_ROLES:
        return g(12,5,2,95), g(45,10,20,70), g(800,150,200,2000), g(180,30,100,300), g(45,5,25,90)
    if role in STORAGE_ROLES:
        return g(33,8,24.5,42), g(45,10,20,70), g(1400,250,400,4000), g(180,30,100,300), g(45,5,25,90)
    return g(33,8,24.5,42), g(45,10,20,70), g(800,150,200,2000), g(180,30,100,300), g(45,5,25,90)


def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    droplet = cfg["droplet"]
    devices = cfg["devices"]
    edges   = cfg["edges"]

    start_http_server(PORT)
    print(f"[+] {droplet} exporter on :{PORT} ({len(devices)} devices, {len(edges)} edges)")

    while True:
        for d in devices:
            c, m, i, p, t = sample(d["role"])
            CPU.labels(d["id"], droplet, d["role"]).set(c)
            MEM.labels(d["id"], droplet, d["role"]).set(m)
            IOPS.labels(d["id"], droplet, d["role"]).set(i)
            PWR.labels(d["id"], droplet, d["role"]).set(p)
            TMP.labels(d["id"], droplet, d["role"]).set(t)
        for src, tgt in edges:
            LAT.labels(src, tgt).set(g(12, 3, 1, 50))
            LOSS.labels(src, tgt).set(g(0.05, 0.02, 0, 1))
            BW.labels(src, tgt).set(g(800, 100, 400, 1000))
        time.sleep(3)


if __name__ == "__main__":
    main()
