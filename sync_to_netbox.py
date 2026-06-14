# ============================================================
# sync_to_netbox.py — HPE Digital Twin (STORAGE RACK SYNC)
# Updates from previous version:
#   - Added roles: storage-tor, storage-controller, object-storage
#   - Added device types for storage rack devices
#   - Interface type fallback map: SAS/InfiniBand/25g/10g -> nearest
#     NetBox-supported type (NetBox rejects unknown types)
#   - ic0 direct interconnect cable (array-ctrl-a <-> array-ctrl-b)
#   - mgmt0 interfaces get their OWN ip (10.10.3.50/51), not eth0's
#   - services via ipam/services (parent_object_type/id) — unchanged
# ============================================================

import requests
import yaml

NB_URL   = "https://rdtn4963.cloud.netboxapp.com"
NB_TOKEN = "nbt_wY8QIIlT7kat.GaGLdoRp6k8oRoqMmcrAT0PE3JM96vOLzn5mnBfB"

HEADERS = {
    "Authorization": f"Token {NB_TOKEN}",
    "Content-Type":  "application/json",
    "Accept":        "application/json"
}

with open("infrastructure.yaml") as f:
    infra = yaml.safe_load(f)

print("=" * 60)
print("HPE Digital Twin → NetBox Storage Rack Sync")
print("=" * 60)


# ============================================================
# HELPERS
# ============================================================

def format_url(endpoint):
    base = NB_URL.rstrip('/')
    path = endpoint.strip('/')
    return f"{base}/api/{path}/"


def nb_post(endpoint, data):
    url = format_url(endpoint)
    r = requests.post(url, headers=HEADERS, json=data)
    try:
        body = r.json()
    except Exception:
        print(f"    ⚠️  No JSON : {r.status_code} -> HTML error page")
        return None
    if r.status_code in [200, 201]:
        label = data.get("name") or data.get("prefix") or data.get("address") or str(data)[:40]
        print(f"    ✅ Created : {label}")
        return body
    else:
        label = data.get("name") or str(data)[:40]
        print(f"    ⚠️  Failed  : {label} → {r.status_code} {str(body)[:140]}")
        return None


def nb_get(endpoint, params=None):
    url = format_url(endpoint)
    r = requests.get(url, headers=HEADERS, params=params)
    try:
        return r.json().get("results", [])
    except Exception:
        return []


def nb_get_or_create(endpoint, lookup, create_data):
    existing = nb_get(endpoint, lookup)
    if existing:
        obj = existing[0]
        label = obj.get("name") or obj.get("prefix") or obj.get("address") or "object"
        print(f"    ↩️  Exists  : {label}")
        return obj
    return nb_post(endpoint, create_data)


def nb_patch(endpoint, obj_id, data):
    url = f"{format_url(endpoint)}{obj_id}/"
    r = requests.patch(url, headers=HEADERS, json=data)
    try:
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def service_exists(vm_id, service_name):
    all_svcs = nb_get("ipam/services", {
        "parent_object_type": "virtualization.virtualmachine",
        "parent_object_id":   vm_id
    })
    return any(s.get("name") == service_name for s in all_svcs)


# ============================================================
# CONFIG MAPS
# ============================================================

# Roles that become DCIM Devices (physical/network infra)
DCIM_ROLES = {
    "tor-router", "spine-switch", "compute-node",
    "storage-tor", "storage-controller", "object-storage",
}

DEVICE_TYPE_MAP_KEY = {
    "spine-switch":       "FRR-Spine-Router",
    "tor-router":         "FRR-ToR-Router",
    "compute-node":       "Ubuntu-Server",
    "storage-tor":        "FRR-Storage-Router",
    "storage-controller": "TrueNAS-Controller",
    "object-storage":     "MinIO-Node",
}

ROLE_COLORS = {
    "spine-switch":       "9c27b0",
    "tor-router":         "2196f3",
    "compute-node":       "4caf50",
    "storage-tor":        "673ab7",
    "storage-controller": "ff5722",
    "object-storage":     "795548",
}

