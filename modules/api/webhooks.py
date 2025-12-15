"""
Outbound Webhook Dispatcher
Sends signed HMAC-SHA256 webhook notifications to registered endpoints
when new CAP alerts are ingested and verified.
"""
import hashlib
import hmac
import json
import logging
import asyncio
import httpx
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubled each attempt
MAX_REGISTERED_WEBHOOKS = 50


@dataclass
class WebhookEndpoint:
    id: str
    url: str
    secret: str
    events: list[str] = field(default_factory=lambda: ["alert.new", "alert.update", "alert.cancel"])
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_delivery_at: datetime | None = None
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


@dataclass
class WebhookDeliveryResult:
    webhook_id: str
    event: str
    status_code: int | None
    success: bool
    attempt: int
    delivered_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


class WebhookDispatcher:
    """
    Dispatches signed webhook events to registered endpoints with retry logic.
    Registered via POST /api/webhooks REST endpoint.
    """

    def __init__(self):
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._client = httpx.AsyncClient(timeout=5.0)

    def register(self, endpoint: WebhookEndpoint) -> None:
        if len(self._endpoints) >= MAX_REGISTERED_WEBHOOKS:
            raise ValueError(f"Maximum webhook registrations ({MAX_REGISTERED_WEBHOOKS}) reached")
        self._endpoints[endpoint.id] = endpoint
        logger.info(f"Webhook registered: {endpoint.id} → {endpoint.url}")

    def deregister(self, webhook_id: str) -> bool:
        return self._endpoints.pop(webhook_id, None) is not None

    async def dispatch(self, event: str, payload: dict) -> list[WebhookDeliveryResult]:
        """Dispatch an event to all registered endpoints that subscribe to it."""
        targets = [ep for ep in self._endpoints.values() if ep.active and event in ep.events]
        tasks = [self._deliver(ep, event, payload) for ep in targets]
        return await asyncio.gather(*tasks)

    async def _deliver(
        self,
        endpoint: WebhookEndpoint,
        event: str,
        payload: dict,
    ) -> WebhookDeliveryResult:
        body = json.dumps({"event": event, "timestamp": datetime.utcnow().isoformat(), **payload})
        signature = self._sign(body, endpoint.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Source": "cap-ipaws-bridge",
        }

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                resp = await self._client.post(endpoint.url, content=body, headers=headers)
                success = 200 <= resp.status_code < 300
                if success:
                    endpoint.success_count += 1
                    endpoint.last_delivery_at = datetime.utcnow()
                    return WebhookDeliveryResult(
                        webhook_id=endpoint.id, event=event,
                        status_code=resp.status_code, success=True, attempt=attempt,
                    )
                else:
                    logger.warning(f"Webhook {endpoint.id} returned {resp.status_code} on attempt {attempt}")
            except httpx.HTTPError as e:
                logger.warning(f"Webhook {endpoint.id} attempt {attempt} failed: {e}")

            if attempt < MAX_RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        endpoint.failure_count += 1
        return WebhookDeliveryResult(
            webhook_id=endpoint.id, event=event,
            status_code=None, success=False, attempt=MAX_RETRY_ATTEMPTS,
            error="Max retries exceeded",
        )

    @staticmethod
    def _sign(body: str, secret: str) -> str:
        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    def get_stats(self) -> dict:
        return {
            ep_id: {
                "url": ep.url, "active": ep.active,
                "success_rate": ep.success_rate,
                "last_delivery": ep.last_delivery_at.isoformat() if ep.last_delivery_at else None,
            }
            for ep_id, ep in self._endpoints.items()
        }

    async def close(self) -> None:
        await self._client.aclose()
