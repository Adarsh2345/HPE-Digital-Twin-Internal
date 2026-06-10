"""
core/validation/rack_validator.py
Checks that node count per rack does not exceed 42U cabinet limit.
Each compute node = 1U, each router = 2U.
"""
import networkx as nx
from config.settings import RACK_U_LIMIT
from config.constants import NODE_ROLES

U_SIZE = {
    NODE_ROLES["COMPUTE"]: 1,
    NODE_ROLES["TOR_ROUTER"]: 2,
    NODE_ROLES["SPINE"]: 4,
    NODE_ROLES["NETBOX"]: 2,
    NODE_ROLES["NEO4J"]: 2,
    NODE_ROLES["MIDDLEWARE"]: 1,
}


class RackValidator:
    def validate(self, G: nx.DiGraph) -> dict:
        violations = []
        warnings = []

        droplet_u: dict[str, int] = {}
        for node_id in G.nodes:
            node = G.nodes[node_id]
            droplet = node.get("droplet", "unknown")
            role = node.get("role", "")
            u = U_SIZE.get(role, 1)
            droplet_u[droplet] = droplet_u.get(droplet, 0) + u

        for droplet, total_u in droplet_u.items():
            if total_u > RACK_U_LIMIT:
                violations.append(
                    f"Rack U-Space Breach on {droplet}: "
                    f"{total_u}U occupied (Limit: {RACK_U_LIMIT}U)."
                )
            elif total_u > RACK_U_LIMIT * 0.85:
                warnings.append(
                    f"Rack Warning on {droplet}: {total_u}U used "
                    f"({(total_u/RACK_U_LIMIT*100):.1f}% of {RACK_U_LIMIT}U)."
                )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "droplet_u_usage": droplet_u,
        }
