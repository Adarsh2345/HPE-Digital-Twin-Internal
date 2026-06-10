"""
core/validation/validator_engine.py
The 4-Tier Gatekeeper Validator Engine.
Runs all constraint checks in sequence and produces a compliance verdict.
Tiers:
  1. Environmental (power + rack U-space)
  2. Compute performance (CPU + memory)
  3. Storage IOPS capacity
  4. Network SLA latency
"""
import networkx as nx
import logging
from core.validation.power_validator import PowerValidator
from core.validation.rack_validator import RackValidator
from core.validation.compute_validator import ComputeValidator
from core.validation.storage_validator import StorageValidator
from core.validation.network_validator import NetworkValidator

logger = logging.getLogger(__name__)


class ValidatorEngine:
    def __init__(self):
        self.power_validator = PowerValidator()
        self.rack_validator = RackValidator()
        self.compute_validator = ComputeValidator()
        self.storage_validator = StorageValidator()
        self.network_validator = NetworkValidator()

    def validate(self, G: nx.DiGraph, projections: list[dict] = None) -> dict:
        results = {}

        # Tier 1 - Environmental
        results["power"] = self.power_validator.validate(G)
        results["rack"] = self.rack_validator.validate(G)

        # Tier 2 - Compute performance
        results["compute"] = self.compute_validator.validate(G, projections)

        # Tier 3 - Storage IOPS
        results["storage"] = self.storage_validator.validate(G, projections)

        # Tier 4 - Network SLA
        results["network"] = self.network_validator.validate(G, projections)

        # Aggregate verdict
        all_violations = []
        all_warnings = []
        for tier_name, result in results.items():
            all_violations.extend(result.get("violations", []))
            all_warnings.extend(result.get("warnings", []))

        allowed = len(all_violations) == 0

        if allowed:
            logger.info("✅ Validation PASSED — all constraint tiers cleared")
        else:
            logger.warning(f"❌ Validation FAILED — {len(all_violations)} violation(s)")

        return {
            "allowed": allowed,
            "reasons": all_violations,
            "warnings": all_warnings,
            "tier_results": results,
        }
