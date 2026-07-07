"""Async token bucket rate limiter."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable


Clock = Callable[[], float]


@dataclass(slots=True)
class TokenBucket:
    """Token bucket limiter that waits for capacity instead of dropping calls."""

    rate: float
    burst: int
    _clock: Clock = time.monotonic
    _tokens: float = field(init=False)
    _updated_at: float = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("rate must be greater than 0")
        if self.burst <= 0:
            raise ValueError("burst must be greater than 0")

        self._tokens = float(self.burst)
        self._updated_at = self._clock()

    async def acquire(self, tokens: int = 1) -> float:
        """Wait until tokens are available and return the elapsed wait time."""

        if tokens <= 0:
            raise ValueError("tokens must be greater than 0")
        if tokens > self.burst:
            raise ValueError("tokens cannot exceed burst capacity")

        started_at = self._clock()

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return self._clock() - started_at

                missing = tokens - self._tokens
                wait_seconds = missing / self.rate

            await asyncio.sleep(wait_seconds)

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated_at)
        self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate)
        self._updated_at = now
