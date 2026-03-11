"""Tests for the background task retry logic."""

import asyncio
import pytest
from app.utils.task_retry import with_retry, retry_async


@pytest.mark.asyncio
class TestWithRetry:
    """Test the @with_retry decorator."""

    async def test_success_first_attempt(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def good_task():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await good_task()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_transient_failure(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def flaky_task():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await flaky_task()
        assert result == "recovered"
        assert call_count == 3

    async def test_raises_after_max_retries(self):
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError):
            await always_fails()
        assert call_count == 3  # initial + 2 retries

    async def test_no_retry_on_valueerror(self):
        """ValueError is non-retryable by default."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def bad_input():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await bad_input()
        assert call_count == 1  # No retry

    async def test_no_retry_on_typeerror(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def type_err():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await type_err()
        assert call_count == 1

    async def test_custom_retryable_exceptions(self):
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def custom_retry():
            nonlocal call_count
            call_count += 1
            raise ValueError("retry me")

        with pytest.raises(ValueError):
            await custom_retry()
        assert call_count == 3  # Now retried because explicitly allowed


@pytest.mark.asyncio
class TestRetryAsync:
    """Test the retry_async helper."""

    async def test_inline_retry(self):
        call_count = 0

        async def flaky(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("oops")
            return x * 2

        result = await retry_async(flaky, args=(5,), max_retries=3, base_delay=0.01)
        assert result == 10
        assert call_count == 2
