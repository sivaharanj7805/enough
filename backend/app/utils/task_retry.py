"""Background task retry logic with exponential backoff.

Provides a decorator and a helper to wrap any async function with retry
semantics, suitable for FastAPI BackgroundTasks or standalone coroutines.

Usage:
    @with_retry(max_retries=3, base_delay=2.0)
    async def my_background_task(site_id: UUID):
        ...

    # Or inline:
    await retry_async(my_func, args=(site_id,), max_retries=3)
"""

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exceptions that are never retried
NON_RETRYABLE = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NotImplementedError,
)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
):
    """Decorator: wrap an async function with exponential-backoff retry logic.

    Args:
        max_retries: Maximum number of retry attempts (total calls = max_retries + 1).
        base_delay: Base delay in seconds (doubles each attempt).
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: If set, only retry on these specific exception types.
            By default, retries all exceptions except NON_RETRYABLE.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Check if retryable
                    if retryable_exceptions:
                        if not isinstance(e, retryable_exceptions):
                            raise
                    elif isinstance(e, NON_RETRYABLE):
                        raise

                    if attempt >= max_retries:
                        logger.error(
                            "Task %s failed after %d attempts: %s",
                            func.__name__, max_retries + 1, e,
                        )
                        raise

                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        "Task %s attempt %d/%d failed (%s), retrying in %.1fs",
                        func.__name__, attempt + 1, max_retries + 1, e, delay,
                    )
                    await asyncio.sleep(delay)

            raise last_error or RuntimeError("Unreachable")

        return wrapper

    return decorator


async def retry_async(
    func: Callable[..., Any],
    args: tuple = (),
    kwargs: dict | None = None,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
) -> Any:
    """Run an async function with retry logic (non-decorator form).

    Example:
        result = await retry_async(do_work, args=(site_id,), max_retries=3)
    """
    kwargs = kwargs or {}
    wrapped = with_retry(max_retries=max_retries, base_delay=base_delay, max_delay=max_delay)(func)
    return await wrapped(*args, **kwargs)
