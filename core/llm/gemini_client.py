"""
core/llm/gemini_client.py
Gemini LLM client for context-aware recommendation enhancement.

Sits on top of the rule-based RecommendationEngine — base recommendations
are always generated first (fast, offline), then Gemini enriches them with
device-specific, metric-aware natural language advice when the API is available.
Falls back silently to base recommendations on any error or timeout.
"""
import json
import logging
import requests
from config.settings import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS, GEMINI_RETRY_ATTEMPTS,
)

logger = logging.getLogger(__name__)

_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent"
)


class GeminiClient:
    def __init__(self):
        self.api_key  = GEMINI_API_KEY
        self.model    = GEMINI_MODEL
        self.timeout  = GEMINI_TIMEOUT_SECONDS
        self.retries  = GEMINI_RETRY_ATTEMPTS
        self._ok      = bool(self.api_key)
        if self._ok:
            logger.info(f"GeminiClient: ready (model={self.model})")
        else:
            logger.info("GeminiClient: no API key — LLM enhancement disabled")

    @property
    def available(self) -> bool:
        return self._ok

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #
    def enhance_recommendations(
        self,
        context: dict,
        base_recs: list[str],
        action: str = "anomaly_alert",
    ) -> list[str]:
        """
        Enrich rule-based recommendations with LLM context.

        Parameters
        ----------
        context : dict
            Keys: node_id, role, metrics, triggers, healthy_stats,
                  anomaly_type, alert_level
        base_recs : list[str]
            Recommendations from remediation_rules (always returned as
            fallback if LLM fails).
        action : str
            "anomaly_alert" | "inject_compute" | "inject_network" | etc.

        Returns
        -------
        list[str]  — LLM-enhanced recommendations, or base_recs on failure.
        """
        if not self._ok or not base_recs:
            return base_recs

        try:
            prompt   = self._build_prompt(context, base_recs, action)
            raw_resp = self._call(prompt)
            if raw_resp:
                enhanced = self._parse(raw_resp)
                if enhanced:
                    logger.info(
                        f"GeminiClient: enhanced {len(enhanced)} recs "
                        f"for {context.get('node_id','?')}"
                    )
                    return enhanced
        except Exception as e:
            logger.warning(f"GeminiClient: enhancement failed ({e}) — using base recs")

        return base_recs

    # ------------------------------------------------------------------ #
    # Prompt builder                                                       #
    # ------------------------------------------------------------------ #
    def _build_prompt(self, ctx: dict, base_recs: list[str], action: str) -> str:
        node_id      = ctx.get("node_id", "unknown")
        role         = ctx.get("role", "unknown")
        triggers     = ctx.get("triggers", [])
        anomaly_type = ctx.get("anomaly_type") or "unknown"
        alert_level  = ctx.get("alert_level", "warning")
        metrics      = ctx.get("metrics", {})
        h_stats      = ctx.get("healthy_stats", {})

        # Build per-metric deviation table
        metric_lines = []
        for f, val in metrics.items():
            if not isinstance(val, (int, float)):
                continue
            s = h_stats.get(f, {})
            mean = s.get("mean")
            std  = s.get("std")
            if mean is not None and std is not None:
                z = (float(val) - mean) / max(float(std), 1e-6)
                metric_lines.append(
                    f"  {f}: {val:.1f}  "
                    f"(healthy {mean:.1f}±{std:.1f}, z={z:+.1f}σ)"
                )
            else:
                metric_lines.append(f"  {f}: {val}")

        metrics_block = "\n".join(metric_lines) or "  (no metrics)"
        base_block    = "\n".join(f"- {r}" for r in base_recs)
        triggers_str  = ", ".join(triggers) or "none"

        return f"""You are an expert HPE datacenter SRE assistant integrated into a Digital Twin monitoring platform.
Analyze the following infrastructure anomaly and provide specific, actionable remediation advice.

=== ALERT CONTEXT ===
Node ID    : {node_id}
Role       : {role}
Alert level: {alert_level.upper()}
Action     : {action}
Triggers   : {triggers_str}
Anomaly    : {anomaly_type}

=== METRIC DEVIATIONS FROM HEALTHY BASELINE ===
{metrics_block}

=== RULE-BASED RECOMMENDATIONS ALREADY GENERATED ===
{base_block}

=== YOUR TASK ===
Provide exactly 3 concise, specific remediation recommendations for this exact node and situation.
Requirements:
- Be specific to the node role ({role}) and the triggered metrics
- Reference actual values where relevant (e.g. "CPU at {metrics.get('cpu_percent', '?')}%")
- Prioritise immediate mitigation, then root-cause investigation, then prevention
- Do NOT repeat the rule-based recommendations verbatim — augment them
- Keep each recommendation under 25 words

Return ONLY a valid JSON array of 3 strings. No explanation, no markdown, no extra text.
Example: ["rec 1", "rec 2", "rec 3"]"""

    # ------------------------------------------------------------------ #
    # HTTP call                                                            #
    # ------------------------------------------------------------------ #
    def _call(self, prompt: str) -> dict | None:
        url = _API_URL.format(model=self.model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature":    0.3,
                "maxOutputTokens": 300,
                "topP":           0.8,
            },
        }
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    params={"key": self.api_key},
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(
                    f"GeminiClient: HTTP {resp.status_code} "
                    f"(attempt {attempt}/{self.retries}): {resp.text[:200]}"
                )
            except requests.Timeout:
                logger.warning(
                    f"GeminiClient: timeout after {self.timeout}s "
                    f"(attempt {attempt}/{self.retries})"
                )
            except Exception as e:
                logger.warning(f"GeminiClient: request error: {e}")
                break
        return None

    # ------------------------------------------------------------------ #
    # Response parser                                                      #
    # ------------------------------------------------------------------ #
    def _parse(self, response: dict) -> list[str]:
        try:
            text = (
                response["candidates"][0]["content"]["parts"][0]["text"]
                .strip()
            )
            # Extract JSON array even if surrounded by stray text
            start = text.find("[")
            end   = text.rfind("]") + 1
            if start >= 0 and end > start:
                arr = json.loads(text[start:end])
                if isinstance(arr, list) and arr:
                    return [str(s) for s in arr if s]
        except Exception as e:
            logger.debug(f"GeminiClient: parse error: {e}")
        return []


# Module-level singleton
gemini_client = GeminiClient()
