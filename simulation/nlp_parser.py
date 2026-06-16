from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

from simulation.models import SimulationRequest, normalize_request

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = [408, 500, 502, 503, 504]
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "move_server", "add_compute", "remove_node",
                "inject_compute", "inject_network", "inject_storage",
                "migrate_rack", "blast_radius_query",
            ],
        },
        "server_id": {"type": "string"},
        "target_router_id": {"type": "string"},
        "target_rack_id": {"type": "string"},
        "node_id": {"type": "string"},
        "source_node_id": {"type": "string"},
        "target_node_id": {"type": "string"},
        "failed_device_id": {"type": "string"},
        "quantity": {"type": "integer", "minimum": 1},
        "cpu_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "memory_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "temp_c": {"type": "number"},
        "power_w": {"type": "number", "minimum": 0},
        "latency_ms": {"type": "number", "minimum": 0},
        "packet_loss_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "disk_iops": {"type": "number", "minimum": 0},
    },
    "required": ["action"],
    "additionalProperties": False,
}


def parse_request(text: str, inventory_ids: Iterable[str] = ()) -> SimulationRequest:
    """
    Primary entry point. Tries Gemini first if configured, then rule-based,
    then falls back to blast_radius_query with parser_used=fallback.
    """
    inventory = set(inventory_ids)

    # 1. Try Gemini if key is available
    llm = _gemini_parse(text, inventory)
    if llm is not None:
        return llm

    # 2. Try deterministic rule-based parser
    rule = rule_based_parse(text)
    if rule is not None:
        return rule

    # 3. Fallback
    return _fallback(text)


def rule_based_parse(text: str) -> SimulationRequest | None:
    raw = text.strip()
    lower = _normalize_spoken_ids(raw.lower())

    # Extract all node-like IDs — supports both bare (server-1) and
    # composite (droplet-1-tor1/server-1) formats
    ids = re.findall(
        r"\b(?:droplet[-\w]+/)?(?:droplet|rack|server|router|spine|array-ctrl|obj-node|storage-router|pdu)[-\w/]*\b",
        lower,
    )
    quantity_match = re.search(r"\b(\d+)\s*(?:x\s*)?(?:servers?|dl360|dl380)", lower)
    quantity = int(quantity_match.group(1)) if quantity_match else 1
    common = {"request_text": raw, "parser_used": "rule_based"}

    if "blast" in lower or ("fail" in lower and "server" not in lower):
        target = ids[-1] if ids else ""
        if target:
            return normalize_request({"action": "blast_radius_query", "failed_device_id": target, **common})

    if "remove" in lower or "decommission" in lower:
        if ids:
            return normalize_request({"action": "remove_node", "node_id": ids[0], **common})

    if "migrate" in lower:
        node = next((v for v in ids if "server" in v), "")
        rack = next((v for v in ids if v.startswith(("rack", "droplet"))), "")
        router = next((v for v in ids if "router" in v), "")
        if node and rack and router:
            return normalize_request({
                "action": "migrate_rack", "node_id": node,
                "target_rack_id": rack, "target_router_id": router, **common,
            })

    if "move" in lower:
        node = next((v for v in ids if "server" in v), "")
        router = next((v for v in ids if "router" in v), "")
        if node and router:
            return normalize_request({
                "action": "move_server", "server_id": node,
                "target_router_id": router, **common,
            })

    if "add" in lower:
        rack = next((v for v in ids if v.startswith(("rack", "droplet"))), "")
        router = next((v for v in ids if "router" in v), "")
        if not rack or not router:
            return None
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

    if any(k in lower for k in ("cpu", "temperature", "memory", "power")):
        if not ids:
            return None
        values = _metric_values(lower)
        return normalize_request({"action": "inject_compute", "node_id": ids[0], **values, **common})

    if "latency" in lower or "packet loss" in lower:
        if len(ids) < 2:
            return None
        values = _metric_values(lower)
        return normalize_request({
            "action": "inject_network",
            "source_node_id": ids[0],
            "target_node_id": ids[1],
            **values, **common,
        })

    return None


def _normalize_spoken_ids(text: str) -> str:
    return re.sub(
        r"\b(server|router|rack|droplet|pdu)\s+(\d+)\b",
        lambda m: f"{m.group(1)}-{m.group(2)}",
        text,
    )


