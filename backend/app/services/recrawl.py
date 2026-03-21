"""Re-crawl and data refresh system.

Handles scheduled re-crawling of sites to detect content changes,
and refreshing of GSC/GA4 analytics data.

Schedule:
- Daily: Pull fresh GSC + GA4 data (lightweight API calls)
- Weekly: Re-crawl site to detect new/updated/deleted posts via content_hash
- Monthly: Full re-embed if significant content changes detected (>10% of posts)
"""

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

import asyncpg

from app.database import get_pool
from app.services.sitemap import SitemapCrawler
from app.services.wordpress import WordPressConnector
from app.services.normalizer import save_normalized_posts, compute_content_hash
from app.services.ga4 import GA4Connector
from app.services.gsc import GSCConnector
from app.services.embeddings import EmbeddingPipeline
from app.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def get_sites_needing_refresh(
    db: asyncpg.Connection,
    refresh_type: str,
) -> list[dict]:
    """Find sites that need a data refresh.

    refresh_type:
        - 'analytics_daily': GSC/GA4 data older than 24h
        - 'crawl_weekly': content crawl older than 7 days
        - 'embed_monthly': embeddings older than 30 days with content changes
    """
    now = datetime.now(timezone.utc)

    if refresh_type == "analytics_daily":
        threshold = now - timedelta(hours=24)
        rows = await db.fetch(
            """
            SELECT s.* FROM sites s
            WHERE s.google_refresh_token IS NOT NULL
              AND (s.last_analytics_sync_at IS NULL OR s.last_analytics_sync_at < $1)
            ORDER BY s.last_analytics_sync_at ASC NULLS FIRST
            LIMIT 50
            """,
            threshold,
        )
    elif refresh_type == "crawl_weekly":
        threshold = now - timedelta(days=7)
        rows = await db.fetch(
            """
            SELECT s.* FROM sites s
            WHERE (s.last_crawl_at IS NULL OR s.last_crawl_at < $1)
            ORDER BY s.last_crawl_at ASC NULLS FIRST
            LIMIT 20
            """,
            threshold,
        )
    elif refresh_type == "embed_monthly":
        threshold = now - timedelta(days=30)
        rows = await db.fetch(
            """
            SELECT s.* FROM sites s
            WHERE s.id IN (
                SELECT DISTINCT p.site_id
                FROM post_embeddings pe
                JOIN posts p ON pe.post_id = p.id
                WHERE pe.content_hash != p.content_hash
                  OR pe.updated_at < $1
                GROUP BY p.site_id
            )
            OR s.id NOT IN (SELECT DISTINCT p.site_id FROM post_embeddings pe JOIN posts p ON pe.post_id = p.id)
            LIMIT 10
            """,
            threshold,
        )
    else:
        return []

    return [dict(row) for row in rows]


async def refresh_analytics(site_id: UUID, site: dict) -> dict:
    """Pull fresh GSC + GA4 data for a site.

    Returns: {"gsc_rows": int, "ga4_rows": int}
    """
    pool = await get_pool()
    refresh_token = decrypt_value(site["google_refresh_token"]) if site.get("google_refresh_token") else None

    if not refresh_token:
        return {"gsc_rows": 0, "ga4_rows": 0, "error": "No Google refresh token"}

    result = {"gsc_rows": 0, "ga4_rows": 0}

    async with pool.acquire() as db:
        try:
            if site.get("gsc_site_url"):
                gsc = GSCConnector(
                    site_url=site["gsc_site_url"],
                    refresh_token=refresh_token,
                )
                result["gsc_rows"] = await gsc.sync_metrics(db, site_id)
                logger.info("GSC refresh: %d rows for site %s", result["gsc_rows"], site_id)
        except Exception as e:
            logger.error("GSC refresh failed for site %s: %s", site_id, e)
            result["gsc_error"] = str(e)[:200]

        try:
            if site.get("ga4_property_id"):
                ga4 = GA4Connector(
                    property_id=site["ga4_property_id"],
                    refresh_token=refresh_token,
                )
                result["ga4_rows"] = await ga4.sync_metrics(db, site_id)
                logger.info("GA4 refresh: %d rows for site %s", result["ga4_rows"], site_id)
        except Exception as e:
            logger.error("GA4 refresh failed for site %s: %s", site_id, e)
            result["ga4_error"] = str(e)[:200]

        # Update last sync timestamp
        await db.execute(
            "UPDATE sites SET last_analytics_sync_at = $1 WHERE id = $2",
            datetime.now(timezone.utc), site_id,
        )

    return result


