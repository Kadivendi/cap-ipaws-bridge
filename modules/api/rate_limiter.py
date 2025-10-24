"""Adaptive rate limiter for IPAWS polling and webhook dispatch.

Uses token bucket algorithm with per-endpoint rate limits. Adapts
automatically based on upstream response codes: increases interval
on 429 (Too Many Requests) and decreases on success.
"""
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a single rate limit bucket."""
    tokens_per_second: float
    burst_capacity: int
    backoff_multiplier: float = 2.0
    min_interval_seconds: float = 0.1
    max_interval_seconds: float = 60.0


DEFAULT_LIMITS: Dict[str, RateLimitConfig] = {
    "ipaws_poll": RateLimitConfig(tokens_per_second=0.5, burst_capacity=3),
    "webhook_dispatch": RateLimitConfig(tokens_per_second=10.0, burst_capacity=50),
    "cap_validate": RateLimitConfig(tokens_per_second=100.0, burst_capacity=200),
    "feed_ingest": RateLimitConfig(tokens_per_second=2.0, burst_capacity=10),
}


class TokenBucket:
    """Thread-safe token bucket rate limiter with adaptive backoff."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._tokens = float(config.burst_capacity)
        self._last_refill = time.time()
        self._current_rate = config.tokens_per_second
        self._lock = Lock()
        self._total_allowed = 0
        self._total_rejected = 0

    def try_acquire(self) -> bool:
        """Attempt to acquire a token. Returns True if allowed."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._total_allowed += 1
                return True
            self._total_rejected += 1
            return False

    def on_success(self) -> None:
        """Notify the limiter of a successful request (restore rate)."""
        with self._lock:
            self._current_rate = min(
                self._current_rate * 1.1,
                self.config.tokens_per_second,
            )

    def on_rate_limited(self) -> None:
        """Notify the limiter of a 429 response (reduce rate)."""
        with self._lock:
            self._current_rate = max(
                self._current_rate / self.config.backoff_multiplier,
                1.0 / self.config.max_interval_seconds,
            )
            logger.warning(
                "Rate limit backoff: new rate=%.2f/s",
                self._current_rate,
            )

    @property
    def stats(self) -> Dict:
        return {
            "current_rate": round(self._current_rate, 3),
            "configured_rate": self.config.tokens_per_second,
            "available_tokens": round(self._tokens, 1),
            "burst_capacity": self.config.burst_capacity,
            "total_allowed": self._total_allowed,
            "total_rejected": self._total_rejected,
        }

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self.config.burst_capacity),
            self._tokens + elapsed * self._current_rate,
        )
        self._last_refill = now


class AdaptiveRateLimiter:
    """Manages rate limiters for multiple endpoints."""

    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        for name, config in DEFAULT_LIMITS.items():
            self._buckets[name] = TokenBucket(config)
        logger.info("AdaptiveRateLimiter initialized with %d endpoints", len(self._buckets))

    def try_acquire(self, endpoint: str) -> bool:
        """Attempt to acquire a rate limit token for an endpoint."""
        bucket = self._buckets.get(endpoint)
        if bucket is None:
            logger.warning("No rate limit configured for endpoint: %s", endpoint)
            return True
        return bucket.try_acquire()

    def notify_success(self, endpoint: str) -> None:
        bucket = self._buckets.get(endpoint)
        if bucket:
            bucket.on_success()

    def notify_rate_limited(self, endpoint: str) -> None:
        bucket = self._buckets.get(endpoint)
        if bucket:
            bucket.on_rate_limited()

    def get_all_stats(self) -> Dict[str, Dict]:
        return {name: bucket.stats for name, bucket in self._buckets.items()}


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

_PUBLIC_PATH_PREFIXES = (
    "/api/v1/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-request rate limiter applied to all non-public paths.

    Looks up the route by its first path segment after ``/api/`` and falls back
    to a generic ``http_request`` bucket. Returns HTTP 429 with a Retry-After
    hint when the bucket is empty.
    """

    GENERIC_LIMIT = RateLimitConfig(tokens_per_second=50.0, burst_capacity=100)

    def __init__(self, app):
        super().__init__(app)
        self._limiters = AdaptiveRateLimiter()
        # Register a generic bucket the lookup falls back to.
        self._limiters._buckets["http_request"] = TokenBucket(self.GENERIC_LIMIT)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        endpoint = self._classify(path)
        if not self._limiters.try_acquire(endpoint):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "1"},
                content={"detail": f"Rate limit exceeded for {endpoint}"},
            )

        response = await call_next(request)
        if response.status_code == 429:
            self._limiters.notify_rate_limited(endpoint)
        elif 200 <= response.status_code < 400:
            self._limiters.notify_success(endpoint)
        return response

    @staticmethod
    def _classify(path: str) -> str:
        if path.startswith("/api/v1/compose"):
            return "cap_validate"
        if path.startswith("/api/mesh/broadcast"):
            return "feed_ingest"
        if path.startswith("/webhooks"):
            return "webhook_dispatch"
        return "http_request"
