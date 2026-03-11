#!/usr/bin/env python3
"""Database migration runner with applied-migration tracking.

Scans backend/migrations/*.sql, applies them in order, and records each
in a `schema_migrations` table so they only run once.

Usage:
    python migrate.py              # Apply pending migrations
    python migrate.py --status     # Show migration status
    python migrate.py --rollback N # (future placeholder)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

TRACKING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version  TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def get_dsn() -> str:
    """Resolve DATABASE_URL from env or .env file."""
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DATABASE_URL not set — provide via env or .env file")


async def ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(TRACKING_TABLE_DDL)


async def applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return {r["version"] for r in rows}


def discover_migrations() -> list[tuple[str, Path]]:
    """Return sorted list of (version, path) tuples."""
    if not MIGRATIONS_DIR.is_dir():
        logger.warning("No migrations directory at %s", MIGRATIONS_DIR)
        return []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(f.stem, f) for f in files]


async def apply_migration(conn: asyncpg.Connection, version: str, path: Path) -> None:
    sql = path.read_text()
    logger.info("Applying migration %s ...", version)
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version) VALUES ($1)", version
        )
    logger.info("  ✓ %s applied", version)


async def run_migrations() -> None:
    dsn = await get_dsn()
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await ensure_tracking_table(conn)
        applied = await applied_versions(conn)
        migrations = discover_migrations()
        pending = [(v, p) for v, p in migrations if v not in applied]

        if not pending:
            logger.info("All migrations are up to date (%d applied)", len(applied))
            return

        logger.info("%d pending migration(s) to apply", len(pending))
        for version, path in pending:
            await apply_migration(conn, version, path)

        logger.info("All migrations applied successfully")
    finally:
        await conn.close()


async def show_status() -> None:
    dsn = await get_dsn()
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await ensure_tracking_table(conn)
        applied = await applied_versions(conn)
        migrations = discover_migrations()

        print(f"\n{'Version':<40} {'Status':<12}")
        print("-" * 52)
        for version, _ in migrations:
            status = "✓ applied" if version in applied else "⏳ pending"
            print(f"{version:<40} {status}")
        print()
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Enough DB migration runner")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    if args.status:
        asyncio.run(show_status())
    else:
        asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
