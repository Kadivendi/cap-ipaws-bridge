"""
Mesh Network Bridge Client
When standard delivery channels (push, SMS, Telegram) fail, this module
hands off verified CAP alerts to the resilient-mesh-gateway for offline broadcast.
"""
import httpx
import logging
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DeliveryStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


@dataclass
class MeshDeliveryResult:
    alert_id: str
    status: DeliveryStatus
    zone_id: str
    injected_at: datetime
    nodes_reached: int = 0
    error: str | None = None


class MeshBridgeClient:
    """
    HTTP client for the resilient-mesh-gateway injection API.
    Used when rapid-alert-platform delivery rate drops below threshold.
    """
    DEFAULT_TIMEOUT = 10.0
    DELIVERY_FAILURE_THRESHOLD = 0.80  # trigger mesh if standard < 80%

    def __init__(
        self,
        gateway_url: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self._gateway_url = gateway_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Source": "cap-ipaws-bridge",
        }
        self._client = httpx.AsyncClient(timeout=timeout, headers=self._headers)
        self._delivery_rates: list[float] = []

    async def inject_alert(
        self,
        alert_id: str,
        cap_xml: str,
        zone_id: str,
        severity: str,
    ) -> MeshDeliveryResult:
        """Inject a CAP alert into the mesh gateway for offline broadcast."""
        payload = {
            "alert_id": alert_id,
            "cap_xml": cap_xml,
            "zone_id": zone_id,
            "severity": severity,
            "source": "cap-ipaws-bridge",
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            resp = await self._client.post(
                f"{self._gateway_url}/api/mesh/inject",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return MeshDeliveryResult(
                alert_id=alert_id,
                status=DeliveryStatus.SENT,
                zone_id=zone_id,
                injected_at=datetime.utcnow(),
                nodes_reached=data.get("nodes_reached", 0),
            )
        except httpx.HTTPError as e:
            logger.error(f"Mesh injection failed for alert {alert_id}: {e}")
            return MeshDeliveryResult(
                alert_id=alert_id,
                status=DeliveryStatus.FAILED,
                zone_id=zone_id,
                injected_at=datetime.utcnow(),
                error=str(e),
            )

    def record_delivery_rate(self, rate: float) -> None:
        """Track rolling delivery rate to decide when to activate mesh fallback."""
        self._delivery_rates.append(rate)
        if len(self._delivery_rates) > 20:
            self._delivery_rates.pop(0)

    @property
    def should_activate_mesh(self) -> bool:
        if len(self._delivery_rates) < 3:
            return False
        recent_avg = sum(self._delivery_rates[-5:]) / min(5, len(self._delivery_rates))
        return recent_avg < self.DELIVERY_FAILURE_THRESHOLD

    async def close(self) -> None:
        await self._client.aclose()
