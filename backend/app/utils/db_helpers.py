"""Database utility helpers — transaction wrapper, retry, etc."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

logger = logging.getLogger(__name__)


@asynccontextmanager
async def transaction(conn: asyncpg.Connection) -> AsyncGenerator[asyncpg.Connection, None]:
    """Wrap a block of DB operations in a transaction.
    
    Usage:
        async with transaction(conn) as tx:
            await tx.execute("INSERT ...")
            await tx.execute("UPDATE ...")
        # auto-commits on success, auto-rolls-back on exception
    """
    tr = conn.transaction()
    await tr.start()
    try:
        yield conn
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise
