"""
Content-Hash Deduplication Engine for CAP Alert Processing

Detects and suppresses duplicate CAP alerts using SHA-256 content hashing.
IPAWS feeds frequently re-deliver the same alert within short windows;
this engine ensures each unique alert is processed exactly once while
maintaining a time-bounded cache of seen hashes.

Architecture:
    Incoming XML → normalize → SHA-256 → lookup in hash table → accept/reject
    Expired entries are lazily evicted on each check or via periodic sweep.
"""
import hashlib
import logging
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Default deduplication window: 2 hours covers IPAWS re-delivery patterns
DEFAULT_TTL_SECONDS = 7200
DEFAULT_MAX_ENTRIES = 50_000


@dataclass(frozen=True)
class DedupResult:
    """Result of a deduplication check."""
    is_duplicate: bool
    content_hash: str
    alert_identifier: Optional[str] = None
    first_seen: Optional[float] = None


@dataclass
class _HashEntry:
    """Internal entry tracking when a content hash was first observed."""
    content_hash: str
    alert_identifier: str
    first_seen: float
    expires_at: float


@dataclass
class DedupMetrics:
    """Counters for deduplication performance monitoring."""
    total_checked: int = 0
    duplicates_caught: int = 0
    unique_accepted: int = 0
    evictions: int = 0
    collisions: int = 0

    @property
    def duplicate_rate(self) -> float:
        if self.total_checked == 0:
            return 0.0
        return self.duplicates_caught / self.total_checked

    def to_dict(self) -> dict:
        return {
            "total_checked": self.total_checked,
            "duplicates_caught": self.duplicates_caught,
            "unique_accepted": self.unique_accepted,
            "evictions": self.evictions,
            "duplicate_rate": round(self.duplicate_rate, 4),
        }


class DedupEngine:
    """
    Thread-safe content-hash deduplication engine.

    Uses SHA-256 of normalized alert content to detect duplicates within
    a configurable TTL window. Designed for high-throughput IPAWS polling
    where the same alert may appear in consecutive feed fetches.

    Usage:
        engine = DedupEngine(ttl_seconds=3600)
        result = engine.check(cap_xml, alert_id="urn:oid:2.49.0.1.840.0")
        if result.is_duplicate:
            logger.info(f"Skipping duplicate {alert_id}")
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._hash_table: dict[str, _HashEntry] = {}
        self._lock = threading.Lock()
        self._metrics = DedupMetrics()
        logger.info(
            f"DedupEngine initialized: ttl={ttl_seconds}s, max_entries={max_entries}"
        )

    def check(self, content: str, alert_identifier: str = "") -> DedupResult:
        """
        Check whether content has been seen before within the TTL window.

        Args:
            content: Raw CAP XML or alert body text.
            alert_identifier: Optional CAP identifier for logging.

        Returns:
            DedupResult indicating whether the content is a duplicate.
        """
        normalized = self._normalize(content)
        content_hash = self._compute_hash(normalized)
        now = time.monotonic()

        with self._lock:
            self._metrics.total_checked += 1
            self._lazy_evict(now)

            existing = self._hash_table.get(content_hash)
            if existing is not None and existing.expires_at > now:
                self._metrics.duplicates_caught += 1
                logger.debug(
                    f"Duplicate detected: hash={content_hash[:12]}… "
                    f"alert={alert_identifier or existing.alert_identifier}"
                )
                return DedupResult(
                    is_duplicate=True,
                    content_hash=content_hash,
                    alert_identifier=existing.alert_identifier,
                    first_seen=existing.first_seen,
                )

            # New unique content — register it
            entry = _HashEntry(
                content_hash=content_hash,
                alert_identifier=alert_identifier,
                first_seen=now,
                expires_at=now + self._ttl,
            )
            self._hash_table[content_hash] = entry
            self._metrics.unique_accepted += 1

            # Enforce max entries (evict oldest if needed)
            if len(self._hash_table) > self._max_entries:
                self._evict_oldest()

            return DedupResult(
                is_duplicate=False,
                content_hash=content_hash,
                alert_identifier=alert_identifier,
                first_seen=now,
            )

    def sweep_expired(self) -> int:
        """Remove all expired entries. Returns count of evicted entries."""
        now = time.monotonic()
        evicted = 0
        with self._lock:
            expired_keys = [
                k for k, v in self._hash_table.items()
                if v.expires_at <= now
            ]
            for key in expired_keys:
                del self._hash_table[key]
                evicted += 1
            self._metrics.evictions += evicted
        if evicted > 0:
            logger.info(f"DedupEngine sweep: evicted {evicted} expired entries")
        return evicted

    @property
    def metrics(self) -> DedupMetrics:
        return self._metrics

    @property
    def size(self) -> int:
        return len(self._hash_table)

    def reset(self) -> None:
        """Clear all entries and reset metrics."""
        with self._lock:
            self._hash_table.clear()
            self._metrics = DedupMetrics()
        logger.info("DedupEngine reset: all entries cleared")

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _normalize(content: str) -> str:
        """
        Normalize CAP XML for consistent hashing.
        Strips whitespace variations and XML declarations that differ
        between feed fetches but don't change alert semantics.
        """
        text = content.strip()
        # Remove XML declaration (encoding may differ)
        text = re.sub(r'<\?xml[^?]*\?>', '', text)
        # Collapse whitespace runs
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def _compute_hash(content: str) -> str:
        """SHA-256 hex digest of normalized content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _lazy_evict(self, now: float) -> None:
        """Evict a small batch of expired entries on each check to bound memory."""
        batch = 0
        to_remove = []
        for key, entry in self._hash_table.items():
            if entry.expires_at <= now:
                to_remove.append(key)
                batch += 1
                if batch >= 10:  # cap per-call eviction work
                    break
        for key in to_remove:
            del self._hash_table[key]
        self._metrics.evictions += len(to_remove)

    def _evict_oldest(self) -> None:
        """Remove the oldest entry when max_entries is exceeded."""
        if not self._hash_table:
            return
        oldest_key = min(
            self._hash_table, key=lambda k: self._hash_table[k].first_seen
        )
        del self._hash_table[oldest_key]
        self._metrics.evictions += 1
        logger.debug(f"DedupEngine: evicted oldest entry (max_entries exceeded)")
