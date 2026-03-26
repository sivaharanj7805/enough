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
from datetime import UTC, datetime, timedelta
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
        # Crawl-only mode — use proxy signals instead of zeroing 50%
        return {
            "traffic_trend": 0.0,
            "ranking": 0.0,
            "engagement": 0.0,
            "freshness": 0.12,
            "content_depth": 0.10,
            "internal_links": 0.08,
            "technical_seo": 0.07,
            "ai_readiness": 0.18,
            "predicted_engagement": 0.25,
            "content_structure": 0.20,
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

        # Score clusters — parallel for large sites, sequential for small
        total_scored = 0
        if len(clusters) > 10:
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
            for r in results:
                if isinstance(r, int):
                    total_scored += r
                elif isinstance(r, Exception):
                    logger.warning("Cluster scoring failed: %s", r)
        else:
            for cluster_row in clusters:
                scored = await self._score_cluster(
                    db, cluster_row["id"], site_id,
                    has_ga4=has_ga4, has_gsc=has_gsc,
                    is_short_form=is_short_form,
                )
                total_scored += scored

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
                factor_scores = {}
                if factor_row:
                    for key in ("engagement", "freshness", "content_depth",
                                "internal_links", "technical_seo", "ranking", "traffic"):
                        val = factor_row[key]
                        factor_scores[key] = float(val) if val is not None else None

                await db.execute(
                    """INSERT INTO health_score_history (site_id, score, factor_scores, analyzed_at)
                       VALUES ($1, $2, $3, NOW())""",
                    site_id, float(avg_score or 0), json.dumps(factor_scores),
                )
                logger.info("Recorded health score history for site %s: %.1f", site_id, avg_score or 0)
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
                   p.readability_score
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

            # Factor 10: AI Readiness (15%) — average of 4 AI dimensions
            ai_scores_row = ai_scores_map.get(post_id)
            if ai_scores_row:
                ai_dims = [v for v in [
                    ai_scores_row.get("ai_citability_score"),
                    ai_scores_row.get("eeat_score"),
                    ai_scores_row.get("schema_score"),
                    ai_scores_row.get("extraction_score"),
                ] if v is not None]
                ai_readiness_score = sum(ai_dims) / len(ai_dims) if ai_dims else 0.0
            else:
                ai_readiness_score = 0.0

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
                + weights.get("predicted_engagement", 0) * predicted_engagement
                + weights.get("content_structure", 0) * content_structure
            )

            # Traffic contribution (for cluster weighting)
            total_cluster_traffic = sum(traffic_90d_map.values()) or 1
            traffic_contribution = traffic_90d_map.get(post_id, 0) / total_cluster_traffic

            # Role assignment
            is_cannibalizing = post_id in cannibalizing_ids
            has_traffic_data = has_ga4 or has_gsc
            role = _assign_role(composite, traffic_contribution, r_pv, is_cannibalizing, has_traffic_data=has_traffic_data)

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
                "traffic": traffic_90d_map.get(post_id, 0),
                "publish_date": row["publish_date"],
            })

        # ── Z-score normalization: spread scores across wider range ──
        # Spread factor of 12 differentiates posts without crushing low-scorers.
        # Only activate when stddev > 2.0 — tight clusters (low variance)
        # shouldn't be artificially spread. Floor of 15 prevents implausible
        # single-digit scores (a real post with content should never be 5/100).
        if post_metrics:
            raw_scores = [m["composite"] for m in post_metrics]
            mean_score = sum(raw_scores) / len(raw_scores)
            variance = sum((s - mean_score) ** 2 for s in raw_scores) / max(len(raw_scores), 1)
            stddev = variance ** 0.5
            if stddev > 2.0:
                for m in post_metrics:
                    normalized = 50 + (m["composite"] - mean_score) / stddev * 12
                    m["composite"] = max(15.0, min(95.0, normalized))

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
        return 60.0  # No date known — slightly above neutral, don't penalise

    time_sensitive = _is_time_sensitive(title, url)
    evergreen_floor = 10.0 if time_sensitive else 45.0

    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)

    days_old = (now - last_updated).days
    months_old = days_old / 30.44  # Average days per month

    import math

    # Continuous exponential decay instead of step function
    # 1 month = 95, 3 months = 86, 6 months = 74, 12 months = 55, 24 months = 30
    if months_old < 1:
        return 100.0
    raw = 100.0 * math.exp(-0.05 * months_old)
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
    ratio = word_count / cluster_avg
    if ratio < 0.5:
        relative = 15.0
    elif ratio < 0.75:
        relative = 35.0
    elif ratio < 1.0:
        relative = 50.0 + (ratio - 0.75) * 40.0  # 50-60
    elif ratio < 1.5:
        relative = 60.0 + (ratio - 1.0) * 60.0  # 60-90
    else:
        relative = min(100.0, 90.0 + (ratio - 1.5) * 20.0)  # 90-100

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
    if html and ('rel="canonical"' in html or "rel='canonical'" in html):
        score += pts

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
) -> str:
    """Assign a role to a post based on its health metrics.

    When no traffic data is available (no GSC/GA4), derive role from
    composite score alone so posts aren't all labelled dead_weight.
    """
    if not has_traffic_data:
        # Derive role from composite score (content quality signals only)
        if is_cannibalizing:
            return "competitor"
        if composite >= 55:
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

    if has_traffic_data:
        # With traffic data, use full signals
        all_declining = all(m["trend"] in ("declining", "dead") for m in post_metrics)
        avg_traffic = sum(m["traffic"] for m in post_metrics) / post_count if post_count > 0 else 0

        if cannibalization_rate > 0.5 or (post_count > 8 and not has_pillar):
            return "swamp"
        if all_declining or avg_traffic < 5:
            return "desert"
        if has_pillar and cannibalization_rate < 0.2 and cluster_health > 50:
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
        if has_pillar and cannibalization_rate < 0.2 and cluster_health > 50:
            return "forest"

    # Meadow: everything else
    return "meadow"