async def recrawl_site(site_id: UUID, site: dict) -> dict:
    """Re-crawl a site, detecting new/updated/deleted posts via content_hash.

    Returns: {"new": int, "updated": int, "deleted": int, "unchanged": int}
    """
    pool = await get_pool()

    # Get existing content hashes
    async with pool.acquire() as db:
        existing_rows = await db.fetch(
            "SELECT id, url, content_hash FROM posts WHERE site_id = $1",
            site_id,
        )
    existing_hashes = {row["url"]: row["content_hash"] for row in existing_rows}
    existing_urls = set(existing_hashes.keys())

    # Crawl fresh content
    cms_type = site.get("cms_type", "sitemap")
    normalized_posts = []

    if cms_type == "wordpress" and site.get("wordpress_url"):
        app_password = decrypt_value(site["wordpress_app_password"]) if site.get("wordpress_app_password") else None
        connector = WordPressConnector(
            base_url=site["wordpress_url"],
            app_password=app_password,
            domain=site["domain"],
        )
        normalized_posts = await connector.fetch_all_posts()
    elif site.get("sitemap_url") or site.get("domain"):
        sitemap_url = site.get("sitemap_url") or f"https://{site['domain']}/sitemap.xml"
        crawler = SitemapCrawler(
            sitemap_url=sitemap_url,
            domain=site["domain"],
            concurrency=10,
        )
        normalized_posts = await crawler.crawl()

    # Compare hashes to detect changes
    crawled_urls = {post.url for post in normalized_posts}
    new_urls = crawled_urls - existing_urls
    deleted_urls = existing_urls - crawled_urls
    common_urls = existing_urls & crawled_urls

    new_count = len(new_urls)
    updated_count = 0
    unchanged_count = 0

    for post in normalized_posts:
        if post.url in common_urls:
            if post.content_hash != existing_hashes.get(post.url):
                updated_count += 1
            else:
                unchanged_count += 1

    # Save all crawled posts (upsert handles new + updated)
    async with pool.acquire() as db:
        saved = await save_normalized_posts(db, site_id, normalized_posts)

        # Soft-mark deleted posts (don't hard delete — they have analytics history)
        if deleted_urls:
            await db.execute(
                """
                UPDATE posts SET
                    http_status = 410,
                    updated_at = NOW()
                WHERE site_id = $1 AND url = ANY($2::text[])
                """,
                site_id, list(deleted_urls),
            )

        await db.execute(
            "UPDATE sites SET last_crawl_at = $1 WHERE id = $2",
            datetime.now(timezone.utc), site_id,
        )

    result = {
        "new": new_count,
        "updated": updated_count,
        "deleted": len(deleted_urls),
        "unchanged": unchanged_count,
        "total_crawled": len(normalized_posts),
    }
    logger.info("Re-crawl site %s: %s", site_id, result)
    return result


