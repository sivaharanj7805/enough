"""SERP URL fluctuation detection — the strongest cannibalization signal.

When Google alternates between ranking different URLs from the same site
for the same query, it means Google literally cannot decide which page
is the canonical answer. This is active cannibalization happening in
real-time.

Detection approach:
1. Record which URL GSC reports for each query, daily
2. For each query, count distinct URLs in the last 30 days
3. If URL changes ≥3 times in 30 days → active cannibalization
4. Severity based on impressions volume and fluctuation frequency

This signal is the strongest because:
- Cosine similarity shows POTENTIAL cannibalization (similar content)
- GSC query overlap shows PASSIVE cannibalization (same keywords)
- URL fluctuation shows ACTIVE cannibalization (Google is confused RIGHT NOW)
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Thresholds
MIN_FLUCTUATIONS = 3       # URL must change at least 3 times
WINDOW_DAYS = 30           # Look-back window
MIN_IMPRESSIONS = 20       # Ignore low-volume queries


@dataclass
class URLFluctuation:
    """A query where Google alternates ranking URLs."""
    query: str
    urls_involved: list[str]
    fluctuation_count: int
    avg_position: float
    total_impressions: int
    severity: str  # critical/high/medium


class URLFluctuationDetector:
    """Detects active cannibalization from SERP URL fluctuations."""

    async def record_daily_urls(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> int:
        """Record today's URL-per-query from GSC metrics.

        Should be called daily after GSC data refresh.
        Returns number of query-URL pairs recorded.
        """
        # Get latest GSC data — for each query, which URL ranks
        # GSC can report multiple URLs per query; take the one with highest clicks
        rows = await db.fetch(
            """
            SELECT DISTINCT ON (gm.query)
                gm.query,
                p.url,
                gm.position,
                gm.impressions,
                gm.clicks
            FROM gsc_metrics gm
            JOIN posts p ON p.id = gm.post_id
            WHERE p.site_id = $1
              AND gm.impressions >= $2
            ORDER BY gm.query, gm.clicks DESC, gm.impressions DESC
            """,
            site_id, MIN_IMPRESSIONS,
        )

        recorded = 0
        today = date.today()

        for row in rows:
            await db.execute(
                """
                INSERT INTO gsc_query_urls
                    (site_id, query, url, position, impressions, clicks, recorded_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (site_id, query, recorded_date) DO UPDATE SET
                    url = $3, position = $4, impressions = $5, clicks = $6
                """,
                site_id, row["query"], row["url"],
                row["position"], row["impressions"], row["clicks"], today,
            )
            recorded += 1

        logger.info("Recorded %d query-URL pairs for site %s", recorded, site_id)
        return recorded

    async def detect_fluctuations(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        window_days: int = WINDOW_DAYS,
        min_fluctuations: int = MIN_FLUCTUATIONS,
    ) -> list[URLFluctuation]:
        """Detect queries where the ranking URL keeps changing.

        Looks at the last `window_days` of gsc_query_urls data.
        For each query, counts how many distinct URLs appeared.
        If ≥ min_fluctuations different URLs → active cannibalization.

        Returns list of fluctuations found, also stored in url_fluctuations table.
        """
        cutoff = date.today() - timedelta(days=window_days)

        # Find queries with multiple distinct URLs in the window
        fluctuating_queries = await db.fetch(
            """
            SELECT
                query,
                array_agg(DISTINCT url) AS urls,
                COUNT(DISTINCT url) AS url_count,
                AVG(position) AS avg_position,
                SUM(impressions) AS total_impressions
            FROM gsc_query_urls
            WHERE site_id = $1
              AND recorded_date >= $2
            GROUP BY query
            HAVING COUNT(DISTINCT url) >= $3
            ORDER BY SUM(impressions) DESC
            """,
            site_id, cutoff, min_fluctuations,
        )

        # Clear old detections
        await db.execute(
            "DELETE FROM url_fluctuations WHERE site_id = $1", site_id,
        )

        results: list[URLFluctuation] = []

        for row in fluctuating_queries:
            url_count = row["url_count"]
            total_impressions = row["total_impressions"] or 0

            # Severity based on volume and fluctuation frequency
            if url_count >= 5 or total_impressions >= 1000:
                severity = "critical"
            elif url_count >= 4 or total_impressions >= 500:
                severity = "high"
            else:
                severity = "medium"

            fluct = URLFluctuation(
                query=row["query"],
                urls_involved=row["urls"],
                fluctuation_count=url_count,
                avg_position=float(row["avg_position"] or 0),
                total_impressions=total_impressions,
                severity=severity,
            )
            results.append(fluct)

            # Store in DB
            await db.execute(
                """
                INSERT INTO url_fluctuations
                    (site_id, query, urls_involved, fluctuation_count,
                     window_days, avg_position, total_impressions, severity)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (site_id, query) DO UPDATE SET
                    urls_involved = $3, fluctuation_count = $4,
                    avg_position = $6, total_impressions = $7,
                    severity = $8, detected_at = NOW()
                """,
                site_id, fluct.query, fluct.urls_involved,
                fluct.fluctuation_count, window_days,
                fluct.avg_position, fluct.total_impressions,
                fluct.severity,
            )

        logger.info("Detected %d URL fluctuations for site %s",
                     len(results), site_id)
        return results

    async def get_fluctuations(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> list[dict]:
        """Get stored URL fluctuations for a site."""
        rows = await db.fetch(
            """
            SELECT query, urls_involved, fluctuation_count,
                   avg_position, total_impressions, severity, detected_at
            FROM url_fluctuations
            WHERE site_id = $1
            ORDER BY total_impressions DESC
            """,
            site_id,
        )
        return [dict(r) for r in rows]
