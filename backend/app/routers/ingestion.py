"""Content ingestion trigger endpoints."""

import logging
from uuid import UUID
from typing import Annotated
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id, get_verified_site, verify_cron_secret
from app.models.schemas import CrawlStatusResponse, TaskTriggerResponse
from app.services.wordpress import WordPressConnector
from app.services.sitemap import SitemapCrawler
from app.services.normalizer import save_normalized_posts
from app.services.ga4 import GA4Connector
from app.services.gsc import GSCConnector
from app.services.embeddings import EmbeddingPipeline
from app.utils.encryption import decrypt_value

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
    except Exception:
        pass  # Progress updates are best-effort


async def _run_crawl(site_id: UUID, site: dict) -> None:
    """Background task: crawl content from WordPress or sitemap."""
    pool = await get_pool()

    # Initialize crawl status in DB
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO crawl_jobs (site_id, status, started_at, updated_at)
            VALUES ($1, 'crawling', $2, $2)
            ON CONFLICT (site_id) DO UPDATE SET
                status = 'crawling',
                started_at = $2,
                completed_at = NULL,
                error = NULL,
                posts_found = 0,
                posts_processed = 0,
                updated_at = $2
            """,
            site_id, datetime.now(timezone.utc),
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
                datetime.now(timezone.utc), site_id,
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
                saved, datetime.now(timezone.utc), site_id,
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
        except Exception:
            pass


@router.post("/{site_id}/crawl", response_model=TaskTriggerResponse)
async def trigger_crawl(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger a content crawl (WordPress or sitemap) as a background task."""
    site = await _get_site_for_ingestion(site_id, user_id, db)
    background_tasks.add_task(_run_crawl, site_id, site)
    return TaskTriggerResponse(message="Crawl started", site_id=site_id)


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
        except Exception:
            pass  # Don't fail status check for early findings

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
        refresh_token = decrypt_value(site["google_refresh_token"]) if site.get("google_refresh_token") else None

        if not refresh_token:
            logger.warning("No Google refresh token for site %s", site_id)
            return

        async with pool.acquire() as db:
            if site.get("ga4_property_id"):
                ga4 = GA4Connector(
                    property_id=site["ga4_property_id"],
                    refresh_token=refresh_token,
                )
                await ga4.sync_metrics(db, site_id)
                logger.info("GA4 sync completed for site %s", site_id)

            if site.get("gsc_site_url"):
                gsc = GSCConnector(
                    site_url=site["gsc_site_url"],
                    refresh_token=refresh_token,
                )
                await gsc.sync_metrics(db, site_id)
                logger.info("GSC sync completed for site %s", site_id)

            await db.execute(
                "UPDATE sites SET last_analytics_sync_at = $1 WHERE id = $2",
                datetime.now(timezone.utc), site_id,
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
                "UPDATE crawl_jobs SET status=$1, updated_at=NOW() WHERE site_id=$2",
                status, site_id,
            )
        async with pool.acquire() as db:
            await fn(db)
        logger.info("Pipeline step '%s' complete for site %s", step_name, site_id)
        return True
    except Exception as e:
        logger.error("Pipeline step '%s' failed for site %s: %s", step_name, site_id, e)
        import traceback; traceback.print_exc()
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
        except Exception:
            pass
        return False


async def _run_full_pipeline(site_id: UUID, site: dict) -> None:
    """Background: crawl → embed → cluster → health → problems → recs.

    Each step is independently error-handled. A failing step logs the error
    and continues to the next step rather than aborting the whole pipeline.
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

        # Step 6: clustering + Claude labels
        from app.services.clustering import TopicClusterer
        await _pipeline_step(pool, site_id, "clustering", "clustering",
                             lambda db: TopicClusterer().cluster_site(db, site_id, skip_labeling=False))

        # Step 7: health scoring
        from app.services.health_scoring import HealthScorer
        await _pipeline_step(pool, site_id, "health_scoring", "analyzing",
                             lambda db: HealthScorer().score_site(db, site_id))

        # Step 8: cannibalization
        from app.services.cannibalization import CannibalizationDetector
        await _pipeline_step(pool, site_id, "cannibalization", "analyzing",
                             lambda db: CannibalizationDetector().detect_for_site(db, site_id))

        # Step 9: problem detection
        from app.services.problem_detection import ProblemDetector
        await _pipeline_step(pool, site_id, "problem_detection", "analyzing",
                             lambda db: ProblemDetector().detect_all(db, site_id))

        # Step 10: recommendations
        from app.services.fast_recommendations import generate_fast_recommendations
        await _pipeline_step(pool, site_id, "recommendations", "analyzing",
                             lambda db: generate_fast_recommendations(db, site_id))

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
        import traceback; traceback.print_exc()
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status='failed', error=$1, updated_at=NOW() WHERE site_id=$2",
                    str(e)[:500], site_id,
                )
        except Exception:
            pass


class PipelineOptions(BaseModel):
    url_patterns: list[str] | None = None  # e.g. ["/blog/", "/resources/"]


@router.post("/{site_id}/pipeline", response_model=TaskTriggerResponse)
async def trigger_full_pipeline(
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
    background_tasks.add_task(_run_full_pipeline, site_id, site)
    return TaskTriggerResponse(message="Full pipeline started — crawl → analyze → cluster → recommendations", site_id=site_id)


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

        async with pool.acquire() as db:
            await db.execute(
                "UPDATE crawl_jobs SET status='completed', completed_at=NOW(), updated_at=NOW() WHERE site_id=$1",
                site_id,
            )
        logger.info("Incremental pipeline complete for site %s (added %d posts)", site_id, added)

    except Exception as e:
        logger.error("Incremental pipeline outer error for site %s: %s", site_id, e)
        import traceback; traceback.print_exc()
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status='failed', error=$1, updated_at=NOW() WHERE site_id=$2",
                    str(e)[:500], site_id,
                )
        except Exception:
            pass


@router.post("/{site_id}/pipeline/refresh", response_model=TaskTriggerResponse)
async def trigger_incremental_refresh(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Incremental refresh: re-crawl changed posts only, embed new ones, re-analyze.
    Much faster than full pipeline on re-runs — only processes what changed."""
    site = await _get_site_for_ingestion(site_id, user_id, db)
    background_tasks.add_task(_run_incremental_pipeline, site_id, site)
    return TaskTriggerResponse(
        message="Incremental refresh started — only new/changed posts will be re-processed",
        site_id=site_id,
    )
