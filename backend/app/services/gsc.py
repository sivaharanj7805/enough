"""Google Search Console connector.

Uses the Search Console API to fetch per-URL search performance data
(queries, impressions, clicks, CTR, position) with incremental sync.
"""

import logging
from datetime import date, timedelta
from uuid import UUID
from urllib.parse import urlparse

import asyncpg
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# GSC returns max 25,000 rows per request
GSC_ROW_LIMIT = 25000


class GSCConnector:
    """Fetch Google Search Console data and store per-post."""

    def __init__(self, site_url: str, refresh_token: str):
        self.site_url = site_url
        self.refresh_token = refresh_token
        self.rate_limiter = RateLimiter(requests_per_second=2)

    def _get_credentials(self) -> Credentials:
        """Build Google credentials from refresh token."""
        settings = get_settings()
        return Credentials(
            token=None,
            refresh_token=self.refresh_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

    def _get_service(self):
        """Create an authenticated Search Console API service."""
        credentials = self._get_credentials()
        return build("searchconsole", "v1", credentials=credentials)

    async def sync_metrics(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Sync GSC search analytics for all posts in a site.

        Incrementally fetches data from the last sync date.
        Returns the number of metric rows upserted.
        """
        # Determine date range
        last_sync = await db.fetchval(
            "SELECT MAX(date) FROM gsc_metrics g JOIN posts p ON p.id = g.post_id WHERE p.site_id = $1",
            site_id,
        )
        start_date = last_sync + timedelta(days=1) if last_sync else date.today() - timedelta(days=90)
        end_date = date.today() - timedelta(days=3)  # GSC data has ~3 day lag

        if start_date > end_date:
            logger.info("GSC: no new dates to sync for site %s", site_id)
            return 0

        # Fetch post URL mapping
        post_rows = await db.fetch(
            "SELECT id, url FROM posts WHERE site_id = $1", site_id,
        )
        if not post_rows:
            logger.info("GSC: no posts found for site %s", site_id)
            return 0

        # Build URL → post_id map (normalized paths)
        url_map: dict[str, UUID] = {}
        for row in post_rows:
            url_map[row["url"].rstrip("/")] = row["id"]
            # Also map without trailing slash variations
            parsed = urlparse(row["url"])
            path = parsed.path.rstrip("/") or "/"
            url_map[f"{parsed.scheme}://{parsed.netloc}{path}"] = row["id"]

        service = self._get_service()
        total_upserted = 0
        start_row = 0

        while True:
            await self.rate_limiter.wait()

            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["page", "query", "date"],
                "rowLimit": GSC_ROW_LIMIT,
                "startRow": start_row,
            }

            try:
                response = service.searchanalytics().query(
                    siteUrl=self.site_url, body=request_body
                ).execute()
            except Exception as e:
                logger.error("GSC API error: %s", e)
                break

            rows = response.get("rows", [])
            if not rows:
                break

            for row in rows:
                page_url = row["keys"][0].rstrip("/")
                query = row["keys"][1]
                date_str = row["keys"][2]

                # Find matching post
                post_id = url_map.get(page_url)
                if not post_id:
                    continue

                metric_date = date.fromisoformat(date_str)

                try:
                    await db.execute(
                        """
                        INSERT INTO gsc_metrics (
                            post_id, date, query, impressions,
                            clicks, avg_position, ctr
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (post_id, date, query) DO UPDATE SET
                            impressions = EXCLUDED.impressions,
                            clicks = EXCLUDED.clicks,
                            avg_position = EXCLUDED.avg_position,
                            ctr = EXCLUDED.ctr
                        """,
                        post_id,
                        metric_date,
                        query,
                        row.get("impressions", 0),
                        row.get("clicks", 0),
                        row.get("position"),
                        row.get("ctr", 0),
                    )
                    total_upserted += 1
                except Exception as e:
                    logger.warning(
                        "Failed to upsert GSC metric for %s query=%s: %s",
                        page_url, query, e,
                    )

            if len(rows) < GSC_ROW_LIMIT:
                break
            start_row += GSC_ROW_LIMIT

        logger.info("GSC: upserted %d metric rows for site %s", total_upserted, site_id)
        return total_upserted
