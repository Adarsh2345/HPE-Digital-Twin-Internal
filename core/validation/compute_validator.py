"""
core/validation/compute_validator.py
Checks that projected CPU and memory do not exceed 95% capacity ceiling.
"""
import networkx as nx
from config.settings import CPU_CAPACITY_LIMIT, MEMORY_CAPACITY_LIMIT
from config.constants import NODE_ROLES


class ComputeValidator:
    def validate(self, G: nx.DiGraph, projections: list[dict] = None) -> dict:
        violations = []
        warnings = []

        # Check current metrics
        for node_id in G.nodes:
            node = G.nodes[node_id]
            if node.get("role") != NODE_ROLES["COMPUTE"]:
                continue
            metrics = node.get("metrics", {})
            cpu = metrics.get("cpu_percent", 0)
            mem = metrics.get("memory_percent", 0)

            if cpu >= CPU_CAPACITY_LIMIT or mem >= MEMORY_CAPACITY_LIMIT:
                violations.append(
                    f"Compute Overload on {node_id}: "
                    f"CPU={cpu:.1f}% MEM={mem:.1f}% "
                    f"(Limit: {CPU_CAPACITY_LIMIT}%)."
                )
            elif cpu >= CPU_CAPACITY_LIMIT * 0.85 or mem >= MEMORY_CAPACITY_LIMIT * 0.85:
                warnings.append(
                    f"Compute Warning on {node_id}: "
                    f"CPU={cpu:.1f}% MEM={mem:.1f}%."
                )

        # Check projected future steps
        future_violations = []
        if projections:
            for proj in projections:
                step = proj["step"]
                for node_id, pm in proj.get("nodes", {}).items():
                    cpu = pm.get("cpu_percent", 0)
                    mem = pm.get("memory_percent", 0)
                    if cpu >= CPU_CAPACITY_LIMIT or mem >= MEMORY_CAPACITY_LIMIT:
                        future_violations.append(
                            f"Projected Step {step}: {node_id} CPU={cpu:.1f}% MEM={mem:.1f}%."
                        )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "future_violations": future_violations,
        }
