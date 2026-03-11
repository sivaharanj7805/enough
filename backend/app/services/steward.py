"""Steward profile — aggregates user stats from existing data."""

import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class StewardService:
    """Aggregate personal stats for a content steward."""

    async def get_profile(self, db: asyncpg.Connection, user_id: str) -> dict:
        """Build a steward profile from existing data."""
        # Member since
        member_since = await db.fetchval(
            "SELECT created_at FROM profiles WHERE id = $1::uuid",
            user_id,
        )
        member_since_str = (
            member_since.strftime("%Y-%m-%d") if member_since else "Unknown"
        )

        # Get all user site IDs
        site_ids = [
            r["id"]
            for r in await db.fetch(
                "SELECT id FROM sites WHERE user_id = $1", user_id
            )
        ]

        if not site_ids:
            return {
                "user_id": user_id,
                "member_since": member_since_str,
                "swamps_cleared": 0,
                "deserts_revived": 0,
                "seedlings_planted": 0,
                "total_posts_consolidated": 0,
                "total_redirects_created": 0,
                "estimated_traffic_recovered": 0,
                "efficiency_improvement": 0.0,
                "health_improvement": 0.0,
            }

        # Swamps cleared: clusters once 'swamp' that are now forest/meadow
        # We approximate this by counting clusters that are forest/meadow and have
        # consolidation activity (redirects pushed)
        swamps_cleared = 0
        for sid in site_ids:
            count = await db.fetchval(
                """SELECT COUNT(DISTINCT c.id)
                   FROM clusters c
                   WHERE c.site_id = $1
                   AND c.ecosystem_state IN ('forest', 'meadow')
                   AND EXISTS (
                     SELECT 1 FROM redirect_log rl
                     WHERE rl.site_id = $1
                     AND rl.old_url IN (
                       SELECT p.url FROM posts p WHERE p.cluster_id = c.id
                     )
                   )""",
                sid,
            ) or 0
            swamps_cleared += count

        # Deserts revived: desert clusters that became meadow or better
        # Approximation: count meadow/seedbed clusters with low post counts
        deserts_revived = 0
        for sid in site_ids:
            count = await db.fetchval(
                """SELECT COUNT(*)
                   FROM clusters c
                   WHERE c.site_id = $1
                   AND c.ecosystem_state IN ('meadow', 'forest')
                   AND (SELECT COUNT(*) FROM posts p WHERE p.cluster_id = c.id) <= 3""",
                sid,
            ) or 0
            deserts_revived += count

        # Seedlings planted: posts in seedbed clusters
        seedlings_planted = 0
        for sid in site_ids:
            count = await db.fetchval(
                """SELECT COUNT(p.id)
                   FROM posts p
                   JOIN clusters c ON c.id = p.cluster_id
                   WHERE c.site_id = $1 AND c.ecosystem_state = 'seedbed'""",
                sid,
            ) or 0
            seedlings_planted += count

        # Total posts consolidated (from impact tracking)
        total_posts_consolidated = 0
        for sid in site_ids:
            count = await db.fetchval(
                """SELECT COALESCE(SUM(array_length(consolidated_urls, 1)), 0)
                   FROM impact_tracking WHERE site_id = $1""",
                sid,
            ) or 0
            total_posts_consolidated += count

        # Total redirects created
        total_redirects = 0
        for sid in site_ids:
            count = await db.fetchval(
                "SELECT COUNT(*) FROM redirect_log WHERE site_id = $1",
                sid,
            ) or 0
            total_redirects += count

        # Estimated traffic recovered (from impact tracking)
        estimated_traffic = 0
        for sid in site_ids:
            val = await db.fetchval(
                """SELECT COALESCE(SUM(GREATEST(latest_traffic - baseline_traffic, 0)), 0)
                   FROM impact_tracking WHERE site_id = $1""",
                sid,
            ) or 0
            estimated_traffic += val

        # Efficiency improvement: compare earliest vs latest report snapshots
        efficiency_improvement = 0.0
        health_improvement = 0.0
        for sid in site_ids:
            first = await db.fetchrow(
                """SELECT health_score, efficiency_ratio
                   FROM report_snapshots WHERE site_id = $1
                   ORDER BY snapshot_date ASC LIMIT 1""",
                sid,
            )
            latest = await db.fetchrow(
                """SELECT health_score, efficiency_ratio
                   FROM report_snapshots WHERE site_id = $1
                   ORDER BY snapshot_date DESC LIMIT 1""",
                sid,
            )
            if first and latest:
                if first["efficiency_ratio"] is not None and latest["efficiency_ratio"] is not None:
                    efficiency_improvement += latest["efficiency_ratio"] - first["efficiency_ratio"]
                if first["health_score"] is not None and latest["health_score"] is not None:
                    health_improvement += latest["health_score"] - first["health_score"]

        return {
            "user_id": user_id,
            "member_since": member_since_str,
            "swamps_cleared": swamps_cleared,
            "deserts_revived": deserts_revived,
            "seedlings_planted": seedlings_planted,
            "total_posts_consolidated": total_posts_consolidated,
            "total_redirects_created": total_redirects,
            "estimated_traffic_recovered": estimated_traffic,
            "efficiency_improvement": round(efficiency_improvement, 1),
            "health_improvement": round(health_improvement, 1),
        }
