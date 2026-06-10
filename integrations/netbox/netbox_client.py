"""
integrations/netbox/netbox_client.py
Thin wrapper around the NetBox REST API.
"""
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class NetBoxClient:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, endpoint: str) -> Optional[dict]:
        if not _HAS_REQUESTS:
            return None
        try:
            r = requests.get(f"{self.url}/api/{endpoint}", headers=self._headers, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"NetBox GET {endpoint} failed: {e}")
            return None

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        if not _HAS_REQUESTS:
            return None
        try:
            r = requests.post(
                f"{self.url}/api/{endpoint}",
                headers=self._headers,
                data=json.dumps(data),
                timeout=5,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"NetBox POST {endpoint} failed: {e}")
            return None

    def get_devices(self) -> list:
        result = self._get("dcim/devices/?limit=100")
        return result.get("results", []) if result else []

    def create_device(self, name: str, role: str, site: str = "hpe-digital-twin") -> Optional[dict]:
        return self._post("dcim/devices/", {
            "name": name,
            "device_role": {"name": role},
            "site": {"name": site},
        })

    def get_ip_addresses(self) -> list:
        result = self._get("ipam/ip-addresses/?limit=200")
        return result.get("results", []) if result else []

    def create_ip(self, address: str, description: str = "") -> Optional[dict]:
        return self._post("ipam/ip-addresses/", {
            "address": address,
            "description": description,
            "status": "active",
        })
