"""Error handling utilities for service functions."""

import functools
import logging

logger = logging.getLogger(__name__)


def safe_async(default_return=None):
    """Decorator that wraps async functions with try/except.
    
    On exception, logs the error and returns default_return.
    Use for non-critical services where a failure shouldn't crash the pipeline.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "%s.%s failed: %s",
                    func.__module__, func.__qualname__, e,
                    exc_info=True,
                )
                return default_return
        return wrapper
    return decorator
