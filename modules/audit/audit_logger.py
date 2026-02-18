"""Structured audit logging for alert lifecycle tracking.

Records every state transition in CAP alert processing for compliance,
debugging, and analytics. Each event includes a correlation ID for
tracing alerts across the distributed system.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertLifecycleEvent(Enum):
    """Alert lifecycle states for audit tracking."""
    INGESTED = "ingested"
    VALIDATED = "validated"
    DEDUPLICATED = "deduplicated"
    ENRICHED = "enriched"
    ROUTED = "routed"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"
    RETRIED = "retried"
    CANCELLED = "cancelled"


@dataclass
class AuditEntry:
    """Single audit log entry for an alert lifecycle event."""
    event: AlertLifecycleEvent
    alert_identifier: str
    correlation_id: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    destination: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to structured JSON-serializable dictionary."""
        record = {
            "event": self.event.value,
            "alert_id": self.alert_identifier,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "destination": self.destination,
        }
        if self.metadata:
            record["metadata"] = self.metadata
        if self.error_message:
            record["error"] = self.error_message
        if self.duration_ms is not None:
            record["duration_ms"] = self.duration_ms
        return record


class AuditLogger:
    """Audit logger for CAP alert lifecycle events.

    Provides structured logging with correlation IDs for distributed
    tracing and queryable audit trail for compliance reporting.
    """

    def __init__(self, max_entries: int = 100000):
        self._entries: List[AuditEntry] = []
        self._max_entries = max_entries
        self._correlation_map: Dict[str, str] = {}
        logger.info("AuditLogger initialized: max_entries=%d", max_entries)

    def log_event(self, event: AlertLifecycleEvent, alert_identifier: str,
                  source: str = "", destination: str = "",
                  metadata: Optional[Dict] = None,
                  error_message: Optional[str] = None,
                  duration_ms: Optional[float] = None) -> str:
        """Record an audit event and return the correlation ID."""
        correlation_id = self._get_or_create_correlation(alert_identifier)

        entry = AuditEntry(
            event=event,
            alert_identifier=alert_identifier,
            correlation_id=correlation_id,
            source=source,
            destination=destination,
            metadata=metadata or {},
            error_message=error_message,
            duration_ms=duration_ms,
        )

        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        logger.info("Audit: %s alert=%s corr=%s src=%s dst=%s",
                    event.value, alert_identifier, correlation_id[:8],
                    source, destination)
        return correlation_id

    def query(self, alert_identifier: Optional[str] = None,
              event_type: Optional[AlertLifecycleEvent] = None,
              since: Optional[float] = None,
              limit: int = 100) -> List[Dict]:
        """Query audit entries with optional filters."""
        results = self._entries
        if alert_identifier:
            results = [e for e in results if e.alert_identifier == alert_identifier]
        if event_type:
            results = [e for e in results if e.event == event_type]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return [e.to_dict() for e in results[-limit:]]

    def get_event_counts(self) -> Dict[str, int]:
        """Return counts by event type for dashboard display."""
        counts: Dict[str, int] = {}
        for entry in self._entries:
            key = entry.event.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _get_or_create_correlation(self, alert_identifier: str) -> str:
        """Get existing or create new correlation ID for an alert."""
        if alert_identifier not in self._correlation_map:
            self._correlation_map[alert_identifier] = str(uuid.uuid4())
        return self._correlation_map[alert_identifier]
