"""Tests for the mesh gateway bridge client."""
import pytest
from modules.routing.mesh_bridge import MeshBridgeClient, DeliveryStatus


class TestMeshBridgeClient:

    def setup_method(self):
        self.client = MeshBridgeClient(
            gateway_url="http://localhost:9000",
            api_key="test-key",
        )

    def test_should_not_activate_mesh_with_no_data(self):
        assert self.client.should_activate_mesh is False

    def test_should_not_activate_mesh_above_threshold(self):
        for _ in range(5):
            self.client.record_delivery_rate(0.95)
        assert self.client.should_activate_mesh is False

    def test_should_activate_mesh_below_threshold(self):
        for _ in range(5):
            self.client.record_delivery_rate(0.50)
        assert self.client.should_activate_mesh is True

    def test_rolling_window_uses_recent_rates(self):
        for _ in range(15):
            self.client.record_delivery_rate(0.95)
        for _ in range(5):
            self.client.record_delivery_rate(0.30)
        assert self.client.should_activate_mesh is True

    def test_delivery_threshold_value(self):
        assert MeshBridgeClient.DELIVERY_FAILURE_THRESHOLD == 0.80
