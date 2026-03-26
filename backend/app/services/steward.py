"""Steward profile — aggregates user stats from existing data.

Optimized: uses batched queries with ANY($1::uuid[]) instead of per-site loops.
"""

import logging

import asyncpg

logger = logging.getLogger(__name__)


class StewardService:
    """Aggregate personal stats for a content steward."""

    async def get_profile(self, db: asyncpg.Connection, user_id: str) -> dict:
        """Build a steward profile from existing data (batched queries)."""
        # Member since
        member_since = await db.fetchval(
            "SELECT created_at FROM profiles WHERE id = $1::uuid",
            user_id,
        )
        member_since_str = (
            member_since.strftime("%Y-%m-%d") if member_since else "Unknown"
        )

        # Get all user site IDs in one query
        site_rows = await db.fetch(
            "SELECT id FROM sites WHERE user_id = $1", user_id
        )
        site_ids = [r["id"] for r in site_rows]

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

        # ── Batch 1: Swamps cleared ──
        swamps_cleared = await db.fetchval(
            """SELECT COUNT(DISTINCT c.id)
               FROM clusters c
               WHERE c.site_id = ANY($1::uuid[])
               AND c.ecosystem_state IN ('forest', 'meadow')
               AND EXISTS (
                 SELECT 1 FROM redirect_log rl
                 WHERE rl.site_id = c.site_id
                 AND rl.old_url IN (
                   SELECT p.url FROM posts p
                   JOIN post_clusters pc ON pc.post_id = p.id
                   WHERE pc.cluster_id = c.id
                 )
               )""",
            site_ids,
        ) or 0

        # ── Batch 2: Deserts revived ──
        deserts_revived = await db.fetchval(
            """SELECT COUNT(*)
               FROM clusters c
               WHERE c.site_id = ANY($1::uuid[])
               AND c.ecosystem_state IN ('meadow', 'forest')
               AND c.post_count <= 3""",
            site_ids,
        ) or 0

        # ── Batch 3: Seedlings planted ──
        seedlings_planted = await db.fetchval(
            """SELECT COUNT(p.id)
               FROM posts p
               JOIN post_clusters pc ON pc.post_id = p.id
               JOIN clusters c ON c.id = pc.cluster_id
               WHERE c.site_id = ANY($1::uuid[]) AND c.ecosystem_state = 'seedbed'""",
            site_ids,
        ) or 0

        # ── Batch 4: Total posts consolidated ──
        total_posts_consolidated = await db.fetchval(
            """SELECT COUNT(*) FROM redirect_log
               WHERE site_id = ANY($1::uuid[]) AND status = 'verified'""",
            site_ids,
        ) or 0

        # ── Batch 5: Total redirects ──
        total_redirects = await db.fetchval(
            "SELECT COUNT(*) FROM redirect_log WHERE site_id = ANY($1::uuid[])",
            site_ids,
        ) or 0

        # ── Batch 6: Estimated traffic recovered ──
        estimated_traffic = await db.fetchval(
            """SELECT COALESCE(SUM(GREATEST(latest_traffic - baseline_traffic, 0)), 0)
               FROM impact_tracking WHERE site_id = ANY($1::uuid[])""",
            site_ids,
        ) or 0

        # ── Batch 7: Efficiency and health improvement ──
        improvement_rows = await db.fetch(
            """SELECT s.id AS site_id,
                      (SELECT health_score FROM report_snapshots WHERE site_id = s.id ORDER BY snapshot_date ASC LIMIT 1) AS first_health,
                      (SELECT health_score FROM report_snapshots WHERE site_id = s.id ORDER BY snapshot_date DESC LIMIT 1) AS latest_health,
                      (SELECT efficiency_ratio FROM report_snapshots WHERE site_id = s.id ORDER BY snapshot_date ASC LIMIT 1) AS first_eff,
                      (SELECT efficiency_ratio FROM report_snapshots WHERE site_id = s.id ORDER BY snapshot_date DESC LIMIT 1) AS latest_eff
               FROM sites s
               WHERE s.id = ANY($1::uuid[])""",
            site_ids,
        )

        efficiency_improvement = 0.0
        health_improvement = 0.0
        for r in improvement_rows:
            if r["first_eff"] is not None and r["latest_eff"] is not None:
                efficiency_improvement += float(r["latest_eff"]) - float(r["first_eff"])
            if r["first_health"] is not None and r["latest_health"] is not None:
                health_improvement += float(r["latest_health"]) - float(r["first_health"])

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
