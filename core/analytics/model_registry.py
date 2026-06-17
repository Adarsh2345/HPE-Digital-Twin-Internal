"""
core/analytics/model_registry.py
Global singleton that holds all trained analytics components.
"""
import logging
from core.analytics.historical_analyzer import HistoricalPatternAnalyzer
from core.analytics.scenario_generator  import ScenarioGenerator
from core.analytics.behavior_model      import BehaviorModel
from core.analytics.impact_analyzer     import ImpactAnalyzer

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self):
        self.analyzer       = HistoricalPatternAnalyzer()
        self.scenario_gen   = ScenarioGenerator()
        self.behavior_model = BehaviorModel()
        self.impact_analyzer = ImpactAnalyzer(self.behavior_model)
        self._trained = False

    def bootstrap(self, days: int = 30):
        logger.info("ModelRegistry: starting analytics bootstrap...")

        try:
            self.analyzer.analyze(days=days)
            logger.info("  ✔ HistoricalPatternAnalyzer complete")
        except Exception as e:
            logger.warning(f"  HistoricalPatternAnalyzer failed: {e}")

        try:
            self.scenario_gen.generate(days=days)
            logger.info(f"  ✔ ScenarioGenerator: {len(self.scenario_gen.scenarios)} scenarios, k={self.scenario_gen.best_k}")
        except Exception as e:
            logger.warning(f"  ScenarioGenerator failed: {e} — using static fallback")

        try:
            summary = self.behavior_model.train_all(days=days)
            logger.info(f"  ✔ BehaviorModel: trained {len(summary)} nodes")
        except Exception as e:
            logger.warning(f"  BehaviorModel training failed: {e} — using linear fallback")

        try:
            from core.analytics.anomaly_detector import detector as _ad
            loaded = _ad.load()
            if loaded:
                logger.info(f"  ✔ AnomalyDetector: loaded {len(_ad.if_models)} device models")
            else:
                logger.info("  ℹ AnomalyDetector: no saved model — run train_models.py --anomaly to train")
        except Exception as e:
            logger.warning(f"  AnomalyDetector load skipped: {e}")

        self._trained = True
        logger.info("ModelRegistry: bootstrap complete")

    @property
    def ready(self) -> bool:
        return self._trained

    def get_scenarios(self) -> list[dict]:
        return self.scenario_gen.get_scenarios()

    def get_profile(self, node_id: str) -> dict:
        return self.analyzer.get_profile(node_id)

    def get_edge_profile(self, edge_key: str) -> dict:
        return self.analyzer.get_edge_profile(edge_key)


registry = ModelRegistry()