"""Content ingestion trigger endpoints."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db, get_pool
from app.dependencies import SubscriptionGuard, get_current_user_id, verify_cron_secret
from app.models.schemas import CrawlStatusResponse, TaskTriggerResponse
from app.services.embeddings import EmbeddingPipeline
from app.services.ga4 import GA4Connector
from app.services.gsc import GSCConnector
from app.services.normalizer import save_normalized_posts
from app.services.sitemap import SitemapCrawler
from app.services.wordpress import WordPressConnector
from app.utils.encryption import decrypt_value

_limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _update_crawl_progress(site_id: UUID, processed: int, total: int) -> None:
    """Update crawl progress in DB (called from crawler callback)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as db:
            await db.execute(
                """
                UPDATE crawl_jobs SET
                    posts_found = $1,
                    posts_processed = $2,
                    updated_at = NOW()
                WHERE site_id = $3
                """,
                total, processed, site_id,
            )
    except Exception as e:
        logger.debug("Progress update failed (best-effort): %s", e)


async def _run_crawl(site_id: UUID, site: dict) -> None:
    """Background task: crawl content from WordPress or sitemap."""
    pool = await get_pool()

    # Initialize crawl status in DB.
    # Preserve previous crawl's results (prev_completed_at, prev_posts_processed)
    # so they remain queryable during the new crawl. The current crawl counters
    # reset to 0, but the previous crawl's data isn't erased until this one succeeds.
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO crawl_jobs (site_id, status, started_at, updated_at)
            VALUES ($1, 'crawling', $2, $2)
            ON CONFLICT (site_id) DO UPDATE SET
                status = 'crawling',
                prev_completed_at = crawl_jobs.completed_at,
                prev_posts_processed = crawl_jobs.posts_processed,
                started_at = $2,
                completed_at = NULL,
                error = NULL,
                posts_found = 0,
                posts_processed = 0,
                updated_at = $2
            """,
            site_id, datetime.now(UTC),
        )

    try:
        cms_type = site["cms_type"]
        normalized_posts = []

        def on_progress(processed: int, total: int) -> None:
            """Non-blocking progress callback."""
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_update_crawl_progress(site_id, processed, total))
            except RuntimeError:
                pass

        if cms_type == "wordpress" and site.get("wordpress_url"):
            # Decrypt the app password
            app_password = decrypt_value(site["wordpress_app_password"]) if site.get("wordpress_app_password") else None
            connector = WordPressConnector(
                base_url=site["wordpress_url"],
                app_password=app_password,
                domain=site["domain"],
            )
            normalized_posts = await connector.fetch_all_posts()
        elif site.get("sitemap_url") or site.get("domain"):
            # Use sitemap URL if available, otherwise auto-discover from domain
            sitemap_url = site.get("sitemap_url") or f"https://{site['domain']}/sitemap.xml"
            crawler = SitemapCrawler(
                sitemap_url=sitemap_url,
                domain=site["domain"],
                concurrency=10,
                max_retries=3,
                timeout_seconds=30.0,
                on_progress=on_progress,
                url_patterns=site.get("url_patterns") or [],
            )
            normalized_posts = await crawler.crawl()
        else:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status = 'failed', error = $1, updated_at = NOW() WHERE site_id = $2",
                    "No WordPress URL, sitemap URL, or domain configured", site_id,
                )
            return

        async with pool.acquire() as db:
            await db.execute(
                "UPDATE crawl_jobs SET posts_found = $1, updated_at = NOW() WHERE site_id = $2",
                len(normalized_posts), site_id,
            )

            saved = await save_normalized_posts(db, site_id, normalized_posts)

            await db.execute(
                "UPDATE sites SET last_crawl_at = $1 WHERE id = $2",
                datetime.now(UTC), site_id,
            )
            await db.execute(
                """
                UPDATE crawl_jobs SET
                    status = 'completed',
                    posts_processed = $1,
                    completed_at = $2,
                    updated_at = $2
                WHERE site_id = $3
                """,
                saved, datetime.now(UTC), site_id,
            )

        logger.info("Crawl completed for site %s: %d posts", site_id, saved)

    except Exception as e:
        logger.error("Crawl failed for site %s: %s", site_id, e)
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status = 'failed', error = $1, updated_at = NOW() WHERE site_id = $2",
                    str(e)[:500], site_id,
                )
        except Exception as exc:
            logger.debug("Failed to update error status in DB: %s", exc)


require_posts = SubscriptionGuard("posts")


@router.post("/{site_id}/crawl", response_model=TaskTriggerResponse)
@_limiter.limit("5/minute")
async def trigger_crawl(
    request: Request,  # Required by slowapi
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
    _tier: None = Depends(require_posts),
):
    """Trigger a content crawl (WordPress or sitemap) as a background task."""
    site = await _get_site_for_ingestion(site_id, user_id, db)

    # Rate limit: max 1 re-analyze per hour per site (prevents abuse + API costs)
    COOLDOWN_MINUTES = 60
    last_completed = await db.fetchval(
        """SELECT MAX(updated_at) FROM crawl_jobs
           WHERE site_id = $1 AND status = 'completed'""",
        site_id,
    )
    if last_completed:
        elapsed_min = (datetime.now(UTC) - last_completed).total_seconds() / 60
        if elapsed_min < COOLDOWN_MINUTES:
            remaining = int(COOLDOWN_MINUTES - elapsed_min)
            raise HTTPException(
                status_code=429,
                detail=f"Re-analysis available in {remaining} minutes. Maximum 1 analysis per hour.",
            )

    # Check if a crawl is already running (TOCTOU guard).
    # Also recover from orphaned jobs: if a crawl has been stuck in 'crawling'
    # for >30 minutes (e.g. process crash, DB hiccup), auto-reset it to 'failed'
    # so the site isn't permanently locked from re-crawling.
    STALE_MINUTES = 30
    stale_row = await db.fetchrow(
        """SELECT site_id, status, updated_at FROM crawl_jobs
           WHERE site_id = $1 AND status = 'crawling' LIMIT 1""",
        site_id,
    )
    if stale_row:
        elapsed = (datetime.now(UTC) - stale_row["updated_at"]).total_seconds()
        if elapsed > STALE_MINUTES * 60:
            logger.warning(
                "Resetting stale crawl job for site %s (stuck for %.0f min)",
                site_id, elapsed / 60,
            )
            await db.execute(
                """UPDATE crawl_jobs SET status = 'failed',
                   error = 'Crawl timed out (no progress for 30+ minutes)',
                   updated_at = NOW() WHERE site_id = $1""",
                site_id,
            )
        else:
            raise HTTPException(status_code=429, detail="A crawl is already running for this site")

    from app.services.job_queue import enqueue_job
    await enqueue_job(db, "full_pipeline", site_id)
    return TaskTriggerResponse(message="Full pipeline started (crawl + analysis)", site_id=site_id)


@router.get("/{site_id}/crawl/status", response_model=CrawlStatusResponse)
async def crawl_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Check the crawl progress for a site."""
    await _verify_ownership(site_id, user_id, db)

    row = await db.fetchrow(
        "SELECT * FROM crawl_jobs WHERE site_id = $1", site_id,
    )
    if not row:
        return CrawlStatusResponse(site_id=site_id, status="idle")

    posts_found = row["posts_found"] or 0
    status = row["status"]

    # Early findings — surface preliminary results during pipeline wait
    # Available once enough posts are crawled (>= 50) and analysis has started
    early_findings = None
    if status in ("embedding", "analyzing", "clustering", "completed") and posts_found >= 50:
        try:
            posts_sampled = await db.fetchval(
                "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
            ) or 0
            clusters_found = await db.fetchval(
                "SELECT COUNT(DISTINCT cluster_id) FROM post_clusters pc "
                "JOIN posts p ON p.id = pc.post_id WHERE p.site_id = $1", site_id,
            ) or 0
            cann_pairs_found = await db.fetchval(
                "SELECT COUNT(*) FROM cannibalization_pairs cp "
                "JOIN posts p ON p.id = cp.post_a_id WHERE p.site_id = $1", site_id,
            ) or 0
            thin_count = await db.fetchval(
                "SELECT COUNT(*) FROM content_problems cp "
                "JOIN posts p ON p.id = cp.post_id "
                "WHERE p.site_id = $1 AND cp.problem_type = 'thin_content'", site_id,
            ) or 0
            if posts_sampled > 0:
                from app.models.schemas import EarlyFindings
                early_findings = EarlyFindings(
                    posts_sampled=int(posts_sampled),
                    clusters_found=int(clusters_found),
                    cann_pairs_found=int(cann_pairs_found),
                    thin_content_count=int(thin_count),
                    preview_ready=int(clusters_found) > 0,
                )
        except Exception as exc:
            logger.debug("Failed to update error status in DB: %s", exc)  # Don't fail status check for early findings

    return CrawlStatusResponse(
        site_id=row["site_id"],
        status=status,
        posts_found=posts_found,
        posts_processed=row["posts_processed"] or 0,
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error=row["error"],
        early_findings=early_findings,
    )


