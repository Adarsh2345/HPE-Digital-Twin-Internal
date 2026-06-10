"""
core/validation/power_validator.py
Checks that combined power draw does not exceed cabinet envelope (1400W max).
"""
import networkx as nx
from config.settings import POWER_LIMIT_WATTS
from config.constants import NODE_ROLES


class PowerValidator:
    def validate(self, G: nx.DiGraph) -> dict:
        violations = []
        warnings = []

        # Group compute nodes by subnet
        subnet_power: dict[str, float] = {}
        for node_id in G.nodes:
            node = G.nodes[node_id]
            role = node.get("role", "")
            if role not in (NODE_ROLES["COMPUTE"], NODE_ROLES["TOR_ROUTER"]):
                continue
            subnet = node.get("subnet", "unknown")
            power = node.get("metrics", {}).get("power_watts", 180.0)
            subnet_power[subnet] = subnet_power.get(subnet, 0.0) + power

        for subnet, total in subnet_power.items():
            if total > POWER_LIMIT_WATTS:
                violations.append(
                    f"Power Envelope Breach on {subnet}: "
                    f"Combined electrical load is {total:.0f}W "
                    f"(Limit: {POWER_LIMIT_WATTS}W)."
                )
            elif total > POWER_LIMIT_WATTS * 0.85:
                warnings.append(
                    f"Power Warning on {subnet}: Load at {total:.0f}W "
                    f"({(total/POWER_LIMIT_WATTS*100):.1f}% of limit)."
                )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "subnet_power_watts": subnet_power,
        }
