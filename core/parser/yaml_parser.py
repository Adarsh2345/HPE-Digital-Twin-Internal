"""
core/parser/yaml_parser.py
Loads and validates the infrastructure YAML blueprint.
DigitalOcean Droplets → physical racks
Docker containers     → compute blades / routing engines
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class YAMLParser:
    def __init__(self, yaml_path: str):
        self.yaml_path = Path(yaml_path)
        self._raw: dict = {}

    def load(self) -> dict:
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Infrastructure YAML not found: {self.yaml_path}")
        from schema.yaml_validator import load_and_validate, to_legacy_topology
        self._raw = to_legacy_topology(load_and_validate(self.yaml_path))
        logger.info(f"Loaded infrastructure YAML from {self.yaml_path}")
        return self._raw

    @property
    def site(self) -> dict:
        return self._raw.get("site", {})

    @property
    def network(self) -> dict:
        return self._raw.get("network", {})

    @property
    def droplets(self) -> list:
        return self._raw.get("droplets", [])

    @property
    def containers(self) -> dict:
        return self._raw.get("containers", {})

    @property
    def links(self) -> list:
        return self._raw.get("links", [])

    def get_all_nodes(self) -> list[dict]:
        """Flatten all containers across all droplets into a node list."""
        nodes = []
        for droplet_name, clist in self.containers.items():
            droplet_meta = next(
                (d for d in self.droplets if d["name"] == droplet_name), {}
            )
            for c in clist:
                node = {**c, "droplet": droplet_name, "droplet_meta": droplet_meta}
                nodes.append(node)
        return nodes

    def get_subnets(self) -> list[dict]:
        return self.network.get("subnets", [])

    def get_vpc(self) -> dict:
        return self.network.get("vpc", {})