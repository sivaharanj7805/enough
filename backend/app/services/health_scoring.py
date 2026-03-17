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

# 7-factor weights per spec (full-data mode)
W_TRAFFIC_TREND = 0.25
W_RANKING = 0.20
W_ENGAGEMENT = 0.15
W_FRESHNESS = 0.15
W_CONTENT_DEPTH = 0.10
W_INTERNAL_LINKS = 0.10
W_TECHNICAL_SEO = 0.05

# Factors that require GA4/GSC external data
EXTERNAL_DATA_FACTORS = {"traffic_trend", "ranking", "engagement"}
# Factors that work from crawl-only data
CRAWL_ONLY_FACTORS = {"freshness", "content_depth", "internal_links", "technical_seo"}


def compute_dynamic_weights(
    has_ga4: bool, has_gsc: bool,
) -> dict[str, float]:
    """Compute dynamically rebalanced weights based on available data.

    When GA4/GSC data is missing, redistribute those weights proportionally
    to crawl-only factors so scores still sum to 100.

    Returns dict mapping factor name → weight (all sum to 1.0).
    """
    weights = {
        "traffic_trend": W_TRAFFIC_TREND,
        "ranking": W_RANKING,
        "engagement": W_ENGAGEMENT,
        "freshness": W_FRESHNESS,
        "content_depth": W_CONTENT_DEPTH,
        "internal_links": W_INTERNAL_LINKS,
        "technical_seo": W_TECHNICAL_SEO,
    }

    # Zero out unavailable factors
    if not has_ga4:
        weights["traffic_trend"] = 0.0
        weights["engagement"] = 0.0
    if not has_gsc:
        weights["ranking"] = 0.0
        # Traffic trend needs GA4 pageviews (already zeroed if no GA4)
        # but if we have GA4 but no GSC, traffic trend still works

    # Redistribute: scale remaining weights to sum to 1.0
    total = sum(weights.values())
    if total > 0 and total < 1.0:
        scale = 1.0 / total
        weights = {k: v * scale for k, v in weights.items()}

    return weights


