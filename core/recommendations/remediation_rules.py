"""
core/recommendations/remediation_rules.py
Rule definitions for intelligent alternative remediation suggestions.
EXTENDED: added rules for all new simulation scenario types.
"""

REMEDIATION_RULES = [
    # ── Environmental ─────────────────────────────────────────────────
    {
        "trigger_keyword": "Power Envelope Breach",
        "template": (
            "Move heavy workload containers out of {subnet} to balance "
            "rack distribution into the alternate subnet."
        ),
    },
    {
        "trigger_keyword": "Rack U-Space Breach",
        "template": (
            "Migrate lower-priority containers from {droplet} to a less "
            "utilised droplet to free U-space."
        ),
    },
    # ── Compute ───────────────────────────────────────────────────────
    {
        "trigger_keyword": "Compute Overload",
        "template": (
            "Scale {node} workload horizontally — add a sibling compute node "
            "under the same ToR switch and redistribute processes."
        ),
    },
    # ── Storage ───────────────────────────────────────────────────────
    {
        "trigger_keyword": "Storage IOPS Breach",
        "template": (
            "Attach an additional NVMe volume to {node} or enable read "
            "caching (Redis) to reduce raw disk IOPS pressure."
        ),
    },
    # ── Network ───────────────────────────────────────────────────────
    {
        "trigger_keyword": "Network SLA Breach",
        "template": (
            "Inspect FRRouting BGP path on {link} — consider enabling ECMP "
            "load-balancing or switching to an alternate spine route."
        ),
    },
    {
        "trigger_keyword": "Packet Loss Breach",
        "template": (
            "Check physical / virtual NIC on {link} — packet loss indicates "
            "a flapping link or MTU mismatch in the Docker bridge network."
        ),
    },
    # ── New: injected compute stress ──────────────────────────────────
    {
        "trigger_keyword": "Projected Step",
        "template": (
            "Projected degradation on {node} will breach limits within the "
            "simulation horizon — consider live-migrating workloads before "
            "the next maintenance window."
        ),
    },
]


def _extract_param(reason: str, keyword: str) -> str:
    """Heuristic: extract the token after 'on '."""
    try:
        after_on = reason.split(" on ")[1]
        return after_on.split(":")[0].strip()
    except IndexError:
        return "the affected component"


def generate_remediation(reasons: list[str]) -> list[str]:
    """
    Given a list of violation reason strings, return concrete remediation
    recommendations. Deduplicates by trigger keyword.
    """
    suggestions = []
    seen = set()

    for reason in reasons:
        for rule in REMEDIATION_RULES:
            kw = rule["trigger_keyword"]
            if kw in reason and kw not in seen:
                seen.add(kw)
                param = _extract_param(reason, kw)
                msg = rule["template"].format(
                    subnet=param, droplet=param, node=param, link=param
                )
                suggestions.append(msg)

    return suggestions