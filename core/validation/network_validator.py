"""
core/validation/network_validator.py
Checks that FRRouting BGP link latency stays within SLA (150ms limit).
"""
import networkx as nx
from config.settings import NETWORK_LATENCY_SLA_MS
from config.constants import WARNING_THRESHOLDS


class NetworkValidator:
    def validate(self, G: nx.DiGraph, projections: list[dict] = None) -> dict:
        violations = []
        warnings = []

        for u, v in G.edges:
            edge = G.edges[u, v]
            latency = edge.get("metrics", {}).get("latency_ms", 0)
            loss = edge.get("metrics", {}).get("packet_loss_percent", 0)
            link = f"{u}→{v}"

            if latency >= NETWORK_LATENCY_SLA_MS:
                violations.append(
                    f"Network SLA Breach on {link}: "
                    f"Latency={latency:.1f}ms (SLA Limit: {NETWORK_LATENCY_SLA_MS}ms)."
                )
            elif latency >= WARNING_THRESHOLDS["latency_ms"]:
                warnings.append(
                    f"Network Warning on {link}: Latency={latency:.1f}ms."
                )

            if loss >= 5.0:
                violations.append(
                    f"Packet Loss Breach on {link}: {loss:.2f}% loss."
                )

        future_violations = []
        if projections:
            for proj in projections:
                step = proj["step"]
                for edge_key, em in proj.get("edges", {}).items():
                    lat = em.get("latency_ms", 0)
                    if lat >= NETWORK_LATENCY_SLA_MS:
                        future_violations.append(
                            f"Projected Step {step}: {edge_key} latency={lat:.1f}ms."
                        )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "future_violations": future_violations,
        }