class HealthScorer:
    """Calculate health scores at post and cluster levels."""

    async def score_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run full health scoring for all clusters in a site.

        Automatically detects whether GA4/GSC data exists and adjusts
        scoring weights accordingly (graceful degradation).

        Returns the number of posts scored.
        """
        logger.info("Starting health scoring for site %s", site_id)

        # Detect data availability (graceful degradation)
        ga4_count = await db.fetchval(
            """
            SELECT COUNT(*) FROM ga4_metrics
            WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
            LIMIT 1
            """,
            site_id,
        )
        gsc_count = await db.fetchval(
            """
            SELECT COUNT(*) FROM gsc_metrics
            WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
            LIMIT 1
            """,
            site_id,
        )
        has_ga4 = (ga4_count or 0) > 0
        has_gsc = (gsc_count or 0) > 0

        if not has_ga4 and not has_gsc:
            logger.info(
                "No GA4/GSC data for site %s — using crawl-only scoring (40%% of factors)",
                site_id,
            )
        elif not has_ga4:
            logger.info("No GA4 data for site %s — excluding traffic/engagement factors", site_id)
        elif not has_gsc:
            logger.info("No GSC data for site %s — excluding ranking factor", site_id)

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
            scored = await self._score_cluster(
                db, cluster_row["id"], site_id,
                has_ga4=has_ga4, has_gsc=has_gsc,
            )
            total_scored += scored

        logger.info(
            "Health scoring complete for site %s — %d posts scored (ga4=%s, gsc=%s)",
            site_id, total_scored, has_ga4, has_gsc,
        )
        return total_scored

    async def _score_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
        has_ga4: bool = True, has_gsc: bool = True,
    ) -> int:
        """Score all posts in a cluster and assign ecosystem state.

        When has_ga4/has_gsc are False, dynamically rebalances weights
        to use only crawl-derived factors (graceful degradation).
        """
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        sixty_days_ago = now - timedelta(days=60)
        thirty_days_ago = now - timedelta(days=30)

        # Get dynamic weights based on data availability
        weights = compute_dynamic_weights(has_ga4, has_gsc)

        # ── Batch 1: Posts in cluster ──
        post_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.publish_date, p.modified_date,
                   p.word_count, p.headings, p.meta_description, p.body_html
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
        # For very small clusters (< 3 posts), cluster average is unreliable
        # Use absolute thresholds instead
        word_counts = [r["word_count"] or 0 for r in post_rows]
        if len(word_counts) >= 3:
            cluster_avg_word_count = sum(word_counts) / len(word_counts)
        else:
            # Use industry average (~1000 words) for small clusters
            cluster_avg_word_count = 1000.0

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
            freshness_score = _freshness_score(
                last_updated, now,
                title=row["title"] or "", url=row.get("url", ""),
            )

            # Factor 5: Content depth (10%)
            wc = row["word_count"] or 0
            depth_score = _content_depth_score(wc, cluster_avg_word_count, body_html=row.get("body_html"))

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
                body_html=row.get("body_html"),
            )

            # Composite (0-100) — dynamically weighted
            composite = (
                weights["traffic_trend"] * trend_score
                + weights["ranking"] * ranking_score
                + weights["engagement"] * engagement_score
                + weights["freshness"] * freshness_score
                + weights["content_depth"] * depth_score
                + weights["internal_links"] * link_score
                + weights["technical_seo"] * tech_score
            )

            # Traffic contribution (for cluster weighting)
            total_cluster_traffic = sum(traffic_90d_map.values()) or 1
            traffic_contribution = traffic_90d_map.get(post_id, 0) / total_cluster_traffic

            # Role assignment
            is_cannibalizing = post_id in cannibalizing_ids
            has_traffic_data = has_ga4 or has_gsc
            role = _assign_role(composite, traffic_contribution, r_pv, is_cannibalizing, has_traffic_data=has_traffic_data)

            # Page importance multiplier for prioritisation
            page_importance = 1.0
            if inbound >= 10:
                page_importance = 2.0  # Hub / pillar page
            elif inbound >= 5:
                page_importance = 1.5

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

        # ── Batch upsert health scores (one per post, keep highest) ──
        await db.executemany(
            """
            INSERT INTO post_health_scores
                (post_id, traffic_contribution, ranking_strength,
                 trend, internal_link_score, composite_score, role,
                 engagement_score, freshness_score, content_depth_score,
                 technical_seo_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (post_id) DO UPDATE SET
                traffic_contribution = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.traffic_contribution ELSE post_health_scores.traffic_contribution END,
                ranking_strength = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.ranking_strength ELSE post_health_scores.ranking_strength END,
                trend = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.trend ELSE post_health_scores.trend END,
                internal_link_score = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.internal_link_score ELSE post_health_scores.internal_link_score END,
                composite_score = GREATEST(EXCLUDED.composite_score, post_health_scores.composite_score),
                role = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.role ELSE post_health_scores.role END,
                engagement_score = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.engagement_score ELSE post_health_scores.engagement_score END,
                freshness_score = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.freshness_score ELSE post_health_scores.freshness_score END,
                content_depth_score = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.content_depth_score ELSE post_health_scores.content_depth_score END,
                technical_seo_score = CASE WHEN EXCLUDED.composite_score > post_health_scores.composite_score THEN EXCLUDED.technical_seo_score ELSE post_health_scores.technical_seo_score END
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
        # If no traffic data at all (GSC not connected), return "unknown"
        # instead of "dead" — the post may have traffic we can't see
        if total_60d_pv == 0 and prev_pv == 0 and recent_pv == 0:
            return "unknown", 30.0  # Neutral score, not penalised
        return "dead", 0.0

    if prev_pv == 0:
        if recent_pv > 0:
            return "growing", 100.0
        # Both zero but total_60d >= 5 → traffic is from overlap period
        # Treat as stable (neither growing nor declining)
        return "stable", 30.0

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


def _is_time_sensitive(title: str, url: str) -> bool:
    """Detect if content is time-sensitive (year references, listicles, rankings)."""
    import re
    text = f"{title} {url}".lower()
    # Year references in title/URL
    if re.search(r"20[12]\d", text):
        return True
    # "best of", "top X", "ranking", pricing pages
    if any(kw in text for kw in ["best ", "top ", "ranking", "pricing", "review"]):
        return True
    return False


def _freshness_score(
    last_updated: datetime | None, now: datetime,
    title: str = "", url: str = "",
) -> float:
    """Freshness score 0-100 based on months since last update.

    Evergreen content (how-to, guides, what-is) gets a gentler curve.
    Time-sensitive content (year in title, best-of lists) gets a steeper curve.

    Updated this month = 100
    1-3 months = 80
    3-6 months = 60
    6-12 months = 40
    12-18 months = 20
    18+ months = 0 (time-sensitive) or 30 (evergreen)
    """
    if not last_updated:
        return 50.0  # No date known — neutral score, don't penalise

    time_sensitive = _is_time_sensitive(title, url)
    evergreen_floor = 0.0 if time_sensitive else 30.0

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
        return max(40.0, evergreen_floor)
    if months_old < 18:
        return max(20.0, evergreen_floor)
    return evergreen_floor


def _content_quality_bonus(body_html: str | None) -> float:
    """Bonus points (0-15) for content quality signals beyond word count.

    Checks for: lists, data/stats, code blocks, tables, external citations.
    """
    if not body_html:
        return 0.0
    import re
    bonus = 0.0
    html = body_html.lower()
    # Lists indicate structured, scannable content
    if "<li" in html:
        list_count = html.count("<li")
        bonus += min(3.0, list_count * 0.3)
    # Data/statistics: numbers with % or $
    stats = re.findall(r'\d+(?:\.\d+)?(?:%|\$|percent)', html)
    if stats:
        bonus += min(3.0, len(stats) * 0.5)
    # Code blocks indicate technical depth
    if "<pre" in html or "<code" in html:
        bonus += 2.0
    # Tables indicate structured data
    if "<table" in html:
        bonus += 2.0
    # External links (citations / references)
    ext_links = re.findall(r'href=["\']https?://(?!(?:www\.)?close\.com)', html)
    if ext_links:
        bonus += min(3.0, len(ext_links) * 0.3)
    # Images
    if "<img" in html or "<picture" in html or "<figure" in html:
        bonus += 2.0
    return min(15.0, bonus)


def _content_depth_score(word_count: int, cluster_avg: float, body_html: str | None = None) -> float:
    """Content depth score 0-100 based on word count vs cluster average.

    Includes bonus for content quality signals (lists, data, code, tables,
    citations, images).

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
        base = 20.0
    elif ratio < 0.75:
        base = 40.0
    elif ratio < 1.0:
        base = 55.0 + (ratio - 0.75) * 20.0  # 55-60
    elif ratio < 1.5:
        base = 60.0 + (ratio - 1.0) * 60.0  # 60-90
    else:
        base = min(100.0, 90.0 + (ratio - 1.5) * 20.0)  # 90-100

    bonus = _content_quality_bonus(body_html)
    return min(100.0, base + bonus)


def _technical_seo_score(
    meta_description: str | None,
    title: str | None,
    headings: list | str | None,
    has_outbound: bool,
    has_inbound: bool,
    body_html: str | None = None,
) -> float:
    """Technical SEO score 0-100 based on extended checklist.

    8 checks (12.5 points each):
    1. Has meta description
    2. Title length 30-60 chars
    3. Has H2+ headings
    4. Has outbound internal links
    5. Has inbound internal links
    6. Has Open Graph tags (og:title, og:image)
    7. Has structured data (JSON-LD)
    8. Has canonical tag
    """
    import re as _re
    score = 0.0
    pts = 12.5  # 8 checks × 12.5 = 100

    html = (body_html or "").lower()

    # 1. Meta description
    if meta_description and len(meta_description.strip()) > 10:
        score += pts

    # 2. Title length
    if title:
        title_len = len(title.strip())
        if 30 <= title_len <= 60:
            score += pts
        elif 20 <= title_len <= 70:
            score += pts * 0.5  # Partial credit

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
            score += pts

    # 4. Has outbound internal links
    if has_outbound:
        score += pts

    # 5. Has inbound internal links
    if has_inbound:
        score += pts

    # 6. Open Graph tags
    if html and ('og:title' in html or 'og:image' in html or 'property="og:' in html):
        score += pts

    # 7. Structured data (JSON-LD)
    if html and 'application/ld+json' in html:
        score += pts

    # 8. Canonical tag
    if html and 'rel="canonical"' in html or "rel='canonical'" in (body_html or "").lower():
        score += pts

    return min(100.0, score)


def _assign_role(
    composite: float,
    traffic_contribution: float,
    recent_pv: int,
    is_cannibalizing: bool,
    has_traffic_data: bool = True,
) -> str:
    """Assign a role to a post based on its health metrics.

    When no traffic data is available (no GSC/GA4), derive role from
    composite score alone so posts aren't all labelled dead_weight.
    """
    if not has_traffic_data:
        # Derive role from composite score (content quality signals only)
        if is_cannibalizing:
            return "competitor"
        if composite >= 60:
            return "pillar"
        if composite >= 35:
            return "supporter"
        if composite >= 15:
            return "at_risk"
        return "dead_weight"

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