async def _run_analytics_sync(site_id: UUID, site: dict) -> None:
    """Background task: sync GA4 + GSC data."""
    try:
        pool = await get_pool()
        refresh_token = decrypt_value(site["google_tokens"]) if site.get("google_tokens") else None

        if not refresh_token:
            logger.warning("No Google refresh token for site %s", site_id)
            return

        # Acquire connection only for DB writes, not during API fetches
        # to avoid holding a pool connection for minutes during external calls
        if site.get("ga4_property_id"):
            ga4 = GA4Connector(
                property_id=site["ga4_property_id"],
                refresh_token=refresh_token,
            )
            async with pool.acquire() as db:
                await ga4.sync_metrics(db, site_id)
            logger.info("GA4 sync completed for site %s", site_id)

        if site.get("gsc_site_url"):
            gsc = GSCConnector(
                site_url=site["gsc_site_url"],
                refresh_token=refresh_token,
            )
            async with pool.acquire() as db:
                await gsc.sync_metrics(db, site_id)
            logger.info("GSC sync completed for site %s", site_id)

        async with pool.acquire() as db:
            await db.execute(
                "UPDATE sites SET last_analytics_sync_at = $1 WHERE id = $2",
                datetime.now(UTC), site_id,
            )
    except Exception as e:
        logger.error("Analytics sync failed for site %s: %s", site_id, e)


