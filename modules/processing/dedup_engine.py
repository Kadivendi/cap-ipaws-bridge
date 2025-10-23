"""Content-hash deduplication engine for CAP alert processing.

Prevents duplicate alert delivery when the same CAP alert is received
from multiple IPAWS-OPEN feeds, NOAA, or NWS sources simultaneously.
Uses SHA-256 content hashing with configurable TTL window.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class DedupStats:
    """Statistics for deduplication performance monitoring."""
    total_checked: int = 0
    duplicates_caught: int = 0
    unique_alerts: int = 0
    last_duplicate_at: Optional[float] = None

    @property
    def duplicate_rate(self) -> float:
        if self.total_checked == 0:
            return 0.0
        return self.duplicates_caught / self.total_checked


class DedupEngine:
    """Content-hash deduplication engine for CAP alerts.

    Computes SHA-256 hash of normalized alert content (identifier,
    sender, event type, and affected areas) to detect duplicates
    across different feed sources.
    """

    def __init__(self, ttl_seconds: float = 3600.0, max_entries: int = 50000):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._seen: Dict[str, float] = {}
        self._lock = Lock()
        self._stats = DedupStats()
        logger.info("DedupEngine initialized: ttl=%.0fs, max=%d", ttl_seconds, max_entries)

    def is_duplicate(self, alert_identifier: str, sender: str,
                     event_type: str, areas: str) -> bool:
        """Check if an alert with this content has been seen recently."""
        content = f"{alert_identifier}|{sender}|{event_type}|{areas}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        with self._lock:
            self._cleanup_expired()
            self._stats.total_checked += 1

            if content_hash in self._seen:
                self._stats.duplicates_caught += 1
                self._stats.last_duplicate_at = time.time()
                logger.debug("Duplicate detected: hash=%s", content_hash[:12])
                return True

            self._seen[content_hash] = time.time()
            self._stats.unique_alerts += 1
            return False

    def get_stats(self) -> Dict:
        """Return deduplication performance statistics."""
        return {
            "total_checked": self._stats.total_checked,
            "duplicates_caught": self._stats.duplicates_caught,
            "unique_alerts": self._stats.unique_alerts,
            "duplicate_rate": round(self._stats.duplicate_rate, 4),
            "tracked_hashes": len(self._seen),
            "ttl_seconds": self._ttl,
        }

    def _cleanup_expired(self) -> None:
        """Remove entries older than TTL."""
        cutoff = time.time() - self._ttl
        expired = [k for k, v in self._seen.items() if v < cutoff]
        for key in expired:
            del self._seen[key]
        if expired:
            logger.debug("Cleaned up %d expired dedup entries", len(expired))