async def reembed_changed_posts(site_id: UUID) -> dict:
    """Re-generate embeddings for posts whose content_hash changed since last embed.

    Returns: {"reembedded": int, "skipped": int}
    """
    pool = await get_pool()
    pipeline = EmbeddingPipeline()

    async with pool.acquire() as db:
        # Find posts with stale or missing embeddings
        rows = await db.fetch(
            """
            SELECT p.id, p.content_hash
            FROM posts p
            LEFT JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE p.site_id = $1
              AND p.body_text IS NOT NULL
              AND (pe.id IS NULL OR pe.content_hash != p.content_hash)
            """,
            site_id,
        )

        if not rows:
            return {"reembedded": 0, "skipped": 0}

        logger.info("Re-embedding %d posts for site %s", len(rows), site_id)
        count = await pipeline.generate_for_site(db, site_id)

    return {"reembedded": count, "skipped": 0}


async def run_daily_refresh() -> dict:
    """Daily cron: refresh GSC + GA4 data for all eligible sites."""
    pool = await get_pool()
    results = {"sites_refreshed": 0, "errors": 0}

    async with pool.acquire() as db:
        sites = await get_sites_needing_refresh(db, "analytics_daily")

    for site in sites:
        try:
            await refresh_analytics(site["id"], site)
            results["sites_refreshed"] += 1

            # Run position monitoring after fresh GSC data
            try:
                from app.services.position_monitor import PositionMonitor
                async with pool.acquire() as db:
                    monitor = PositionMonitor()
                    alert_counts = await monitor.check_position_changes(db, site["id"])
                    results.setdefault("position_alerts", 0)
                    results["position_alerts"] += sum(alert_counts.values())
            except Exception as pe:
                logger.error("Position monitor failed for site %s: %s", site["id"], pe)
        except Exception as e:
            logger.error("Daily refresh failed for site %s: %s", site["id"], e)
            results["errors"] += 1

    logger.info("Daily analytics refresh: %s", results)
    return results


async def run_weekly_recrawl() -> dict:
    """Weekly cron: re-crawl sites to detect content changes."""
    pool = await get_pool()
    results = {"sites_recrawled": 0, "new_posts": 0, "updated_posts": 0, "errors": 0}

    async with pool.acquire() as db:
        sites = await get_sites_needing_refresh(db, "crawl_weekly")

    for site in sites:
        try:
            r = await recrawl_site(site["id"], site)
            results["sites_recrawled"] += 1
            results["new_posts"] += r["new"]
            results["updated_posts"] += r["updated"]

            # Check new posts for cannibalization and cluster fit
            if r["new"] > 0:
                try:
                    from app.services.new_content_checker import NewContentChecker
                    async with pool.acquire() as db:
                        # Find new post IDs (posts created in the last hour)
                        new_post_rows = await db.fetch(
                            """
                            SELECT id FROM posts
                            WHERE site_id = $1
                              AND created_at > NOW() - INTERVAL '1 hour'
                            """,
                            site["id"],
                        )
                        if new_post_rows:
                            checker = NewContentChecker()
                            new_ids = [row["id"] for row in new_post_rows]
                            alerts = await checker.check_new_posts(db, site["id"], new_ids)
                            results.setdefault("new_post_alerts", 0)
                            results["new_post_alerts"] += alerts
                except Exception as nce:
                    logger.error("New content check failed for site %s: %s", site["id"], nce)
        except Exception as e:
            logger.error("Weekly recrawl failed for site %s: %s", site["id"], e)
            results["errors"] += 1

    logger.info("Weekly recrawl: %s", results)
    return results


async def run_monthly_reembed() -> dict:
    """Monthly cron: re-embed posts with changed content."""
    pool = await get_pool()
    results = {"sites_reembedded": 0, "total_reembedded": 0, "errors": 0}

    async with pool.acquire() as db:
        sites = await get_sites_needing_refresh(db, "embed_monthly")

    for site in sites:
        try:
            r = await reembed_changed_posts(site["id"])
            results["sites_reembedded"] += 1
            results["total_reembedded"] += r["reembedded"]
        except Exception as e:
            logger.error("Monthly re-embed failed for site %s: %s", site["id"], e)
            results["errors"] += 1

    logger.info("Monthly re-embed: %s", results)
    return results
