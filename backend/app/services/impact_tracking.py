"""Impact tracking — prove ROI of recommendations.

When a user marks a recommendation as "completed," this service:
1. Snapshots the current state (health score, traffic, position, problems)
2. Stores it as the "before" baseline
3. On subsequent pipeline runs, updates the "after" metrics
4. Computes the delta to prove whether the recommendation worked

This is what justifies the subscription. "You followed 5 recommendations
last month → traffic increased 23%."

Monthly impact reports aggregate all completed recommendations to show
cumulative value.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class ImpactTracker:
    """Track before/after impact of completed recommendations."""

    async def record_completion(
        self,
        db: asyncpg.Connection,
        recommendation_id: UUID,
    ) -> dict | None:
        """Record baseline metrics when a recommendation is completed.

        Called when recommendation status changes to 'completed'.
        Returns the impact record or None if recommendation not found.
        """
        rec = await db.fetchrow(
            """
            SELECT r.id, r.post_id, cp.site_id
            FROM recommendations r
            JOIN content_problems cp ON cp.id = r.problem_id
            WHERE r.id = $1
            """,
            recommendation_id,
        )

        if not rec:
            logger.warning("Recommendation %s not found", recommendation_id)
            return None

        post_id = rec["post_id"]
        site_id = rec["site_id"]
        now = datetime.now(timezone.utc)

        # Get current metrics as "before" baseline
        metrics = await db.fetchrow(
            """
            SELECT
                ph.composite_score,
                (SELECT COALESCE(SUM(g.clicks), 0) FROM gsc_metrics g
                 WHERE g.post_id = $1 AND g.date >= CURRENT_DATE - 30) AS traffic_30d,
                (SELECT AVG(g.avg_position) FROM gsc_metrics g
                 WHERE g.post_id = $1 AND g.date >= CURRENT_DATE - 30) AS avg_position,
                (SELECT COUNT(*) FROM content_problems cp
                 WHERE cp.post_id = $1) AS problems_count
            FROM post_health_scores ph
            WHERE ph.post_id = $1
            """,
            post_id,
        )

        health_before = float(metrics["composite_score"] or 0) if metrics else 0
        traffic_before = metrics["traffic_30d"] if metrics else 0
        position_before = float(metrics["avg_position"] or 0) if metrics else 0
        problems_before = metrics["problems_count"] if metrics else 0

        impact_id = await db.fetchval(
            """
            INSERT INTO recommendation_impacts
                (recommendation_id, post_id, site_id, completed_at,
                 health_score_before, traffic_before, position_before,
                 problems_before)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            recommendation_id, post_id, site_id, now,
            health_before, traffic_before, position_before, problems_before,
        )

        logger.info(
            "Recorded completion baseline for recommendation %s: "
            "health=%s, traffic=%s, position=%s",
            recommendation_id, health_before, traffic_before, position_before,
        )

        return {
            "impact_id": impact_id,
            "health_before": health_before,
            "traffic_before": traffic_before,
            "position_before": position_before,
        }

    async def update_impacts(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> int:
        """Update "after" metrics for all completed recommendations.

        Should be called after each pipeline run (weekly).
        Returns number of impacts updated.
        """
        # Get all impacts that need measuring (completed > 7 days ago)
        impacts = await db.fetch(
            """
            SELECT ri.id, ri.post_id, ri.recommendation_id,
                   ri.health_score_before, ri.traffic_before,
                   ri.position_before, ri.problems_before
            FROM recommendation_impacts ri
            WHERE ri.site_id = $1
              AND ri.completed_at < NOW() - INTERVAL '7 days'
            """,
            site_id,
        )

        updated = 0
        for impact in impacts:
            post_id = impact["post_id"]

            # Get current metrics
            current = await db.fetchrow(
                """
                SELECT
                    ph.composite_score,
                    (SELECT COALESCE(SUM(g.clicks), 0) FROM gsc_metrics g
                     WHERE g.post_id = $1 AND g.date >= CURRENT_DATE - 30) AS traffic_30d,
                    (SELECT AVG(g.avg_position) FROM gsc_metrics g
                     WHERE g.post_id = $1 AND g.date >= CURRENT_DATE - 30) AS avg_position,
                    (SELECT COUNT(*) FROM content_problems cp
                     WHERE cp.post_id = $1) AS problems_count
                FROM post_health_scores ph
                WHERE ph.post_id = $1
                """,
                post_id,
            )

            if not current:
                continue

            health_after = float(current["composite_score"] or 0)
            traffic_after = current["traffic_30d"]
            position_after = float(current["avg_position"] or 0)
            problems_after = current["problems_count"]

            # Compute changes
            health_change = health_after - (impact["health_score_before"] or 0)
            traffic_before = impact["traffic_before"] or 0
            traffic_change_pct = (
                ((traffic_after - traffic_before) / max(traffic_before, 1)) * 100
                if traffic_before > 0 else 0
            )
            position_change = (impact["position_before"] or 0) - position_after  # Positive = improved

            await db.execute(
                """
                UPDATE recommendation_impacts SET
                    health_score_after = $1, traffic_after = $2,
                    position_after = $3, problems_after = $4,
                    health_change = $5, traffic_change_pct = $6,
                    position_change = $7, last_measured_at = NOW()
                WHERE id = $8
                """,
                health_after, traffic_after, position_after, problems_after,
                health_change, traffic_change_pct, position_change,
                impact["id"],
            )
            updated += 1

        logger.info("Updated %d impact measurements for site %s", updated, site_id)
        return updated

    async def get_monthly_report(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> dict:
        """Generate a monthly impact summary.

        Returns aggregate stats for all completed recommendations
        in the last 30 days.
        """
        report = await db.fetchrow(
            """
            SELECT
                COUNT(*) AS total_completed,
                AVG(health_change) AS avg_health_change,
                AVG(traffic_change_pct) AS avg_traffic_change_pct,
                AVG(position_change) AS avg_position_improvement,
                SUM(CASE WHEN health_change > 0 THEN 1 ELSE 0 END) AS improved,
                SUM(CASE WHEN health_change <= 0 THEN 1 ELSE 0 END) AS unchanged_or_worse
            FROM recommendation_impacts
            WHERE site_id = $1
              AND completed_at >= NOW() - INTERVAL '30 days'
              AND health_score_after IS NOT NULL
            """,
            site_id,
        )

        if not report or report["total_completed"] == 0:
            return {
                "total_completed": 0,
                "message": "No completed recommendations to measure yet.",
            }

        return {
            "total_completed": report["total_completed"],
            "avg_health_improvement": round(report["avg_health_change"] or 0, 1),
            "avg_traffic_change_pct": round(report["avg_traffic_change_pct"] or 0, 1),
            "avg_position_improvement": round(report["avg_position_improvement"] or 0, 1),
            "success_rate": round(
                (report["improved"] or 0) / max(report["total_completed"], 1) * 100, 1,
            ),
            "improved_count": report["improved"] or 0,
        }
