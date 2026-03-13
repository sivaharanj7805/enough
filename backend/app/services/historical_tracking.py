"""Historical tracking — weekly snapshots and change detection.

Takes weekly snapshots of health scores, traffic, and metrics at
post, cluster, and site level. Detects changes between snapshots
to surface trends and generate alerts.

This is THE feature that turns a one-time audit into a dashboard.
Without it, users run analysis once and leave. With it, they
check daily to see what changed.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class HistoricalTracker:
    """Take snapshots and detect changes."""

    async def take_snapshot(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict:
        """Take a point-in-time snapshot of all metrics.

        Should be called weekly (via cron or after pipeline run).
        Returns summary of what was snapshotted.
        """
        today = date.today()
        logger.info("Taking snapshot for site %s on %s", site_id, today)

        # ── Post-level snapshots ──
        posts = await db.fetch(
            """
            SELECT p.id, p.site_id,
                   ph.composite_score, ph.trend, ph.role,
                   (SELECT COALESCE(SUM(g.clicks), 0) FROM gsc_metrics g
                    WHERE g.post_id = p.id
                    AND g.date >= CURRENT_DATE - 30) AS traffic_30d,
                   (SELECT AVG(g.avg_position) FROM gsc_metrics g
                    WHERE g.post_id = p.id
                    AND g.date >= CURRENT_DATE - 30) AS avg_position,
                   (SELECT COUNT(*) FROM content_problems cp
                    WHERE cp.post_id = p.id) AS problems_count
            FROM posts p
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE p.site_id = $1
            """,
            site_id,
        )

        post_count = 0
        for p in posts:
            await db.execute(
                """
                INSERT INTO health_snapshots
                    (site_id, post_id, snapshot_date, composite_score,
                     trend, role, traffic_30d, avg_position, problems_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (post_id, snapshot_date) DO UPDATE SET
                    composite_score = $4, trend = $5, role = $6,
                    traffic_30d = $7, avg_position = $8, problems_count = $9
                """,
                site_id, p["id"], today,
                p["composite_score"], p["trend"], p["role"],
                p["traffic_30d"], p["avg_position"],
                p["problems_count"],
            )
            post_count += 1

        # ── Cluster-level snapshots ──
        clusters = await db.fetch(
            """
            SELECT c.id, c.site_id, c.topical_authority_score, c.post_count,
                   AVG(ph.composite_score) AS avg_health
            FROM clusters c
            LEFT JOIN post_clusters pc ON pc.cluster_id = c.id
            LEFT JOIN post_health_scores ph ON ph.post_id = pc.post_id
            WHERE c.site_id = $1
            GROUP BY c.id
            """,
            site_id,
        )

        for c in clusters:
            await db.execute(
                """
                INSERT INTO cluster_snapshots
                    (cluster_id, site_id, snapshot_date,
                     topical_authority_score, post_count, avg_health_score)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (cluster_id, snapshot_date) DO UPDATE SET
                    topical_authority_score = $4, post_count = $5,
                    avg_health_score = $6
                """,
                c["id"], site_id, today,
                c["topical_authority_score"], c["post_count"],
                float(c["avg_health"] or 0),
            )

        # ── Site-level snapshot ──
        site_metrics = await db.fetchrow(
            """
            SELECT
                AVG(ph.composite_score) AS avg_health,
                COUNT(DISTINCT p.id) AS total_posts,
                COUNT(DISTINCT cp.id) AS total_problems,
                COUNT(DISTINCT CASE WHEN ph.role = 'pillar' THEN p.id END) AS pillar_count,
                COUNT(DISTINCT CASE WHEN ph.role = 'dead_weight' THEN p.id END) AS dead_weight_count
            FROM posts p
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            LEFT JOIN content_problems cp ON cp.post_id = p.id
            WHERE p.site_id = $1
            """,
            site_id,
        )

        cannibal_count = await db.fetchval(
            """
            SELECT COUNT(*) FROM cannibalization_pairs
            WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
            """,
            site_id,
        ) or 0

        gap_count = await db.fetchval(
            "SELECT COUNT(*) FROM content_gaps WHERE site_id = $1 AND status = 'open'",
            site_id,
        ) or 0

        serp_count = await db.fetchval(
            "SELECT COUNT(*) FROM serp_opportunities WHERE site_id = $1",
            site_id,
        ) or 0

        velocity = await db.fetchval(
            "SELECT publishing_velocity FROM sites WHERE id = $1", site_id,
        ) or 0.0

        await db.execute(
            """
            INSERT INTO site_snapshots
                (site_id, snapshot_date, avg_health_score, total_posts,
                 total_problems, pillar_count, dead_weight_count,
                 publishing_velocity, cannibalization_pairs,
                 content_gaps_count, serp_opportunities_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (site_id, snapshot_date) DO UPDATE SET
                avg_health_score = $3, total_posts = $4,
                total_problems = $5, pillar_count = $6,
                dead_weight_count = $7, publishing_velocity = $8,
                cannibalization_pairs = $9, content_gaps_count = $10,
                serp_opportunities_count = $11
            """,
            site_id, today,
            float(site_metrics["avg_health"] or 0),
            site_metrics["total_posts"],
            site_metrics["total_problems"],
            site_metrics["pillar_count"],
            site_metrics["dead_weight_count"],
            velocity, cannibal_count, gap_count, serp_count,
        )

        logger.info(
            "Snapshot complete for site %s: %d posts, %d clusters",
            site_id, post_count, len(clusters),
        )

        return {
            "date": str(today),
            "posts_snapshotted": post_count,
            "clusters_snapshotted": len(clusters),
        }

    async def detect_changes(
        self, db: asyncpg.Connection, site_id: UUID,
        days_back: int = 7,
    ) -> list[dict]:
        """Compare current state with previous snapshot.

        Returns a list of detected changes (for alert generation).
        """
        today = date.today()
        prev_date = today - timedelta(days=days_back)

        changes: list[dict] = []

        # Find posts with health score drops > 10 points
        score_drops = await db.fetch(
            """
            SELECT curr.post_id, p.title,
                   prev.composite_score AS prev_score,
                   curr.composite_score AS curr_score,
                   prev.traffic_30d AS prev_traffic,
                   curr.traffic_30d AS curr_traffic
            FROM health_snapshots curr
            JOIN health_snapshots prev ON prev.post_id = curr.post_id
                AND prev.snapshot_date = (
                    SELECT MAX(snapshot_date) FROM health_snapshots
                    WHERE post_id = curr.post_id AND snapshot_date < $3
                )
            JOIN posts p ON p.id = curr.post_id
            WHERE curr.site_id = $1
              AND curr.snapshot_date = $2
              AND prev.composite_score IS NOT NULL
              AND curr.composite_score IS NOT NULL
              AND prev.composite_score - curr.composite_score > 10
            """,
            site_id, today, prev_date,
        )

        for drop in score_drops:
            change = round(drop["prev_score"] - drop["curr_score"], 1)
            changes.append({
                "type": "health_decline",
                "severity": "critical" if change > 20 else "warning",
                "post_id": drop["post_id"],
                "title": f"Health score dropped {change} points",
                "message": (
                    f"\"{drop['title']}\" health declined from "
                    f"{drop['prev_score']:.0f} to {drop['curr_score']:.0f}"
                ),
                "details": {
                    "prev_score": round(drop["prev_score"], 1),
                    "curr_score": round(drop["curr_score"], 1),
                    "change": -change,
                },
            })

        # Find ranking drops > 5 positions
        ranking_drops = await db.fetch(
            """
            SELECT curr.post_id, p.title,
                   prev.avg_position AS prev_pos,
                   curr.avg_position AS curr_pos
            FROM health_snapshots curr
            JOIN health_snapshots prev ON prev.post_id = curr.post_id
                AND prev.snapshot_date = (
                    SELECT MAX(snapshot_date) FROM health_snapshots
                    WHERE post_id = curr.post_id AND snapshot_date < $3
                )
            JOIN posts p ON p.id = curr.post_id
            WHERE curr.site_id = $1
              AND curr.snapshot_date = $2
              AND prev.avg_position IS NOT NULL
              AND curr.avg_position IS NOT NULL
              AND curr.avg_position - prev.avg_position > 5
            """,
            site_id, today, prev_date,
        )

        for drop in ranking_drops:
            pos_change = round(drop["curr_pos"] - drop["prev_pos"], 1)
            changes.append({
                "type": "ranking_drop",
                "severity": "critical" if drop["curr_pos"] > 10 and drop["prev_pos"] <= 10 else "warning",
                "post_id": drop["post_id"],
                "title": f"Ranking dropped {pos_change} positions",
                "message": (
                    f"\"{drop['title']}\" moved from position "
                    f"{drop['prev_pos']:.1f} to {drop['curr_pos']:.1f}"
                ),
                "details": {
                    "prev_position": round(drop["prev_pos"], 1),
                    "curr_position": round(drop["curr_pos"], 1),
                },
            })

        # Site-level: check total problems increase
        site_change = await db.fetchrow(
            """
            SELECT
                prev.total_problems AS prev_problems,
                curr.total_problems AS curr_problems,
                prev.avg_health_score AS prev_health,
                curr.avg_health_score AS curr_health,
                prev.pillar_count AS prev_pillars,
                curr.pillar_count AS curr_pillars
            FROM site_snapshots curr
            JOIN site_snapshots prev ON prev.site_id = curr.site_id
                AND prev.snapshot_date = (
                    SELECT MAX(snapshot_date) FROM site_snapshots
                    WHERE site_id = curr.site_id AND snapshot_date < $3
                )
            WHERE curr.site_id = $1 AND curr.snapshot_date = $2
            """,
            site_id, today, prev_date,
        )

        if site_change:
            prob_diff = (site_change["curr_problems"] or 0) - (site_change["prev_problems"] or 0)
            if prob_diff > 3:
                changes.append({
                    "type": "new_problems",
                    "severity": "warning",
                    "post_id": None,
                    "title": f"{prob_diff} new problems detected",
                    "message": (
                        f"Total problems increased from {site_change['prev_problems']} "
                        f"to {site_change['curr_problems']}"
                    ),
                    "details": {"new_problems": prob_diff},
                })

            # Pillar at risk
            if (site_change["curr_pillars"] or 0) < (site_change["prev_pillars"] or 0):
                lost = (site_change["prev_pillars"] or 0) - (site_change["curr_pillars"] or 0)
                changes.append({
                    "type": "pillar_at_risk",
                    "severity": "critical",
                    "post_id": None,
                    "title": f"{lost} pillar post(s) lost status",
                    "message": "A pillar post has been downgraded — investigate immediately",
                    "details": {"lost_pillars": lost},
                })

        logger.info(
            "Change detection for site %s: %d changes found", site_id, len(changes),
        )
        return changes
