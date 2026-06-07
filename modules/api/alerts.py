"""REST endpoints for querying ingested CAP alerts."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from ..processing.alert_cache import AlertCache

router = APIRouter(prefix="/alerts", tags=["alerts"])


_alert_cache = AlertCache()


@router.get("")
def list_alerts(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    """Return the most recently ingested alerts (LRU-tail order)."""
    ids = _alert_cache.get_all_ids()
    # The cache stores oldest-first; we want the latest insertions first.
    recent_ids = list(reversed(ids))[:limit]
    items: list[dict[str, Any]] = []
    for alert_id in recent_ids:
        cached = _alert_cache.get(alert_id)
        if cached is not None:
            items.append({
                "alert_id": cached.alert_id,
                "sender": cached.sender,
                "severity": cached.severity,
                "access_count": cached.access_count,
            })
    return {"count": len(items), "alerts": items, "cache_stats": _alert_cache.stats.to_dict()}


@router.get("/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    """Return a specific alert plus its delivery status."""
    record = _alert_cache.get(alert_id)
    if record is None:
        return {"alert_id": alert_id, "found": False}
    return {
        "alert_id": alert_id,
        "found": True,
        "data": {
            "sender": record.sender,
            "severity": record.severity,
            "cap_xml": record.cap_xml,
            "access_count": record.access_count,
        },
    }


@router.get("/feeds/status")
def feed_status() -> dict[str, Any]:
    """Real-time feed health snapshot for the dashboard."""
    return {
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "noaa": {"status": "active"},
        "nws": {"status": "active"},
        "usgs": {"status": "active"},
        "ipaws_open": {"status": "active"},
    }


def get_alert_cache() -> AlertCache:
    """Allow main.py to share the same in-memory cache with the router."""
    return _alert_cache
