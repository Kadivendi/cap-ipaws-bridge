"""
Alert Cache Layer with LRU Eviction and Geographic Indexing

Provides fast in-memory access to recently-ingested CAP alerts with:
  - LRU eviction keeping the working set bounded
  - Bounding-box based geographic index for spatial queries
  - Cache statistics for operational dashboards

This layer sits between the IPAWS poller and the routing engine, reducing
repeated XML parsing and database lookups for alerts that are actively
being routed to multiple subscribers.
"""
import logging
import sys
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 10_000
BYTES_PER_CHAR_ESTIMATE = 2  # rough estimate for sys.getsizeof fallback


@dataclass
class CachedAlert:
    """An alert stored in the cache with metadata for indexing."""
    alert_id: str
    sender: str
    severity: str
    cap_xml: str
    min_lat: float = 0.0
    min_lon: float = 0.0
    max_lat: float = 0.0
    max_lon: float = 0.0
    cached_at: float = field(default_factory=time.monotonic)
    access_count: int = 0

    @property
    def has_geo(self) -> bool:
        return not (
            self.min_lat == 0.0 and self.max_lat == 0.0
            and self.min_lon == 0.0 and self.max_lon == 0.0
        )

    @property
    def estimated_bytes(self) -> int:
        return (
            sys.getsizeof(self.alert_id)
            + sys.getsizeof(self.cap_xml)
            + sys.getsizeof(self.sender)
            + 64  # overhead for floats/ints
        )


@dataclass
class CacheStats:
    """Operational statistics for cache monitoring."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    insertions: int = 0
    geo_queries: int = 0
    geo_results: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def total_lookups(self) -> int:
        return self.hits + self.misses

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "evictions": self.evictions,
            "insertions": self.insertions,
            "geo_queries": self.geo_queries,
            "geo_results": self.geo_results,
        }


class AlertCache:
    """
    LRU cache for CAP alerts with geographic bounding-box index.

    Thread-safe for concurrent reads/writes from poll workers and
    the routing engine.

    Usage:
        cache = AlertCache(max_entries=5000)
        cache.put(CachedAlert(alert_id="urn:oid:...", ...))
        alert = cache.get("urn:oid:...")
        nearby = cache.query_geo(min_lat=33.0, min_lon=-119.0,
                                 max_lat=35.0, max_lon=-117.0)
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._max_entries = max_entries
        self._store: OrderedDict[str, CachedAlert] = OrderedDict()
        self._stats = CacheStats()
        self._lock = threading.Lock()
        logger.info(f"AlertCache initialized: max_entries={max_entries}")

    def get(self, alert_id: str) -> Optional[CachedAlert]:
        """Retrieve an alert by ID, promoting it in the LRU order."""
        with self._lock:
            alert = self._store.get(alert_id)
            if alert is None:
                self._stats.misses += 1
                return None
            # Move to end (most recently used)
            self._store.move_to_end(alert_id)
            alert.access_count += 1
            self._stats.hits += 1
            return alert

    def put(self, alert: CachedAlert) -> None:
        """Insert or update an alert in the cache."""
        with self._lock:
            if alert.alert_id in self._store:
                # Update existing — move to end
                self._store.move_to_end(alert.alert_id)
                self._store[alert.alert_id] = alert
            else:
                self._store[alert.alert_id] = alert
                self._stats.insertions += 1
                # Evict LRU entries if over capacity
                while len(self._store) > self._max_entries:
                    evicted_id, _ = self._store.popitem(last=False)
                    self._stats.evictions += 1
                    logger.debug(f"Cache evicted LRU alert: {evicted_id}")

    def remove(self, alert_id: str) -> bool:
        """Remove an alert from the cache. Returns True if found."""
        with self._lock:
            return self._store.pop(alert_id, None) is not None

    def contains(self, alert_id: str) -> bool:
        """Check presence without affecting LRU order."""
        return alert_id in self._store

    def query_geo(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
    ) -> list[CachedAlert]:
        """
        Find cached alerts whose bounding box intersects the query region.

        Uses simple AABB (axis-aligned bounding box) intersection test.
        Efficient enough for the expected cache sizes (< 10k entries).
        """
        results = []
        with self._lock:
            self._stats.geo_queries += 1
            for alert in self._store.values():
                if not alert.has_geo:
                    continue
                # AABB intersection: two boxes overlap iff they overlap
                # on both the lat and lon axes independently
                if (
                    alert.min_lat <= max_lat
                    and alert.max_lat >= min_lat
                    and alert.min_lon <= max_lon
                    and alert.max_lon >= min_lon
                ):
                    results.append(alert)
            self._stats.geo_results += len(results)
        return results

    def get_all_ids(self) -> list[str]:
        """Return all cached alert IDs in LRU order (oldest first)."""
        with self._lock:
            return list(self._store.keys())

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def stats(self) -> CacheStats:
        return self._stats

    @property
    def memory_estimate_bytes(self) -> int:
        """Rough estimate of total memory used by cached alerts."""
        with self._lock:
            return sum(alert.estimated_bytes for alert in self._store.values())

    def clear(self) -> None:
        """Flush all cached entries."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
        logger.info(f"AlertCache cleared: {count} entries removed")
