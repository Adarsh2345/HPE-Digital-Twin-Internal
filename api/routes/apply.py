"""
api/routes/apply.py
Apply a validated simulation result to real infrastructure.

Servers (server-N, router-N) are Docker containers running INSIDE DigitalOcean
droplets — not separate DO droplets. The correct apply operation is:
  add_compute  → SSH into the target droplet, run a new Docker container
  remove_node  → SSH into the host droplet, stop + remove the container

Rack → droplet mapping:
  droplet-1-tor1  →  165.22.221.170   network: tor1-net  10.10.1.0/24
  droplet-2-tor2  →  157.245.107.150  network: tor2-net  10.10.2.0/24
"""
from __future__ import annotations
import json
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/apply", tags=["Apply"])

_TF_STATE = Path(__file__).parent.parent.parent / "terraform-pipeline" / "terraform.tfstate"

# ── Static rack topology ─────────────────────────────────────────────────────
# IP ranges and Docker network names per rack, matching cloud-init definitions.
_RACK_CONFIG: dict[str, dict] = {
    "droplet-1-tor1": {
        "network":   "docker-compose_tor1-net",
        "ip_prefix": "10.10.1",
    },
    "droplet-2-tor2": {
        "network":   "docker-compose_tor2-net",
        "ip_prefix": "10.10.2",
    },
}

_ROUTER_TO_RACK: dict[str, str] = {
    "router-1": "droplet-1-tor1",
    "droplet-1-tor1/router-1": "droplet-1-tor1",
    "router-2": "droplet-2-tor2",
    "droplet-2-tor2/router-2": "droplet-2-tor2",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tf_state() -> dict:
    if not _TF_STATE.exists():
        return {}
    return json.loads(_TF_STATE.read_text())


def _live_droplet_ips() -> dict[str, str]:
    """Fetch current public IPs from the DO API (terraform state IPs go stale on rebuild)."""
    try:
        token = _do_token()
        import requests
        r = requests.get(
            "https://api.digitalocean.com/v2/droplets",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 100},
            timeout=15,
        )
        r.raise_for_status()
        return {
            d["name"]: d["networks"]["v4"][0]["ip_address"]
            for d in r.json().get("droplets", [])
            if d["networks"]["v4"]
        }
    except Exception as e:
        logger.warning(f"Could not fetch live IPs from DO API, falling back to tf state: {e}")
        state = _tf_state()
        result = {}
        for res in state.get("resources", []):
            if res.get("type") == "digitalocean_droplet":
                for inst in res["instances"]:
                    a = inst["attributes"]
                    result[a["name"]] = a.get("ipv4_address", "")
        return result


def _do_token() -> str:
    from config.settings import BASE_DIR
    tfvars = BASE_DIR / "terraform-pipeline" / "terraform.tfvars"
    if tfvars.exists():
        for line in tfvars.read_text().splitlines():
            if "do_token" in line:
                return line.split("=", 1)[1].strip().strip('"')
    import os
    token = os.getenv("DO_TOKEN", "")
    if not token:
        raise HTTPException(status_code=500, detail="DigitalOcean token not configured")
    return token


def _rack_from_params(params: dict) -> str:
    rack = params.get("target_droplet") or params.get("target_rack_id", "")
    if not rack:
        router = params.get("target_router") or params.get("router_id") or params.get("target_router_id", "")
        rack = _ROUTER_TO_RACK.get(router, "")
        if not rack and "/" in router:
            rack = router.split("/", 1)[0]
    return rack or "droplet-2-tor2"


