"""Database connection management for Supabase/PostgreSQL."""

import logging
import socket
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import asyncpg
from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: asyncpg.Pool | None = None


def _resolve_dsn_ipv4(dsn: str) -> str:
    """Resolve DSN hostname to IPv4 to work around IPv6-only environments (e.g. Railway)."""
    parsed = urlparse(dsn)
    if not parsed.hostname:
        return dsn
    try:
        ipv4 = socket.getaddrinfo(parsed.hostname, None, socket.AF_INET)[0][4][0]
        resolved = parsed._replace(netloc=parsed.netloc.replace(parsed.hostname, ipv4))
        logger.info("Resolved %s -> %s (IPv4)", parsed.hostname, ipv4)
        return urlunparse(resolved)
    except (socket.gaierror, IndexError):
        logger.warning("IPv4 resolution failed for %s, using original", parsed.hostname)
        return dsn


async def get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        ssl_mode = "require" if settings.database_url and "supabase" in settings.database_url else None
        dsn = _resolve_dsn_ipv4(settings.database_url)
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=60,
            ssl=ssl_mode,
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
