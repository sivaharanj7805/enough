"""Rate limiter with exponential backoff.

Provides a simple async rate limiter that enforces a maximum number of
requests per second with automatic backoff on rate limit errors.
"""

import asyncio
import logging
import time
from typing import Callable, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class RateLimiter:
    """Async rate limiter with token bucket algorithm."""

    def __init__(
        self,
        requests_per_second: float = 1.0,
        max_retries: int = 5,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.min_interval = 1.0 / requests_per_second
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Wait until a request is allowed under the rate limit."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self.min_interval:
                delay = self.min_interval - elapsed
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()

    async def execute_with_retry(
        self,
        func: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute a function with rate limiting and exponential backoff.

        Retries on common rate limit and transient errors.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            await self.wait()

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check for rate limit indicators
                is_rate_limit = any(
                    indicator in error_str
                    for indicator in ["rate limit", "429", "quota", "too many requests"]
                )

                # Check for transient errors
                is_transient = any(
                    indicator in error_str
                    for indicator in ["500", "502", "503", "504", "timeout", "connection"]
                )

                if not (is_rate_limit or is_transient):
                    raise  # Non-retryable error

                backoff = min(
                    self.base_backoff * (2 ** attempt),
                    self.max_backoff,
                )
                logger.warning(
                    "Retryable error (attempt %d/%d), backing off %.1fs: %s",
                    attempt + 1, self.max_retries, backoff, e,
                )
                await asyncio.sleep(backoff)

        raise last_error or RuntimeError("Max retries exceeded")
