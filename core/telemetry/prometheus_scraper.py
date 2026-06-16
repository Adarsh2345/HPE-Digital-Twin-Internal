"""
core/telemetry/prometheus_scraper.py
Scrapes live metrics from the real Prometheus HTTP API running on the
management droplet.
"""
import time
import logging

from core.telemetry.prometheus_telemetry_adapter import fetch_snapshot, _query

logger = logging.getLogger(__name__)


class PrometheusScraper:
    def __init__(self, prometheus_url: str = None):
        self.prometheus_url = prometheus_url

    async def scrape(self, nodes: list[dict], edges: list[dict]) -> dict:
        logger.debug(f"Prometheus scrape cycle at {time.strftime('%H:%M:%S')}")
        graph_node_ids = [n["id"] for n in nodes]
        return fetch_snapshot(self.prometheus_url, graph_node_ids)

    async def query_metric(self, metric_name: str, labels: dict = None) -> list:
        return _query(self.prometheus_url, metric_name)
