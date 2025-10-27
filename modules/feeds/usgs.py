"""USGS earthquake feed client."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USGS_ENDPOINT = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_hour.geojson"
)


class USGSFeedClient:
    def __init__(
        self,
        endpoint: str = USGS_ENDPOINT,
        min_magnitude: float = 2.5,
        timeout: float = 10.0,
    ) -> None:
        self._url = endpoint
        self._min_magnitude = min_magnitude
        self._client = httpx.Client(timeout=timeout)

    def fetch_significant_events(self) -> list[dict[str, Any]]:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("USGS fetch failed: %s", exc)
            return []

        features = payload.get("features", [])
        return [
            f
            for f in features
            if (f.get("properties") or {}).get("mag", 0) >= self._min_magnitude
        ]

    def close(self) -> None:
        self._client.close()


def fetch_usgs() -> list[dict[str, Any]]:
    client = USGSFeedClient()
    try:
        return client.fetch_significant_events()
    finally:
        client.close()
