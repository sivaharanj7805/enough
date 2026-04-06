"""Post-level and cluster-level health scoring with ecosystem state assignment.

8-factor health score model (0-100):
  1. Traffic trend (growing/stable/declining/dead)     — 20%
  2. Ranking positions (avg position for top queries)  — 18%
  3. Engagement (bounce rate, time on page)            — 12%
  4. Freshness (months since last update)              — 12%
  5. Content depth (word count vs cluster average)     — 10%
  6. Internal links (inbound from other posts)         — 8%
  7. Technical SEO (meta description, title, headings) — 5%
  8. AI Readiness (citability + E-E-A-T + schema + extraction) — 15%

Each factor normalized 0-100, then weighted sum.

Uses batched CTEs to minimize DB round trips.
Assigns roles (pillar, supporter, competitor, dead_weight) and
ecosystem states (forest, swamp, desert, seedbed, meadow).
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# 8-factor weights per spec (full-data mode)
W_TRAFFIC_TREND = 0.20
W_RANKING = 0.18
W_ENGAGEMENT = 0.12
W_FRESHNESS = 0.12
W_CONTENT_DEPTH = 0.10
W_INTERNAL_LINKS = 0.08
W_TECHNICAL_SEO = 0.05
W_AI_READINESS = 0.15

# Factors that require GA4/GSC external data
EXTERNAL_DATA_FACTORS = {"traffic_trend", "ranking", "engagement"}
# Factors that work from crawl-only data
CRAWL_ONLY_FACTORS = {"freshness", "content_depth", "internal_links", "technical_seo", "ai_readiness"}


def compute_ai_readiness(
    *,
    ai_citability_score: float | None = None,
    eeat_score: float | None = None,
    schema_score: float | None = None,
    extraction_score: float | None = None,
    default: float | None = 40.0,
) -> float | None:
    """Compute AI readiness as mean of available AI dimension scores.

    Central formula — used by both health_scoring (Step 7) and analytics
    (post detail endpoint).  When none of the 4 dimensions have values,
    returns *default* (40.0 for pipeline scoring, None for display).
    """
    ai_dims = [
        v for v in [ai_citability_score, eeat_score, schema_score, extraction_score]
        if v is not None
    ]
    if ai_dims:
        return sum(ai_dims) / len(ai_dims)
    return default


def compute_dynamic_weights(
    has_ga4: bool, has_gsc: bool,
) -> dict[str, float]:
    """Compute dynamically rebalanced weights based on available data.

    When GA4/GSC data is missing, redistribute those weights proportionally
    to crawl-only factors so scores still sum to 100.

    Returns dict mapping factor name → weight (all sum to 1.0).
    """
    if has_ga4 and has_gsc:
        # Full data mode — all 8 original factors
        return {
            "traffic_trend": W_TRAFFIC_TREND,
            "ranking": W_RANKING,
            "engagement": W_ENGAGEMENT,
            "freshness": W_FRESHNESS,
            "content_depth": W_CONTENT_DEPTH,
            "internal_links": W_INTERNAL_LINKS,
            "technical_seo": W_TECHNICAL_SEO,
            "ai_readiness": W_AI_READINESS,
        }

    if not has_ga4 and not has_gsc:
        # Crawl-only mode — rebalanced to maximize score differentiation.
        # AI Readiness is still the largest single factor but reduced from 36% to 28%
        # to avoid dominating when citability scores haven't been computed yet (flat 40.0).
        # Content depth bumped to 20% because it provides the highest variance
        # (stddev 26.6) across crawl-only factors.
        # S4-25: predicted_engagement and content_structure merged into content_richness
        # (15%) to eliminate triple-counting with tech_seo (r=0.59-0.61 correlation).
        return {
            "traffic_trend": 0.0,
            "ranking": 0.0,
            "engagement": 0.0,
            "freshness": 0.15,
            "content_depth": 0.20,
            "internal_links": 0.10,
            "technical_seo": 0.07,
            "ai_readiness": 0.28,
            "content_richness": 0.20,
        }

    # Partial data — zero missing factors, redistribute
    weights = {
        "traffic_trend": W_TRAFFIC_TREND if has_ga4 else 0.0,
        "ranking": W_RANKING if has_gsc else 0.0,
        "engagement": W_ENGAGEMENT if has_ga4 else 0.0,
        "freshness": W_FRESHNESS,
        "content_depth": W_CONTENT_DEPTH,
        "internal_links": W_INTERNAL_LINKS,
        "technical_seo": W_TECHNICAL_SEO,
        "ai_readiness": W_AI_READINESS,
    }
    total = sum(weights.values())
    if total > 0 and total < 1.0:
        scale = 1.0 / total
        weights = {k: v * scale for k, v in weights.items()}
    return weights


class HealthScorer:
    """Calculate health scores at post and cluster levels."""

    async def score_site(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        on_progress: Callable[[str], Any] | None = None,
    ) -> int:
        """Run full health scoring for all clusters in a site.

        Automatically detects whether GA4/GSC data exists and adjusts
        scoring weights accordingly (graceful degradation).

        Args:
            on_progress: Optional callback(status_text) for sub-step progress updates.

        Returns the number of posts scored.
        """
        logger.info("Starting health scoring for site %s", site_id)

        # Capture previous snapshot for analysis diff (before scoring overwrites values)
        _prev_snapshot = await db.fetchrow(
            "SELECT score, factor_scores FROM health_score_history WHERE site_id = $1 ORDER BY analyzed_at DESC LIMIT 1",
            site_id,
        )

        def _report(msg: str) -> None:
            logger.info("Health scoring [%s]: %s", site_id, msg)
            if on_progress:
                on_progress(msg)

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

        mode = "full" if has_ga4 and has_gsc else "partial" if has_ga4 or has_gsc else "crawl-only"
        _report(f"Data mode: {mode}")

        # Detect content profile (short-form vs long-form)
        wc_stats = await db.fetchrow(
            """SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY word_count) AS median_wc,
                      stddev(word_count) AS stddev_wc
               FROM posts WHERE site_id = $1 AND word_count > 50""",
            site_id,
        )
        median_wc = float(wc_stats["median_wc"] or 1000) if wc_stats else 1000
        stddev_wc = float(wc_stats["stddev_wc"] or 500) if wc_stats else 500
        is_short_form = median_wc < 600 and stddev_wc < 400
        if is_short_form:
            logger.info("Site %s detected as short-form (median %dw, stddev %dw)", site_id, median_wc, stddev_wc)

        # Clear old health scores ONLY for posts in leaf clusters (preserve AI score columns).
        # Previous bug: NULLing ALL posts then only re-scoring leaf-cluster posts
        # left posts outside leaf clusters with NULL scores permanently.
        await db.execute(
            """
            UPDATE post_health_scores SET
                traffic_contribution = NULL,
                ranking_strength = NULL,
                trend = NULL,
                internal_link_score = NULL,
                composite_score = NULL,
                role = NULL,
                engagement_score = NULL,
                freshness_score = NULL,
                content_depth_score = NULL,
                technical_seo_score = NULL
            WHERE post_id IN (
                SELECT DISTINCT pc.post_id FROM post_clusters pc
                JOIN clusters c ON c.id = pc.cluster_id
                WHERE c.site_id = $1
                  AND c.id NOT IN (
                      SELECT parent_cluster_id FROM clusters
                      WHERE parent_cluster_id IS NOT NULL AND site_id = $1
                  )
            )
            """,
            site_id,
        )

        clusters = await db.fetch(
            """SELECT id FROM clusters WHERE site_id = $1
               AND id NOT IN (
                   SELECT parent_cluster_id FROM clusters
                   WHERE parent_cluster_id IS NOT NULL AND site_id = $1
               )""",
            site_id,
        )
        if not clusters:
            logger.warning("No clusters for site %s — run clustering first", site_id)
            return 0

        # Score clusters — parallel for large sites, sequential for small.
        # S4-21: threshold based on estimated total posts, not cluster count.
        # A site with 5 clusters x 200 posts (1000 total) should parallelize,
        # while 11 clusters x 3 posts (33 total) should not.
        total_scored = 0
        est_total_posts = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1 AND (word_count IS NULL OR word_count >= 100)",
            site_id,
        ) or 0
        if est_total_posts > 200:
            # Parallel scoring with connection pool (max 5 concurrent)
            from app.database import get_pool
            pool = await get_pool()
            sem = asyncio.Semaphore(5)

            async def _score_one(cluster_id: UUID) -> int:
                async with sem:
                    async with pool.acquire() as conn:
                        return await self._score_cluster(
                            conn, cluster_id, site_id,
                            has_ga4=has_ga4, has_gsc=has_gsc,
                            is_short_form=is_short_form,
                        )

            results = await asyncio.gather(
                *[_score_one(c["id"]) for c in clusters],
                return_exceptions=True,
            )
            for _i, r in enumerate(results):
                if isinstance(r, int):
                    total_scored += r
                elif isinstance(r, Exception):
                    logger.warning("Cluster scoring failed: %s", r)
            _report(f"Scored {len(clusters)} clusters (parallel)")
        else:
            for idx, cluster_row in enumerate(clusters):
                scored = await self._score_cluster(
                    db, cluster_row["id"], site_id,
                    has_ga4=has_ga4, has_gsc=has_gsc,
                    is_short_form=is_short_form,
                )
                total_scored += scored
                _report(f"Scored {idx + 1}/{len(clusters)} clusters ({total_scored} posts)")

        # Record health score snapshot in history table
        if total_scored > 0:
            try:
                import json
                avg_score = await db.fetchval(
                    """SELECT AVG(phs.composite_score)
                       FROM post_health_scores phs
                       JOIN posts p ON p.id = phs.post_id
                       WHERE p.site_id = $1""",
                    site_id,
                )
                factor_row = await db.fetchrow(
                    """SELECT
                        ROUND(AVG(phs.engagement_score)::numeric, 2) AS engagement,
                        ROUND(AVG(phs.freshness_score)::numeric, 2) AS freshness,
                        ROUND(AVG(phs.content_depth_score)::numeric, 2) AS content_depth,
                        ROUND(AVG(phs.internal_link_score * 100)::numeric, 2) AS internal_links,
                        ROUND(AVG(phs.technical_seo_score)::numeric, 2) AS technical_seo,
                        ROUND(AVG(phs.ranking_strength * 100)::numeric, 2) AS ranking,
                        ROUND(AVG(phs.traffic_contribution * 100)::numeric, 2) AS traffic
                       FROM post_health_scores phs
                       JOIN posts p ON p.id = phs.post_id
                       WHERE p.site_id = $1""",
                    site_id,
                )
                # S4-13: Include ALL active factors in history, not just the original 7.
                # AI readiness, predicted_engagement, content_structure are missing from
                # the query above (they're not stored as separate columns), so compute
                # them from the composite and known weights.
                factor_scores = {}
                if factor_row:
                    for key in ("engagement", "freshness", "content_depth",
                                "internal_links", "technical_seo", "ranking", "traffic"):
                        val = factor_row[key]
                        factor_scores[key] = float(val) if val is not None else None
                # Add AI readiness average from the ai_citability scores
                ai_avg = await db.fetchval(
                    """SELECT ROUND(AVG(
                        COALESCE(ai_citability_score, 0) + COALESCE(eeat_score, 0)
                        + COALESCE(schema_score, 0) + COALESCE(extraction_score, 0)
                    )::numeric / 4, 2)
                    FROM post_health_scores phs
                    JOIN posts p ON p.id = phs.post_id
                    WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL""",
                    site_id,
                )
                factor_scores["ai_readiness"] = float(ai_avg) if ai_avg else None
                factor_scores["scoring_mode"] = "full" if has_ga4 and has_gsc else "partial" if has_ga4 or has_gsc else "crawl_only"

                await db.execute(
                    """INSERT INTO health_score_history (site_id, score, factor_scores, analyzed_at)
                       VALUES ($1, $2, $3, NOW())""",
                    site_id, float(avg_score or 0), json.dumps(factor_scores),
                )
                logger.info("Recorded health score history for site %s: %.1f", site_id, avg_score or 0)

                # Update impact measurements for completed recommendations
                try:
                    from app.services.impact_tracking import ImpactTracker
                    tracker = ImpactTracker()
                    impact_updated = await tracker.update_impacts(db, site_id)
                    if impact_updated:
                        logger.info("Updated %d impact measurements for site %s", impact_updated, site_id)
                except Exception as e2:
                    logger.warning("Failed to update impact measurements for site %s: %s", site_id, e2)

                # Generate analysis diff (before/after comparison)
                try:
                    prev_score = float(_prev_snapshot["score"]) if _prev_snapshot else None
                    prev_factors = _prev_snapshot["factor_scores"] if _prev_snapshot else None
                    if isinstance(prev_factors, str):
                        prev_factors = json.loads(prev_factors)

                    from app.services.analysis_diff import generate_and_store_diff
                    await generate_and_store_diff(
                        db, site_id,
                        prev_score=prev_score,
                        prev_factors=prev_factors,
                        new_score=float(avg_score or 0),
                        new_factors=factor_scores,
                    )
                except Exception as e3:
                    logger.warning("Failed to generate analysis diff for site %s: %s", site_id, e3)
            except Exception as e:
                logger.warning("Failed to record health score history for site %s: %s", site_id, e)

        logger.info(
            "Health scoring complete for site %s — %d posts scored (ga4=%s, gsc=%s)",
            site_id, total_scored, has_ga4, has_gsc,
        )
        return total_scored

    async def _score_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
        has_ga4: bool = True, has_gsc: bool = True, is_short_form: bool = False,
    ) -> int:
        """Score all posts in a cluster and assign ecosystem state.

        When has_ga4/has_gsc are False, dynamically rebalances weights
        to use only crawl-derived factors (graceful degradation).
        """
        now = datetime.now(UTC)
        ninety_days_ago = now - timedelta(days=90)
        sixty_days_ago = now - timedelta(days=60)
        thirty_days_ago = now - timedelta(days=30)

        # Get dynamic weights based on data availability
        weights = compute_dynamic_weights(has_ga4, has_gsc)

        # ── Batch 1: Posts in cluster ──
        # Minimum 100 words — excludes tool pages, redirects, index pages
        post_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.publish_date, p.modified_date,
                   p.word_count, p.headings, p.meta_description, p.body_html,
                   p.readability_score, p.eeat_metadata, p.page_type
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            WHERE pc.cluster_id = $1
              AND (p.word_count IS NULL OR p.word_count >= 100)
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

        # ── Batch 7: AI readiness scores ──
        ai_rows = await db.fetch(
            """
            SELECT post_id, ai_citability_score, eeat_score, schema_score, extraction_score
            FROM post_health_scores
            WHERE post_id = ANY($1::uuid[])
              AND ai_citability_score IS NOT NULL
            """,
            post_ids,
        )
        ai_scores_map: dict[UUID, dict] = {
            r["post_id"]: dict(r) for r in ai_rows
        }

        # S4-01: Warn if most posts lack AI citability scores (Step 6c dependency)
        ai_null_count = len(post_ids) - len(ai_rows)
        if ai_null_count > len(post_ids) * 0.5:
            logger.warning(
                "Cluster %s: %d/%d posts lack AI citability scores — health scores will have reduced variance. "
                "Ensure AI citability (Step 6c) runs before health scoring.",
                cluster_id, ai_null_count, len(post_ids),
            )

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
            depth_score = _content_depth_score(wc, cluster_avg_word_count, body_html=row.get("body_html"), short_form=is_short_form)

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
                eeat_metadata=row.get("eeat_metadata"),
            )

            # Factor 8: Predicted Engagement proxy (crawl-only substitute for GA4 engagement)
            predicted_engagement = _predicted_engagement_score(
                body_html=row.get("body_html"),
                readability_score=row.get("readability_score"),
                headings=row.get("headings"),
            )

            # Factor 9: Content Structure (crawl-only richness signal)
            content_structure = _content_structure_score(
                body_html=row.get("body_html"),
                word_count=wc,
                headings=row.get("headings"),
            )

            # S4-25: Merged content_richness factor (average of predicted_engagement + content_structure)
            # Eliminates triple-counting between these two and technical_seo (r=0.59-0.61).
            content_richness = (predicted_engagement + content_structure) / 2.0

            # Factor 10: AI Readiness — average of 4 AI dimensions
            # Must run ai_citability BEFORE health_scoring in the pipeline.
            ai_scores_row = ai_scores_map.get(post_id)
            if ai_scores_row:
                ai_readiness_score = compute_ai_readiness(
                    ai_citability_score=ai_scores_row.get("ai_citability_score"),
                    eeat_score=ai_scores_row.get("eeat_score"),
                    schema_score=ai_scores_row.get("schema_score"),
                    extraction_score=ai_scores_row.get("extraction_score"),
                    default=40.0,
                )
            else:
                ai_readiness_score = 40.0  # Neutral default — don't penalize unscored posts

            # Composite (0-100) — dynamically weighted
            composite = (
                weights["traffic_trend"] * trend_score
                + weights["ranking"] * ranking_score
                + weights["engagement"] * engagement_score
                + weights["freshness"] * freshness_score
                + weights["content_depth"] * depth_score
                + weights["internal_links"] * link_score
                + weights["technical_seo"] * tech_score
                + weights["ai_readiness"] * ai_readiness_score
                + weights.get("content_richness", 0) * content_richness
                + weights.get("predicted_engagement", 0) * predicted_engagement
                + weights.get("content_structure", 0) * content_structure
            )

            # Traffic contribution (for cluster weighting)
            total_cluster_traffic = sum(traffic_90d_map.values()) or 1
            traffic_contribution = traffic_90d_map.get(post_id, 0) / total_cluster_traffic

            # Role assignment
            is_cannibalizing = post_id in cannibalizing_ids
            has_traffic_data = has_ga4 or has_gsc
            page_type = row.get("page_type") or "blog"
            role = _assign_role(composite, traffic_contribution, r_pv, is_cannibalizing, has_traffic_data=has_traffic_data, page_type=page_type)

            # Page importance multiplier for prioritisation
            if inbound >= 10:
                pass  # Hub / pillar page
            elif inbound >= 5:
                pass

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
                "page_type": page_type,
                "traffic": traffic_90d_map.get(post_id, 0),
                "publish_date": row["publish_date"],
            })

        # ── Score clamping (no normalization) ──
        # Z-score normalization was removed because it forces every cluster's
        # mean to exactly 50, destroying the variance that AI Readiness (36%
        # weight) creates between clusters. Raw composites already have real
        # spread from the rebalanced weights. Just clamp to valid range.
        for m in post_metrics:
            m["composite"] = max(10.0, min(95.0, m["composite"]))

        # S4-30: Relative pillar threshold in crawl-only mode.
        # Absolute thresholds produce too many pillars (28%) because crawl-only
        # scores compress into a narrow band. Use the 85th percentile composite
        # within this cluster as the pillar cutoff — ensures pillar = top ~15%.
        has_traffic_data = has_ga4 or has_gsc
        if not has_traffic_data and len(post_metrics) >= 3:
            sorted_composites = sorted(m["composite"] for m in post_metrics)
            pillar_cutoff = sorted_composites[int(len(sorted_composites) * 0.85)]
            for m in post_metrics:
                if m["role"] == "competitor":
                    continue  # Don't override cannibalization-based role
                if m["composite"] >= pillar_cutoff:
                    # Landing/index pages are structural, never pillars
                    pt = m.get("page_type") or "blog"
                    m["role"] = "supporter" if pt in ("landing", "index") else "pillar"
                elif m["composite"] >= 30:
                    m["role"] = "supporter"
                elif m["composite"] >= 15:
                    m["role"] = "at_risk"
                else:
                    m["role"] = "dead_weight"

        # Determine score confidence level
        score_confidence = (
            "full" if has_ga4 and has_gsc
            else "partial" if has_ga4 or has_gsc
            else "crawl_only"
        )

        # ── Batch upsert health scores (one per post in leaf clusters) ──
        await db.executemany(
            """
            INSERT INTO post_health_scores
                (post_id, traffic_contribution, ranking_strength,
                 trend, internal_link_score, composite_score, role,
                 engagement_score, freshness_score, content_depth_score,
                 technical_seo_score, score_confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (post_id) DO UPDATE SET
                traffic_contribution = EXCLUDED.traffic_contribution,
                ranking_strength = EXCLUDED.ranking_strength,
                trend = EXCLUDED.trend,
                internal_link_score = EXCLUDED.internal_link_score,
                composite_score = EXCLUDED.composite_score,
                role = EXCLUDED.role,
                engagement_score = EXCLUDED.engagement_score,
                freshness_score = EXCLUDED.freshness_score,
                content_depth_score = EXCLUDED.content_depth_score,
                technical_seo_score = EXCLUDED.technical_seo_score,
                score_confidence = EXCLUDED.score_confidence
            """,
            [
                (
                    m["post_id"], m["traffic_contribution"], m["ranking_strength"],
                    m["trend"], m["internal_link_score"], m["composite"],
                    m["role"], m["engagement_score"], m["freshness_score"],
                    m["content_depth_score"], m["technical_seo_score"],
                    score_confidence,
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
                has_traffic_data=has_ga4 or has_gsc,
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

    async def patch_roles_after_cannibalization(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Lightweight role + ecosystem state patch after cannibalization detection.

        Runs after Step 8 (cannibalization) to fix:
        1. Posts in medium/high/critical pairs get "competitor" role
        2. Cannibalization rate per cluster is recalculated
        3. Ecosystem state re-evaluated for affected clusters

        This avoids re-running the full health scorer while fixing the two
        outputs that depend on cannibalization data (which didn't exist on
        the first health scoring pass).
        """
        # Detect data availability for ecosystem state logic
        ga4_count = await db.fetchval(
            "SELECT COUNT(*) FROM ga4_metrics WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1) LIMIT 1",
            site_id,
        )
        has_traffic_data = (ga4_count or 0) > 0

        # 1. Find all posts in medium/high/critical cannibalization pairs
        cannibal_posts = await db.fetch(
            """
            SELECT DISTINCT post_id FROM (
                SELECT cp.post_a_id AS post_id FROM cannibalization_pairs cp
                JOIN posts p ON p.id = cp.post_a_id
                WHERE p.site_id = $1 AND cp.severity IN ('medium', 'high', 'critical')
                UNION
                SELECT cp.post_b_id AS post_id FROM cannibalization_pairs cp
                JOIN posts p ON p.id = cp.post_b_id
                WHERE p.site_id = $1 AND cp.severity IN ('medium', 'high', 'critical')
            ) sub
            """,
            site_id,
        )
        cannibal_ids = {r["post_id"] for r in cannibal_posts}

        if not cannibal_ids:
            logger.info("No cannibalization pairs for site %s -- role patch skipped", site_id)
            return 0

        # 2. Mark cannibalizing posts as "competitor" (only if not already pillar)
        patched = await db.execute(
            """
            UPDATE post_health_scores SET role = 'competitor'
            WHERE post_id = ANY($1::uuid[])
              AND role != 'pillar'
            """,
            list(cannibal_ids),
        )
        patched_count = int(patched.split()[-1]) if patched else 0
        logger.info("Role patch: marked %d posts as competitor for site %s", patched_count, site_id)

        # 3. Re-evaluate ecosystem state for affected clusters
        affected_clusters = await db.fetch(
            """
            SELECT DISTINCT c.id AS cluster_id
            FROM clusters c
            JOIN post_clusters pc ON pc.cluster_id = c.id
            WHERE c.site_id = $1
              AND pc.post_id = ANY($2::uuid[])
              AND c.id NOT IN (
                  SELECT parent_cluster_id FROM clusters
                  WHERE parent_cluster_id IS NOT NULL AND site_id = $1
              )
            """,
            site_id, list(cannibal_ids),
        )

        now = datetime.now(UTC)
        thirty_days_ago = now - timedelta(days=30)

        for cluster_row in affected_clusters:
            cid = cluster_row["cluster_id"]

            # Fetch post metrics for this cluster
            metrics = await db.fetch(
                """
                SELECT phs.composite_score, phs.role, phs.trend,
                       phs.traffic_contribution, p.publish_date
                FROM post_health_scores phs
                JOIN post_clusters pc ON pc.post_id = phs.post_id
                JOIN posts p ON p.id = phs.post_id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )
            if not metrics:
                continue

            post_metrics = [
                {
                    "composite": float(m["composite_score"] or 0),
                    "role": m["role"] or "dead_weight",
                    "trend": m["trend"] or "unknown",
                    "traffic": float(m["traffic_contribution"] or 0),
                    "publish_date": m["publish_date"],
                }
                for m in metrics
            ]

            # Count cannibalization pairs for this cluster
            pair_count = await db.fetchval(
                "SELECT COUNT(*) FROM cannibalization_pairs WHERE cluster_id = $1 AND severity IN ('medium', 'high', 'critical')",
                cid,
            )

            cluster_health = await db.fetchval(
                "SELECT health_score FROM clusters WHERE id = $1", cid,
            ) or 0

            ecosystem_state = _assign_ecosystem_state(
                post_metrics=post_metrics,
                cannibal_pairs_count=pair_count or 0,
                post_count=len(post_metrics),
                cluster_health=float(cluster_health),
                now=now,
                thirty_days_ago=thirty_days_ago,
                has_traffic_data=has_traffic_data,
            )

            await db.execute(
                "UPDATE clusters SET ecosystem_state = $1, updated_at = NOW() WHERE id = $2",
                ecosystem_state, cid,
            )

        logger.info(
            "Role patch complete for site %s: %d competitors marked, %d clusters re-evaluated",
            site_id, patched_count, len(affected_clusters),
        )
        return patched_count


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

    Position 1 = 100, Position 3 = ~80, Position 10 = ~35, Position 20 = ~15, Position 50+ = 0.
    Uses a steeper exponent (1.5) because positions beyond 10 get near-zero real traffic.
    """
    if avg_position <= 1:
        return 100.0
    if avg_position >= 50:
        return 0.0

    # Steep exponential decay — top 3 positions get the vast majority of clicks
    return max(0.0, 100.0 * (1.0 - (avg_position - 1.0) / 49.0) ** 1.5)


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
        return 35.0  # No date known — slightly above evergreen floor (30). Don't reward missing dates over known-old dates.

    time_sensitive = _is_time_sensitive(title, url)
    evergreen_floor = 10.0 if time_sensitive else 30.0

    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)

    days_old = (now - last_updated).days
    months_old = days_old / 30.44  # Average days per month

    import math

    # Continuous exponential decay with half-life approach
    # Evergreen: half-life 12 months → today=100, 6mo=71, 12mo=50, 24mo=25
    # Time-sensitive: half-life 6 months → today=100, 3mo=71, 6mo=50, 12mo=25
    if months_old < 0.5:
        return 100.0
    half_life = 6.0 if time_sensitive else 12.0
    raw = 100.0 * math.pow(0.5, months_old / half_life)
    return max(evergreen_floor, raw)


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
    ext_links = re.findall(r'href=["\']https?://', html)
    if ext_links:
        bonus += min(3.0, len(ext_links) * 0.3)
    # Images
    if "<img" in html or "<picture" in html or "<figure" in html:
        bonus += 2.0
    return min(15.0, bonus)


def _content_depth_score(
    word_count: int, cluster_avg: float, body_html: str | None = None, short_form: bool = False,
) -> float:
    """Content depth score 0-100 based on word count vs cluster average.

    For short-form sites (median < 600w), uses a gentler absolute curve
    that doesn't penalize concise writing as heavily.
    """
    if cluster_avg <= 0:
        cluster_avg = 500.0

    # Absolute scale depends on content profile
    if short_form:
        # Short-form: 200w=40, 500w=70, 1000+=100
        if word_count < 50:
            absolute = word_count / 50.0 * 5.0
        elif word_count < 200:
            absolute = 20.0 + (word_count - 50) / 150.0 * 20.0  # 20-40
        elif word_count < 500:
            absolute = 40.0 + (word_count - 200) / 300.0 * 30.0  # 40-70
        else:
            absolute = min(100.0, 70.0 + (word_count - 500) / 500.0 * 30.0)  # 70-100
    else:
        # Long-form: 0w=0, 500=25, 1000=50, 2000=80, 3000+=100
        absolute = min(100.0, (word_count / 2500.0) * 100.0) if word_count >= 100 else word_count / 100.0 * 5.0

    # Relative scale: how does this compare to cluster peers?
    # Wider curve: 0.5x avg = 20, 1.0x avg = 50, 1.5x avg = 80, 2.0x avg = 95
    ratio = word_count / cluster_avg
    if ratio < 0.3:
        relative = 5.0
    elif ratio < 0.5:
        relative = 5.0 + (ratio - 0.3) * 75.0  # 5-20
    elif ratio < 1.0:
        relative = 20.0 + (ratio - 0.5) * 60.0  # 20-50
    elif ratio < 1.5:
        relative = 50.0 + (ratio - 1.0) * 60.0  # 50-80
    elif ratio < 2.0:
        relative = 80.0 + (ratio - 1.5) * 30.0  # 80-95
    else:
        relative = min(100.0, 95.0 + (ratio - 2.0) * 5.0)  # 95-100

    # Blend — short-form sites weight relative higher (their cluster avg IS the right length)
    if short_form:
        base = 0.35 * absolute + 0.65 * relative
    else:
        base = 0.5 * absolute + 0.5 * relative

    # Quality bonus cap is higher for short-form (density matters more than length)
    bonus = _content_quality_bonus(body_html)
    max_bonus = 25.0 if short_form else 15.0
    bonus = min(max_bonus, bonus)
    return min(100.0, base + bonus)


def _technical_seo_score(
    meta_description: str | None,
    title: str | None,
    headings: list | str | None,
    has_outbound: bool,
    has_inbound: bool,
    body_html: str | None = None,
    eeat_metadata: dict | None = None,
) -> float:
    """Technical SEO score 0-100 based on extended checklist.

    8 checks (12.5 points each):
    1. Has meta description
    2. Title length 30-60 chars
    3. Has H2+ headings
    4. Has outbound internal links
    5. Has inbound internal links
    6. Has Open Graph tags (from eeat_metadata, extracted from <head> during crawl)
    7. Has structured data / JSON-LD (from eeat_metadata)
    8. Has canonical tag (from eeat_metadata)
    """
    score = 0.0
    pts = 12.5  # 8 checks × 12.5 = 100
    eeat = eeat_metadata or {}
    if isinstance(eeat, str):
        import json as _json
        try:
            eeat = _json.loads(eeat)
        except (ValueError, TypeError):
            eeat = {}

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

    # 6. Open Graph tags — from eeat_metadata (extracted from <head> during crawl)
    # body_html only contains article content, so OG tags in <head> are invisible there.
    if eeat.get("has_og_tags"):
        score += pts
    elif body_html and ('og:title' in body_html.lower() or 'property="og:' in body_html.lower()):
        score += pts  # fallback for inline OG (rare)

    # 7. Structured data (JSON-LD) — from eeat_metadata
    if eeat.get("has_jsonld") or eeat.get("schema_types"):
        score += pts
    elif body_html and 'application/ld+json' in body_html.lower():
        score += pts  # fallback for inline JSON-LD

    # 8. Canonical tag — from eeat_metadata
    if eeat.get("has_canonical"):
        score += pts
    elif body_html and ('rel="canonical"' in body_html.lower() or "rel='canonical'" in body_html.lower()):
        score += pts  # fallback

    return min(100.0, score)


def _predicted_engagement_score(
    body_html: str | None = None,
    readability_score: float | None = None,
    headings: list | None = None,
) -> float:
    """Predict engagement from structural signals (proxy for GA4 bounce/time).

    Sites without GA4 get this as a substitute for the engagement factor.
    """
    score = 0.0
    html = body_html or ""

    # Has images (lower bounce)
    if any(tag in html for tag in ["<img", "<picture", "<figure", "data-src"]):
        score += 20.0

    # Has lists (better scannability)
    if "<li" in html:
        score += 15.0

    # Readability in sweet spot (60-80 Flesch = easy to read but not simplistic)
    if readability_score is not None:
        if 60 <= readability_score <= 80:
            score += 20.0
        elif 40 <= readability_score < 60 or 80 < readability_score <= 90:
            score += 10.0

    # Good heading structure (3+ H2s = well-organized)
    h_count = len(headings) if headings else 0
    if h_count >= 5:
        score += 15.0
    elif h_count >= 3:
        score += 10.0

    # Table of contents signal (long posts with many headings)
    if h_count >= 6 and "table of contents" in html.lower():
        score += 10.0

    # Code blocks (for technical content — shows depth)
    if "<pre" in html or "<code" in html:
        score += 10.0

    # S4-17: Normalize to full 0-100 scale. Max achievable is ~90
    # (images 20 + lists 15 + readability 20 + headings 15 + ToC 10 + code 10).
    # Without normalization, 8% weight on a 0-90 factor is effectively 7.2% on 0-100.
    score = score * (100.0 / 90.0)
    return min(100.0, score)


def _content_structure_score(
    body_html: str | None = None,
    word_count: int = 0,
    headings: list | None = None,
) -> float:
    """Score content richness/structure (proxy for content quality without traffic data)."""
    score = 0.0
    html = body_html or ""

    # Heading density (H2s per 500 words)
    h_count = len(headings) if headings else 0
    if word_count > 0:
        density = h_count / (word_count / 500.0)
        if density >= 1.5:
            score += 25.0
        elif density >= 0.8:
            score += 15.0
        elif density >= 0.4:
            score += 8.0

    # List richness
    li_count = html.count("<li")
    if li_count >= 10:
        score += 20.0
    elif li_count >= 5:
        score += 12.0
    elif li_count >= 2:
        score += 5.0

    # Image count
    img_count = html.count("<img") + html.count("<picture") + html.count("<figure")
    if img_count >= 5:
        score += 20.0
    elif img_count >= 2:
        score += 12.0
    elif img_count >= 1:
        score += 5.0

    # Tables
    if "<table" in html:
        score += 15.0

    # External links (authority signals)
    ext_links = html.count('href="http') - html.count('href="http://localhost') - html.count('href="https://localhost')
    if ext_links >= 5:
        score += 15.0
    elif ext_links >= 2:
        score += 8.0

    # Blockquotes (citations, expert quotes)
    if "<blockquote" in html:
        score += 5.0

    return min(100.0, score)


def _assign_role(
    composite: float,
    traffic_contribution: float,
    recent_pv: int,
    is_cannibalizing: bool,
    has_traffic_data: bool = True,
    page_type: str = "blog",
) -> str:
    """Assign a role to a post based on its health metrics.

    When no traffic data is available (no GSC/GA4), derive role from
    composite score alone so posts aren't all labelled dead_weight.

    Landing and index pages are never assigned the "pillar" role — they
    are structural pages, not content pillars.
    """
    # Landing/index pages should never be pillars — they're structural pages
    is_structural = page_type in ("landing", "index")

    if not has_traffic_data:
        if is_cannibalizing:
            return "competitor"
        if composite >= 45:
            return "supporter" if is_structural else "pillar"
        if composite >= 30:
            return "supporter"
        if composite >= 15:
            return "at_risk"
        return "dead_weight"

    if composite < 15 or recent_pv == 0:
        return "dead_weight"
    if is_cannibalizing:
        return "competitor"
    if traffic_contribution > 0.25 and composite >= 40:
        return "supporter" if is_structural else "pillar"
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
    has_traffic_data: bool = True,
) -> str:
    """Assign ecosystem state to a cluster."""
    has_pillar = any(m["role"] == "pillar" for m in post_metrics)

    total_possible_pairs = post_count * (post_count - 1) / 2 if post_count > 1 else 1
    cannibalization_rate = cannibal_pairs_count / total_possible_pairs

    has_recent = any(
        m["publish_date"] is not None
        and m["publish_date"].replace(tzinfo=UTC) >= thirty_days_ago
        for m in post_metrics
    )

    # Seedbed: recent posts, small cluster
    if has_recent and post_count <= 3:
        return "seedbed"

    # S4-22: Forest health threshold is lower in crawl-only mode because
    # composites compress into a narrower band (~27-55 vs ~10-95 with traffic).
    # With traffic: 50. Without: 38 (achievable for top clusters).
    forest_health_threshold = 50.0 if has_traffic_data else 38.0

    if has_traffic_data:
        # With traffic data, use full signals
        all_declining = all(m["trend"] in ("declining", "dead") for m in post_metrics)
        avg_traffic = sum(m["traffic"] for m in post_metrics) / post_count if post_count > 0 else 0

        if cannibalization_rate > 0.5 or (post_count > 8 and not has_pillar):
            return "swamp"
        if all_declining or avg_traffic < 5:
            return "desert"
        if has_pillar and cannibalization_rate < 0.2 and cluster_health > forest_health_threshold:
            return "forest"
    else:
        # Without traffic, use content quality signals only
        avg_freshness = sum(m.get("freshness_score", 45) for m in post_metrics) / max(post_count, 1)

        # Swamp: only if cannibalization is genuinely high (>50%)
        if cannibalization_rate > 0.5:
            return "swamp"
        # Desert: very stale content
        if avg_freshness < 25:
            return "desert"
        # Forest: has pillar, low cannibalization, good health
        if has_pillar and cannibalization_rate < 0.2 and cluster_health > forest_health_threshold:
            return "forest"

    # Meadow: everything else
    return "meadow"
