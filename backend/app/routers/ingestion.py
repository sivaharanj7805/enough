"""Content ingestion trigger endpoints."""

import logging
from uuid import UUID
from typing import Annotated
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks

from app.database import get_db, get_pool
from app.models.schemas import CrawlStatusResponse, TaskTriggerResponse
from app.services.wordpress import WordPressConnector
from app.services.sitemap import SitemapCrawler
from app.services.normalizer import save_normalized_posts
from app.services.ga4 import GA4Connector
from app.services.gsc import GSCConnector
from app.services.embeddings import EmbeddingPipeline

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory crawl status tracking (use Redis in production)
_crawl_status: dict[str, CrawlStatusResponse] = {}


async def _get_user_id(authorization: Annotated[str, Header()]) -> str:
    token = authorization.replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization")
    return token


async def _get_site(site_id: UUID, user_id: str, db: asyncpg.Connection) -> dict:
    """Fetch a site ensuring ownership."""
    row = await db.fetchrow(
        "SELECT * FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return dict(row)


async def _run_crawl(site_id: UUID, site: dict) -> None:
    """Background task: crawl content from WordPress or sitemap."""
    status_key = str(site_id)
    _crawl_status[status_key] = CrawlStatusResponse(
        site_id=site_id, status="crawling", started_at=datetime.now(timezone.utc),
    )

    try:
        pool = await get_pool()
        cms_type = site["cms_type"]
        normalized_posts = []

        if cms_type == "wordpress" and site.get("wordpress_url"):
            connector = WordPressConnector(
                base_url=site["wordpress_url"],
                app_password=site.get("wordpress_app_password"),
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
            _crawl_status[status_key].status = "failed"
            _crawl_status[status_key].error = "No WordPress URL or sitemap URL configured"
            return

        _crawl_status[status_key].posts_found = len(normalized_posts)

        async with pool.acquire() as db:
            await save_normalized_posts(db, site_id, normalized_posts)
            await db.execute(
                "UPDATE sites SET last_crawl_at = $1 WHERE id = $2",
                datetime.now(timezone.utc), site_id,
            )

        _crawl_status[status_key].status = "completed"
        _crawl_status[status_key].posts_processed = len(normalized_posts)
        _crawl_status[status_key].completed_at = datetime.now(timezone.utc)
        logger.info("Crawl completed for site %s: %d posts", site_id, len(normalized_posts))

    except Exception as e:
        logger.error("Crawl failed for site %s: %s", site_id, e)
        _crawl_status[status_key].status = "failed"
        _crawl_status[status_key].error = str(e)


@router.post("/{site_id}/crawl", response_model=TaskTriggerResponse)
async def trigger_crawl(
    site_id: UUID,
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger a content crawl (WordPress or sitemap) as a background task."""
    site = await _get_site(site_id, user_id, db)
    background_tasks.add_task(_run_crawl, site_id, site)
    return TaskTriggerResponse(message="Crawl started", site_id=site_id)


@router.get("/{site_id}/crawl/status", response_model=CrawlStatusResponse)
async def crawl_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Check the crawl progress for a site."""
    await _get_site(site_id, user_id, db)  # Verify ownership
    status_key = str(site_id)
    if status_key not in _crawl_status:
        return CrawlStatusResponse(site_id=site_id, status="idle")
    return _crawl_status[status_key]


async def _run_analytics_sync(site_id: UUID, site: dict) -> None:
    """Background task: sync GA4 + GSC data."""
    try:
        pool = await get_pool()
        async with pool.acquire() as db:
            if site.get("ga4_property_id") and site.get("google_refresh_token"):
                ga4 = GA4Connector(
                    property_id=site["ga4_property_id"],
                    refresh_token=site["google_refresh_token"],
                )
                await ga4.sync_metrics(db, site_id)
                logger.info("GA4 sync completed for site %s", site_id)

            if site.get("gsc_site_url") and site.get("google_refresh_token"):
                gsc = GSCConnector(
                    site_url=site["gsc_site_url"],
                    refresh_token=site["google_refresh_token"],
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
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger GA4 + GSC data sync as a background task."""
    site = await _get_site(site_id, user_id, db)
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
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Trigger embedding generation for all posts in a site."""
    await _get_site(site_id, user_id, db)
    background_tasks.add_task(_run_embeddings, site_id)
    return TaskTriggerResponse(message="Embedding generation started", site_id=site_id)
