"""
core/llm/gemini_client.py

Gemini API wrapper for intelligent, context-aware recommendations.
Receives structured anomaly or simulation-failure context and returns
a human-readable analysis with root cause, prioritised actions, and
long-term fixes.

Set GEMINI_API_KEY environment variable before use.
Model: configurable via GEMINI_MODEL env var, defaults to gemini-2.0-flash.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    def __init__(self, api_key: str = None):
        self.api_key    = api_key or os.getenv("GEMINI_API_KEY", "")
        self._client    = None
        self._available = False
        self._init()

    def _init(self):
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — LLM recommendations disabled")
            return
        try:
            from google import genai
            self._client    = genai.Client(api_key=self.api_key)
            self._available = True
            logger.info(f"Gemini client ready (model={self.MODEL})")
        except ImportError:
            logger.warning(
                "google-genai package missing. "
                "Install with: pip install google-genai"
            )
        except Exception as exc:
            logger.warning(f"Gemini init failed: {exc}")

    @property
    def available(self) -> bool:
        return self._available

    # ── Anomaly recommendation ─────────────────────────────────────────────

    def get_anomaly_recommendation(
        self,
        node_id:             str,
        role:                str,
        anomaly_type:        str,
        severity:            str,
        current_metrics:     dict,
        baseline_metrics:    dict,
        connected_nodes:     list[str],
        rule_suggestions:    list[str],
    ) -> str:
        """
        Called when Isolation Forest + RF Classifier detect an anomaly.
        Returns a plain-text action plan.
        """
        if not self._available:
            return self._fallback(rule_suggestions)

        prompt = f"""You are an expert HPE datacenter infrastructure engineer.
An anomaly was detected in the HPE Digital Twin simulation.

ANOMALY DETAILS
  Node         : {node_id}
  Role         : {role}
  Anomaly type : {anomaly_type}
  Severity     : {severity}

CURRENT METRICS vs NORMAL BASELINE
{self._metric_table(current_metrics, baseline_metrics)}

CONNECTED NODES (potentially impacted)
  {', '.join(connected_nodes) if connected_nodes else 'none'}

AUTOMATED RULE-BASED SUGGESTIONS ALREADY GENERATED
{self._bullet(rule_suggestions)}

Your response must contain exactly four labelled sections:
1. ROOT CAUSE — 1-2 sentences explaining the most likely cause given the role and anomaly type.
2. IMMEDIATE ACTIONS — ordered bullet list (most urgent first).
3. RISK IF IGNORED — what cascades next if this is not resolved within 10 minutes.
4. LONG-TERM FIX — 1-2 sentences on preventing recurrence.

Be specific to role="{role}" and anomaly_type="{anomaly_type}". Plain text only, no markdown.
"""
        return self._call(prompt)

    # ── Simulation failure recommendation ─────────────────────────────────

    def get_simulation_failure_recommendation(
        self,
        action:           str,
        params:           dict,
        failure_reasons:  list[str],
        rule_suggestions: list[str],
        impact_preview:   dict,
    ) -> str:
        """
        Called when the simulation validator rejects a proposed action.
        Returns a plain-text explanation with an alternative approach.
        """
        if not self._available:
            return self._fallback(rule_suggestions)

        prompt = f"""You are an expert HPE datacenter infrastructure engineer.
A simulation action was REJECTED by the HPE Digital Twin validator.

ATTEMPTED ACTION : {action}
PARAMETERS       : {json.dumps(params, indent=2)}

VALIDATION FAILURES
{self._bullet(failure_reasons)}

PREDICTED IMPACT IF FORCED
{json.dumps(impact_preview, indent=2) if impact_preview else '  not available'}

AUTOMATED RULE-BASED SUGGESTIONS ALREADY GENERATED
{self._bullet(rule_suggestions)}

Your response must contain exactly four labelled sections:
1. WHY IT FAILED — plain English, not just repeating the error code.
2. HOW TO MAKE IT WORK — a modified version of the action that would pass validation.
3. SAFE ALTERNATIVES — different actions that achieve the same operational goal without breaching limits.
4. RISK ASSESSMENT — is forcing the action ever justified, and under what conditions?

Plain text only, no markdown.
"""
        return self._call(prompt)

    # ── Threshold breach (fast path, no ML needed) ─────────────────────────

    def get_threshold_breach_summary(
        self,
        alerts:        list[dict],
        affected_nodes: list[str],
    ) -> str:
        """
        Called immediately when a critical threshold is breached —
        before ML models even run. Quick triage summary.
        """
        if not self._available:
            return f"Critical threshold breach on: {', '.join(affected_nodes)}"

        alert_lines = "\n".join(
            f"  {a['node_id']} — {a['metric']}={a['value']} "
            f"(threshold={a['threshold']}, level={a['level']})"
            for a in alerts[:10]   # cap at 10 to keep prompt small
        )
        prompt = f"""You are an expert HPE datacenter infrastructure engineer.
The following CRITICAL threshold breaches were detected in real time:

{alert_lines}

Affected nodes: {', '.join(affected_nodes)}

Provide a concise triage summary (5-8 sentences):
- Most likely cause
- Which nodes are at immediate risk
- The single most important action to take right now
- Whether this looks like an isolated event or the start of a cascade

Plain text only.
"""
        return self._call(prompt)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _call(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as exc:
            logger.error(f"Gemini API call failed: {exc}")
            return f"[LLM unavailable: {exc}]"

    @staticmethod
    def _metric_table(current: dict, baseline: dict) -> str:
        all_keys = sorted(set(list(current.keys()) + list(baseline.keys())))
        lines = []
        for k in all_keys:
            cur = current.get(k, "N/A")
            bas = baseline.get(k, "N/A")
            cur = f"{cur:.2f}" if isinstance(cur, float) else str(cur)
            bas = f"{bas:.2f}" if isinstance(bas, float) else str(bas)
            lines.append(f"  {k:<28} current={cur:<10} baseline={bas}")
        return "\n".join(lines) if lines else "  (no metric data)"

    @staticmethod
    def _bullet(items: list[str]) -> str:
        if not items:
            return "  (none)"
        return "\n".join(f"  - {item}" for item in items)

    @staticmethod
    def _fallback(rule_suggestions: list[str]) -> str:
        if rule_suggestions:
            return "Rule-based recommendations:\n" + "\n".join(f"- {r}" for r in rule_suggestions)
        return "No recommendations available (LLM disabled, no rules matched)."