def _ssh(host: str, command: str) -> str:
    """
    Run a command on a remote droplet over SSH.
    Uses the DO console SSH key expected at ~/.ssh/id_rsa (standard DO key location).
    StrictHostKeyChecking disabled since droplet IPs can change after rebuilds.
    """
    # Use the repo deploy key — works from any machine that has the repo checked out
    deploy_key = Path(__file__).parent.parent.parent / "terraform-pipeline" / "hpe-twin-deploy-key"
    # Fall back to personal key if deploy key missing (local dev without full repo)
    ssh_key = deploy_key if deploy_key.exists() else Path.home() / ".ssh" / "id_ed25519"
    ssh_cmd = [
        "ssh",
        "-i", str(ssh_key),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        "-o", "BatchMode=yes",
        f"root@{host}",
        command,
    ]
    logger.info(f"SSH {host}: {command}")
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise HTTPException(
                status_code=502,
                detail=f"SSH command failed on {host}: {result.stderr.strip() or result.stdout.strip()}",
            )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"SSH connection to {host} timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="SSH client not found on the server")


def _next_container_ip(host: str, ip_prefix: str) -> str:
    """Ask the remote host which IPs are already in use on its Docker network, pick the next free one."""
    try:
        out = _ssh(host, "docker inspect $(docker ps -aq) --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || true")
        used_octets = set()
        for line in out.splitlines():
            line = line.strip()
            if line.startswith(ip_prefix + "."):
                try:
                    used_octets.add(int(line.split(".")[-1]))
                except ValueError:
                    pass
        octet = 11
        while octet in used_octets:
            octet += 1
        return f"{ip_prefix}.{octet}"
    except Exception:
        # If we can't inspect, just return .20 as a safe fallback
        return f"{ip_prefix}.20"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/simulate")
def apply_change(payload: dict = Body(...)):
    """
    Apply a validated simulation result to live infrastructure.
    add_compute → SSH into the target droplet, start a new Docker container.
    remove_node → SSH into the host droplet, stop and remove the container.
    """
    action = payload.get("action", "")
    params = payload.get("params", {})

    if action == "add_compute":
        return _apply_add_compute(params)
    elif action == "remove_node":
        return _apply_remove_node(params)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{action}' cannot be applied to live infrastructure. "
                   "Only add_compute and remove_node are supported.",
        )


@router.post("/revert")
def revert_change(payload: dict = Body(...)):
    """
    Revert a previously applied change.
    add_compute was applied → revert = stop + remove the container.
    remove_node was applied → revert = recreate the container.
    """
    action        = payload.get("action", "")
    container     = payload.get("container_name", "")
    host          = payload.get("host", "")
    rack          = payload.get("rack", "")
    params        = payload.get("params", {})

    if action == "add_compute":
        return _revert_add_compute(host, container)
    elif action == "remove_node":
        return _revert_remove_node(host, container, rack, params)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot revert action '{action}'. Only add_compute and remove_node are supported.",
        )


# ── Add compute ───────────────────────────────────────────────────────────────

def _apply_add_compute(params: dict) -> dict:
    node_id = params.get("node_id", "")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required for add_compute")

    # Strip composite prefix if present (e.g. "droplet-2-tor2/server-5" → "server-5")
    short_name = node_id.split("/")[-1]

    rack = _rack_from_params(params)
    rack_cfg = _RACK_CONFIG.get(rack)
    if not rack_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown rack '{rack}'. Expected droplet-1-tor1 or droplet-2-tor2.")

    # Get live public IP of the target droplet
    ips = _live_droplet_ips()
    host = ips.get(rack)
    if not host:
        raise HTTPException(status_code=502, detail=f"Could not resolve public IP for {rack}. Available: {list(ips.keys())}")

    network   = rack_cfg["network"]
    ip_prefix = rack_cfg["ip_prefix"]
    container_ip = _next_container_ip(host, ip_prefix)

    logger.info(f"apply add_compute: launching container '{short_name}' on {rack} ({host}) ip={container_ip}")

    # Check container doesn't already exist
    existing = _ssh(host, f"docker ps -a --filter name=^{short_name}$ --format '{{{{.Names}}}}'")
    if existing.strip():
        raise HTTPException(status_code=409, detail=f"Container '{short_name}' already exists on {rack}.")

    _ssh(
        host,
        f"docker run -d --name {short_name} "
        f"--network {network} "
        f"--ip {container_ip} "
        f"--cap-add NET_ADMIN "
        f"--restart unless-stopped "
        f"ubuntu:24.04 sleep infinity"
    )

    logger.info(f"Container '{short_name}' started on {rack} at {container_ip}")

    return {
        "status":         "applied",
        "action":         "add_compute",
        "container_name": short_name,
        "host":           host,
        "rack":           rack,
        "container_ip":   container_ip,
        "message":        f"Container '{short_name}' is now running on {rack} ({host}) "
                          f"at {container_ip} on the {network} network.",
    }


