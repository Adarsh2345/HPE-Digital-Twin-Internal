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
                "id": raw["name"],
                "name": raw["name"],
                "role": raw.get("role", "unknown"),
                "ip": raw.get("ip", ""),
                "image": raw.get("image", ""),
                "droplet": raw.get("droplet", ""),
                "description": raw.get("description", ""),
                "port": raw.get("port"),
                "subnet": raw.get("droplet_meta", {}).get("subnet", ""),
                "size": raw.get("droplet_meta", {}).get("size", ""),
                "tags": raw.get("droplet_meta", {}).get("tags", []),
                # 🟢 ADDED: Retain individual host port interface lists in the node graph definition
                "interfaces": raw.get("interfaces", []),
                "state": "healthy",
                "metrics": {},
            }
            nodes.append(node)
        return nodes

    def _build_edges(self) -> list[dict]:
        edges = []
        for link in self.parser.links:
            edge = {
                "source": link["source"],
                "target": link["target"],
                # 🟢 ADDED: Map explicit physical interfaces and link types onto the network edges
                "source_iface": link.get("source_iface", "eth0"),
                "target_iface": link.get("target_iface", "eth0"),
                "link_type": link.get("link_type", "ethernet"),
                "description": link.get("description", ""),
                "state": "active",
                "metrics": {},
            }
            edges.append(edge)
        return edges