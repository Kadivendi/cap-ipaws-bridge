"""
Adaptive Rate Limiter for IPAWS Polling and Webhook Dispatch

Token-bucket algorithm with adaptive backoff: the polling interval
automatically increases when upstream returns 429 (Too Many Requests)
and decreases on consecutive successes.  Thread-safe via atomic
compare-and-swap on the token counter.

Design decisions:
    - Per-endpoint rate limits allow different ceilings for IPAWS-OPEN
      (strict FEMA quotas) vs. outbound webhooks (self-managed).
    - Adaptive factor avoids hard-coding retry delays — the limiter
      learns the optimal polling cadence from upstream responses.
"""
import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Defaults tuned for IPAWS-OPEN: 30 requests/minute baseline
DEFAULT_TOKENS_PER_SECOND = 0.5
DEFAULT_BUCKET_SIZE = 10
BACKOFF_MULTIPLIER = 2.0
RECOVERY_DIVISOR = 1.5
MIN_INTERVAL_SECONDS = 0.1
MAX_INTERVAL_SECONDS = 300.0


@dataclass
class RateLimitConfig:
    """Configuration for a single endpoint rate limit."""
    endpoint_name: str
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    bucket_size: int = DEFAULT_BUCKET_SIZE
    adaptive: bool = True
    backoff_multiplier: float = BACKOFF_MULTIPLIER
    recovery_divisor: float = RECOVERY_DIVISOR


@dataclass
class RateLimitStats:
    """Per-endpoint rate-limit statistics."""
    endpoint_name: str = ""
    total_requests: int = 0
    total_allowed: int = 0
    total_throttled: int = 0
    total_backoffs: int = 0
    current_interval: float = 0.0
    bucket_tokens: float = 0.0

    @property
    def throttle_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_throttled / self.total_requests

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint_name,
            "total_requests": self.total_requests,
            "allowed": self.total_allowed,
            "throttled": self.total_throttled,
            "backoffs": self.total_backoffs,
            "throttle_rate": round(self.throttle_rate, 4),
            "current_interval_s": round(self.current_interval, 3),
        }


