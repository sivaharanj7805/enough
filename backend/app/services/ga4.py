"""Google Analytics 4 connector.

Uses the GA4 Data API to fetch per-URL metrics (pageviews, sessions,
engagement) with incremental sync support.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
)
from google.oauth2.credentials import Credentials

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class GA4Connector:
    """Fetch GA4 metrics and store them per-post."""

    def __init__(self, property_id: str, refresh_token: str):
        self.property_id = property_id
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

    def _get_client(self) -> BetaAnalyticsDataClient:
        """Create an authenticated GA4 Data API client."""
        credentials = self._get_credentials()
        return BetaAnalyticsDataClient(credentials=credentials)

    async def sync_metrics(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Sync GA4 metrics for all posts in a site.

        Uses incremental sync: only fetches data from the last sync date.
        Returns the number of metric rows upserted.
        """
        # Determine date range
        last_sync = await db.fetchval(
            "SELECT MAX(date) FROM ga4_metrics g JOIN posts p ON p.id = g.post_id WHERE p.site_id = $1",
            site_id,
        )
        start_date = last_sync + timedelta(days=1) if last_sync else date.today() - timedelta(days=90)
        end_date = date.today() - timedelta(days=1)  # Yesterday (GA4 data has ~24h lag)

        if start_date > end_date:
            logger.info("GA4: no new dates to sync for site %s", site_id)
            return 0

        # Fetch post URL mapping
        post_rows = await db.fetch(
            "SELECT id, url FROM posts WHERE site_id = $1", site_id,
        )
        if not post_rows:
            logger.info("GA4: no posts found for site %s", site_id)
            return 0

        # Build URL path → post_id map
        from urllib.parse import urlparse
        url_map: dict[str, UUID] = {}
        for row in post_rows:
            parsed = urlparse(row["url"])
            path = parsed.path.rstrip("/") or "/"
            url_map[path] = row["id"]

        # Fetch GA4 data
        client = self._get_client()
        total_upserted = 0
        offset = 0
        limit = 10000

        while True:
            await self.rate_limiter.wait()

            request = RunReportRequest(
                property=f"properties/{self.property_id}",
                date_ranges=[DateRange(
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )],
                dimensions=[
                    Dimension(name="pagePath"),
                    Dimension(name="date"),
                ],
                metrics=[
                    Metric(name="screenPageViews"),
                    Metric(name="sessions"),
                    Metric(name="engagedSessions"),
                    Metric(name="averageSessionDuration"),
                    Metric(name="bounceRate"),
                    Metric(name="conversions"),
                ],
                offset=offset,
                limit=limit,
            )

            try:
                response = client.run_report(request)
            except Exception as e:
                logger.error("GA4 API error: %s", e)
                break

            if not response.rows:
                break

            for row in response.rows:
                page_path = row.dimension_values[0].value.rstrip("/") or "/"
                date_str = row.dimension_values[1].value

                post_id = url_map.get(page_path)
                if not post_id:
                    continue

                metric_date = datetime.strptime(date_str, "%Y%m%d").date()

                try:
                    await db.execute(
                        """
                        INSERT INTO ga4_metrics (
                            post_id, date, pageviews, sessions,
                            engaged_sessions, avg_engagement_time_seconds,
                            bounce_rate, conversions
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (post_id, date) DO UPDATE SET
                            pageviews = EXCLUDED.pageviews,
                            sessions = EXCLUDED.sessions,
                            engaged_sessions = EXCLUDED.engaged_sessions,
                            avg_engagement_time_seconds = EXCLUDED.avg_engagement_time_seconds,
                            bounce_rate = EXCLUDED.bounce_rate,
                            conversions = EXCLUDED.conversions
                        """,
                        post_id,
                        metric_date,
                        int(row.metric_values[0].value),
                        int(row.metric_values[1].value),
                        int(row.metric_values[2].value),
                        float(row.metric_values[3].value),
                        float(row.metric_values[4].value),
                        int(row.metric_values[5].value),
                    )
                    total_upserted += 1
                except Exception as e:
                    logger.warning("Failed to upsert GA4 metric for %s on %s: %s", page_path, date_str, e)

            if len(response.rows) < limit:
                break
            offset += limit

        logger.info("GA4: upserted %d metric rows for site %s", total_upserted, site_id)
        return total_upserted
