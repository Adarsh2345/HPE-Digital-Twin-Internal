"""
core/recommendations/remediation_rules.py
Rule definitions for intelligent alternative remediation suggestions.
"""

REMEDIATION_RULES = [
    {
        "trigger_keyword": "Power Envelope Breach",
        "extract_subnet": True,
        "template": (
            "Move heavy workload containers out of {subnet} to balance "
            "rack distribution into the alternate subnet."
        ),
    },
    {
        "trigger_keyword": "Rack U-Space Breach",
        "extract_droplet": True,
        "template": (
            "Migrate lower-priority containers from {droplet} to a less "
            "utilised droplet to free U-space."
        ),
    },
    {
        "trigger_keyword": "Compute Overload",
        "extract_node": True,
        "template": (
            "Scale {node} workload horizontally — add a sibling compute node "
            "under the same ToR switch and redistribute processes."
        ),
    },
    {
        "trigger_keyword": "Storage IOPS Breach",
        "extract_node": True,
        "template": (
            "Attach an additional NVMe volume to {node} or enable read "
            "caching (Redis) to reduce raw disk IOPS pressure."
        ),
    },
    {
        "trigger_keyword": "Network SLA Breach",
        "extract_link": True,
        "template": (
            "Inspect FRRouting BGP path on {link} — consider enabling ECMP "
            "load-balancing or switching to an alternate spine route."
        ),
    },
    {
        "trigger_keyword": "Packet Loss Breach",
        "extract_link": True,
        "template": (
            "Check physical / virtual NIC on {link} — packet loss indicates "
            "a flapping link or MTU mismatch in the Docker bridge network."
        ),
    },
]


def _extract_param(reason: str, keyword: str) -> str:
    """Simple heuristic: extract the token after 'on '."""
    try:
        after_on = reason.split(" on ")[1]
        return after_on.split(":")[0].strip()
    except IndexError:
        return "the affected component"


def generate_remediation(reasons: list[str]) -> list[str]:
    """
    Given a list of violation reason strings, return concrete remediation
    recommendations.
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
