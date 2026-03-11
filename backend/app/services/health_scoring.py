"""Post-level and cluster-level health scoring with ecosystem state assignment.

Computes composite health scores from traffic, ranking, trend, and link metrics.
Assigns roles (pillar, supporter, competitor, dead_weight) and ecosystem states
(forest, swamp, desert, seedbed, meadow).

Optimized: uses batched CTEs instead of per-post queries to minimize DB round trips.
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
        """Score all posts in a cluster and assign ecosystem state.

        Uses batched queries: one query per metric type instead of per-post.
        """
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        thirty_days_ago = now - timedelta(days=30)

        # ── Batch 1: Get all posts in cluster ──
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

        post_ids = [r["id"] for r in post_rows]

        # ── Batch 2: Traffic per post (90 days) — single query ──
        traffic_rows = await db.fetch(
            """
            SELECT post_id, COALESCE(SUM(pageviews), 0) AS total_pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= $2
            GROUP BY post_id
            """,
            post_ids, ninety_days_ago.date(),
        )
        traffic_map: dict[UUID, int] = {r["post_id"]: r["total_pv"] for r in traffic_rows}
        cluster_traffic = sum(traffic_map.values())

        # ── Batch 3: Average position per post (90 days) — single query ──
        position_rows = await db.fetch(
            """
            SELECT post_id, AVG(avg_position) AS avg_pos
            FROM gsc_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= $2
            GROUP BY post_id
            """,
            post_ids, ninety_days_ago.date(),
        )
        position_map: dict[UUID, float] = {
            r["post_id"]: float(r["avg_pos"]) for r in position_rows if r["avg_pos"] is not None
        }

        # ── Batch 4: Daily traffic for trend calculation — single query ──
        daily_rows = await db.fetch(
            """
            SELECT post_id, date, SUM(pageviews) AS pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= $2
            GROUP BY post_id, date
            ORDER BY post_id, date
            """,
            post_ids, ninety_days_ago.date(),
        )
        # Group by post_id
        daily_map: dict[UUID, list[dict]] = {}
        for r in daily_rows:
            daily_map.setdefault(r["post_id"], []).append(
                {"date": r["date"], "pv": r["pv"]}
            )

        # ── Batch 5: Internal link counts — single query ──
        link_rows = await db.fetch(
            """
            SELECT post_id, SUM(cnt) AS total_links FROM (
                SELECT source_post_id AS post_id, COUNT(*) AS cnt
                FROM internal_links
                WHERE source_post_id = ANY($1::uuid[])
                GROUP BY source_post_id
                UNION ALL
                SELECT target_post_id AS post_id, COUNT(*) AS cnt
                FROM internal_links
                WHERE target_post_id = ANY($1::uuid[])
                GROUP BY target_post_id
            ) combined
            GROUP BY post_id
            """,
            post_ids,
        )
        link_map: dict[UUID, int] = {r["post_id"]: r["total_links"] for r in link_rows}
        max_links = max(link_map.values()) if link_map else 1

        # ── Batch 6: Cannibalizing post IDs (medium+ severity) — single query ──
        cannibal_rows = await db.fetch(
            """
            SELECT post_a_id, post_b_id FROM cannibalization_pairs
            WHERE cluster_id = $1 AND severity IN ('medium', 'high', 'critical')
            """,
            cluster_id,
        )
        cannibalizing_post_ids: set[UUID] = set()
        for cr in cannibal_rows:
            cannibalizing_post_ids.add(cr["post_a_id"])
            cannibalizing_post_ids.add(cr["post_b_id"])

        # ── Score each post (no DB calls in this loop) ──
        post_metrics: list[dict] = []

        for row in post_rows:
            post_id = row["id"]

            # 1. Traffic contribution
            post_pageviews = traffic_map.get(post_id, 0)
            traffic_contribution = (
                post_pageviews / cluster_traffic if cluster_traffic > 0 else 0.0
            )

            # 2. Ranking strength
            avg_position = position_map.get(post_id, 100.0)
            ranking_strength = max(0.0, 1.0 - (avg_position - 1.0) / 50.0)

            # 3. Trend
            daily_data = daily_map.get(post_id, [])
            trend, trend_score = _compute_trend(daily_data)

            # 4. Internal link score
            link_count = link_map.get(post_id, 0)
            internal_link_score = link_count / max_links if max_links > 0 else 0.0

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

            post_metrics.append({
                "post_id": post_id,
                "composite": composite,
                "traffic_contribution": traffic_contribution,
                "ranking_strength": ranking_strength,
                "trend": trend,
                "trend_score": trend_score,
                "internal_link_score": internal_link_score,
                "role": role,
                "traffic": post_pageviews,
                "publish_date": row["publish_date"],
            })

        # ── Batch insert all health scores — single executemany ──
        await db.executemany(
            """
            INSERT INTO post_health_scores
                (post_id, traffic_contribution, ranking_strength,
                 trend, internal_link_score, composite_score, role)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            [
                (
                    m["post_id"], m["traffic_contribution"], m["ranking_strength"],
                    m["trend"], m["internal_link_score"], m["composite"], m["role"],
                )
                for m in post_metrics
            ],
        )

        # ── Cluster-level health and ecosystem state ──
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


def _compute_trend(daily_rows: list[dict]) -> tuple[str, float]:
    """Compute traffic trend via linear regression.

    Returns (trend_label, trend_score) where score is 0.0-1.0.
    """
    if len(daily_rows) < 7:
        return "stable", 0.5

    pageviews = [float(r["pv"]) for r in daily_rows]
    x = np.arange(len(pageviews), dtype=np.float64)
    y = np.array(pageviews, dtype=np.float64)

    # Simple linear regression
    x_mean = x.mean()
    y_mean = y.mean()
    denom = np.sum((x - x_mean) ** 2)
    slope = np.sum((x - x_mean) * (y - y_mean)) / denom if denom > 0 else 0.0

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
    has_pillar = any(m["role"] == "pillar" for m in post_metrics)

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
        m["publish_date"] is not None
        and m["publish_date"].replace(tzinfo=timezone.utc) >= thirty_days_ago
        for m in post_metrics
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