class _TokenBucket:
    """
    Lock-free-ish token bucket using a single lock for refill + consume.

    We accept a lock here rather than true CAS because Python's GIL
    makes atomic operations less critical, and correctness matters more
    than micro-performance for a polling rate limiter.
    """

    def __init__(self, rate: float, capacity: int):
        self._rate = rate           # tokens added per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def try_consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens. Returns True if allowed."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self) -> float:
        """Seconds until at least 1 token is available."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                return 0.0
            deficit = 1.0 - self._tokens
            return deficit / self._rate if self._rate > 0 else MAX_INTERVAL_SECONDS

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def set_rate(self, new_rate: float) -> None:
        with self._lock:
            self._refill()
            self._rate = max(new_rate, 1e-6)
            logger.debug(f"Token bucket rate adjusted to {self._rate:.4f} tok/s")

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


class AdaptiveRateLimiter:
    """
    Multi-endpoint adaptive rate limiter.

    Usage:
        limiter = AdaptiveRateLimiter()
        limiter.add_endpoint(RateLimitConfig("ipaws-open", tokens_per_second=0.5))

        if limiter.acquire("ipaws-open"):
            resp = poll_ipaws()
            if resp.status_code == 429:
                limiter.record_backoff("ipaws-open")
            else:
                limiter.record_success("ipaws-open")
    """

    def __init__(self):
        self._buckets: dict[str, _TokenBucket] = {}
        self._configs: dict[str, RateLimitConfig] = {}
        self._stats: dict[str, RateLimitStats] = {}
        self._consecutive_successes: dict[str, int] = {}
        self._lock = threading.Lock()

    def add_endpoint(self, config: RateLimitConfig) -> None:
        """Register a rate-limited endpoint."""
        with self._lock:
            self._configs[config.endpoint_name] = config
            self._buckets[config.endpoint_name] = _TokenBucket(
                rate=config.tokens_per_second,
                capacity=config.bucket_size,
            )
            self._stats[config.endpoint_name] = RateLimitStats(
                endpoint_name=config.endpoint_name,
                current_interval=1.0 / max(config.tokens_per_second, 1e-6),
            )
            self._consecutive_successes[config.endpoint_name] = 0
        logger.info(
            f"Rate limiter endpoint added: {config.endpoint_name} "
            f"({config.tokens_per_second} tok/s, bucket={config.bucket_size})"
        )

    def acquire(self, endpoint: str, tokens: int = 1) -> bool:
        """
        Try to acquire tokens for the named endpoint.
        Returns True if the request is allowed, False if throttled.
        """
        bucket = self._buckets.get(endpoint)
        if bucket is None:
            logger.warning(f"Rate limiter: unknown endpoint '{endpoint}', allowing")
            return True

        stats = self._stats[endpoint]
        stats.total_requests += 1

        if bucket.try_consume(tokens):
            stats.total_allowed += 1
            stats.bucket_tokens = bucket.available_tokens
            return True

        stats.total_throttled += 1
        logger.debug(f"Rate limited: {endpoint} (wait ~{bucket.wait_time():.1f}s)")
        return False

    def wait_time(self, endpoint: str) -> float:
        """Seconds until the endpoint has available capacity."""
        bucket = self._buckets.get(endpoint)
        return bucket.wait_time() if bucket else 0.0

    def record_backoff(self, endpoint: str) -> None:
        """
        Upstream returned 429 or equivalent — slow down.
        Divides the token rate by backoff_multiplier to reduce pressure.
        """
        config = self._configs.get(endpoint)
        bucket = self._buckets.get(endpoint)
        if config is None or bucket is None or not config.adaptive:
            return

        with self._lock:
            self._consecutive_successes[endpoint] = 0
            new_rate = max(
                config.tokens_per_second / (config.backoff_multiplier ** 3),
                1.0 / MAX_INTERVAL_SECONDS,
            )
            # Reduce current rate by backoff multiplier
            current_interval = self._stats[endpoint].current_interval
            new_interval = min(
                current_interval * config.backoff_multiplier,
                MAX_INTERVAL_SECONDS,
            )
            adjusted_rate = 1.0 / new_interval
            bucket.set_rate(adjusted_rate)
            self._stats[endpoint].current_interval = new_interval
            self._stats[endpoint].total_backoffs += 1

        logger.warning(
            f"Rate limiter backoff: {endpoint} → interval {new_interval:.1f}s"
        )

    def record_success(self, endpoint: str) -> None:
        """
        Upstream responded successfully — cautiously speed up if adaptive.
        After 5 consecutive successes, increase rate toward the baseline.
        """
        config = self._configs.get(endpoint)
        bucket = self._buckets.get(endpoint)
        if config is None or bucket is None or not config.adaptive:
            return

        with self._lock:
            self._consecutive_successes[endpoint] = (
                self._consecutive_successes.get(endpoint, 0) + 1
            )
            if self._consecutive_successes[endpoint] >= 5:
                baseline_interval = 1.0 / max(config.tokens_per_second, 1e-6)
                current_interval = self._stats[endpoint].current_interval
                new_interval = max(
                    current_interval / config.recovery_divisor,
                    baseline_interval,
                    MIN_INTERVAL_SECONDS,
                )
                bucket.set_rate(1.0 / new_interval)
                self._stats[endpoint].current_interval = new_interval
                self._consecutive_successes[endpoint] = 0
                logger.info(
                    f"Rate limiter recovery: {endpoint} → interval {new_interval:.1f}s"
                )

    def get_stats(self, endpoint: Optional[str] = None) -> dict:
        """Get rate limit statistics for one or all endpoints."""
        if endpoint:
            stats = self._stats.get(endpoint)
            return stats.to_dict() if stats else {}
        return {name: s.to_dict() for name, s in self._stats.items()}

    def remove_endpoint(self, endpoint: str) -> bool:
        """Deregister an endpoint."""
        with self._lock:
            removed = self._buckets.pop(endpoint, None) is not None
            self._configs.pop(endpoint, None)
            self._stats.pop(endpoint, None)
            self._consecutive_successes.pop(endpoint, None)
        return removed
