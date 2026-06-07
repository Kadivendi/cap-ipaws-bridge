"""
Routing decision engine.

Given a verified CAP alert, decides:

  * whether to fan out via `rapid-alert-platform` (the standard online path),
  * whether to bridge into the offline mesh (`resilient-mesh-gateway`), and
  * which webhook subscribers should be notified.

Every decision is guarded by a circuit breaker so a downstream outage does not
take the whole router down.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..cap.parser import CAPAlert
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .mesh_bridge import MeshBridgeClient
from .rapid_alert import RapidAlertClient

logger = logging.getLogger(__name__)


SEVERITY_PRIORITY = {
    "extreme": 4,
    "severe": 3,
    "moderate": 2,
    "minor": 1,
    "unknown": 0,
}


@dataclass
class RoutingDecision:
    rapid_alert: bool = False
    mesh: bool = False
    audit: bool = True
    webhooks: list[str] = field(default_factory=list)
    reason: str = ""


class AlertRouter:
    """Decides where to send a verified CAP alert."""

    def __init__(
        self,
        rapid_alert_client: RapidAlertClient | None = None,
        mesh_client: MeshBridgeClient | None = None,
        mesh_severity_threshold: str = "severe",
    ) -> None:
        self._rapid = rapid_alert_client
        self._mesh = mesh_client
        self._threshold = SEVERITY_PRIORITY.get(mesh_severity_threshold.lower(), 3)

        self._rapid_breaker = CircuitBreaker(CircuitBreakerConfig(name="rapid-alert"))
        self._mesh_breaker = CircuitBreaker(CircuitBreakerConfig(name="mesh-gateway"))

    def decide(self, alert: CAPAlert, webhook_subscribers: list[str] | None = None) -> RoutingDecision:
        severity_level = SEVERITY_PRIORITY.get((alert.severity or "").lower(), 0)
        decision = RoutingDecision(
            rapid_alert=alert.scope.lower() == "public" and severity_level > 0,
            mesh=severity_level >= self._threshold,
            webhooks=list(webhook_subscribers or []),
        )
        if not decision.rapid_alert and not decision.mesh:
            decision.reason = "Severity below all channel thresholds"
        else:
            parts = []
            if decision.rapid_alert:
                parts.append("rapid-alert-platform")
            if decision.mesh:
                parts.append("mesh-gateway")
            decision.reason = "Routing to: " + ", ".join(parts)
        return decision

    async def dispatch(self, alert: CAPAlert, decision: RoutingDecision) -> dict:
        """Execute a routing decision through circuit breakers."""
        result = {"alert_id": alert.identifier, "dispatched": [], "skipped": [], "errors": []}

        if decision.rapid_alert and self._rapid is not None:
            await self._guarded(
                self._rapid_breaker,
                lambda: self._rapid.dispatch(alert),
                channel="rapid-alert-platform",
                result=result,
            )

        if decision.mesh and self._mesh is not None:
            await self._guarded(
                self._mesh_breaker,
                lambda: self._mesh.inject_alert(
                    alert_id=alert.identifier,
                    cap_xml=alert.raw_xml,
                    zone_id=_first_area(alert),
                    severity=alert.severity,
                ),
                channel="mesh-gateway",
                result=result,
            )

        return result

    async def _guarded(
        self,
        breaker: CircuitBreaker,
        call: Callable[[], Awaitable],
        *,
        channel: str,
        result: dict,
    ) -> None:
        try:
            await breaker.async_call(call)
            result["dispatched"].append(channel)
        except RuntimeError as exc:
            logger.warning("Routing skipped (%s): %s", channel, exc)
            result["skipped"].append({channel: str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.error("Routing %s failed: %s", channel, exc)
            result["errors"].append({channel: str(exc)})

    @property
    def stats(self) -> dict:
        return {
            "rapid_alert": self._rapid_breaker.stats,
            "mesh_gateway": self._mesh_breaker.stats,
        }


def _first_area(alert: CAPAlert) -> str:
    if not alert.infos or not alert.infos[0].areas:
        return ""
    return alert.infos[0].areas[0].area_desc