def _revert_add_compute(host: str, container_name: str) -> dict:
    if not host or not container_name:
        raise HTTPException(status_code=400, detail="host and container_name are required to revert add_compute")

    logger.info(f"revert add_compute: stopping and removing container '{container_name}' on {host}")
    _ssh(host, f"docker stop {container_name} && docker rm {container_name}")

    return {
        "status":         "reverted",
        "action":         "add_compute",
        "container_name": container_name,
        "host":           host,
        "message":        f"Container '{container_name}' has been stopped and removed. Infrastructure is back to its previous state.",
    }


# ── Remove node ───────────────────────────────────────────────────────────────

def _apply_remove_node(params: dict) -> dict:
    node_id = params.get("node_id") or params.get("server_id", "")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required for remove_node")

    short_name = node_id.split("/")[-1]

    # Find which droplet hosts this container by checking both racks
    ips = _live_droplet_ips()
    host = None
    rack = None

    for rack_name, rack_cfg in _RACK_CONFIG.items():
        candidate_host = ips.get(rack_name)
        if not candidate_host:
            continue
        try:
            out = _ssh(candidate_host, f"docker ps -a --filter name=^{short_name}$ --format '{{{{.Names}}}}'")
            if out.strip():
                host = candidate_host
                rack = rack_name
                break
        except Exception:
            continue

    if not host:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{short_name}' not found on any rack droplet. "
                   f"Checked: {list(_RACK_CONFIG.keys())}",
        )

    # Capture container config before removing (for revert)
    inspect_raw = _ssh(host, f"docker inspect {short_name} --format '{{{{json .NetworkSettings.Networks}}}}'")

    logger.info(f"apply remove_node: stopping container '{short_name}' on {rack} ({host})")
    _ssh(host, f"docker stop {short_name} && docker rm {short_name}")

    return {
        "status":         "applied",
        "action":         "remove_node",
        "container_name": short_name,
        "host":           host,
        "rack":           rack,
        "inspect_snapshot": inspect_raw,
        "message":        f"Container '{short_name}' has been stopped and removed from {rack} ({host}).",
    }


def _revert_remove_node(host: str, container_name: str, rack: str, params: dict) -> dict:
    if not host or not container_name:
        raise HTTPException(status_code=400, detail="host and container_name are required to revert remove_node")

    rack_cfg = _RACK_CONFIG.get(rack, _RACK_CONFIG["droplet-2-tor2"])
    network   = rack_cfg["network"]
    ip_prefix = rack_cfg["ip_prefix"]
    container_ip = _next_container_ip(host, ip_prefix)

    logger.info(f"revert remove_node: recreating container '{container_name}' on {rack} ({host})")

    _ssh(
        host,
        f"docker run -d --name {container_name} "
        f"--network {network} "
        f"--ip {container_ip} "
        f"--cap-add NET_ADMIN "
        f"--restart unless-stopped "
        f"ubuntu:24.04 sleep infinity"
    )

    return {
        "status":         "reverted",
        "action":         "remove_node",
        "container_name": container_name,
        "host":           host,
        "rack":           rack,
        "container_ip":   container_ip,
        "message":        f"Container '{container_name}' has been recreated on {rack} ({host}) at {container_ip}. Infrastructure is back to its previous state.",
    }
