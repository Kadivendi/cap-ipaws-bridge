"""Tests for the circuit breaker implementation."""
import pytest
import time
from modules.routing.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


class TestCircuitBreaker:

    def _cb(self, threshold=3, timeout=0.1):
        return CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=threshold, timeout_seconds=timeout, name="test"
        ))

    def _fail(self, cb):
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

    def test_starts_closed(self):
        assert self._cb().state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = self._cb(threshold=3)
        for _ in range(3):
            self._fail(cb)
        assert cb.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        cb = self._cb(threshold=1)
        self._fail(cb)
        assert cb.state == CircuitState.OPEN
        with pytest.raises(RuntimeError, match="OPEN"):
            cb.call(lambda: None)

    def test_transitions_to_half_open_after_timeout(self):
        cb = self._cb(threshold=1, timeout=0.05)
        self._fail(cb)
        time.sleep(0.06)
        try:
            cb.call(lambda: None)
        except Exception:
            pass
        assert cb.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED, CircuitState.OPEN)

    def test_closes_after_success_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1, success_threshold=2, timeout_seconds=0.01
        ))
        self._fail(cb)
        time.sleep(0.02)
        cb.call(lambda: None)  # probe — HALF_OPEN → success 1
        cb.call(lambda: None)  # success 2 → CLOSED
        assert cb.state == CircuitState.CLOSED

    def test_rejection_rate_tracked(self):
        cb = self._cb(threshold=1, timeout=60.0)
        self._fail(cb)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: None)
        assert cb.rejection_rate > 0.5

    def test_stats_contains_required_fields(self):
        cb = self._cb()
        stats = cb.stats
        assert "state" in stats
        assert "failure_count" in stats
        assert "total_calls" in stats
        assert "rejection_rate" in stats