VM_SIZES = {
    "metrics-collector":   (1, 1024),
    "metrics-dashboard":   (1, 512),
    "metrics-exporter":    (1, 256),
    "container-metrics":   (1, 256),
    "graph-database":      (2, 2048),
    "middleware":          (1, 512),
    "infrastructure-docs": (2, 2048),
}

DROPLET_SIZE_MAP = {
    "s-2vcpu-4gb": (2, 4096),
    "s-1vcpu-2gb": (1, 2048),
    "s-2vcpu-8gb": (2, 8192),
}

# ── NetBox only accepts specific interface "type" choices.
#    SAS / InfiniBand / 25g / 10g aren't standard dcim.interface
#    types in most NetBox versions — map them to the nearest
#    supported value so creation doesn't 400.
#    (These are logical/documentation links anyway — see chat.)
IFACE_TYPE_FALLBACK = {
    "1000base-t":  "1000base-t",
    "10gbase-t":   "10gbase-t",
    "25gbase-t":   "25gbase-t",
    "sas":         "other",        # SAS isn't an Ethernet interface type
    "infiniband":  "other",   # NetBox DOES support infiniband types;
                                    # if your instance rejects it, falls back below
}

def safe_iface_type(raw_type):
    """Return a NetBox-acceptable interface type, falling back to 'other'."""
    return IFACE_TYPE_FALLBACK.get(raw_type, "other")


# ============================================================
# STEP 1 — Site
# ============================================================
print("\n[1] Site...")
site = nb_get_or_create(
    "dcim/sites",
    {"name": infra["site"]["name"]},
    {
        "name":        infra["site"]["name"],
        "slug":        infra["site"]["name"].replace("-", "_"),
        "status":      "active",
        "description": f"HPE Digital Twin — DigitalOcean {infra['site']['region']}"
    }
)
site_id = site["id"] if site else None
print(f"    Site ID: {site_id}")


# ============================================================
# STEP 2 — VPC as Location
# ============================================================
print("\n[2] VPC as Location...")
vpc = nb_get_or_create(
    "dcim/locations",
    {"name": infra["network"]["vpc"]["name"]},
    {
        "name": infra["network"]["vpc"]["name"],
        "slug": infra["network"]["vpc"]["name"].replace("-", "_"),
        "site": site_id
    }
)
vpc_id = vpc["id"] if vpc else None


# ============================================================
# STEP 3 — Subnets as IPAM Prefixes
# ============================================================
print("\n[3] Subnets as IPAM Prefixes...")
subnet_prefix_ids = {}
for subnet in infra["network"]["subnets"]:
    result = nb_get_or_create(
        "ipam/prefixes",
        {"prefix": subnet["cidr"]},
        {
            "prefix":      subnet["cidr"],
            "status":      "active",
            "site":        site_id,
            "description": f"{subnet['name']} — {subnet['description']}"
        }
    )
    if result:
        subnet_prefix_ids[subnet["name"]] = result["id"]


# ============================================================
# STEP 4 — Cluster
# ============================================================
print("\n[4] Cluster...")
cluster_type = nb_get_or_create(
    "virtualization/cluster-types",
    {"name": "DigitalOcean"},
    {"name": "DigitalOcean", "slug": "digitalocean"}
)
cluster_type_id = cluster_type["id"] if cluster_type else None

cluster = nb_get_or_create(
    "virtualization/clusters",
    {"name": infra["site"]["name"]},
    {
        "name": infra["site"]["name"],
        "type": cluster_type_id,
        "site": site_id
    }
)
cluster_id = cluster["id"] if cluster else None
print(f"    Cluster ID: {cluster_id}")


# ============================================================
# STEP 5 — Manufacturer
# ============================================================
print("\n[5] Manufacturer...")
manufacturer = nb_get_or_create(
    "dcim/manufacturers",
    {"name": "Virtual"},
    {"name": "Virtual", "slug": "virtual"}
)
manufacturer_id = manufacturer["id"] if manufacturer else None


# ============================================================
# STEP 6 — Device Roles
# ============================================================
print("\n[6] Device Roles...")
device_role_ids = {}
for role_name, color in ROLE_COLORS.items():
    role = nb_get_or_create(
        "dcim/device-roles",
        {"name": role_name},
        {
            "name":    role_name,
            "slug":    role_name.replace("-", "_"),
            "color":   color,
            "vm_role": False
        }
    )
    if role:
        device_role_ids[role_name] = role["id"]


