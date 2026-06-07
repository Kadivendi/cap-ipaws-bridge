"""NOAA CAP Atom feed parser."""
from __future__ import annotations

import logging
from typing import Iterable

import httpx

from ..cap.parser import CAPAlert, CAPParser

logger = logging.getLogger(__name__)

NOAA_FEED_URL = "https://api.weather.gov/alerts/active.atom"


class NOAAFeedClient:
    """Pulls active NOAA weather alerts as CAP 1.2 objects."""

    def __init__(self, feed_url: str = NOAA_FEED_URL, timeout: float = 10.0) -> None:
        self._url = feed_url
        self._client = httpx.Client(timeout=timeout, headers={"Accept": "application/atom+xml"})
        self._parser = CAPParser()

    def fetch_active_alerts(self) -> Iterable[CAPAlert]:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
            yield from self._parser.parse_atom_feed(response.text)
        except httpx.HTTPError as exc:
            logger.warning("NOAA fetch failed: %s", exc)
            return []

    def close(self) -> None:
        self._client.close()


# Backwards-compatible procedural wrapper.
def fetch_noaa() -> list[CAPAlert]:
    client = NOAAFeedClient()
    try:
        return list(client.fetch_active_alerts())
    finally:
        client.close()
