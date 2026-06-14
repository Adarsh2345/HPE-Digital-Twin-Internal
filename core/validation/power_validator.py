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

        # Group hardware elements by their subnet envelope boundaries
        subnet_power: dict[str, float] = {}
        for node_id in G.nodes:
            node = G.nodes[node_id]
            role = node.get("role", "")
            
            # 🟢 EXTENDED: Ensure power draw validation captures your new storage fabric roles
            if role not in (
                NODE_ROLES["COMPUTE"], 
                NODE_ROLES["TOR_ROUTER"],
                NODE_ROLES["STORAGE_TOR"],
                NODE_ROLES["STORAGE_CONTROLLER"],
                NODE_ROLES["OBJECT_STORAGE"]
            ):
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
                subnet_pct = (total / POWER_LIMIT_WATTS * 100)
                warnings.append(
                    f"Power Warning on {subnet}: Load at {total:.0f}W "
                    f"({subnet_pct:.1f}% of limit)."
                )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "subnet_power_watts": subnet_power,
        }