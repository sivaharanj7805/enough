"""Content velocity tracking — publishing frequency analysis.

Tracks publishing frequency over time and detects velocity changes.
Research: 3+ posts/week → 3.5x more traffic (HubSpot).
Publishing velocity directly correlates with crawl frequency.

Detects when publishing slows down and flags as a problem.
If a blog published 4 posts/week for 6 months then dropped to
1/month, rankings will decay — we predict and warn about this.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Thresholds
VELOCITY_DECLINE_RATIO = 0.5  # Flag when current < 50% of 90d avg
VELOCITY_GROWTH_RATIO = 1.5   # Growing when current > 150% of 90d avg


class ContentVelocityTracker:
    """Track publishing velocity for a site."""

    async def compute_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict:
        """Compute publishing velocity metrics.

        Returns dict with:
          velocity_30d: posts/week over last 30 days
          velocity_90d: posts/week over last 90 days
          trend: growing, stable, declining
          total_posts: total post count
        """
        logger.info("Computing content velocity for site %s", site_id)
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        ninety_days_ago = now - timedelta(days=90)

        # Count posts published in last 30 days
        count_30d = await db.fetchval(
            """
            SELECT COUNT(*) FROM posts
            WHERE site_id = $1 AND publish_date >= $2
            """,
            site_id, thirty_days_ago,
        ) or 0

        # Count posts published in last 90 days
        count_90d = await db.fetchval(
            """
            SELECT COUNT(*) FROM posts
            WHERE site_id = $1 AND publish_date >= $2
            """,
            site_id, ninety_days_ago,
        ) or 0

        # Total posts
        total = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
        ) or 0

        # Velocity (posts per week)
        velocity_30d = count_30d / (30 / 7)   # ~4.28 weeks
        velocity_90d = count_90d / (90 / 7)   # ~12.86 weeks

        # Determine trend
        if velocity_90d == 0:
            trend = "stable" if velocity_30d == 0 else "growing"
        elif velocity_30d >= velocity_90d * VELOCITY_GROWTH_RATIO:
            trend = "growing"
        elif velocity_30d <= velocity_90d * VELOCITY_DECLINE_RATIO:
            trend = "declining"
        else:
            trend = "stable"

        # Store on sites table
        await db.execute(
            """
            UPDATE sites
            SET publishing_velocity = $1,
                velocity_trend = $2,
                velocity_updated_at = NOW()
            WHERE id = $3
            """,
            velocity_30d, trend, site_id,
        )

        result = {
            "velocity_30d": round(velocity_30d, 2),
            "velocity_90d": round(velocity_90d, 2),
            "trend": trend,
            "count_30d": count_30d,
            "count_90d": count_90d,
            "total_posts": total,
        }

        logger.info("Content velocity for site %s: %s", site_id, result)
        return result