def _metric_values(text: str) -> dict:
    patterns = {
        "cpu_pct":         r"cpu(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "memory_pct":      r"memory(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "temp_c":          r"temperature(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "power_w":         r"power(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "latency_ms":      r"latency(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "packet_loss_pct": r"(?:packet\s+)?loss(?:\s+to|\s+at)?\s*(\d+(?:\.\d+)?)",
        "disk_iops":       r"(\d+(?:\.\d+)?)\s*iops",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            values[key] = float(match.group(1))
    return values


def _gemini_parse(text: str, inventory: set[str]) -> SimulationRequest | None:
    # Read from settings so .env is respected
    from config.settings import (
        ENABLE_LLM_PARSER, GEMINI_API_KEY, GEMINI_MODEL,
        GEMINI_TIMEOUT_SECONDS, GEMINI_RETRY_ATTEMPTS,
    )

    if not ENABLE_LLM_PARSER:
        return None
    if not GEMINI_API_KEY or not GEMINI_MODEL:
        logger.warning("Gemini enabled but GEMINI_API_KEY or GEMINI_MODEL not set")
        return None

    # Build a short-name inventory so Gemini gets human-readable IDs
    # e.g. "droplet-1-tor1/server-1" → also expose "server-1"
    short_inventory = set()
    for node_id in inventory:
        short_inventory.add(node_id)
        if "/" in node_id:
            short_inventory.add(node_id.split("/", 1)[1])

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=_http_options(types, GEMINI_TIMEOUT_SECONDS, GEMINI_RETRY_ATTEMPTS),
        )

        system_prompt = (
            "You are an infrastructure intent parser. "
            "Return ONE flat JSON object only — no markdown, no code fences, no nesting under 'params'. "
            "Do NOT invent node IDs; only use IDs from the inventory provided. "
            "Use the short name (e.g. 'server-1') not the composite path. "
            "Supported actions and their required fields:\n"
            "  move_server       → server_id, target_router_id\n"
            "  add_compute       → target_router_id, target_rack_id\n"
            "  remove_node       → node_id\n"
            "  inject_compute    → node_id, [cpu_pct, memory_pct, power_w]\n"
            "  inject_network    → source_node_id, target_node_id, [latency_ms, packet_loss_pct]\n"
            "  inject_storage    → node_id, [disk_iops]\n"
            "  migrate_rack      → node_id, target_rack_id, target_router_id\n"
            "  blast_radius_query → failed_device_id\n"
            f"Inventory (short names): {sorted(short_inventory)}\n"
            f"Request: {text}"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=system_prompt,
            config=_generation_config(types, GEMINI_MODEL),
        )

        raw_text = response.text.strip()
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        payload = json.loads(raw_text)

        # Flatten any nested params
        nested = payload.pop("parameters", payload.pop("params", {}))
        if isinstance(nested, dict):
            payload.update(nested)

        # Handle common Gemini field name variations
        if payload.get("action") == "move_server" and "destination_id" in payload:
            payload["target_router_id"] = payload.pop("destination_id")

        # --- FIX: Convert Short/Typo Names to Canonical Composite IDs ---
        target_keys = [
            "node_id", "server_id", "source_node_id", "target_node_id", 
            "target_router_id", "target_rack_id", "failed_device_id"
        ]
        for key in target_keys:
            if key in payload and isinstance(payload[key], str) and payload[key]:
                val = payload[key]
                # Strip out any bad/missing dash prefix strings parsed from typo inputs
                if "/" in val:
                    val = val.split("/", 1)[1]
                
                # Match back exactly to long NetworkX graph identifiers 
                full_match = next((nid for nid in inventory if nid.endswith(f"/{val}") or nid == val), None)
                if full_match:
                    payload[key] = full_match

        request = normalize_request({
            **payload,
            "request_text": text,
            "parser_used": "gemini",
        })

        # Validate that resolved IDs exist in final system paths
        supplied = {
            v for k, v in request.model_dump().items()
            if k.endswith("_id") and isinstance(v, str) and v
        }
        # Include specific structural identifier metrics 
        if "node_id" in request.model_dump():
            supplied.add(request.node_id)

        if inventory and not supplied.issubset(inventory | short_inventory | {""}):
            logger.warning(f"Gemini returned IDs not in inventory: {supplied - inventory}")
            return None

        logger.info(f"Gemini parsed and matched canonical path: action={request.action}, ids={supplied}")
        return request

    except Exception as exc:
        status = getattr(exc, "code", None)
        logger.warning(
            "Gemini parser failed, falling back to rule-based "
            "(model=%s, status=%s, error=%s: %s)",
            GEMINI_MODEL, status, type(exc).__name__, str(exc)[:200],
        )
        return None

def _http_options(types, timeout_seconds: float, retry_attempts: int):
    return types.HttpOptions(
        timeout=int(timeout_seconds * 1000),
        retry_options=types.HttpRetryOptions(
            attempts=retry_attempts,
            initial_delay=0.5,
            max_delay=2.0,
            exp_base=2,
            jitter=0.5,
            http_status_codes=_TRANSIENT_STATUS_CODES,  # 🌟 FIXED: Changed from allowed_status_codes
        ),
    )


def _generation_config(types, model: str):
    thinking_config = (
        types.ThinkingConfig(thinking_budget=0)
        if model.startswith("gemini-2.5-flash")
        else None
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=_RESPONSE_SCHEMA,
        thinking_config=thinking_config,
        temperature=0,
        max_output_tokens=512,
    )


def _fallback(text: str) -> SimulationRequest:
    return normalize_request({
        "action": "blast_radius_query",
        "failed_device_id": "__unresolved__",
        "request_text": text,
        "parser_used": "fallback",
    })