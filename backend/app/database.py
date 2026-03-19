"""Database connection management for Supabase/PostgreSQL."""

import logging
from typing import AsyncGenerator

import asyncpg
from supabase import create_client, Client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=60,
        )
        logger.info("Database connection pool created")
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency that yields a database connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


def get_supabase_client() -> Client:
    """Create a Supabase client for auth operations."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


def get_supabase_admin() -> Client:
    """Create a Supabase admin client with service key."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
