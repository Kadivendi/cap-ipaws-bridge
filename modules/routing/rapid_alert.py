"""
HTTP client for the `rapid-alert-platform` notification dispatch service.

Exposes the single side of the bridge → `rapid-alert-platform` integration so
the rest of the router stays decoupled from the Java service's exact REST shape.
The notification-service authenticates incoming requests via the platform's JWT;
the token is acquired from the security-service once at startup.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..cap.parser import CAPAlert

logger = logging.getLogger(__name__)


class RapidAlertClient:
    """Thin async HTTP client targeting the rapid-alert-platform gateway."""

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 8.0,
    ) -> None:
        self._base = (base_url or os.environ.get("RAPID_ALERT_URL", "http://rapid-alert-platform:8080")).rstrip("/")
        self._client_id = client_id or os.environ.get("RAPID_ALERT_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("RAPID_ALERT_CLIENT_SECRET", "")
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout, headers={"X-Source": "cap-ipaws-bridge"})

    async def _ensure_token(self) -> str | None:
        if self._token or not self._client_id or not self._client_secret:
            return self._token
        try:
            resp = await self._client.post(
                f"{self._base}/api/v1/auth/authenticate",
                json={"email": self._client_id, "password": self._client_secret},
            )
            resp.raise_for_status()
            self._token = (resp.json() or {}).get("token")
        except httpx.HTTPError as exc:
            logger.warning("Could not authenticate to rapid-alert-platform: %s", exc)
            self._token = None
        return self._token

    async def dispatch(self, alert: CAPAlert) -> dict[str, Any]:
        """Translate a CAP alert into a rapid-alert notification request."""
        token = await self._ensure_token()
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "event_id": alert.identifier,
            "severity": alert.severity,
            "urgency": alert.infos[0].urgency if alert.infos else "",
            "category": alert.infos[0].category if alert.infos else "",
            "headline": alert.headline,
            "description": alert.infos[0].description if alert.infos else "",
            "instruction": alert.infos[0].instruction if alert.infos else "",
            "source": "cap-ipaws-bridge",
            "areas": [a.area_desc for info in alert.infos for a in info.areas],
        }

        url = f"{self._base}/api/v1/notifications/ingest/cap"
        try:
            resp = await self._client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return {"ok": True, "status_code": resp.status_code, "body": _safe_json(resp)}
        except httpx.HTTPStatusError as exc:
            logger.warning("rapid-alert-platform rejected alert %s: %s", alert.identifier, exc)
            return {"ok": False, "status_code": exc.response.status_code, "body": exc.response.text}
        except httpx.HTTPError as exc:
            logger.warning("rapid-alert-platform unreachable for alert %s: %s", alert.identifier, exc)
            return {"ok": False, "error": str(exc)}

    async def close(self) -> None:
        await self._client.aclose()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


# Procedural alias preserved for legacy callers.
def rapid_alert_push() -> None:  # noqa: D401
    """Deprecated synchronous shim — use :class:`RapidAlertClient`."""
    logger.warning("rapid_alert_push() is a legacy no-op; use RapidAlertClient.dispatch().")
