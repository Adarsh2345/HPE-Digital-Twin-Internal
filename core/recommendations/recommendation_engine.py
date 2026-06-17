"""
core/recommendations/recommendation_engine.py
Wra wraps the validator output and remediation rules into a
structured Recommendation Report.
"""
import time
import logging
from core.recommendations.remediation_rules import generate_remediation

logger = logging.getLogger(__name__)


class RecommendationEngine:
    def generate_report(
        self,
        action: str,
        params: dict,
        validation_result: dict,
        mutation_result: dict = None,
        projections: list[dict] = None,
        llm_context: dict = None,
    ) -> dict:
        allowed = validation_result.get("allowed", False)
        reasons = validation_result.get("reasons", [])
        warnings = validation_result.get("warnings", [])

        recommendations = []
        if not allowed:
            recommendations = generate_remediation(reasons)
            # Enhance with Gemini when context is provided
            if llm_context and recommendations:
                try:
                    from core.llm.gemini_client import gemini_client
                    if gemini_client.available:
                        recommendations = gemini_client.enhance_recommendations(
                            context=llm_context,
                            base_recs=recommendations,
                            action=action,
                        )
                except Exception as e:
                    logger.warning(f"LLM enhancement skipped: {e}")

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "params": params,
            "allowed": allowed,
            "verdict": "PASS ✅" if allowed else "FAIL ❌",
            "reasons": reasons,
            "warnings": warnings,
            "recommendations": recommendations,
            "tier_results": validation_result.get("tier_results", {}),
            "mutation_summary": mutation_result,
            "projection_steps": len(projections) if projections else 0,
        }

        logger.info(
            f"Recommendation report generated — allowed={allowed}, "
            f"violations={len(reasons)}, recommendations={len(recommendations)}"
        )
        return report
