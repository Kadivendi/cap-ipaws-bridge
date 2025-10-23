"""Webhook delivery retry engine with dead-letter queue.

Handles transient delivery failures with exponential backoff and jitter.
Permanently failed deliveries are moved to a dead-letter queue for
manual investigation and replay.
"""
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeliveryAttempt:
    """Record of a single delivery attempt."""
    attempt_number: int
    timestamp: float
    success: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class RetryableDelivery:
    """A delivery that can be retried on failure."""
    delivery_id: str
    destination_url: str
    payload: Dict[str, Any]
    max_retries: int = 3
    attempts: List[DeliveryAttempt] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    is_completed: bool = False
    is_dead_lettered: bool = False

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def has_retries_remaining(self) -> bool:
        return self.attempt_count < self.max_retries and not self.is_completed

    def get_backoff_seconds(self) -> float:
        """Exponential backoff with jitter: 2^attempt * (0.5-1.5)."""
        base = 2 ** self.attempt_count
        jitter = random.uniform(0.5, 1.5)
        return min(base * jitter, 60.0)  # cap at 60s


class RetryEngine:
    """Manages webhook delivery retries with dead-letter queue.

    Features:
    - Exponential backoff with jitter (2^n * random(0.5, 1.5))
    - Configurable max retries (default 3)
    - Dead-letter queue for permanently failed deliveries
    - Delivery statistics and failure rate monitoring
    """

    def __init__(self, max_retries: int = 3):
        self._max_retries = max_retries
        self._pending: Dict[str, RetryableDelivery] = {}
        self._dead_letter: List[RetryableDelivery] = []
        self._total_delivered = 0
        self._total_failed = 0
        logger.info("RetryEngine initialized: max_retries=%d", max_retries)

    def submit(self, delivery_id: str, destination_url: str,
               payload: Dict[str, Any]) -> RetryableDelivery:
        """Submit a new delivery for processing."""
        delivery = RetryableDelivery(
            delivery_id=delivery_id,
            destination_url=destination_url,
            payload=payload,
            max_retries=self._max_retries,
        )
        self._pending[delivery_id] = delivery
        return delivery

    def record_success(self, delivery_id: str, status_code: int,
                       latency_ms: float) -> None:
        """Record a successful delivery."""
        delivery = self._pending.get(delivery_id)
        if not delivery:
            return
        delivery.attempts.append(DeliveryAttempt(
            attempt_number=delivery.attempt_count + 1,
            timestamp=time.time(),
            success=True,
            status_code=status_code,
            latency_ms=latency_ms,
        ))
        delivery.is_completed = True
        self._total_delivered += 1
        del self._pending[delivery_id]
        logger.info("Delivery succeeded: id=%s attempts=%d",
                    delivery_id, delivery.attempt_count)

    def record_failure(self, delivery_id: str, status_code: Optional[int],
                       error_message: str) -> Optional[float]:
        """Record a failed delivery. Returns backoff time or None if dead-lettered."""
        delivery = self._pending.get(delivery_id)
        if not delivery:
            return None

        delivery.attempts.append(DeliveryAttempt(
            attempt_number=delivery.attempt_count + 1,
            timestamp=time.time(),
            success=False,
            status_code=status_code,
            error_message=error_message,
        ))

        if delivery.has_retries_remaining:
            backoff = delivery.get_backoff_seconds()
            logger.warning("Delivery failed: id=%s attempt=%d/%d backoff=%.1fs error=%s",
                          delivery_id, delivery.attempt_count, delivery.max_retries,
                          backoff, error_message)
            return backoff
        else:
            delivery.is_dead_lettered = True
            self._dead_letter.append(delivery)
            self._total_failed += 1
            del self._pending[delivery_id]
            logger.error("Delivery dead-lettered: id=%s after %d attempts",
                        delivery_id, delivery.attempt_count)
            return None

    def get_dead_letter_queue(self, limit: int = 50) -> List[Dict]:
        """Return dead-lettered deliveries for manual review."""
        return [
            {
                "delivery_id": d.delivery_id,
                "destination": d.destination_url,
                "attempts": d.attempt_count,
                "last_error": d.attempts[-1].error_message if d.attempts else None,
                "created_at": d.created_at,
            }
            for d in self._dead_letter[-limit:]
        ]

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "pending": len(self._pending),
            "dead_lettered": len(self._dead_letter),
            "total_delivered": self._total_delivered,
            "total_failed": self._total_failed,
            "failure_rate": (
                self._total_failed / (self._total_delivered + self._total_failed)
                if (self._total_delivered + self._total_failed) > 0 else 0.0
            ),
        }