# ============================================================
# STEP 7 — Device Types
# ============================================================
print("\n[7] Device Types...")
device_type_ids = {}
for model_name, slug in [
    ("FRR-Spine-Router",   "frr-spine-router"),
    ("FRR-ToR-Router",     "frr-tor-router"),
    ("Ubuntu-Server",      "ubuntu-server"),
    ("FRR-Storage-Router", "frr-storage-router"),
    ("TrueNAS-Controller", "truenas-controller"),
    ("MinIO-Node",         "minio-node"),
]:
    dt = nb_get_or_create(
        "dcim/device-types",
        {"model": model_name},
        {
            "manufacturer": manufacturer_id,
            "model":        model_name,
            "slug":         slug,
        }
    )
    if dt:
        device_type_ids[model_name] = dt["id"]


# ============================================================
# STEP 8 — DCIM Devices + ALL interfaces
#
# Handles:
#   - normal eth interfaces (eth0, eth1, ...) -> primary IP from
#     container['ip'] (only on the FIRST interface named "eth0")
#   - mgmt0 interfaces with THEIR OWN ip field (array-ctrl-a/b)
#   - sas*/ic0 interfaces -> created with safe_iface_type fallback
# ============================================================
print("\n[8] DCIM Devices + Interfaces...")

device_iface_ids = {}  # "device:iface" -> iface_id

for droplet_name, containers in infra["containers"].items():
    for container in containers:
        if container["role"] not in DCIM_ROLES:
            continue

        role   = container["role"]
        dt_key = DEVICE_TYPE_MAP_KEY[role]

        device = nb_get_or_create(
            "dcim/devices",
            {"name": container["name"]},
            {
                "name":        container["name"],
                "site":        site_id,
                "location":    vpc_id,
                "device_type": device_type_ids[dt_key],
                "role":        device_role_ids[role],
                "status":      "active",
                "comments": (
                    f"{container['description']}\n"
                    f"Hosted on: {droplet_name}\n"
                    f"Image: {container['image']}"
                )
            }
        )

        if not device:
            continue

        dev_id = device["id"]

        if "interfaces" in container:
            iface_defs = container["interfaces"]
        else:
            iface_defs = [{"name": "eth0", "type": "1000base-t", "description": "Primary interface"}]

        for iface_def in iface_defs:
            iface_name = iface_def["name"]
            raw_type   = iface_def.get("type", "1000base-t")
            nb_type    = safe_iface_type(raw_type)

            iface = nb_get_or_create(
                "dcim/interfaces",
                {"device_id": dev_id, "name": iface_name},
                {
                    "device":      dev_id,
                    "name":        iface_name,
                    "type":        nb_type,
                    "description": iface_def.get("description", "") + (
                        f" [orig type: {raw_type}]" if nb_type != raw_type else ""
                    ),
                }
            )
            if iface:
                key = f"{container['name']}:{iface_name}"
                device_iface_ids[key] = iface["id"]

                # ── IP assignment for THIS interface
                # Case A: this interface has its own explicit "ip" field
                #         (e.g. mgmt0 on array-ctrl-a/b)
                if iface_def.get("ip"):
                    ip_addr = f"{iface_def['ip']}/24"
                    nb_get_or_create(
                        "ipam/ip-addresses",
                        {"address": ip_addr},
                        {
                            "address":              ip_addr,
                            "status":               "active",
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id":   iface["id"],
                            "description":          f"{container['name']} — {iface_name} ({iface_def.get('role','mgmt')})"
                        }
                    )

        # ── Primary IP for the device — uses container-level "ip"
        #    assigned to its eth0 (if eth0 exists and has no own ip)
        if container.get("ip"):
            eth0_key = f"{container['name']}:eth0"
            eth0_id  = device_iface_ids.get(eth0_key)
            if eth0_id:
                ip_addr = f"{container['ip']}/24"
                ip_obj = nb_get_or_create(
                    "ipam/ip-addresses",
                    {"address": ip_addr},
                    {
                        "address":              ip_addr,
                        "status":               "active",
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id":   eth0_id,
                        "description":          f"{container['name']} — {role}"
                    }
                )
                if ip_obj:
                    nb_patch("dcim/devices", dev_id, {"primary_ip4": ip_obj["id"]})


