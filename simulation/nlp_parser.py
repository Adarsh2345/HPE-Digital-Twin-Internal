from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

from simulation.models import SimulationRequest, normalize_request

logger = logging.getLogger(__name__)

# Maps LLM rack aliases → canonical droplet/rack names used in target_rack_id.
# These are NOT graph node IDs — they are the droplet prefix of composite IDs.
_RACK_ALIASES: dict[str, str] = {
    "rack1":          "droplet-1-tor1",
    "rack 1":         "droplet-1-tor1",
    "tor1":           "droplet-1-tor1",
    "tor-1":          "droplet-1-tor1",
    "first rack":     "droplet-1-tor1",
    "droplet-1-tor1": "droplet-1-tor1",
    "rack2":          "droplet-2-tor2",
    "rack 2":         "droplet-2-tor2",
    "tor2":           "droplet-2-tor2",
    "tor-2":          "droplet-2-tor2",
    "second rack":    "droplet-2-tor2",
    "droplet-2-tor2": "droplet-2-tor2",
    "storage":        "droplet-4-storage",
    "storage rack":   "droplet-4-storage",
    "droplet-4-storage": "droplet-4-storage",
}

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
    Primary entry point. Tries LLM first, then falls back to
    blast_radius_query with parser_used=fallback.
    """
    inventory = set(inventory_ids)

    llm = _gemini_parse(text, inventory)
    if llm is not None:
        return llm

    return _fallback(text)


def _resolve_id(token: str, inventory: set[str]) -> str | None:
    """Map a short or composite token to a canonical graph node id."""
    val = token.strip()
    if not val:
        return None
    if val in inventory:
        return val
    if "/" in val:
        val = val.split("/", 1)[1]
    return next(
        (nid for nid in inventory if nid == val or nid.endswith(f"/{val}")),
        None,
    )



def _gemini_parse(text: str, inventory: set[str]) -> SimulationRequest | None:
    # Read from settings so .env is respected
    from config.settings import (
        GEMINI_API_KEY, GEMINI_MODEL,
        GEMINI_TIMEOUT_SECONDS, GEMINI_RETRY_ATTEMPTS,
    )

    if not GEMINI_API_KEY or not GEMINI_MODEL:
        logger.warning("LLM enabled but API key or model not set")
        return None

    # Build a short-name inventory so the LLM gets human-readable IDs
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

        # Build rack→router mapping so the LLM can pick the right rack
        rack_router_map: dict[str, str] = {}
        for node_id in inventory:
            if "/" in node_id:
                rack, short = node_id.split("/", 1)
                if short.startswith("router-"):
                    rack_router_map[rack] = short

        rack_info = "; ".join(
            f"{rack} contains {router}" for rack, router in sorted(rack_router_map.items())
        ) or "no rack mapping available"

        system_prompt = (
            "You are an infrastructure intent parser for an HPE data-centre digital twin. "
            "Return ONE flat JSON object only — no markdown, no code fences, no nesting. "
            "RULES:\n"
            "  1. Only use node IDs that appear in the inventory below. Never invent IDs.\n"
            "  2. Use the SHORT name (e.g. 'server-1'), not the composite path.\n"
            "  3. For add_compute: set target_router_id to the router of the chosen rack, "
            "and target_rack_id to the rack name (droplet-X-torY). "
            "If the user says 'rack 1' or 'tor1' or 'first rack' use rack droplet-1-tor1 with router-1. "
            "If the user says 'rack 2' or 'tor2' or 'second rack' use rack droplet-2-tor2 with router-2.\n"
            "  4. For inject_network: source_node_id and target_node_id must both be in inventory.\n"
            "  5. For remove_node / inject_compute / inject_storage: node_id must be in inventory.\n"
            "  6. If you cannot confidently map the request to an action and real inventory IDs, "
            "return {\"action\": \"blast_radius_query\", \"failed_device_id\": \"__unresolved__\"}.\n"
            "Supported actions:\n"
            "  move_server       → server_id, target_router_id\n"
            "  add_compute       → target_router_id, target_rack_id\n"
            "  remove_node       → node_id\n"
            "  inject_compute    → node_id, [cpu_pct, memory_pct, power_w]\n"
            "  inject_network    → source_node_id, target_node_id, [latency_ms, packet_loss_pct]\n"
            "  inject_storage    → node_id, [disk_iops]\n"
            "  migrate_rack      → node_id, target_rack_id, target_router_id\n"
            "  blast_radius_query → failed_device_id\n"
            f"Rack layout: {rack_info}\n"
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

        # Handle common LLM field name variations
        if payload.get("action") == "move_server" and "destination_id" in payload:
            payload["target_router_id"] = payload.pop("destination_id")

        # Resolve short/composite node IDs to canonical graph node IDs.
        # target_rack_id is intentionally excluded — rack names (droplet-X-torY)
        # are droplet prefixes, not graph nodes, so they must not be validated
        # against the node inventory.
        node_id_keys = [
            "node_id", "server_id", "source_node_id", "target_node_id",
            "target_router_id", "failed_device_id",
        ]
        for key in node_id_keys:
            if key in payload and isinstance(payload[key], str) and payload[key]:
                val = payload[key]
                if "/" in val:
                    val = val.split("/", 1)[1]
                full_match = next(
                    (nid for nid in inventory if nid.endswith(f"/{val}") or nid == val),
                    None,
                )
                if full_match:
                    payload[key] = full_match

        # Normalise rack aliases the LLM may return (e.g. "tor2" → "droplet-2-tor2")
        rack_val = payload.get("target_rack_id", "")
        if rack_val:
            rack_val = _RACK_ALIASES.get(rack_val.lower(), rack_val)
            payload["target_rack_id"] = rack_val

        request = normalize_request({
            **payload,
            "request_text": text,
            "parser_used": "llm",
        })

        # Validate that graph-node IDs exist in inventory.
        # Exclude target_rack_id — it is a rack/droplet name, not a graph node.
        dump = request.model_dump()
        supplied = {
            v for k, v in dump.items()
            if k.endswith("_id") and k != "target_rack_id"
            and isinstance(v, str) and v
        }

        if inventory and not supplied.issubset(inventory | short_inventory | {"", "__unresolved__"}):
            logger.warning(f"LLM returned IDs not in inventory: {supplied - (inventory | short_inventory)}")
            return None

        logger.info(f"LLM parsed and matched canonical path: action={request.action}, ids={supplied}")
        return request

    except Exception as exc:
        status = getattr(exc, "code", None)
        logger.warning(
            "LLM parser failed, falling back "
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