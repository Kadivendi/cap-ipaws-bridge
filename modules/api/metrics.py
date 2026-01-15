"""
Prometheus Metrics Exporter
Exposes /metrics endpoint for Prometheus scraping — tracks alert delivery
rates, IPAWS poll latency, webhook success rates, and mesh failover events.
"""
import time
import logging
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime

logger = logging.getLogger(__name__)

# Metric names follow Prometheus naming conventions
METRIC_ALERTS_INGESTED = "cap_bridge_alerts_ingested_total"
METRIC_ALERTS_DELIVERED = "cap_bridge_alerts_delivered_total"
METRIC_DELIVERY_LATENCY = "cap_bridge_delivery_latency_seconds"
METRIC_IPAWS_POLL_LATENCY = "cap_bridge_ipaws_poll_latency_seconds"
METRIC_MESH_FAILOVERS = "cap_bridge_mesh_failover_total"
METRIC_WEBHOOK_DELIVERIES = "cap_bridge_webhook_deliveries_total"
METRIC_CIRCUIT_STATE = "cap_bridge_circuit_breaker_state"


@dataclass
class MetricsCollector:
    """
    Lightweight in-process metrics collector compatible with Prometheus text format.
    Exposed via GET /metrics endpoint (OpenMetrics 1.0 text format).
    """
    _counters: dict = field(default_factory=lambda: defaultdict(int))
    _gauges: dict = field(default_factory=lambda: defaultdict(float))
    _histograms: dict = field(default_factory=lambda: defaultdict(list))

    def inc(self, metric: str, labels: dict | None = None, value: int = 1):
        key = self._key(metric, labels)
        self._counters[key] += value

    def set_gauge(self, metric: str, value: float, labels: dict | None = None):
        key = self._key(metric, labels)
        self._gauges[key] = value

    def observe(self, metric: str, value: float, labels: dict | None = None):
        key = self._key(metric, labels)
        self._histograms[key].append(value)
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def record_alert_ingested(self, source: str, severity: str):
        self.inc(METRIC_ALERTS_INGESTED, {"source": source, "severity": severity})

    def record_alert_delivered(self, channel: str, status: str):
        self.inc(METRIC_ALERTS_DELIVERED, {"channel": channel, "status": status})

    def record_delivery_latency(self, channel: str, latency_seconds: float):
        self.observe(METRIC_DELIVERY_LATENCY, latency_seconds, {"channel": channel})

    def record_ipaws_poll(self, latency_seconds: float, success: bool):
        self.observe(METRIC_IPAWS_POLL_LATENCY, latency_seconds)
        self.inc(METRIC_ALERTS_INGESTED, {"source": "ipaws", "success": str(success)})

    def record_mesh_failover(self, zone_id: str):
        self.inc(METRIC_MESH_FAILOVERS, {"zone": zone_id})

    def record_webhook_delivery(self, webhook_id: str, success: bool):
        self.inc(METRIC_WEBHOOK_DELIVERIES, {"webhook": webhook_id, "success": str(success)})

    def render_text(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        lines = [f"# CAP IPAWS Bridge Metrics — {datetime.utcnow().isoformat()}\n"]
        for key, value in self._counters.items():
            lines.append(f"{key} {value}")
        for key, value in self._gauges.items():
            lines.append(f"{key} {value:.6f}")
        for key, observations in self._histograms.items():
            if observations:
                avg = sum(observations) / len(observations)
                p95 = sorted(observations)[int(len(observations) * 0.95)]
                lines.append(f"{key}_avg {avg:.6f}")
                lines.append(f"{key}_p95 {p95:.6f}")
                lines.append(f"{key}_count {len(observations)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _key(metric: str, labels: dict | None) -> str:
        if not labels:
            return metric
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{metric}{{{label_str}}}"
