"""Consolidation impact tracking with 30/60/90 day milestones."""

import logging
from datetime import date
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class ImpactTracker:
    """Track the impact of content consolidations over time."""

    async def start_tracking(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        cluster_id: UUID | None,
        consolidated_urls: list[str],
        pillar_url: str,
    ) -> UUID:
        """Create an impact tracking record with baseline metrics."""
        # Get baseline traffic for the pillar URL
        baseline_traffic = await db.fetchval(
            """SELECT COALESCE(SUM(g.sessions), 0)
               FROM ga4_metrics g
               JOIN posts p ON p.id = g.post_id
               WHERE p.site_id = $1 AND p.url = $2
               AND g.date >= CURRENT_DATE - INTERVAL '30 days'""",
            site_id,
            pillar_url,
        ) or 0

        # Get baseline avg position
        baseline_position = await db.fetchval(
            """SELECT AVG(gs.avg_position)
               FROM gsc_metrics gs
               JOIN posts p ON p.id = gs.post_id
               WHERE p.site_id = $1 AND p.url = $2
               AND gs.date >= CURRENT_DATE - INTERVAL '30 days'""",
            site_id,
            pillar_url,
        )

        tracking_id = await db.fetchval(
            """INSERT INTO impact_tracking
               (site_id, cluster_id, pillar_url, consolidated_urls,
                baseline_traffic, baseline_avg_position, baseline_date)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id""",
            site_id,
            cluster_id,
            pillar_url,
            consolidated_urls,
            baseline_traffic,
            float(baseline_position) if baseline_position else None,
            date.today(),
        )

        logger.info(
            "Started impact tracking %s for pillar %s (baseline: %d sessions, pos: %s)",
            tracking_id,
            pillar_url,
            baseline_traffic,
            baseline_position,
        )
        return tracking_id

    async def check_impact(self, db: asyncpg.Connection, tracking_id: UUID) -> dict:
        """Compare current metrics to baseline for a tracking record."""
        tracking = await db.fetchrow(
            "SELECT * FROM impact_tracking WHERE id = $1", tracking_id
        )
        if not tracking:
            raise ValueError(f"Tracking {tracking_id} not found")

        t = dict(tracking)
        site_id = t["site_id"]
        pillar_url = t["pillar_url"]

        # Current traffic (last 30 days)
        current_traffic = await db.fetchval(
            """SELECT COALESCE(SUM(g.sessions), 0)
               FROM ga4_metrics g
               JOIN posts p ON p.id = g.post_id
               WHERE p.site_id = $1 AND p.url = $2
               AND g.date >= CURRENT_DATE - INTERVAL '30 days'""",
            site_id,
            pillar_url,
        ) or 0

        # Current avg position
        current_position = await db.fetchval(
            """SELECT AVG(gs.avg_position)
               FROM gsc_metrics gs
               JOIN posts p ON p.id = gs.post_id
               WHERE p.site_id = $1 AND p.url = $2
               AND gs.date >= CURRENT_DATE - INTERVAL '30 days'""",
            site_id,
            pillar_url,
        )

        # Check redirects working
        redirects_working = await db.fetchval(
            """SELECT COUNT(*) FROM redirect_log
               WHERE site_id = $1 AND status = 'verified'
               AND old_url = ANY($2)""",
            site_id,
            t["consolidated_urls"],
        ) or 0

        # Calculate days since
        days_since = (date.today() - t["baseline_date"]).days

        # Determine milestone
        milestone = None
        if days_since >= 90:
            milestone = "90d"
        elif days_since >= 60:
            milestone = "60d"
        elif days_since >= 30:
            milestone = "30d"

        # Traffic change
        baseline = t["baseline_traffic"] or 0
        traffic_change = current_traffic - baseline
        traffic_change_pct = (traffic_change / baseline * 100) if baseline > 0 else 0.0

        # Update tracking record
        await db.execute(
            """UPDATE impact_tracking
               SET latest_traffic = $1, latest_avg_position = $2,
                   latest_check_date = $3, traffic_change_pct = $4,
                   status = CASE WHEN $5 >= 90 THEN 'complete' ELSE 'tracking' END
               WHERE id = $6""",
            current_traffic,
            float(current_position) if current_position else None,
            date.today(),
            traffic_change_pct,
            days_since,
            tracking_id,
        )

        # Save snapshot if at a milestone boundary
        if milestone:
            existing = await db.fetchval(
                """SELECT id FROM impact_snapshots
                   WHERE tracking_id = $1 AND milestone = $2""",
                tracking_id,
                milestone,
            )
            if not existing:
                await db.execute(
                    """INSERT INTO impact_snapshots
                       (tracking_id, snapshot_date, traffic, avg_position,
                        redirects_working, milestone)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    tracking_id,
                    date.today(),
                    current_traffic,
                    float(current_position) if current_position else None,
                    redirects_working,
                    milestone,
                )

        return {
            "tracking_id": tracking_id,
            "cluster_id": t["cluster_id"],
            "pillar_url": pillar_url,
            "baseline_traffic": baseline,
            "current_traffic": current_traffic,
            "traffic_change": traffic_change,
            "traffic_change_pct": round(traffic_change_pct, 1),
            "baseline_avg_position": float(t["baseline_avg_position"]) if t["baseline_avg_position"] else None,
            "current_avg_position": float(current_position) if current_position else None,
            "position_change": (
                round(float(t["baseline_avg_position"]) - float(current_position), 1)
                if t.get("baseline_avg_position") is not None and current_position is not None
                else None
            ),
            "consolidated_urls_count": len(t["consolidated_urls"]),
            "redirects_working": redirects_working,
            "days_since_consolidation": days_since,
            "status": "complete" if days_since >= 90 else "tracking",
            "milestone": milestone,
        }

    async def check_all_active(self, db: asyncpg.Connection) -> list[dict]:
        """Check all active trackings (for cron job)."""
        rows = await db.fetch(
            "SELECT id FROM impact_tracking WHERE status = 'tracking'"
        )
        results = []
        for row in rows:
            try:
                result = await self.check_impact(db, row["id"])
                results.append(result)
            except Exception as e:
                logger.error("Failed to check impact %s: %s", row["id"], e)
        return results

    async def generate_impact_card(
        self, db: asyncpg.Connection, tracking_id: UUID
    ) -> dict:
        """Generate a shareable impact summary."""
        tracking = await db.fetchrow(
            "SELECT * FROM impact_tracking WHERE id = $1", tracking_id
        )
        if not tracking:
            raise ValueError(f"Tracking {tracking_id} not found")

        t = dict(tracking)
        days_since = (date.today() - t["baseline_date"]).days
        baseline = t["baseline_traffic"] or 0
        current = t["latest_traffic"] or 0
        change = current - baseline
        change_pct = (change / baseline * 100) if baseline > 0 else 0.0
        posts_count = len(t["consolidated_urls"])

        # Redirects working
        redirects_working = await db.fetchval(
            """SELECT COUNT(*) FROM redirect_log
               WHERE site_id = $1 AND status = 'verified'
               AND old_url = ANY($2)""",
            t["site_id"],
            t["consolidated_urls"],
        ) or 0

        headline = f"{'📈' if change >= 0 else '📉'} Consolidation Impact: {abs(change_pct):.0f}% {'increase' if change >= 0 else 'decrease'}"

        summary = (
            f"You consolidated {posts_count} posts into 1 on {t['baseline_date'].strftime('%B %d')}. "
            f"In {days_since} days: pillar traffic {'+' if change >= 0 else ''}{change_pct:.0f}%. "
            f"{redirects_working} redirects passing authority correctly. "
            f"Net: {'+' if change >= 0 else ''}{change:,} monthly sessions from fewer posts."
        )

        return {
            "tracking_id": tracking_id,
            "headline": headline,
            "pillar_url": t["pillar_url"],
            "days_since": days_since,
            "traffic_change": change,
            "traffic_change_pct": round(change_pct, 1),
            "posts_consolidated": posts_count,
            "redirects_working": redirects_working,
            "summary": summary,
        }

    async def get_all_for_site(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> list[dict]:
        """Get all impact trackings for a site."""
        rows = await db.fetch(
            """SELECT id, site_id, cluster_id, pillar_url, consolidated_urls,
                      baseline_traffic, baseline_avg_position, baseline_date,
                      latest_traffic, latest_avg_position, latest_check_date,
                      traffic_change_pct, status, created_at
               FROM impact_tracking
               WHERE site_id = $1
               ORDER BY created_at DESC""",
            site_id,
        )
        results = []
        for r in rows:
            d = dict(r)
            d["days_since"] = (date.today() - d["baseline_date"]).days
            results.append(d)
        return results

    async def get_detail(
        self, db: asyncpg.Connection, tracking_id: UUID
    ) -> dict:
        """Get detailed impact tracking with snapshots."""
        tracking = await db.fetchrow(
            """SELECT id, site_id, cluster_id, pillar_url, consolidated_urls,
                      baseline_traffic, baseline_avg_position, baseline_date,
                      latest_traffic, latest_avg_position, latest_check_date,
                      traffic_change_pct, status, created_at
               FROM impact_tracking WHERE id = $1""",
            tracking_id,
        )
        if not tracking:
            raise ValueError(f"Tracking {tracking_id} not found")

        t = dict(tracking)
        t["days_since"] = (date.today() - t["baseline_date"]).days

        snapshots = await db.fetch(
            """SELECT snapshot_date, traffic, avg_position,
                      redirects_working, milestone
               FROM impact_snapshots
               WHERE tracking_id = $1
               ORDER BY snapshot_date ASC""",
            tracking_id,
        )

        return {
            "tracking": t,
            "snapshots": [dict(s) for s in snapshots],
        }