@router.post("/{site_id}/sync-analytics", response_model=TaskTriggerResponse)
async def trigger_analytics_sync(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger GA4 + GSC data sync as a background task."""
    site = await _get_site_for_ingestion(site_id, user_id, db)
    background_tasks.add_task(_run_analytics_sync, site_id, site)
    return TaskTriggerResponse(message="Analytics sync started", site_id=site_id)


async def _run_embeddings(site_id: UUID) -> None:
    """Background task: generate embeddings for all posts."""
    try:
        pool = await get_pool()
        pipeline = EmbeddingPipeline()
        async with pool.acquire() as db:
            await pipeline.generate_for_site(db, site_id)
        logger.info("Embedding generation completed for site %s", site_id)
    except Exception as e:
        logger.error("Embedding generation failed for site %s: %s", site_id, e)


@router.post("/{site_id}/generate-embeddings", response_model=TaskTriggerResponse)
async def trigger_embeddings(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger embedding generation for all posts in a site."""
    await _verify_ownership(site_id, user_id, db)
    background_tasks.add_task(_run_embeddings, site_id)
    return TaskTriggerResponse(message="Embedding generation started", site_id=site_id)


@router.post("/cron/daily-refresh", response_model=TaskTriggerResponse)
async def trigger_daily_refresh(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Trigger daily analytics refresh. Requires X-Cron-Secret header."""
    from app.services.recrawl import run_daily_refresh
    background_tasks.add_task(run_daily_refresh)
    return TaskTriggerResponse(message="Daily analytics refresh started", site_id=None)


@router.post("/cron/weekly-recrawl", response_model=TaskTriggerResponse)
async def trigger_weekly_recrawl(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Trigger weekly re-crawl. Requires X-Cron-Secret header."""
    from app.services.recrawl import run_weekly_recrawl
    background_tasks.add_task(run_weekly_recrawl)
    return TaskTriggerResponse(message="Weekly re-crawl started", site_id=None)


@router.post("/cron/monthly-reembed", response_model=TaskTriggerResponse)
async def trigger_monthly_reembed(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Trigger monthly re-embedding. Requires X-Cron-Secret header."""
    from app.services.recrawl import run_monthly_reembed
    background_tasks.add_task(run_monthly_reembed)
    return TaskTriggerResponse(message="Monthly re-embed started", site_id=None)


@router.post("/cron/winback-emails", response_model=TaskTriggerResponse)
async def trigger_winback_emails(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Process win-back emails for cancelled subscribers.

    Sends:
    - Day 7 post-cancel: "Your content health has gone unchecked for a week"
    - Day 30: "Here's what changed on your blog since you left"
    - Day 60: Final attempt with discount offer

    Wire to a daily cron. Requires X-Cron-Secret header.
    """
    async def _process():
        from app.database import get_pool
        from app.services.stripe_service import StripeService

        pool = await get_pool()
        async with pool.acquire() as db:
            service = StripeService()
            sent = await service.process_winback_emails(db)
            logger.info("Win-back processing: sent %d emails", sent)

    background_tasks.add_task(_process)
    return TaskTriggerResponse(message="Win-back email processing started", site_id=None)


@router.post("/cron/process-drips", response_model=TaskTriggerResponse)
async def trigger_process_drips(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Process pending drip emails for audit leads.

    Sends scheduled drip emails (day 2 and day 5 follow-ups) for
    audit report leads. Wire to a frequent cron (e.g. every 30 min).
    Requires X-Cron-Secret header.
    """
    async def _process():
        from app.database import get_pool
        from app.services.drip_sequence import DripSequenceService

        pool = await get_pool()
        async with pool.acquire() as db:
            service = DripSequenceService()
            sent = await service.process_pending_drips(db)
            logger.info("Drip processing: sent %d emails", sent)

    background_tasks.add_task(_process)
    return TaskTriggerResponse(message="Drip email processing started", site_id=None)


@router.post("/cron/weekly-digest", response_model=TaskTriggerResponse)
async def trigger_weekly_digest(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Send weekly ecosystem email digest to all users.

    Sends a personalized email per site with:
    - Health score delta (this week vs last)
    - Top recommendation ("do this one thing")
    - Quick win consolidation opportunity
    - Post breakdown changes

    Requires X-Cron-Secret header. Wire to a weekly cron (e.g. Monday 9am).
    """
    async def _send_digests():
        from app.database import get_pool
        from app.services.weekly_report import WeeklyReportService

        pool = await get_pool()
        async with pool.acquire() as db:
            service = WeeklyReportService()
            sent = await service.send_all_reports(db)
            logger.info("Weekly digest: sent %d reports", sent)

    background_tasks.add_task(_send_digests)
    return TaskTriggerResponse(message="Weekly digest emails queued", site_id=None)


@router.post("/cron/monthly-report", response_model=TaskTriggerResponse)
async def trigger_monthly_report(
    background_tasks: BackgroundTasks,
    _cron: None = Depends(verify_cron_secret),
):
    """Send monthly health report emails to all paid users.

    Includes health score delta, completed recommendations, and new issues.
    Wire to a monthly cron (e.g., 1st of month at 9am).
    """
    async def _send_reports():
        from app.database import get_pool
        from app.services.monthly_email import send_all_monthly_reports

        pool = await get_pool()
        async with pool.acquire() as db:
            sent = await send_all_monthly_reports(db)
            logger.info("Monthly report: sent %d reports", sent)

    background_tasks.add_task(_send_reports)
    return TaskTriggerResponse(message="Monthly report emails queued", site_id=None)


@router.get("/{site_id}/pipeline/status")
async def get_pipeline_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get full pipeline status with stage tracking, partial results, and time estimates.

    Returns a richer status than the intelligence pipeline-status endpoint,
    including crawl stage info, partial results availability, and ETA.
    """
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    # Check crawl_jobs (primary pipeline tracker)
    crawl = await db.fetchrow(
        "SELECT status, started_at, completed_at, posts_found, posts_processed, error FROM crawl_jobs WHERE site_id = $1",
        site_id,
    )
    # Check intelligence pipeline_jobs
    pipeline = await db.fetchrow(
        "SELECT status, current_step, steps_completed, started_at, completed_at, error FROM pipeline_jobs WHERE site_id = $1",
        site_id,
    )

    # Determine overall status
    if not crawl and not pipeline:
        return {
            "status": "idle",
            "current_stage": None,
            "completed_stages": [],
            "partial_results_available": False,
            "estimated_time_remaining": None,
            "started_at": None,
            "completed_at": None,
        }

    # Map crawl_jobs status to pipeline stages
    STAGE_MAP = {
        "crawling": "crawling",
        "embedding": "embedding",
        "analyzing": "health_scoring",
        "clustering": "clustering",
        "completed": None,
        "failed": None,
    }

    # Determine current stage and completed stages
    completed_stages: list[str] = []
    current_stage = None
    status = "idle"
    started_at = None
    completed_at = None
    error = None

    if crawl:
        started_at = crawl["started_at"]
        crawl_status = crawl["status"] or "idle"

        if crawl_status == "completed":
            completed_stages.append("crawling")
            completed_stages.append("embedding")
            status = "completed"
            completed_at = crawl["completed_at"]
        elif crawl_status == "failed":
            status = "failed"
            error = crawl["error"]
        elif crawl_status == "crawling":
            status = "running"
            current_stage = "crawling"
        elif crawl_status in ("embedding", "analyzing", "clustering"):
            status = "running"
            completed_stages.append("crawling")
            if crawl_status in ("analyzing", "clustering"):
                completed_stages.append("embedding")
            if crawl_status == "clustering":
                completed_stages.append("clustering")
            current_stage = STAGE_MAP.get(crawl_status, crawl_status)

    # Overlay intelligence pipeline_jobs if available
    if pipeline:
        pipe_status = pipeline["status"] or "idle"
        pipe_steps = pipeline["steps_completed"] or []
        if pipe_status == "running":
            status = "running"
            current_stage = pipeline["current_step"]
            # Merge completed stages
            for step in pipe_steps:
                if step not in completed_stages:
                    completed_stages.append(step)
        elif pipe_status == "completed":
            status = "completed"
            completed_at = pipeline["completed_at"] or completed_at
            for step in pipe_steps:
                if step not in completed_stages:
                    completed_stages.append(step)
        elif pipe_status == "failed" and status != "running":
            status = "failed"
            error = pipeline["error"] or error

    # Check if partial results are available
    partial_results_available = False
    if completed_stages:
        # If clustering is done, we have partial results
        has_clusters = await db.fetchval(
            "SELECT EXISTS(SELECT 1 FROM clusters WHERE site_id = $1)", site_id,
        )
        partial_results_available = bool(has_clusters)

    # Estimate time remaining (rough heuristic based on post count + stage)
    estimated_time_remaining = None
    if status == "running" and started_at:
        post_count = crawl["posts_found"] or 0 if crawl else 0
        # Rough estimates: crawling ~2s/post, embedding ~1s/post, analysis ~0.5s/post
        total_estimate = max(120, post_count * 3.5)  # seconds
        elapsed = (datetime.now(UTC) - started_at).total_seconds()
        remaining = max(0, total_estimate - elapsed)
        estimated_time_remaining = round(remaining)

    return {
        "status": status,
        "current_stage": current_stage,
        "completed_stages": completed_stages,
        "partial_results_available": partial_results_available,
        "estimated_time_remaining": estimated_time_remaining,
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
    }


async def _verify_ownership(site_id: UUID, user_id: str, db: asyncpg.Connection) -> None:
    """Quick ownership check without returning full site data."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


async def _get_site_for_ingestion(
    site_id: UUID, user_id: str, db: asyncpg.Connection,
) -> dict:
    """Fetch full site record (including encrypted fields) for background processing."""
    row = await db.fetchrow(
        "SELECT * FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return dict(row)


# ── Full pipeline trigger (crawl → analyze → cluster → recs) ─────────────────

async def _pipeline_step(pool, site_id: UUID, step_name: str, status: str, fn) -> bool:
    """Run one pipeline step with status update + error recovery.

    Returns True on success, False on failure (pipeline continues to next step).
    """
    try:
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE crawl_jobs SET status=$1, current_step=$2,
                   steps_completed = COALESCE(steps_completed, 0) + 1,
                   updated_at=NOW() WHERE site_id=$3""",
                status, step_name, site_id,
            )
        async with pool.acquire() as db:
            await fn(db)
        logger.info("Pipeline step '%s' complete for site %s", step_name, site_id)
        return True
    except Exception as e:
        logger.error("Pipeline step '%s' failed for site %s: %s", step_name, site_id, e)
        logger.exception("Stack trace for above error")
        # Log step failure but don't abort — continue to next step
        try:
            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE crawl_jobs SET
                        error = COALESCE(error, '') || $1,
                        updated_at = NOW()
                       WHERE site_id = $2""",
                    f"[{step_name}]: {str(e)[:200]}; ", site_id,
                )
        except Exception as exc:
            logger.debug("Failed to update error status in DB: %s", exc)
        return False


async def _run_full_pipeline(
    site_id: UUID,
    site: dict,
    *,
    skip_chunk_confirmation: bool = False,
) -> None:
    """Background: crawl → embed → cluster → health → problems → recs.

    Each step is independently error-handled. A failing step logs the error
    and continues to the next step rather than aborting the whole pipeline.

    Pipeline steps (see PIPELINE.md for full reference):
      Step 1     : Crawl + Normalize
      Steps 2-5  : Enrichment (Embed, Readability, PageRank, Intent)
      Step 6     : Clustering (UMAP + HDBSCAN + sub-cluster)
      Step 6b    : TF-IDF cluster labels
      Step 6c    : AI Citability
      Step 7     : Health Scoring
      Step 8     : Cannibalization
      Step 8b    : Chunk confirmation (optional, $0.50)
      Step 8c    : Role patch (post-cannibalization)
      Step 9     : Problem Detection
      Step 10    : Recommendations
      Step 10b   : Claude enrichment (optional)

    Args:
        skip_chunk_confirmation: Skip the $0.50 chunk-level cannibalization step.
            Pass True for cold outreach / prospect pipelines to control cost.
    """
    pool = await get_pool()

    try:
        # Step 1: crawl (owns its own status updates)
        await _run_crawl(site_id, site)

        # Verify crawl produced posts
        async with pool.acquire() as db:
            crawl = await db.fetchrow(
                "SELECT status, posts_processed FROM crawl_jobs WHERE site_id=$1", site_id
            )
        if not crawl or crawl["status"] == "failed":
            logger.error("Crawl failed for site %s — aborting pipeline", site_id)
            return
        if (crawl["posts_processed"] or 0) == 0:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status='failed', error='No posts found in sitemap', updated_at=NOW() WHERE site_id=$1",
                    site_id,
                )
            return

        # Step 2: embeddings
        from app.services.embeddings import EmbeddingPipeline
        await _pipeline_step(pool, site_id, "embeddings", "embedding",
                             lambda db: EmbeddingPipeline().generate_for_site(db, site_id))

        # Step 3: readability
        from app.services.readability import ReadabilityScorer
        await _pipeline_step(pool, site_id, "readability", "analyzing",
                             lambda db: ReadabilityScorer().score_site(db, site_id))

        # Step 4: pagerank
        from app.services.pagerank import InternalPageRank
        await _pipeline_step(pool, site_id, "pagerank", "analyzing",
                             lambda db: InternalPageRank().compute_for_site(db, site_id))

        # Step 5: intent classification
        from app.services.fast_intent import classify_site_fast
        await _pipeline_step(pool, site_id, "intent", "analyzing",
                             lambda db: classify_site_fast(db, site_id))

        # Step 6: clustering (TF-IDF labels — no Claude calls)
        from app.services.clustering import TopicClusterer

        async def _clustering_with_progress(db: "asyncpg.Connection") -> int:
            async def _on_clustering_progress(msg: str) -> None:
                """Best-effort progress update using a separate pool connection."""
                try:
                    async with pool.acquire() as progress_db:
                        await progress_db.execute(
                            "UPDATE crawl_jobs SET current_step=$1, updated_at=NOW() WHERE site_id=$2",
                            f"clustering: {msg}", site_id,
                        )
                except Exception:
                    pass

            def _fire_progress(msg: str) -> None:
                asyncio.create_task(_on_clustering_progress(msg))

            return await TopicClusterer().cluster_site(
                db, site_id, skip_labeling=True, on_progress=_fire_progress,
            )

        await _pipeline_step(pool, site_id, "clustering", "clustering", _clustering_with_progress)

        # Step 6b: fast TF-IDF cluster labels
        from app.services.fast_cluster_labels import label_clusters_fast
        await _pipeline_step(pool, site_id, "cluster_labels", "clustering",
                             lambda db: label_clusters_fast(db, site_id))

        # Step 6c: AI citability scoring — runs ONLY here (not in enrichment).
        # Must run before health scoring so the 15% ai_readiness weight is populated.
        from app.services.ai_citability import AICitabilityService
        await _pipeline_step(pool, site_id, "ai_citability", "analyzing",
                             lambda db: AICitabilityService().score_site(db, site_id))

        # Step 7: health scoring
        from app.services.health_scoring import HealthScorer

        async def _health_with_progress(db: "asyncpg.Connection") -> int:
            async def _on_health_progress(msg: str) -> None:
                try:
                    async with pool.acquire() as progress_db:
                        await progress_db.execute(
                            "UPDATE crawl_jobs SET current_step=$1, updated_at=NOW() WHERE site_id=$2",
                            f"health_scoring: {msg}", site_id,
                        )
                except Exception:
                    pass

            def _fire_health_progress(msg: str) -> None:
                asyncio.create_task(_on_health_progress(msg))

            return await HealthScorer().score_site(db, site_id, on_progress=_fire_health_progress)

        await _pipeline_step(pool, site_id, "health_scoring", "analyzing", _health_with_progress)

        # Step 8: cannibalization
        from app.services.cannibalization import CannibalizationDetector
        await _pipeline_step(pool, site_id, "cannibalization", "analyzing",
                             lambda db: CannibalizationDetector().detect_for_site(db, site_id))

        # Step 8b: chunk-level cannibalization confirmation (non-fatal, OpenAI ~$0.50)
        # Skipped for cold outreach / prospect pipelines to control cost.
        if not skip_chunk_confirmation:
            try:
                from app.services.chunk_cannibalization import confirm_chunk_overlap
                async with pool.acquire() as db:
                    result = await confirm_chunk_overlap(db, site_id, pair_limit=50)
                    logger.info("Chunk confirmation: %s", result)
            except Exception as e:
                logger.warning("Chunk confirmation failed (non-fatal): %s", e)
        else:
            logger.info("Skipping chunk confirmation for site %s (skip_chunk_confirmation=True)", site_id)

        # Step 8c: post-cannibalization role patch
        # Fixes competitor roles + ecosystem states that depend on cannibalization data
        # (health scoring at Step 7 ran before cannibalization at Step 8, so roles were incomplete)
        from app.services.health_scoring import HealthScorer as _HS
        await _pipeline_step(pool, site_id, "role_patch", "analyzing",
                             lambda db: _HS().patch_roles_after_cannibalization(db, site_id))

        # Step 9: problem detection
        from app.services.problem_detection import ProblemDetector
        await _pipeline_step(pool, site_id, "problem_detection", "analyzing",
                             lambda db: ProblemDetector().detect_all(db, site_id))

        # Step 10: recommendations
        from app.services.fast_recommendations import generate_fast_recommendations
        await _pipeline_step(pool, site_id, "recommendations", "analyzing",
                             lambda db: generate_fast_recommendations(db, site_id))

        # Step 10b: auto-enrich top 10 recommendations with Claude (non-fatal)
        # Pass pool directly for concurrent enrichment (~3x faster than sequential)
        try:
            from app.services.on_demand_enrichment import auto_enrich_top_recs
            enriched = await auto_enrich_top_recs(pool, site_id, limit=10)
            logger.info("Auto-enriched %d recs for site %s", enriched, site_id)
        except Exception as e:
            logger.warning("Auto-enrichment failed (non-fatal): %s", e)

        # Mark complete
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE crawl_jobs SET status='completed', completed_at=NOW(), updated_at=NOW()
                   WHERE site_id=$1""",
                site_id,
            )
        logger.info("Full pipeline complete for site %s", site_id)

    except Exception as e:
        logger.error("Full pipeline outer error for site %s: %s", site_id, e)
        logger.exception("Stack trace for above error")
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status='failed', error=$1, updated_at=NOW() WHERE site_id=$2",
                    str(e)[:500], site_id,
                )
        except Exception as exc:
            logger.debug("Failed to update error status in DB: %s", exc)


class PipelineOptions(BaseModel):
    url_patterns: list[str] | None = None  # e.g. ["/blog/", "/resources/"]

    def model_post_init(self, __context) -> None:
        """Validate url_patterns to prevent accidental over-matching."""
        if self.url_patterns:
            cleaned = []
            for pat in self.url_patterns:
                pat = pat.strip()
                if not pat:
                    continue
                # Require patterns to start with / to match path segments, not substrings.
                # "blog" would match /about-blogging; "/blog/" is correct.
                if not pat.startswith("/"):
                    pat = "/" + pat
                cleaned.append(pat)
            self.url_patterns = cleaned or None


@router.post("/{site_id}/pipeline", response_model=TaskTriggerResponse)
@_limiter.limit("3/minute")
async def trigger_full_pipeline(
    request: Request,  # Required by slowapi
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
    options: PipelineOptions | None = None,
):
    """Trigger full pipeline: crawl → embed → cluster → health → recs.
    Takes 10-40 min depending on site size. Poll /crawl/status for progress.
    Optional body: { url_patterns: ["/blog/", "/resources/"] } to filter crawled URLs."""
    site = await _get_site_for_ingestion(site_id, user_id, db)
    # Persist url_patterns to sites table so incremental refresh reuses them
    if options and options.url_patterns is not None:
        await db.execute(
            "UPDATE sites SET url_patterns = $1 WHERE id = $2",
            options.url_patterns, site_id,
        )
        site = dict(site)
        site["url_patterns"] = options.url_patterns
    from app.services.job_queue import enqueue_job
    payload = {"url_patterns": options.url_patterns} if options and options.url_patterns else {}
    await enqueue_job(db, "full_pipeline", site_id, payload)
    return TaskTriggerResponse(
        message="Full pipeline started — crawl → analyze → cluster → recommendations",
        site_id=site_id,
    )


# ── Incremental refresh (re-crawl new/changed posts only, then re-analyze) ────

async def _run_incremental_pipeline(site_id: UUID, site: dict) -> None:
    """Background: crawl only changed posts → embed new ones → re-score site.
    Each step independently error-handled — failures log and continue."""
    pool = await get_pool()

    try:
        async with pool.acquire() as db:
            prev_count = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id=$1", site_id) or 0

        # Step 1: crawl (upsert — unchanged posts keep content_hash, skip reprocessing)
        await _run_crawl(site_id, site)

        async with pool.acquire() as db:
            new_count = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id=$1", site_id) or 0
        added = max(0, new_count - prev_count)
        logger.info("Incremental crawl: %d new/updated posts for site %s", added, site_id)

        # Step 2: embed only new/changed posts (skips unchanged via content_hash)
        from app.services.embeddings import EmbeddingPipeline
        await _pipeline_step(pool, site_id, "embeddings", "embedding",
                             lambda db: EmbeddingPipeline().generate_for_site(db, site_id))

        # Steps 3-7: always re-run analysis (fast — no embedding cost for unchanged posts)
        from app.services.fast_intent import classify_site_fast
        await _pipeline_step(pool, site_id, "intent", "analyzing",
                             lambda db: classify_site_fast(db, site_id))

        from app.services.pagerank import InternalPageRank
        await _pipeline_step(pool, site_id, "pagerank", "analyzing",
                             lambda db: InternalPageRank().compute_for_site(db, site_id))

        # AI citability before health scoring so composite includes AI readiness
        from app.services.ai_citability import AICitabilityService
        await _pipeline_step(pool, site_id, "ai_citability", "analyzing",
                             lambda db: AICitabilityService().score_site(db, site_id))

        from app.services.health_scoring import HealthScorer
        await _pipeline_step(pool, site_id, "health_scoring", "analyzing",
                             lambda db: HealthScorer().score_site(db, site_id))

        from app.services.cannibalization import CannibalizationDetector
        await _pipeline_step(pool, site_id, "cannibalization", "analyzing",
                             lambda db: CannibalizationDetector().detect_for_site(db, site_id))

        from app.services.problem_detection import ProblemDetector
        await _pipeline_step(pool, site_id, "problem_detection", "analyzing",
                             lambda db: ProblemDetector().detect_all(db, site_id))

        from app.services.fast_recommendations import generate_fast_recommendations
        await _pipeline_step(pool, site_id, "recommendations", "analyzing",
                             lambda db: generate_fast_recommendations(db, site_id))

        # Auto-enrich top recs with Claude (non-fatal)
        try:
            from app.services.on_demand_enrichment import auto_enrich_top_recs
            enriched = await auto_enrich_top_recs(pool, site_id, limit=10)
            logger.info("Auto-enriched %d recs for site %s", enriched, site_id)
        except Exception as e:
            logger.warning("Auto-enrichment failed (non-fatal): %s", e)

        async with pool.acquire() as db:
            await db.execute(
                "UPDATE crawl_jobs SET status='completed', completed_at=NOW(), updated_at=NOW() WHERE site_id=$1",
                site_id,
            )
        logger.info("Incremental pipeline complete for site %s (added %d posts)", site_id, added)

    except Exception as e:
        logger.error("Incremental pipeline outer error for site %s: %s", site_id, e)
        logger.exception("Stack trace for above error")
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status='failed', error=$1, updated_at=NOW() WHERE site_id=$2",
                    str(e)[:500], site_id,
                )
        except Exception as exc:
            logger.debug("Failed to update error status in DB: %s", exc)


@router.post("/{site_id}/pipeline/refresh", response_model=TaskTriggerResponse)
async def trigger_incremental_refresh(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Incremental refresh: re-crawl changed posts only, embed new ones, re-analyze.
    Much faster than full pipeline on re-runs — only processes what changed."""
    await _get_site_for_ingestion(site_id, user_id, db)
    from app.services.job_queue import enqueue_job
    await enqueue_job(db, "incremental_pipeline", site_id)
    return TaskTriggerResponse(
        message="Incremental refresh started — only new/changed posts will be re-processed",
        site_id=site_id,
    )
