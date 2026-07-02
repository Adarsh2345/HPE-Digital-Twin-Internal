"""
integrations/digitalocean/do_client.py
Thin wrapper around the DigitalOcean v2 REST API.
Only implements the operations the digital twin actually needs.
"""
from __future__ import annotations
import logging
import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.digitalocean.com/v2"


class DOClient:
    def __init__(self, token: str):
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    # ── Read ────────────────────────────────────────────────────────────────

    def list_droplets(self) -> list[dict]:
        r = self._session.get(f"{_BASE}/droplets", params={"per_page": 100}, timeout=15)
        r.raise_for_status()
        return r.json().get("droplets", [])

    def get_droplet(self, droplet_id: int) -> dict:
        r = self._session.get(f"{_BASE}/droplets/{droplet_id}", timeout=15)
        r.raise_for_status()
        return r.json()["droplet"]

    def list_vpcs(self) -> list[dict]:
        r = self._session.get(f"{_BASE}/vpcs", params={"per_page": 100}, timeout=15)
        r.raise_for_status()
        return r.json().get("vpcs", [])

    # ── Create Droplet ───────────────────────────────────────────────────────

    def create_droplet(
        self,
        name: str,
        region: str,
        size: str,
        image: str,
        vpc_uuid: str,
        tags: list[str] | None = None,
        user_data: str | None = None,
    ) -> dict:
        body: dict = {
            "name": name,
            "region": region,
            "size": size,
            "image": image,
            "vpc_uuid": vpc_uuid,
            "tags": tags or [],
        }
        if user_data:
            body["user_data"] = user_data
        r = self._session.post(f"{_BASE}/droplets", json=body, timeout=30)
        r.raise_for_status()
        return r.json()["droplet"]

    # ── Delete Droplet ───────────────────────────────────────────────────────

    def delete_droplet(self, droplet_id: int) -> None:
        r = self._session.delete(f"{_BASE}/droplets/{droplet_id}", timeout=15)
        r.raise_for_status()

    # ── Tag helpers ──────────────────────────────────────────────────────────

    def tag_droplet(self, droplet_id: int, tag: str) -> None:
        # Ensure tag exists
        self._session.post(f"{_BASE}/tags", json={"name": tag}, timeout=10)
        r = self._session.post(
            f"{_BASE}/tags/{tag}/resources",
            json={"resources": [{"resource_id": str(droplet_id), "resource_type": "droplet"}]},
            timeout=10,
        )
        r.raise_for_status()
