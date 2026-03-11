"""Post-level and cluster-level health scoring with ecosystem state assignment.

Computes composite health scores from traffic, ranking, trend, and link metrics.
Assigns roles (pillar, supporter, competitor, dead_weight) and ecosystem states
(forest, swamp, desert, seedbed, meadow).
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

# Composite score weights
W_TRAFFIC = 0.35
W_RANKING = 0.25
W_TREND = 0.25
W_LINKS = 0.15


class HealthScorer:
    """Calculate health scores at post and cluster levels."""

    async def score_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run full health scoring for all clusters in a site.

        Requires clusters and cannibalization data to exist.
        Returns the number of posts scored.
        """
        logger.info("Starting health scoring for site %s", site_id)

        # Clear old health scores for this site
        await db.execute(
            """
            DELETE FROM post_health_scores
            WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
            """,
            site_id,
        )

        clusters = await db.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id,
        )
        if not clusters:
            logger.warning("No clusters for site %s — run clustering first", site_id)
            return 0

        total_scored = 0
        for cluster_row in clusters:
            cluster_id = cluster_row["id"]
            scored = await self._score_cluster(db, cluster_id, site_id)
            total_scored += scored

        logger.info(
            "Health scoring complete for site %s — %d posts scored",
            site_id, total_scored,
        )
        return total_scored

    async def _score_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
    ) -> int:
        """Score all posts in a cluster and assign ecosystem state."""
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        thirty_days_ago = now - timedelta(days=30)

        # Get all posts in cluster
        post_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.publish_date, p.word_count
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            WHERE pc.cluster_id = $1
            """,
            cluster_id,
        )

        if not post_rows:
            return 0

        # Gather per-post metrics
        post_metrics: list[dict] = []

        # Cluster-level traffic total (90 days)
        cluster_traffic = 0
        for row in post_rows:
            pv = await db.fetchval(
                """
                SELECT COALESCE(SUM(pageviews), 0)
                FROM ga4_metrics
                WHERE post_id = $1 AND date >= $2
                """,
                row["id"], ninety_days_ago.date(),
            )
            cluster_traffic += pv

        # Max internal links in cluster (for normalization)
        max_links = 1  # Avoid division by zero
        for row in post_rows:
            links = await db.fetchval(
                """
                SELECT COUNT(*) FROM (
                    SELECT id FROM internal_links WHERE source_post_id = $1
                    UNION ALL
                    SELECT id FROM internal_links WHERE target_post_id = $1
                ) combined
                """,
                row["id"],
            )
            max_links = max(max_links, links)

        # Cannibalization post IDs (medium+ severity)
        cannibalizing_post_ids = set()
        cannibal_rows = await db.fetch(
            """
            SELECT post_a_id, post_b_id FROM cannibalization_pairs
            WHERE cluster_id = $1 AND severity IN ('medium', 'high', 'critical')
            """,
            cluster_id,
        )
        for cr in cannibal_rows:
            cannibalizing_post_ids.add(cr["post_a_id"])
            cannibalizing_post_ids.add(cr["post_b_id"])

        for row in post_rows:
            post_id = row["id"]

            # 1. Traffic contribution
            post_pageviews = await db.fetchval(
                """
                SELECT COALESCE(SUM(pageviews), 0)
                FROM ga4_metrics
                WHERE post_id = $1 AND date >= $2
                """,
                post_id, ninety_days_ago.date(),
            )
            traffic_contribution = (
                post_pageviews / cluster_traffic if cluster_traffic > 0 else 0.0
            )

            # 2. Ranking strength
            avg_pos_row = await db.fetchrow(
                """
                SELECT AVG(avg_position) AS avg_pos
                FROM gsc_metrics
                WHERE post_id = $1 AND date >= $2
                """,
                post_id, ninety_days_ago.date(),
            )
            avg_position = (
                avg_pos_row["avg_pos"] if avg_pos_row and avg_pos_row["avg_pos"] else 100.0
            )
            ranking_strength = max(0.0, 1.0 - (avg_position - 1.0) / 50.0)

            # 3. Trend (linear regression on daily traffic, last 90 days)
            daily_rows = await db.fetch(
                """
                SELECT date, SUM(pageviews) AS pv
                FROM ga4_metrics
                WHERE post_id = $1 AND date >= $2
                GROUP BY date
                ORDER BY date
                """,
                post_id, ninety_days_ago.date(),
            )
            trend, trend_score = _compute_trend(daily_rows)

            # 4. Internal link score
            link_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM (
                    SELECT id FROM internal_links WHERE source_post_id = $1
                    UNION ALL
                    SELECT id FROM internal_links WHERE target_post_id = $1
                ) combined
                """,
                post_id,
            )
            internal_link_score = link_count / max_links

            # 5. Composite score (0-100)
            composite = (
                W_TRAFFIC * traffic_contribution
                + W_RANKING * ranking_strength
                + W_TREND * trend_score
                + W_LINKS * internal_link_score
            ) * 100.0

            # 6. Role assignment
            is_cannibalizing = post_id in cannibalizing_post_ids
            role = _assign_role(
                composite, traffic_contribution, post_pageviews, is_cannibalizing,
            )

            # Store health score
            await db.execute(
                """
                INSERT INTO post_health_scores
                    (post_id, traffic_contribution, ranking_strength,
                     trend, internal_link_score, composite_score, role)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                post_id, traffic_contribution, ranking_strength,
                trend, internal_link_score, composite, role,
            )

            post_metrics.append({
                "post_id": post_id,
                "composite": composite,
                "traffic": post_pageviews,
                "trend": trend,
                "publish_date": row["publish_date"],
            })

        # Cluster-level health and ecosystem state
        if post_metrics:
            total_traffic = sum(m["traffic"] for m in post_metrics)
            if total_traffic > 0:
                cluster_health = sum(
                    m["composite"] * (m["traffic"] / total_traffic)
                    for m in post_metrics
                )
            else:
                cluster_health = sum(m["composite"] for m in post_metrics) / len(post_metrics)

            ecosystem_state = _assign_ecosystem_state(
                post_metrics=post_metrics,
                cannibal_pairs_count=len(cannibal_rows),
                post_count=len(post_metrics),
                cluster_health=cluster_health,
                now=now,
                thirty_days_ago=thirty_days_ago,
            )

            await db.execute(
                """
                UPDATE clusters
                SET health_score = $1, ecosystem_state = $2, updated_at = NOW()
                WHERE id = $3
                """,
                cluster_health, ecosystem_state, cluster_id,
            )

        return len(post_metrics)


def _compute_trend(daily_rows: list) -> tuple[str, float]:
    """Compute traffic trend via linear regression.

    Returns (trend_label, trend_score) where score is 0.0-1.0.
    """
    if len(daily_rows) < 7:
        return "stable", 0.5

    pageviews = [float(r["pv"]) for r in daily_rows]
    x = np.arange(len(pageviews), dtype=np.float64)
    y = np.array(pageviews, dtype=np.float64)

    # Simple linear regression
    n = len(x)
    x_mean = x.mean()
    y_mean = y.mean()
    slope = (
        np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        if np.sum((x - x_mean) ** 2) > 0 else 0.0
    )

    # Normalize slope as weekly percentage change
    avg_traffic = y_mean if y_mean > 0 else 1.0
    weekly_pct_change = (slope * 7.0) / avg_traffic

    if weekly_pct_change > 0.02:
        return "growing", 1.0
    elif weekly_pct_change < -0.02:
        return "declining", 0.0
    else:
        return "stable", 0.5


def _assign_role(
    composite: float,
    traffic_contribution: float,
    pageviews: int,
    is_cannibalizing: bool,
) -> str:
    """Assign a role to a post based on its health metrics."""
    if composite < 15 or pageviews == 0:
        return "dead_weight"
    if is_cannibalizing:
        return "competitor"
    if traffic_contribution > 0.30 and composite >= 40:
        return "pillar"
    if composite >= 40:
        return "supporter"
    return "dead_weight"


def _assign_ecosystem_state(
    post_metrics: list[dict],
    cannibal_pairs_count: int,
    post_count: int,
    cluster_health: float,
    now: datetime,
    thirty_days_ago: datetime,
) -> str:
    """Assign ecosystem state to a cluster."""
    # Check for pillar
    has_pillar = any(
        m["composite"] >= 40 and m.get("traffic", 0) > 0
        for m in post_metrics
    )

    # Cannibalization rate
    total_possible_pairs = post_count * (post_count - 1) / 2 if post_count > 1 else 1
    cannibalization_rate = cannibal_pairs_count / total_possible_pairs

    # All declining?
    all_declining = all(m["trend"] == "declining" for m in post_metrics)

    # Average traffic
    avg_traffic = (
        sum(m["traffic"] for m in post_metrics) / post_count if post_count > 0 else 0
    )

    # Any recent posts?
    has_recent = any(
        m["publish_date"] and m["publish_date"].replace(tzinfo=timezone.utc) >= thirty_days_ago
        for m in post_metrics
        if m["publish_date"] is not None
    )

    # Seedbed: recent posts, small cluster
    if has_recent and post_count <= 3:
        return "seedbed"

    # Swamp: high cannibalization or too many posts without a pillar
    if cannibalization_rate > 0.5 or (post_count > 8 and not has_pillar):
        return "swamp"

    # Desert: all declining or very low traffic
    if all_declining or avg_traffic < 5:
        return "desert"

    # Forest: healthy with pillar
    if has_pillar and cannibalization_rate < 0.2 and cluster_health > 50:
        return "forest"

    # Meadow: everything else
    return "meadow"
