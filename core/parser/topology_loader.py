"""
core/parser/topology_loader.py
Converts parsed YAML into structured topology data ready for NetworkX.
EXTENDED: Preserves physical interface port parameters for precise impact mapping.
"""
from core.parser.yaml_parser import YAMLParser
from config.constants import NODE_ROLES
import logging

logger = logging.getLogger(__name__)


class TopologyLoader:
    def __init__(self, parser: YAMLParser):
        self.parser = parser

    def load_topology(self) -> dict:
        nodes = self._build_nodes()
        edges = self._build_edges()
        meta = {
            "site": self.parser.site,
            "vpc": self.parser.get_vpc(),
            "subnets": self.parser.get_subnets(),
            "droplets": self.parser.droplets,
        }
        topology = {"nodes": nodes, "edges": edges, "meta": meta}
        logger.info(
            f"Topology loaded: {len(nodes)} nodes, {len(edges)} edges"
        )
        return topology

    def _build_nodes(self) -> list[dict]:
        nodes = []
        for raw in self.parser.get_all_nodes():
            node = {
                "id": f"{raw['droplet']}/{raw['name']}",
                "name": raw["name"],
                "display_name": raw["name"],
                "node_type": self._node_type(raw.get("role", "unknown")),
                "role": raw.get("role", "unknown"),
                "ip": raw.get("ip", ""),
                "image": raw.get("image", ""),
                "droplet": raw.get("droplet", ""),
                "description": raw.get("description", ""),
                "port": raw.get("port"),
                "subnet": raw.get("droplet_meta", {}).get("subnet", ""),
                "size": raw.get("droplet_meta", {}).get("size", ""),
                "tags": raw.get("droplet_meta", {}).get("tags", []),
                "interfaces": raw.get("interfaces", []),
                "state": "healthy",
                "metrics": {},
                "capacity": {},
                "metadata": {},
                "source": "yaml",
            }
            nodes.append(node)
        return nodes

    def _build_edges(self) -> list[dict]:
        edges = []
        local_ids: dict[str, list[str]] = {}
        for node in self._build_nodes():
            local_ids.setdefault(node["display_name"], []).append(node["id"])

        def resolve(value: str) -> str:
            if "/" in value:
                return value
            matches = local_ids.get(value, [])
            return matches[0] if len(matches) == 1 else value

        for link in self.parser.links:
            edge = {
                "source": resolve(link["source"]),
                "target": resolve(link["target"]),
                "source_iface": link.get("source_iface", "eth0"),
                "target_iface": link.get("target_iface", "eth0"),
                "link_type": link.get("link_type", "network_link"),
                "edge_type": "network_link" if link.get("link_type") != "direct" else "replicates_to",
                "dependency_direction": "provider_to_dependents",
                "description": link.get("description", ""),
                "state": "active",
                "metrics": {},
            }
            edges.append(edge)
        return edges

    @staticmethod
    def _node_type(role: str) -> str:
        return {
            "compute-node": "server",
            "tor-router": "switch",
            "storage-tor": "switch",
            "spine-switch": "switch",
            "storage-controller": "storage_controller",
            "object-storage": "object_storage",
            "metrics-exporter": "metrics_exporter",
            "container-metrics": "metrics_exporter",
        }.get(role, "service")
