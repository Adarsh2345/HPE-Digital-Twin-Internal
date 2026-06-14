from __future__ import annotations

import json
import os
import re
from typing import Iterable

from simulation.models import SimulationRequest, normalize_request


def parse_request(text: str, inventory_ids: Iterable[str] = ()) -> SimulationRequest:
    rule_result = rule_based_parse(text)
    if rule_result is not None:
        return rule_result
    if os.getenv("ENABLE_LLM_PARSER", "false").lower() == "true":
        llm = _gemini_parse(text, set(inventory_ids))
        if llm is not None:
            return llm
    return _fallback(text)


def rule_based_parse(text: str) -> SimulationRequest | None:
    raw = text.strip()
    lower = raw.lower()
    ids = re.findall(r"\b(?:droplet|rack|server|router|spine|array-ctrl|obj-node|pdu)[-\w/]*\b", lower)
    quantity = int((re.search(r"\b(\d+)\s*(?:x\s*)?(?:servers?|dl360|dl380)", lower) or ["", "1"])[1])
    common = {"request_text": raw, "parser_used": "rule_based"}
    if "blast" in lower or "fail" in lower:
        target = ids[-1] if ids else ""
        if target:
            return normalize_request({"action": "blast_radius_query", "failed_device_id": target, **common})
    if "remove" in lower or "decommission" in lower:
        if ids:
            return normalize_request({"action": "remove_node", "node_id": ids[0], **common})
    if "migrate" in lower:
        node = next((value for value in ids if value.startswith("server")), "")
        rack = next((value for value in ids if value.startswith(("rack", "droplet"))), "")
        router = next((value for value in ids if "router" in value), "")
        if node and rack and router:
            return normalize_request({
                "action": "migrate_rack", "node_id": node,
                "target_rack_id": rack, "target_router_id": router, **common,
            })
    if "move" in lower:
        node = next((value for value in ids if value.startswith("server")), "")
        router = next((value for value in ids if "router" in value), "")
        if node and router:
            return normalize_request({
                "action": "move_server", "server_id": node,
                "target_router_id": router, **common,
            })
    if "add" in lower:
        rack = next((value for value in ids if value.startswith(("rack", "droplet"))), "")
        router = next((value for value in ids if "router" in value), "")
        model = "HPE ProLiant DL380 Gen12" if "dl380" in lower else "HPE ProLiant DL360 Gen12"
        return normalize_request({
            "action": "add_compute", "target_rack_id": rack,
            "target_router_id": router, "quantity": quantity, "model": model,
            "u_size": 2 if "dl380" in lower else 1,
            "max_power_w": 800 if "dl380" in lower else 500, **common,
        })
    if "iops" in lower:
        if not ids:
            return None
        values = _metric_values(lower)
        return normalize_request({"action": "inject_storage", "node_id": ids[0], **values, **common})
    if "cpu" in lower or "temperature" in lower or "memory" in lower or "power" in lower:
        if not ids:
            return None
        values = _metric_values(lower)
        return normalize_request({"action": "inject_compute", "node_id": ids[0], **values, **common})
    if "latency" in lower or "packet loss" in lower:
        if len(ids) < 2:
            return None
        values = _metric_values(lower)
        return normalize_request({"action": "inject_network", "source_node_id": ids[0], "target_node_id": ids[1], **values, **common})
    return None


def _metric_values(text: str) -> dict:
    patterns = {
        "cpu_pct": r"cpu(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "memory_pct": r"memory(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "temp_c": r"temperature(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "power_w": r"power(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "latency_ms": r"latency(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "packet_loss_pct": r"(?:packet\s+)?loss(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "disk_iops": r"(\d+(?:\.\d+)?)\s*iops",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            values[key] = float(match.group(1))
    return values


def _gemini_parse(text: str, inventory: set[str]) -> SimulationRequest | None:
    key, model = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL")
    if not key or not model:
        return None
    try:
        from google import genai
        from google.genai import types
        timeout_ms = int(float(os.getenv("GEMINI_TIMEOUT_SECONDS", "5")) * 1000)
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeout_ms))
        response = client.models.generate_content(
            model=model,
            contents=(
                "Return JSON only for one supported simulation action. "
                "Do not invent inventory IDs. Supported actions: move_server, add_compute, "
                "remove_node, inject_compute, inject_network, inject_storage, migrate_rack, "
                f"blast_radius_query. Inventory: {sorted(inventory)}. Request: {text}"
            ),
        )
        payload = json.loads(response.text)
        request = normalize_request({**payload, "request_text": text, "parser_used": "gemini"})
        supplied = {value for key, value in request.model_dump().items() if key.endswith("_id") and value}
        if inventory and not supplied.issubset(inventory):
            return None
        return request
    except Exception:
        return None


def _fallback(text: str) -> SimulationRequest:
    return normalize_request({
        "action": "blast_radius_query", "failed_device_id": "__unresolved__",
        "request_text": text, "parser_used": "fallback",
    })