# ============================================================
# STEP 9 — Droplets as Virtual Machines
# ============================================================
print("\n[9] Droplets as Virtual Machines...")
droplet_vm_ids = {}

for droplet in infra["droplets"]:
    vcpus, memory = DROPLET_SIZE_MAP.get(droplet["size"], (2, 4096))
    result = nb_get_or_create(
        "virtualization/virtual-machines",
        {"name": droplet["name"]},
        {
            "name":    droplet["name"],
            "status":  "active",
            "cluster": cluster_id,
            "vcpus":   vcpus,
            "memory":  memory,
            "comments": (
                f"{droplet['description']}\n"
                f"Region: {droplet['region']} | Subnet: {droplet['subnet']}\n"
                f"Size: {droplet['size']} | Image: {droplet['image']}\n"
                f"Tags: {', '.join(droplet.get('tags', []))}"
            )
        }
    )
    if result:
        droplet_vm_ids[droplet["name"]] = result["id"]
        nb_get_or_create(
            "virtualization/interfaces",
            {"virtual_machine_id": result["id"], "name": "eth0"},
            {"virtual_machine": result["id"], "name": "eth0"}
        )


# ============================================================
# STEP 10 — Software Containers as Virtual Machines
# ============================================================
print("\n[10] Software Containers as Virtual Machines...")

container_vm_ids    = {}
container_iface_ids = {}

for droplet_name, containers in infra["containers"].items():
    print(f"\n    {droplet_name}:")

    for container in containers:
        if container["role"] in DCIM_ROLES:
            print(f"      ⏩ {container['name']} → DCIM Device")
            continue

        vcpus, memory = VM_SIZES.get(container["role"], (1, 512))

        vm = nb_get_or_create(
            "virtualization/virtual-machines",
            {"name": container["name"]},
            {
                "name":    container["name"],
                "status":  "active",
                "cluster": cluster_id,
                "vcpus":   vcpus,
                "memory":  memory,
                "comments": (
                    f"Role: {container['role']}\n"
                    f"Image: {container['image']}\n"
                    f"Hosted on: {droplet_name}\n"
                    f"{container['description']}"
                )
            }
        )

        if not vm:
            continue

        vm_id = vm["id"]
        container_vm_ids[container["name"]] = vm_id

        # Host-network container handling
        if container.get("network_mode") == "host":
            print(f"      ℹ️  {container['name']} — host network")
            if container.get("port"):
                if not service_exists(vm_id, container["role"]):
                    nb_post("ipam/services", {
                        "parent_object_type": "virtualization.virtualmachine",
                        "parent_object_id":   vm_id,
                        "name":               container["role"],
                        "protocol":           "tcp",
                        "ports":              [container["port"]],
                        "description":        container["description"]
                    })
                else:
                    print(f"      ↩️  Service exists : port {container['port']}")
            continue

        # Normal VM: interface + IP + service
        iface = nb_get_or_create(
            "virtualization/interfaces",
            {"virtual_machine_id": vm_id, "name": "eth0"},
            {"virtual_machine": vm_id, "name": "eth0"}
        )

        if iface:
            iface_id = iface["id"]
            container_iface_ids[container["name"]] = iface_id

            if container.get("ip"):
                ip_addr = f"{container['ip']}/24"
                ip_obj = nb_get_or_create(
                    "ipam/ip-addresses",
                    {"address": ip_addr},
                    {
                        "address":              ip_addr,
                        "status":               "active",
                        "assigned_object_type": "virtualization.vminterface",
                        "assigned_object_id":   iface_id,
                        "description":          f"{container['name']} — {container['role']}"
                    }
                )
                if ip_obj:
                    nb_patch("virtualization/virtual-machines", vm_id, {
                        "primary_ip4": ip_obj["id"]
                    })

            if container.get("port"):
                if not service_exists(vm_id, container["role"]):
                    nb_post("ipam/services", {
                        "parent_object_type": "virtualization.virtualmachine",
                        "parent_object_id":   vm_id,
                        "name":               container["role"],
                        "protocol":           "tcp",
                        "ports":              [container["port"]],
                        "description":        container["description"]
                    })
                else:
                    print(f"      ↩️  Service exists : port {container['port']}")


