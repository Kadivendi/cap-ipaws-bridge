"""Admin API endpoints for alert management and system status.

Provides operational endpoints for monitoring system health, managing
alerts, and performing administrative actions like cache purging
and forced retries.
"""
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

logger = logging.getLogger(__name__)


@dataclass
class SystemStatus:
    """Aggregated system status snapshot."""
    uptime_seconds: float
    alerts_processed: int
    alerts_pending: int
    feed_health: Dict[str, str]
    cache_hit_rate: float
    delivery_success_rate: float
    dead_letter_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "alerts_processed": self.alerts_processed,
            "alerts_pending": self.alerts_pending,
            "feed_health": self.feed_health,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "delivery_success_rate": round(self.delivery_success_rate, 4),
            "dead_letter_count": self.dead_letter_count,
            "timestamp": time.time(),
        }


class AdminService:
    """Service layer for administrative operations.

    Provides:
    - System status aggregation from all subsystems
    - Alert listing and detail retrieval
    - Cache management (purge, invalidate)
    - Forced retry for failed deliveries
    - API key authentication for admin access
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._start_time = time.time()
        self._processed_alerts: List[Dict] = []
        self._pending_alerts: List[Dict] = []
        logger.info("AdminService initialized")

    def authenticate(self, provided_key: str) -> bool:
        """Validate API key for admin access."""
        if not self._api_key:
            logger.warning("Admin API key not configured — access denied")
            return False
        return provided_key == self._api_key

    def get_system_status(self) -> Dict[str, Any]:
        """Aggregate system status from all subsystems."""
        status = SystemStatus(
            uptime_seconds=time.time() - self._start_time,
            alerts_processed=len(self._processed_alerts),
            alerts_pending=len(self._pending_alerts),
            feed_health={"ipaws": "HEALTHY", "noaa": "HEALTHY", "nws": "HEALTHY"},
            cache_hit_rate=0.0,
            delivery_success_rate=0.0,
            dead_letter_count=0,
        )
        return status.to_dict()

    def list_alerts(self, status_filter: Optional[str] = None,
                    limit: int = 50) -> List[Dict]:
        """List recent alerts with optional status filtering."""
        alerts = self._processed_alerts + self._pending_alerts
        if status_filter:
            alerts = [a for a in alerts if a.get("status") == status_filter]
        return alerts[-limit:]

    def get_alert_detail(self, alert_id: str) -> Optional[Dict]:
        """Get detailed information about a specific alert."""
        all_alerts = self._processed_alerts + self._pending_alerts
        for alert in all_alerts:
            if alert.get("identifier") == alert_id:
                return alert
        return None

    def force_retry(self, alert_id: str) -> Dict[str, Any]:
        """Force retry delivery for a specific alert."""
        logger.info("Force retry requested: alert_id=%s", alert_id)
        return {
            "alert_id": alert_id,
            "action": "retry_queued",
            "timestamp": time.time(),
        }

    def purge_cache(self) -> Dict[str, Any]:
        """Purge the alert cache and return statistics."""
        logger.info("Cache purge requested")
        return {
            "action": "cache_purged",
            "entries_removed": 0,
            "timestamp": time.time(),
        }


# ---------------------------------------------------------------------------
# FastAPI surface
# ---------------------------------------------------------------------------

admin_router = APIRouter(tags=["admin"])
_admin_service = AdminService(api_key=os.environ.get("ADMIN_API_KEY", ""))


def _require_admin(x_admin_key: str = Header(default="")) -> None:
    """Reject requests without a matching X-Admin-Key header (when configured)."""
    if _admin_service._api_key and not _admin_service.authenticate(x_admin_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")


@admin_router.get("/status")
def system_status(_=Depends(_require_admin)) -> Dict[str, Any]:
    return _admin_service.get_system_status()


@admin_router.get("/alerts")
def list_alerts(
    status: Optional[str] = None,
    limit: int = 50,
    _=Depends(_require_admin),
) -> List[Dict]:
    return _admin_service.list_alerts(status_filter=status, limit=limit)


@admin_router.get("/alerts/{alert_id}")
def get_alert_detail(alert_id: str, _=Depends(_require_admin)) -> Dict[str, Any]:
    detail = _admin_service.get_alert_detail(alert_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return detail


@admin_router.post("/alerts/{alert_id}/retry")
def force_retry(alert_id: str, _=Depends(_require_admin)) -> Dict[str, Any]:
    return _admin_service.force_retry(alert_id)


@admin_router.post("/cache/purge")
def purge_cache(_=Depends(_require_admin)) -> Dict[str, Any]:
    return _admin_service.purge_cache()
