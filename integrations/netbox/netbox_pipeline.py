"""
integrations/netbox/netbox_pipeline.py
Syncs the parsed infrastructure topology into NetBox (IPAM + DCIM).
Phase 1, Step 3: The Visual Registry Sync.
"""
import logging
from integrations.netbox.netbox_client import NetBoxClient

logger = logging.getLogger(__name__)


class NetBoxPipeline:
    def __init__(self, client: NetBoxClient):
        self.client = client

    def sync_topology(self, topology: dict):
        """
        Register all nodes as devices and all IPs in NetBox.
        Runs on startup as part of Phase 1 bootstrap.
        """
        logger.info("NetBox sync started — registering IPAM/DCIM records")
        nodes = topology.get("nodes", [])
        synced = 0
        for node in nodes:
            name = node.get("id", "")
            role = node.get("role", "unknown")
            ip = node.get("ip", "")

            # Create device
            self.client.create_device(name=name, role=role)

            # Register IP
            if ip:
                self.client.create_ip(address=f"{ip}/24", description=f"Interface IP for {name}")

            synced += 1

        logger.info(f"NetBox sync complete — {synced} records registered")

    def get_inventory(self) -> dict:
        devices = self.client.get_devices()
        ips = self.client.get_ip_addresses()
        return {"devices": devices, "ip_addresses": ips}
