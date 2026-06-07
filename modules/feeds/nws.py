"""National Weather Service feed client.

NWS exposes both Atom (CAP) and JSON variants of the active-alerts endpoint;
this client uses the JSON variant for cheap polling and surfaces each entry
as a lightweight dict so the rest of the pipeline can treat it uniformly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NWS_ENDPOINT = "https://api.weather.gov/alerts/active"


class NWSFeedClient:
    def __init__(self, endpoint: str = NWS_ENDPOINT, timeout: float = 10.0) -> None:
        self._url = endpoint
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Accept": "application/geo+json",
                "User-Agent": "cap-ipaws-bridge/1.0 (kv11@iitbbs.ac.in)",
            },
        )

    def fetch_active_warnings(self) -> list[dict[str, Any]]:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
            data = response.json()
            return data.get("features", [])
        except httpx.HTTPError as exc:
            logger.warning("NWS fetch failed: %s", exc)
            return []

    def close(self) -> None:
        self._client.close()


def fetch_nws() -> list[dict[str, Any]]:
    client = NWSFeedClient()
    try:
        return client.fetch_active_warnings()
    finally:
        client.close()
