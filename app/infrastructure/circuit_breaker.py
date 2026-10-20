"""
circuit_breaker.py
==================
Async circuit breaker for Milvus and Redis.

States:
  CLOSED    — normal, requests go through
  OPEN      — too many failures, requests fail immediately (no call made)
  HALF_OPEN — after recovery_timeout, one probe is allowed through

Usage:
    async with milvus_breaker:
        result = await milvus_operation()

    # or functional style:
    result = await milvus_breaker.call(my_async_fn, arg1, arg2)
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit is OPEN and the call is rejected immediately."""
    def __init__(self, name: str, retry_in: float):
        super().__init__(
            f"Service '{name}' is temporarily unavailable (circuit OPEN). "
            f"Retry in {retry_in:.0f}s."
        )
        self.retry_in = retry_in


class CircuitBreaker:
    """
    Args:
        name:              shown in logs and error messages
        failure_threshold: consecutive failures before opening
        recovery_timeout:  seconds to wait in OPEN before probing again
        expected_exc:      exception types that count as failures
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exc: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.expected_exc      = expected_exc

        self._state         = CircuitState.CLOSED
        self._failures      = 0
        self._opened_at     = 0.0
        self._lock          = asyncio.Lock()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    # ── Context manager ───────────────────────────────────────────────────

    async def __aenter__(self) -> "CircuitBreaker":
        await self._check_state()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type and issubclass(exc_type, self.expected_exc):
            await self._record_failure()
            return False
        await self._record_success()
        return False

    # ── Functional wrapper ────────────────────────────────────────────────

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Wrap any async callable with circuit breaker protection."""
        async with self:
            return await fn(*args, **kwargs)

    # ── State machine ─────────────────────────────────────────────────────

    async def _check_state(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed   = time.monotonic() - self._opened_at
                remaining = self.recovery_timeout - elapsed
                if remaining > 0:
                    raise CircuitBreakerOpen(self.name, remaining)
                # Timeout expired — allow one probe
                self._state = CircuitState.HALF_OPEN
                logger.info("[CB:%s] OPEN → HALF_OPEN (probing service)", self.name)

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info("[CB:%s] Probe succeeded → CLOSED", self.name)
            self._failures = 0
            self._state    = CircuitState.CLOSED

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            logger.warning("[CB:%s] Failure %d/%d", self.name, self._failures, self.failure_threshold)
            if self._failures >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
                self._state     = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.error(
                    "[CB:%s] → OPEN after %d failures. Retry in %.0fs.",
                    self.name, self._failures, self.recovery_timeout,
                )


# ── Singletons — import these everywhere ─────────────────────────────────────

milvus_breaker = CircuitBreaker(
    name="milvus",
    failure_threshold=5,
    recovery_timeout=30.0,
)

redis_breaker = CircuitBreaker(
    name="redis",
    failure_threshold=3,
    recovery_timeout=15.0,
)
