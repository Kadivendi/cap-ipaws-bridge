"""Tests for the webhook dispatcher."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from modules.api.webhooks import WebhookDispatcher, WebhookEndpoint, WebhookDeliveryResult


class TestWebhookDispatcher:

    def setup_method(self):
        self.dispatcher = WebhookDispatcher()

    def _make_endpoint(self, ep_id="ep-001", url="https://example.com/hook"):
        return WebhookEndpoint(id=ep_id, url=url, secret="test-secret-key")

    def test_register_endpoint(self):
        ep = self._make_endpoint()
        self.dispatcher.register(ep)
        assert "ep-001" in self.dispatcher._endpoints

    def test_deregister_endpoint(self):
        ep = self._make_endpoint()
        self.dispatcher.register(ep)
        assert self.dispatcher.deregister("ep-001") is True
        assert "ep-001" not in self.dispatcher._endpoints

    def test_deregister_nonexistent_returns_false(self):
        assert self.dispatcher.deregister("does-not-exist") is False

    def test_max_registrations_enforced(self):
        for i in range(50):
            self.dispatcher.register(self._make_endpoint(f"ep-{i}", f"https://example.com/{i}"))
        with pytest.raises(ValueError, match="Maximum webhook registrations"):
            self.dispatcher.register(self._make_endpoint("ep-overflow"))

    def test_sign_is_deterministic(self):
        sig1 = WebhookDispatcher._sign("body", "secret")
        sig2 = WebhookDispatcher._sign("body", "secret")
        assert sig1 == sig2

    def test_sign_differs_for_different_secrets(self):
        s1 = WebhookDispatcher._sign("body", "secret1")
        s2 = WebhookDispatcher._sign("body", "secret2")
        assert s1 != s2

    def test_success_rate_calculation(self):
        ep = self._make_endpoint()
        ep.success_count = 8
        ep.failure_count = 2
        assert ep.success_rate == pytest.approx(0.8)

    def test_get_stats_returns_registered_endpoints(self):
        self.dispatcher.register(self._make_endpoint("ep-stat"))
        stats = self.dispatcher.get_stats()
        assert "ep-stat" in stats
        assert "url" in stats["ep-stat"]
