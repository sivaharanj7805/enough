"""Content ingestion trigger endpoints."""

import logging
from uuid import UUID
from typing import Annotated
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id, get_verified_site
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


async def _run_crawl(site_id: UUID, site: dict) -> None:
    """Background task: crawl content from WordPress or sitemap."""
    pool = await get_pool()

    # Initialize crawl status in DB
    async with pool.acquire() as db:
        await db.execute(
            """
            INSERT INTO crawl_jobs (site_id, status, started_at)
            VALUES ($1, 'crawling', $2)
            ON CONFLICT (site_id) DO UPDATE SET
                status = 'crawling',
                started_at = $2,
                completed_at = NULL,
                error = NULL,
                posts_found = 0,
                posts_processed = 0
            """,
            site_id, datetime.now(timezone.utc),
        )

    try:
        cms_type = site["cms_type"]
        normalized_posts = []

        if cms_type == "wordpress" and site.get("wordpress_url"):
            # Decrypt the app password
            app_password = decrypt_value(site["wordpress_app_password"]) if site.get("wordpress_app_password") else None
            connector = WordPressConnector(
                base_url=site["wordpress_url"],
                app_password=app_password,
                domain=site["domain"],
            )
            normalized_posts = await connector.fetch_all_posts()
        elif site.get("sitemap_url"):
            crawler = SitemapCrawler(
                sitemap_url=site["sitemap_url"],
                domain=site["domain"],
            )
            normalized_posts = await crawler.crawl()
        else:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE crawl_jobs SET status = 'failed', error = $1 WHERE site_id = $2",
                    "No WordPress URL or sitemap URL configured", site_id,
                )
            return

        async with pool.acquire() as db:
            await db.execute(
                "UPDATE crawl_jobs SET posts_found = $1 WHERE site_id = $2",
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
                    completed_at = $2
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
                    "UPDATE crawl_jobs SET status = 'failed', error = $1 WHERE site_id = $2",
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

    return CrawlStatusResponse(
        site_id=row["site_id"],
        status=row["status"],
        posts_found=row["posts_found"] or 0,
        posts_processed=row["posts_processed"] or 0,
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error=row["error"],
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
