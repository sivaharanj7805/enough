"""Tests for the rate limiter utility."""

import asyncio
import time
import pytest
from app.utils.rate_limiter import RateLimiter


@pytest.mark.asyncio
class TestRateLimiter:
    """Test the async rate limiter."""

    async def test_basic_wait(self):
        """Wait should enforce minimum interval."""
        limiter = RateLimiter(requests_per_second=100)  # Fast for testing
        start = time.monotonic()
        await limiter.wait()
        await limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.01  # At least one interval

    async def test_no_delay_first_call(self):
        """First call should not wait significantly."""
        limiter = RateLimiter(requests_per_second=1)
        start = time.monotonic()
        await limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 1.0

    async def test_execute_with_retry_success(self):
        """Successful function should return on first try."""
        limiter = RateLimiter(requests_per_second=100)

        async def good_func():
            return 42

        result = await limiter.execute_with_retry(good_func)
        assert result == 42

    async def test_execute_with_retry_transient(self):
        """Transient errors should trigger retries."""
        limiter = RateLimiter(requests_per_second=100, base_backoff=0.01, max_retries=3)
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("500 internal server error")
            return "ok"

        result = await limiter.execute_with_retry(flaky)
        assert result == "ok"
        assert call_count == 2

    async def test_execute_with_retry_non_retryable(self):
        """Non-retryable errors should raise immediately."""
        limiter = RateLimiter(requests_per_second=100, max_retries=3)

        async def bad_input():
            raise ValueError("invalid argument")

        with pytest.raises(ValueError):
            await limiter.execute_with_retry(bad_input)
