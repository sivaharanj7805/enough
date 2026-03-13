"""Post-level and cluster-level health scoring with ecosystem state assignment.

7-factor health score model (0-100):
  1. Traffic trend (growing/stable/declining/dead)     — 25%
  2. Ranking positions (avg position for top queries)  — 20%
  3. Engagement (bounce rate, time on page)            — 15%
  4. Freshness (months since last update)              — 15%
  5. Content depth (word count vs cluster average)     — 10%
  6. Internal links (inbound from other posts)         — 10%
  7. Technical SEO (meta description, title, headings) — 5%

Each factor normalized 0-100, then weighted sum.

Uses batched CTEs to minimize DB round trips.
Assigns roles (pillar, supporter, competitor, dead_weight) and
ecosystem states (forest, swamp, desert, seedbed, meadow).
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

# 7-factor weights per spec
W_TRAFFIC_TREND = 0.25
W_RANKING = 0.20
W_ENGAGEMENT = 0.15
W_FRESHNESS = 0.15
W_CONTENT_DEPTH = 0.10
W_INTERNAL_LINKS = 0.10
W_TECHNICAL_SEO = 0.05


class HealthScorer:
    """Calculate health scores at post and cluster levels."""

    async def score_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run full health scoring for all clusters in a site.

        Returns the number of posts scored.
        """
        logger.info("Starting health scoring for site %s", site_id)

        # Clear old health scores
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
            scored = await self._score_cluster(db, cluster_row["id"], site_id)
            total_scored += scored

        logger.info(
            "Health scoring complete for site %s — %d posts scored", site_id, total_scored,
        )
        return total_scored

    async def _score_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
    ) -> int:
        """Score all posts in a cluster and assign ecosystem state."""
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        sixty_days_ago = now - timedelta(days=60)
        thirty_days_ago = now - timedelta(days=30)

        # ── Batch 1: Posts in cluster ──
        post_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.publish_date, p.modified_date,
                   p.word_count, p.headings, p.meta_description
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            WHERE pc.cluster_id = $1
            """,
            cluster_id,
        )
        if not post_rows:
            return 0

        post_ids = [r["id"] for r in post_rows]

        # Cluster average word count (for content depth comparison)
        word_counts = [r["word_count"] or 0 for r in post_rows]
        cluster_avg_word_count = sum(word_counts) / len(word_counts) if word_counts else 500

        # ── Batch 2: Traffic (recent 30d vs previous 30d) ──
        traffic_recent = await db.fetch(
            """
            SELECT post_id, COALESCE(SUM(pageviews), 0) AS pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            GROUP BY post_id
            """,
            post_ids, thirty_days_ago.date(),
        )
        recent_pv: dict[UUID, int] = {r["post_id"]: r["pv"] for r in traffic_recent}

        traffic_prev = await db.fetch(
            """
            SELECT post_id, COALESCE(SUM(pageviews), 0) AS pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= $2 AND date < $3
            GROUP BY post_id
            """,
            post_ids, sixty_days_ago.date(), thirty_days_ago.date(),
        )
        prev_pv: dict[UUID, int] = {r["post_id"]: r["pv"] for r in traffic_prev}

        # Total traffic for 60 days (for "dead" detection)
        traffic_60d = await db.fetch(
            """
            SELECT post_id, COALESCE(SUM(pageviews), 0) AS pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            GROUP BY post_id
            """,
            post_ids, sixty_days_ago.date(),
        )
        total_60d_pv: dict[UUID, int] = {r["post_id"]: r["pv"] for r in traffic_60d}

        # Total 90d traffic (for cluster weighting)
        traffic_90d = await db.fetch(
            """
            SELECT post_id, COALESCE(SUM(pageviews), 0) AS pv
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            GROUP BY post_id
            """,
            post_ids, ninety_days_ago.date(),
        )
        traffic_90d_map: dict[UUID, int] = {r["post_id"]: r["pv"] for r in traffic_90d}

        # ── Batch 3: Ranking (avg position, 90d) ──
        position_rows = await db.fetch(
            """
            SELECT post_id, AVG(avg_position) AS avg_pos
            FROM gsc_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            GROUP BY post_id
            """,
            post_ids, ninety_days_ago.date(),
        )
        position_map: dict[UUID, float] = {
            r["post_id"]: float(r["avg_pos"]) for r in position_rows if r["avg_pos"] is not None
        }

        # ── Batch 4: Engagement (bounce rate, avg engagement time) ──
        engagement_rows = await db.fetch(
            """
            SELECT post_id,
                   AVG(bounce_rate) AS avg_bounce,
                   AVG(avg_engagement_time_seconds) AS avg_time
            FROM ga4_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            GROUP BY post_id
            """,
            post_ids, ninety_days_ago.date(),
        )
        engagement_map: dict[UUID, dict] = {
            r["post_id"]: {
                "bounce_rate": float(r["avg_bounce"]) if r["avg_bounce"] else 0.5,
                "avg_time": float(r["avg_time"]) if r["avg_time"] else 60.0,
            }
            for r in engagement_rows
        }

        # ── Batch 5: Internal links (inbound count) ──
        inbound_links = await db.fetch(
            """
            SELECT target_post_id AS post_id, COUNT(*) AS cnt
            FROM internal_links
            WHERE target_post_id = ANY($1::uuid[])
            GROUP BY target_post_id
            """,
            post_ids,
        )
        inbound_map: dict[UUID, int] = {r["post_id"]: r["cnt"] for r in inbound_links}

        outbound_links = await db.fetch(
            """
            SELECT source_post_id AS post_id, COUNT(*) AS cnt
            FROM internal_links
            WHERE source_post_id = ANY($1::uuid[])
            GROUP BY source_post_id
            """,
            post_ids,
        )
        outbound_map: dict[UUID, int] = {r["post_id"]: r["cnt"] for r in outbound_links}

        max_inbound = max(inbound_map.values()) if inbound_map else 1

        # ── Batch 6: Cannibalization pairs ──
        cannibal_rows = await db.fetch(
            """
            SELECT post_a_id, post_b_id FROM cannibalization_pairs
            WHERE cluster_id = $1 AND severity IN ('medium', 'high', 'critical')
            """,
            cluster_id,
        )
        cannibalizing_ids: set[UUID] = set()
        for cr in cannibal_rows:
            cannibalizing_ids.add(cr["post_a_id"])
            cannibalizing_ids.add(cr["post_b_id"])

        # ── Score each post ──
        post_metrics: list[dict] = []

        for row in post_rows:
            post_id = row["id"]

            # Factor 1: Traffic trend (25%)
            r_pv = recent_pv.get(post_id, 0)
            p_pv = prev_pv.get(post_id, 0)
            t_60d = total_60d_pv.get(post_id, 0)
            trend, trend_score = _compute_trend(r_pv, p_pv, t_60d)

            # Factor 2: Ranking (20%)
            avg_pos = position_map.get(post_id, 100.0)
            ranking_score = _ranking_score(avg_pos)

            # Factor 3: Engagement (15%)
            eng = engagement_map.get(post_id, {"bounce_rate": 0.5, "avg_time": 60.0})
            engagement_score = _engagement_score(eng["bounce_rate"], eng["avg_time"])

            # Factor 4: Freshness (15%)
            last_updated = row["modified_date"] or row["publish_date"]
            freshness_score = _freshness_score(last_updated, now)

            # Factor 5: Content depth (10%)
            wc = row["word_count"] or 0
            depth_score = _content_depth_score(wc, cluster_avg_word_count)

            # Factor 6: Internal links (10%)
            inbound = inbound_map.get(post_id, 0)
            link_score = min(100.0, (inbound / max(max_inbound, 1)) * 100.0)

            # Factor 7: Technical SEO (5%)
            tech_score = _technical_seo_score(
                meta_description=row["meta_description"],
                title=row["title"],
                headings=row["headings"],
                has_outbound=outbound_map.get(post_id, 0) > 0,
                has_inbound=inbound > 0,
            )

            # Composite (0-100)
            composite = (
                W_TRAFFIC_TREND * trend_score
                + W_RANKING * ranking_score
                + W_ENGAGEMENT * engagement_score
                + W_FRESHNESS * freshness_score
                + W_CONTENT_DEPTH * depth_score
                + W_INTERNAL_LINKS * link_score
                + W_TECHNICAL_SEO * tech_score
            )

            # Traffic contribution (for cluster weighting)
            total_cluster_traffic = sum(traffic_90d_map.values()) or 1
            traffic_contribution = traffic_90d_map.get(post_id, 0) / total_cluster_traffic

            # Role assignment
            is_cannibalizing = post_id in cannibalizing_ids
            role = _assign_role(composite, traffic_contribution, r_pv, is_cannibalizing)

            post_metrics.append({
                "post_id": post_id,
                "composite": composite,
                "traffic_contribution": traffic_contribution,
                "ranking_strength": ranking_score / 100.0,
                "trend": trend,
                "trend_score": trend_score,
                "engagement_score": engagement_score,
                "freshness_score": freshness_score,
                "content_depth_score": depth_score,
                "internal_link_score": link_score / 100.0,
                "technical_seo_score": tech_score,
                "role": role,
                "traffic": traffic_90d_map.get(post_id, 0),
                "publish_date": row["publish_date"],
            })

        # ── Batch insert health scores ──
        await db.executemany(
            """
            INSERT INTO post_health_scores
                (post_id, traffic_contribution, ranking_strength,
                 trend, internal_link_score, composite_score, role,
                 engagement_score, freshness_score, content_depth_score,
                 technical_seo_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            [
                (
                    m["post_id"], m["traffic_contribution"], m["ranking_strength"],
                    m["trend"], m["internal_link_score"], m["composite"],
                    m["role"], m["engagement_score"], m["freshness_score"],
                    m["content_depth_score"], m["technical_seo_score"],
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


# ═══════════════════════════════════════════════
# Factor scoring functions
# ═══════════════════════════════════════════════


def _compute_trend(
    recent_pv: int, prev_pv: int, total_60d_pv: int,
) -> tuple[str, float]:
    """Compute traffic trend from 30-day comparison.

    Categories per spec:
    - Growing: >15% increase
    - Stable: -15% to +15%
    - Declining: >15% decrease
    - Dead: <5 clicks total in 60 days
    """
    if total_60d_pv < 5:
        return "dead", 0.0

    if prev_pv == 0:
        if recent_pv > 0:
            return "growing", 100.0
        return "dead", 0.0

    pct_change = (recent_pv - prev_pv) / prev_pv

    if pct_change > 0.15:
        # Score 75-100 based on growth magnitude
        return "growing", min(100.0, 75.0 + pct_change * 50.0)
    elif pct_change < -0.15:
        # Score 0-25 based on decline magnitude
        return "declining", max(0.0, 25.0 + pct_change * 50.0)
    else:
        # Stable: 40-60
        return "stable", 50.0


def _ranking_score(avg_position: float) -> float:
    """Ranking score 0-100.

    Position 1 = 100, Position 10 = 60, Position 20 = 30, Position 50+ = 0.
    """
    if avg_position <= 1:
        return 100.0
    if avg_position >= 50:
        return 0.0

    # Exponential decay — top positions worth much more
    return max(0.0, 100.0 * (1.0 - (avg_position - 1.0) / 49.0) ** 0.7)


def _engagement_score(bounce_rate: float, avg_time_seconds: float) -> float:
    """Engagement score 0-100 from bounce rate and time on page.

    bounce_rate: 0.0-1.0 (lower is better)
    avg_time_seconds: higher is better, caps at 300s
    """
    # Bounce score: 0% bounce = 100, 100% bounce = 0
    bounce_score = max(0.0, (1.0 - bounce_rate) * 100.0)

    # Time score: 0s = 0, 30s = 25, 60s = 50, 120s = 75, 300s+ = 100
    time_score = min(100.0, (avg_time_seconds / 300.0) * 100.0)

    # 60/40 weight (time on page is more meaningful than bounce)
    return 0.4 * bounce_score + 0.6 * time_score


def _freshness_score(last_updated: datetime | None, now: datetime) -> float:
    """Freshness score 0-100 based on months since last update.

    Updated this month = 100
    1-3 months = 80
    3-6 months = 60
    6-12 months = 40
    12-18 months = 20
    18+ months = 0
    """
    if not last_updated:
        return 20.0  # No date known — assume stale but not dead

    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    days_old = (now - last_updated).days
    months_old = days_old / 30.44  # Average days per month

    if months_old < 1:
        return 100.0
    if months_old < 3:
        return 80.0
    if months_old < 6:
        return 60.0
    if months_old < 12:
        return 40.0
    if months_old < 18:
        return 20.0
    return 0.0


def _content_depth_score(word_count: int, cluster_avg: float) -> float:
    """Content depth score 0-100 based on word count vs cluster average.

    Below 500 words: penalized
    At cluster average: 60
    Above cluster average: up to 100
    2x+ cluster average: 100 (diminishing returns)
    """
    if word_count < 300:
        return 10.0
    if word_count < 500:
        return 30.0

    if cluster_avg <= 0:
        cluster_avg = 500.0

    ratio = word_count / cluster_avg

    if ratio < 0.5:
        return 20.0
    if ratio < 0.75:
        return 40.0
    if ratio < 1.0:
        return 55.0 + (ratio - 0.75) * 20.0  # 55-60
    if ratio < 1.5:
        return 60.0 + (ratio - 1.0) * 60.0  # 60-90
    return min(100.0, 90.0 + (ratio - 1.5) * 20.0)  # 90-100


def _technical_seo_score(
    meta_description: str | None,
    title: str | None,
    headings: list | str | None,
    has_outbound: bool,
    has_inbound: bool,
) -> float:
    """Technical SEO score 0-100 based on checklist.

    5 checks, each worth 20 points:
    1. Has meta description
    2. Title length 30-60 chars
    3. Has H2+ headings
    4. Has outbound internal links
    5. Has inbound internal links
    """
    score = 0.0

    # 1. Meta description
    if meta_description and len(meta_description.strip()) > 10:
        score += 20.0

    # 2. Title length
    if title:
        title_len = len(title.strip())
        if 30 <= title_len <= 60:
            score += 20.0
        elif 20 <= title_len <= 70:
            score += 10.0  # Partial credit

    # 3. Headings (H2+)
    if headings:
        # headings can be a JSON string or list
        if isinstance(headings, str):
            import json
            try:
                headings = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                headings = []

        has_h2 = any(
            h.get("level") in ("h2", "h3", "h4")
            for h in headings
            if isinstance(h, dict)
        )
        if has_h2:
            score += 20.0

    # 4. Has outbound internal links
    if has_outbound:
        score += 20.0

    # 5. Has inbound internal links
    if has_inbound:
        score += 20.0

    return score


def _assign_role(
    composite: float,
    traffic_contribution: float,
    recent_pv: int,
    is_cannibalizing: bool,
) -> str:
    """Assign a role to a post based on its health metrics."""
    if composite < 15 or recent_pv == 0:
        return "dead_weight"
    if is_cannibalizing:
        return "competitor"
    if traffic_contribution > 0.25 and composite >= 40:
        return "pillar"
    if composite >= 30:
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

    total_possible_pairs = post_count * (post_count - 1) / 2 if post_count > 1 else 1
    cannibalization_rate = cannibal_pairs_count / total_possible_pairs

    all_declining = all(m["trend"] in ("declining", "dead") for m in post_metrics)

    avg_traffic = (
        sum(m["traffic"] for m in post_metrics) / post_count if post_count > 0 else 0
    )

    has_recent = any(
        m["publish_date"] is not None
        and m["publish_date"].replace(tzinfo=timezone.utc) >= thirty_days_ago
        for m in post_metrics
    )

    # Seedbed: recent posts, small cluster
    if has_recent and post_count <= 3:
        return "seedbed"

    # Swamp: high cannibalization
    if cannibalization_rate > 0.5 or (post_count > 8 and not has_pillar):
        return "swamp"

    # Desert: all declining or dead
    if all_declining or avg_traffic < 5:
        return "desert"

    # Forest: healthy with pillar
    if has_pillar and cannibalization_rate < 0.2 and cluster_health > 50:
        return "forest"

    # Meadow: everything else
    return "meadow"
