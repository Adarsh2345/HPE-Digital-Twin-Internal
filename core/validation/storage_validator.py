"""
core/validation/storage_validator.py
Checks disk IOPS against NVMe hardware limit (4000 IOPS max).
"""
import networkx as nx
from config.settings import STORAGE_IOPS_LIMIT
from config.constants import NODE_ROLES


class StorageValidator:
    def validate(self, G: nx.DiGraph, projections: list[dict] = None) -> dict:
        violations = []
        warnings = []

        for node_id in G.nodes:
            node = G.nodes[node_id]
            if node.get("role") not in (NODE_ROLES["COMPUTE"], NODE_ROLES["MIDDLEWARE"], NODE_ROLES["NEO4J"]):
                continue
            iops = node.get("metrics", {}).get("disk_iops", 0)
            if iops >= STORAGE_IOPS_LIMIT:
                violations.append(
                    f"Storage IOPS Breach on {node_id}: "
                    f"{iops} IOPS (Limit: {STORAGE_IOPS_LIMIT} IOPS)."
                )
            elif iops >= STORAGE_IOPS_LIMIT * 0.75:
                warnings.append(
                    f"Storage Warning on {node_id}: {iops} IOPS "
                    f"({(iops/STORAGE_IOPS_LIMIT*100):.1f}% of limit)."
                )

        future_violations = []
        if projections:
            for proj in projections:
                step = proj["step"]
                for node_id, pm in proj.get("nodes", {}).items():
                    iops = pm.get("disk_iops", 0)
                    if iops >= STORAGE_IOPS_LIMIT:
                        future_violations.append(
                            f"Projected Step {step}: {node_id} IOPS={iops}."
                        )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "future_violations": future_violations,
        }
