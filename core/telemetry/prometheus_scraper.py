"""
core/telemetry/prometheus_scraper.py

Scrapes real Prometheus metrics from the mock-exporter running on each
droplet (port 9200).  Falls back to the mock MetricsGenerator when the
endpoint is unreachable.

Prometheus label schema (post teammate change):
  node_telemetry_<field>{id, role, droplet, rack, instance, job}
  edge_telemetry_<field>{source, target, droplet, rack, instance, job}

The `id` label is the exact node ID from the topology (server-1, router-1 …),
so no IP-to-node mapping is required.
"""
import time
import asyncio
import logging
import requests

from core.telemetry.metrics_generator import MetricsGenerator

logger = logging.getLogger(__name__)

# Node metrics exposed by the mock-exporter — already computed values
NODE_METRIC_NAMES = [
    "node_telemetry_cpu_percent",
    "node_telemetry_memory_percent",
    "node_telemetry_disk_iops",
    "node_telemetry_power_watts",
    "node_telemetry_temperature_celsius",
]

# Edge metrics exposed by the mock-exporter
EDGE_METRIC_NAMES = [
    "edge_telemetry_latency_ms",
    "edge_telemetry_bandwidth_mbps",
    "edge_telemetry_packet_loss_percent",
]


class PrometheusScraper:
    """
    Unified scraper: real Prometheus HTTP API when available, mock otherwise.

    Real path:
      - Queries node_telemetry_* and edge_telemetry_* from the mock-exporter
      - Maps by `id` label → topology node ID (exact match, no IP lookup)
      - Nodes not present in Prometheus get mock data so the graph stays full

    Mock path:
      - Falls back to MetricsGenerator (Gaussian random) when Prometheus
        is unreachable or during bootstrap before the scraper is enabled.
    """

    def __init__(self, prometheus_url: str = None):
        self.prometheus_url = prometheus_url
        self._generator: MetricsGenerator = None
        self._real_enabled = False
        self._session: requests.Session = None

        if prometheus_url:
            self._try_enable_real(prometheus_url)

    # ── Init ───────────────────────────────────────────────────────────────

    def _try_enable_real(self, url: str):
        try:
            r = requests.get(f"{url.rstrip('/')}/-/healthy", timeout=4)
            if r.status_code == 200:
                self._real_enabled = True
                self._session = requests.Session()
                self._session.headers.update({"Accept": "application/json"})
                logger.info(f"✅ Real Prometheus scraper active: {url}")
            else:
                logger.warning(
                    f"Prometheus health returned {r.status_code} — using mock"
                )
        except Exception as exc:
            logger.warning(f"Prometheus unreachable ({exc}) — using mock")

    def set_generator(self, generator: MetricsGenerator):
        self._generator = generator

    # ── Public interface ───────────────────────────────────────────────────

    async def scrape(self, nodes: list[dict], edges: list[dict]) -> dict:
        if self._real_enabled:
            try:
                return await self._scrape_real(nodes, edges)
            except Exception as exc:
                logger.warning(f"Real scrape failed ({exc}) — falling back to mock")
        return self._scrape_mock(nodes, edges)

    async def query_metric(self, metric_name: str, labels: dict = None) -> list:
        if self._real_enabled:
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._instant_query, metric_name
                )
            except Exception:
                pass
        return [{"metric": labels or {}, "value": [time.time(), "0"]}]

    # ── Real scrape path ───────────────────────────────────────────────────

    async def _scrape_real(self, nodes: list[dict], edges: list[dict]) -> dict:
        loop = asyncio.get_event_loop()
        node_data, edge_data = await loop.run_in_executor(
            None, self._fetch_all_metrics
        )

        node_metrics: dict[str, dict] = {}
        for node in nodes:
            nid = node["id"]
            if nid in node_data:
                node_metrics[nid] = node_data[nid]
            else:
                # No Prometheus series for this node — use mock
                node_metrics[nid] = self._mock_generator().generate_node_metrics(node)

        edge_metrics: dict[str, dict] = {}
        for edge in edges:
            key = f"{edge['source']}->{edge['target']}"
            if key in edge_data:
                edge_metrics[key] = edge_data[key]
            else:
                edge_metrics[key] = self._mock_generator().generate_edge_metrics(
                    edge["source"], edge["target"]
                )

        return {
            "nodes":        node_metrics,
            "edges":        edge_metrics,
            "generated_at": time.time(),
            "chaos_mode":   False,
            "source":       "prometheus_real",
        }

    def _fetch_all_metrics(self) -> tuple[dict, dict]:
        """
        Synchronous: fetch all node and edge metrics from Prometheus.
        Returns (node_data, edge_data) keyed by node_id and "src->tgt".
        """
        base = self.prometheus_url.rstrip("/")
        node_data: dict[str, dict] = {}   # node_id → {field: value}
        edge_data: dict[str, dict] = {}   # "src->tgt" → {field: value}

        # ── Node metrics ──────────────────────────────────────────────────
        for metric_name in NODE_METRIC_NAMES:
            field = metric_name.replace("node_telemetry_", "")
            try:
                r = self._session.get(
                    f"{base}/api/v1/query",
                    params={"query": metric_name},
                    timeout=8,
                )
                r.raise_for_status()
                for result in r.json().get("data", {}).get("result", []):
                    labels  = result["metric"]
                    node_id = labels.get("id", "")
                    if not node_id:
                        continue
                    try:
                        value = float(result["value"][1])
                        if value != value:      # NaN check
                            continue
                    except (ValueError, IndexError):
                        continue

                    if node_id not in node_data:
                        node_data[node_id] = {
                            "timestamp": time.time(),
                            "_role":     labels.get("role", ""),
                            "_droplet":  labels.get("droplet", ""),
                            "_rack":     labels.get("rack", ""),
                        }
                    node_data[node_id][field] = value
            except Exception as exc:
                logger.debug(f"Node metric fetch failed [{metric_name}]: {exc}")

        # ── Edge metrics ──────────────────────────────────────────────────
        for metric_name in EDGE_METRIC_NAMES:
            field = metric_name.replace("edge_telemetry_", "")
            try:
                r = self._session.get(
                    f"{base}/api/v1/query",
                    params={"query": metric_name},
                    timeout=8,
                )
                r.raise_for_status()
                for result in r.json().get("data", {}).get("result", []):
                    labels = result["metric"]
                    src    = labels.get("source", "")
                    tgt    = labels.get("target", "")
                    if not src or not tgt:
                        continue
                    try:
                        value = float(result["value"][1])
                        if value != value:
                            continue
                    except (ValueError, IndexError):
                        continue

                    key = f"{src}->{tgt}"
                    if key not in edge_data:
                        edge_data[key] = {"timestamp": time.time()}
                    edge_data[key][field] = value
            except Exception as exc:
                logger.debug(f"Edge metric fetch failed [{metric_name}]: {exc}")

        return node_data, edge_data

    def _instant_query(self, metric_name: str) -> list:
        base = self.prometheus_url.rstrip("/")
        r = self._session.get(
            f"{base}/api/v1/query",
            params={"query": metric_name},
            timeout=8,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])

    # ── Mock path ──────────────────────────────────────────────────────────

    def _mock_generator(self) -> MetricsGenerator:
        if self._generator is None:
            self._generator = MetricsGenerator()
        return self._generator

    def _scrape_mock(self, nodes: list[dict], edges: list[dict]) -> dict:
        logger.debug(f"Mock Prometheus scrape at {time.strftime('%H:%M:%S')}")
        return self._mock_generator().generate_full_snapshot(nodes, edges)
