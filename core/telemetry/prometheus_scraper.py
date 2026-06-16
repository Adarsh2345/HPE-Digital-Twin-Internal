"""
core/telemetry/prometheus_scraper.py
Simulates scraping Prometheus metrics as if collected from DigitalOcean.
In a real deployment this would call the Prometheus HTTP API.
"""
import time
import logging
from core.telemetry.metrics_generator import MetricsGenerator

logger = logging.getLogger(__name__)


class PrometheusScraper:
    def __init__(self, prometheus_url: str = None):
        self.prometheus_url = prometheus_url
        self._generator: MetricsGenerator = None

    def set_generator(self, generator: MetricsGenerator):
        self._generator = generator

    async def scrape(self, nodes: list[dict], edges: list[dict]) -> dict:
        """
        Simulates a Prometheus scrape cycle.
        Returns a snapshot dict matching what real /api/v1/query returns.
        """
        logger.debug(f"Prometheus scrape cycle at {time.strftime('%H:%M:%S')}")
        if self._generator is None:
            self._generator = MetricsGenerator()
        snapshot = self._generator.generate_full_snapshot(nodes, edges)
        return snapshot

    async def query_metric(self, metric_name: str, labels: dict = None) -> list:
        """Mock Prometheus instant query."""
        return [{"metric": labels or {}, "value": [time.time(), "0"]}]
