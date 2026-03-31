"""Postgres-backed job queue for crawl and pipeline tasks.

Replaces FastAPI BackgroundTasks which die silently on process restart.
Workers claim jobs with SELECT FOR UPDATE SKIP LOCKED — safe for
concurrent workers and survives deploys/crashes/OOM.

Usage:
    # Enqueue a job (from a route handler):
    await enqueue_job(db, "full_pipeline", site_id, {"url_patterns": ["/blog/"]})

    # Start the worker (from FastAPI lifespan):
    asyncio.create_task(run_worker(pool))
"""

import asyncio
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def enqueue_job(
    db: asyncpg.Connection,
    job_type: str,
    site_id: UUID,
    payload: dict | None = None,
) -> UUID:
    """Add a job to the queue. Returns the job ID."""
    row = await db.fetchrow(
        """
        INSERT INTO job_queue (job_type, site_id, payload)
        VALUES ($1, $2, $3::jsonb)
        RETURNING id
        """,
        job_type,
        site_id,
        __import__("json").dumps(payload or {}),
    )
    logger.info("Enqueued %s job for site %s: %s", job_type, site_id, row["id"])
    return row["id"]


async def claim_job(db: asyncpg.Connection) -> dict | None:
    """Claim the oldest pending job. Returns None if queue is empty.

    Uses SELECT FOR UPDATE SKIP LOCKED so multiple workers don't
    grab the same job.
    """
    row = await db.fetchrow(
        """
        UPDATE job_queue
        SET status = 'running', claimed_at = NOW()
        WHERE id = (
            SELECT id FROM job_queue
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, job_type, site_id, payload
        """,
    )
    return dict(row) if row else None


async def complete_job(db: asyncpg.Connection, job_id: UUID, error: str | None = None) -> None:
    """Mark a job as completed or failed."""
    status = "failed" if error else "completed"
    await db.execute(
        """
        UPDATE job_queue
        SET status = $1, completed_at = NOW(), error = $2
        WHERE id = $3
        """,
        status,
        error[:500] if error else None,
        job_id,
    )


async def recover_stale_jobs(db: asyncpg.Connection, stale_minutes: int = 30) -> int:
    """Reset jobs stuck in 'running' for too long back to 'failed'.

    Called on worker startup to recover from previous crashes.
    """
    result = await db.execute(
        """
        UPDATE job_queue
        SET status = 'failed', error = 'Worker died (stale job recovery)'
        WHERE status = 'running'
          AND claimed_at < NOW() - INTERVAL '1 minute' * $1
        """,
        stale_minutes,
    )
    count = int(result.split()[-1]) if result else 0
    if count > 0:
        logger.warning("Recovered %d stale jobs", count)
    return count


async def run_worker(pool: asyncpg.Pool, poll_interval: float = 5.0) -> None:
    """Long-running worker loop that processes jobs from the queue.

    Start as an asyncio task in FastAPI lifespan:
        asyncio.create_task(run_worker(pool))
    """
    logger.info("Job queue worker started (poll every %.1fs)", poll_interval)

    # Recover any jobs left running from a previous crash
    async with pool.acquire() as db:
        await recover_stale_jobs(db)

    while True:
        try:
            async with pool.acquire() as db:
                job = await claim_job(db)

            if not job:
                await asyncio.sleep(poll_interval)
                continue

            job_id = job["id"]
            job_type = job["job_type"]
            site_id = job["site_id"]
            payload = job["payload"] or {}

            logger.info("Processing job %s: %s for site %s", job_id, job_type, site_id)

            try:
                await _execute_job(pool, job_type, site_id, payload)
                async with pool.acquire() as db:
                    await complete_job(db, job_id)
                logger.info("Job %s completed", job_id)
            except Exception as e:
                logger.error("Job %s failed: %s", job_id, e)
                logger.exception("Stack trace for job %s", job_id)
                async with pool.acquire() as db:
                    await complete_job(db, job_id, error=str(e))

        except asyncio.CancelledError:
            logger.info("Job queue worker shutting down")
            break
        except Exception as e:
            logger.error("Job queue worker error: %s", e)
            await asyncio.sleep(poll_interval)


async def _execute_job(pool: asyncpg.Pool, job_type: str, site_id: UUID, payload: dict) -> None:
    """Dispatch a job to the appropriate handler."""
    # Fetch site data
    async with pool.acquire() as db:
        site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
    if not site:
        raise ValueError(f"Site {site_id} not found")

    site_dict = dict(site)
    if payload.get("url_patterns"):
        site_dict["url_patterns"] = payload["url_patterns"]

    # Import handlers lazily to avoid circular imports
    from app.routers.ingestion import (
        _run_crawl,
        _run_full_pipeline,
        _run_incremental_pipeline,
    )

    if job_type == "crawl":
        await _run_crawl(site_id, site_dict)
    elif job_type == "full_pipeline":
        await _run_full_pipeline(site_id, site_dict)
    elif job_type == "incremental_pipeline":
        await _run_incremental_pipeline(site_id, site_dict)
    elif job_type == "analytics_sync":
        from app.routers.ingestion import _run_analytics_sync
        await _run_analytics_sync(site_id, site_dict)
    elif job_type == "embeddings":
        from app.routers.ingestion import _run_embeddings
        await _run_embeddings(site_id)
    else:
        raise ValueError(f"Unknown job type: {job_type}")
