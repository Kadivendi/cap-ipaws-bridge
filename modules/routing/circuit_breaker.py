"""
Circuit Breaker for IPAWS-OPEN and Mesh Gateway Connections
Prevents cascading failures when downstream services are unavailable.
Implements the standard CLOSED → OPEN → HALF_OPEN state machine.
"""
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Failing — reject calls immediately
    HALF_OPEN = "HALF_OPEN"  # Testing recovery — allow one probe call


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5       # failures before opening
    success_threshold: int = 2       # consecutive successes to close from HALF_OPEN
    timeout_seconds: float = 30.0    # seconds before OPEN → HALF_OPEN probe
    name: str = "default"


class CircuitBreaker:
    """
    Thread-safe circuit breaker protecting calls to external services
    (IPAWS-OPEN API, mesh-gateway injection endpoint, NOAA/USGS feeds).

    Usage:
        cb = CircuitBreaker(CircuitBreakerConfig(name="ipaws-open"))
        result = cb.call(fetch_ipaws_alerts)
    """

    def __init__(self, config: CircuitBreakerConfig = CircuitBreakerConfig()):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = Lock()
        self._total_calls = 0
        self._rejected_calls = 0

    def call(self, fn, *args, **kwargs):
        with self._lock:
            self._total_calls += 1
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit [{self.config.name}] → HALF_OPEN (probing)")
                else:
                    self._rejected_calls += 1
                    raise RuntimeError(
                        f"Circuit [{self.config.name}] is OPEN — "
                        f"retry in {self._seconds_until_probe():.0f}s"
                    )

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                self._on_success()
            return result
        except Exception as exc:
            with self._lock:
                self._on_failure()
            raise

    def _on_success(self):
        self._failure_count = 0
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._success_count = 0
                logger.info(f"Circuit [{self.config.name}] → CLOSED (recovered)")

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._success_count = 0
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit [{self.config.name}] → OPEN after {self._failure_count} failures"
            )

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return time.monotonic() - self._last_failure_time >= self.config.timeout_seconds

    def _seconds_until_probe(self) -> float:
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self.config.timeout_seconds - elapsed)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def rejection_rate(self) -> float:
        if self._total_calls == 0:
            return 0.0
        return self._rejected_calls / self._total_calls

    @property
    def stats(self) -> dict:
        return {
            "name": self.config.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "total_calls": self._total_calls,
            "rejected_calls": self._rejected_calls,
            "rejection_rate": round(self.rejection_rate, 3),
        }
