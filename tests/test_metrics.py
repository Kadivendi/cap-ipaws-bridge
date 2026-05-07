"""Tests for the Prometheus metrics collector."""
import pytest
from modules.api.metrics import MetricsCollector, METRIC_ALERTS_INGESTED, METRIC_MESH_FAILOVERS


class TestMetricsCollector:

    def setup_method(self):
        self.m = MetricsCollector()

    def test_counter_increments(self):
        self.m.inc(METRIC_ALERTS_INGESTED, {"source": "noaa", "severity": "extreme"})
        self.m.inc(METRIC_ALERTS_INGESTED, {"source": "noaa", "severity": "extreme"})
        output = self.m.render_text()
        assert 'source="noaa"' in output

    def test_mesh_failover_recorded(self):
        self.m.record_mesh_failover("US-CA-LA-001")
        output = self.m.render_text()
        assert METRIC_MESH_FAILOVERS in output

    def test_histogram_computes_avg_and_p95(self):
        for i in range(100):
            self.m.record_delivery_latency("telegram", float(i) / 100.0)
        output = self.m.render_text()
        assert "_avg" in output
        assert "_p95" in output

    def test_render_text_returns_string(self):
        assert isinstance(self.m.render_text(), str)

    def test_webhook_delivery_tracking(self):
        self.m.record_webhook_delivery("wh-001", success=True)
        self.m.record_webhook_delivery("wh-001", success=False)
        output = self.m.render_text()
        assert "webhook" in output.lower() or "deliveries" in output.lower()