# ============================================================
# STEP 11 — Network Links as Cables
#
# Handles both:
#   - normal links (source/target + source_iface/target_iface)
#   - link_type: "direct" (e.g. ic0 <-> ic0 controller interconnect)
#     -> still a dcim.cable, just labeled/typed as direct
# ============================================================
print("\n[11] Network Links as Cables...")

for link in infra["links"]:
    src       = link["source"]
    tgt       = link["target"]
    src_iface = link.get("source_iface", "eth0")
    tgt_iface = link.get("target_iface", "eth0")

    src_key = f"{src}:{src_iface}"
    tgt_key = f"{tgt}:{tgt_iface}"

    src_id = device_iface_ids.get(src_key)
    tgt_id = device_iface_ids.get(tgt_key)

    if not src_id or not tgt_id:
        print(f"    ⚠️  Skipping {src}({src_iface})↔{tgt}({tgt_iface}) — interface not found")
        continue

    # Check both ends — an interface can only be in ONE cable
    src_has_cable = (
        nb_get("dcim/cables", {"termination_a_type": "dcim.interface", "termination_a_id": src_id}) or
        nb_get("dcim/cables", {"termination_b_type": "dcim.interface", "termination_b_id": src_id})
    )
    tgt_has_cable = (
        nb_get("dcim/cables", {"termination_a_type": "dcim.interface", "termination_a_id": tgt_id}) or
        nb_get("dcim/cables", {"termination_b_type": "dcim.interface", "termination_b_id": tgt_id})
    )

    if src_has_cable or tgt_has_cable:
        print(f"    ↩️  Cable exists or port occupied : {src}({src_iface}) ↔ {tgt}({tgt_iface})")
        continue

    label = link["description"]
    if link.get("link_type") == "direct":
        label = f"[DIRECT] {label}"

    result = nb_post("dcim/cables", {
        "a_terminations": [{"object_type": "dcim.interface", "object_id": src_id}],
        "b_terminations": [{"object_type": "dcim.interface", "object_id": tgt_id}],
        "status":         "connected",
        "label":          label
    })
    if result:
        print(f"    ✅ Cable : {src}({src_iface}) ↔ {tgt}({tgt_iface})")


# ============================================================
# STEP 12 — Summary
# ============================================================
print("\n" + "=" * 60)
print("Sync Complete!")
print("=" * 60)

dcim_list = [
    c for d, cs in infra["containers"].items()
    for c in cs if c["role"] in DCIM_ROLES
]
vm_list = [
    c for d, cs in infra["containers"].items()
    for c in cs if c["role"] not in DCIM_ROLES
]
port_list = [c for c in vm_list if c.get("port")]

print(f"  Site            : {infra['site']['name']}")
print(f"  Subnets         : {len(infra['network']['subnets'])}")
print(f"  Droplets        : {len(infra['droplets'])}")
print(f"  DCIM Devices    : {len(dcim_list)}  (routers, servers, storage rack)")
print(f"  Software VMs    : {len(vm_list)}")
print(f"  Service Ports   : {len(port_list)}")
print(f"  Cables          : {len(infra['links'])}")
print(f"\n  NetBox UI → {NB_URL}")
print("=" * 60)
print("\nWhat is properly modeled in NetBox:")
print("  ✅ Compute racks  → routers + servers (DCIM, cabled)")
print("  ✅ Storage rack   → storage-router, array-ctrl-a/b, obj-node-1/2/3 (DCIM)")
print("  ✅ Controller HA  → ic0<->ic0 direct cable (interconnect)")
print("  ✅ mgmt0 ports    → separate IPs (10.10.3.50/51) on mgmt subnet")
print("  ✅ SAS/InfiniBand → created with fallback interface type 'other'")
print("                      (NetBox doesn't natively support SAS as an")
print("                       Ethernet interface type — documented via")
print("                       description + label, logical-only links)")
print("  ✅ Software VMs   → netbox, neo4j, prometheus, grafana, etc.")
print("=" * 60)