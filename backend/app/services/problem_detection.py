"""Content problem detection — decay, thin content, SEO issues, orphans,
readability, velocity decline.

Scans all posts for a site and stores detected problems in the
content_problems table. Designed to run after health scoring completes.

Problems are idempotent — re-running clears and re-detects.

Problem types:
  decay_severe, decay_moderate, decay_mild
  thin_content, thin_below_cluster_avg, thin_high_bounce
  seo_missing_meta, seo_title_length, seo_no_headings,
  seo_no_internal_links, seo_no_images
  orphan
  readability_too_complex     (NEW: Flesch < 40)
  velocity_decline            (NEW: publishing rate dropped 50%+)
  intent_mismatch             (NEW: detected by IntentClassifier)
  serp_opportunity_missed     (NEW: detected by SERPFeatureDetector)
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class ProblemDetector:
    """Detect content problems across a site."""

    def __init__(self) -> None:
        self._first_detected_map: dict[tuple, datetime] = {}

    def _get_first_detected(self, post_id, problem_type: str):
        """Look up preserved first_detected_at for a continuing problem."""
        return self._first_detected_map.get((str(post_id), problem_type))

    async def detect_all(self, db: asyncpg.Connection, site_id: UUID) -> dict[str, int]:
        """Run all problem detection scans for a site.

        Automatically detects data availability and skips checks that
        require missing data sources (graceful degradation).

        Returns a dict of problem_type → count.
        """
        logger.info("Starting problem detection for site %s", site_id)

        # Detect data availability
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

        # Preserve first_detected_at for continuing problems
        # Save existing problem fingerprints before clearing
        existing_problems = await db.fetch(
            """
            SELECT post_id, problem_type, first_detected_at
            FROM content_problems
            WHERE site_id = $1
            """,
            site_id,
        )
        first_detected_map: dict[tuple, datetime] = {}
        for ep in existing_problems:
            key = (str(ep["post_id"]), ep["problem_type"])
            if ep["first_detected_at"]:
                first_detected_map[key] = ep["first_detected_at"]

        # Store the map for use in insert methods
        self._first_detected_map = first_detected_map

        # Clear old problems (idempotent)
        await db.execute(
            "DELETE FROM content_problems WHERE site_id = $1", site_id,
        )

        counts: dict[str, int] = {}

        # Each detector is wrapped in try/except so one crashing detector
        # doesn't kill all subsequent ones. Partial results > no results.

        # Decay detection: GSC-based signals + proxy signals (crawl-based).
        # Proxy decay always runs — it's the crawl-only fallback.
        counts["decay"] = 0
        if has_gsc:
            try:
                counts["decay"] = await self._detect_content_decay(db, site_id)
            except Exception:
                logger.exception("GSC decay detection failed for site %s", site_id)
        else:
            logger.info("Skipping GSC decay detection — no GSC data for site %s", site_id)

        # Proxy decay: always runs (uses crawl dates + title patterns, no GSC needed)
        try:
            counts["decay"] += await self._detect_proxy_decay(db, site_id)
        except Exception:
            logger.exception("Proxy decay detection failed for site %s", site_id)

        # Thin content: absolute word count works without external data,
        # but bounce/engagement check needs GA4
        try:
            counts["thin"] = await self._detect_thin_content(db, site_id, has_ga4=has_ga4)
        except Exception:
            logger.exception("Thin content detection failed for site %s", site_id)
            counts["thin"] = 0

        # Quality gate: check internal link resolution rate before orphan/link checks.
        # On capped crawls (e.g., 150 of 3000 URLs), most link targets don't exist
        # in the dataset, inflating orphan/no-internal-links counts to near 100%.
        # Skip those checks if resolution rate < 20%.
        link_resolution_reliable = True
        try:
            total_links = await db.fetchval(
                "SELECT COUNT(*) FROM internal_links WHERE site_id = $1", site_id,
            )
            resolved_links = await db.fetchval(
                "SELECT COUNT(*) FROM internal_links WHERE site_id = $1 AND target_post_id IS NOT NULL",
                site_id,
            )
            resolution_rate = resolved_links / max(total_links, 1)
            if total_links > 0 and resolution_rate < 0.20:
                link_resolution_reliable = False
                logger.warning(
                    "Internal link resolution rate is %.1f%% for site %s "
                    "(%d/%d links resolved) — skipping orphan and seo_no_internal_links "
                    "detection (data unreliable, likely capped crawl)",
                    resolution_rate * 100, site_id, resolved_links, total_links,
                )
        except Exception:
            logger.exception("Link resolution rate check failed for site %s — skipping link-based checks", site_id)
            link_resolution_reliable = False

        # SEO issues: fully crawl-based, always runs
        # Pass link_resolution_reliable so seo_no_internal_links is skipped on capped crawls
        try:
            counts["seo"] = await self._detect_seo_issues(
                db, site_id, skip_link_check=not link_resolution_reliable,
            )
        except Exception:
            logger.exception("SEO issue detection failed for site %s", site_id)
            counts["seo"] = 0

        # Orphans: skip if link resolution is unreliable (capped crawl)
        if link_resolution_reliable:
            try:
                counts["orphan"] = await self._detect_orphans(db, site_id)
            except Exception:
                logger.exception("Orphan detection failed for site %s", site_id)
                counts["orphan"] = 0
        else:
            counts["orphan"] = 0
            logger.info("Skipping orphan detection — link resolution unreliable for site %s", site_id)

        # Readability: fully crawl-based, always runs
        try:
            counts["readability"] = await self._detect_readability_issues(db, site_id)
        except Exception:
            logger.exception("Readability detection failed for site %s", site_id)
            counts["readability"] = 0

        # Velocity decline: needs publish dates (crawl-based)
        try:
            counts["velocity"] = await self._detect_velocity_decline(db, site_id)
        except Exception:
            logger.exception("Velocity decline detection failed for site %s", site_id)
            counts["velocity"] = 0

        # AI readiness: 2026 SEO signals — runs if ai_citability_score already computed
        try:
            counts["ai_readiness"] = await self._detect_ai_readiness_issues(db, site_id)
        except Exception:
            logger.exception("AI readiness detection failed for site %s", site_id)
            counts["ai_readiness"] = 0

        # Group related problems and suppress duplicates.
        # When orphan + seo_no_internal_links co-occur, the latter is deleted.
        # Subtract suppressed count from seo to keep counts accurate.
        try:
            suppressed = await self._group_related_problems(db, site_id)
            counts["seo"] = max(0, counts.get("seo", 0) - suppressed)
        except Exception:
            logger.exception("Related problem grouping failed for site %s", site_id)

        total = sum(counts.values())
        logger.info(
            "Problem detection complete for site %s — %d total problems "
            "(decay=%d, thin=%d, seo=%d, orphan=%d, readability=%d, velocity=%d, ai=%d) "
            "[ga4=%s, gsc=%s]",
            site_id, total, counts["decay"], counts["thin"],
            counts["seo"], counts["orphan"], counts["readability"],
            counts["velocity"], counts["ai_readiness"], has_ga4, has_gsc,
        )
        return counts

    async def _detect_ai_readiness_issues(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect AI-era SEO problems: low citability, weak E-E-A-T, missing schema, poor structure."""
        # Only run if AI scores have been computed
        scored_count = await db.fetchval(
            """SELECT COUNT(*) FROM post_health_scores phs
               JOIN posts p ON p.id = phs.post_id
               WHERE p.site_id = $1 AND phs.ai_citability_score IS NOT NULL""",
            site_id,
        )
        if not scored_count:
            logger.info("Skipping AI readiness problems — scores not yet computed for site %s", site_id)
            return 0

        rows = await db.fetch(
            """SELECT phs.post_id, p.title,
                      phs.ai_citability_score, phs.eeat_score,
                      phs.schema_score, phs.extraction_score, phs.ai_signals
               FROM post_health_scores phs
               JOIN posts p ON p.id = phs.post_id
               WHERE p.site_id = $1
                 AND phs.ai_citability_score IS NOT NULL""",
            site_id,
        )

        from app.services.ai_citability import generate_ai_problems
        count = 0
        problems_batch: list[tuple[UUID, UUID, str, str, dict]] = []
        for row in rows:
            signals = row["ai_signals"] or {}
            if isinstance(signals, str):
                import json as _json
                signals = _json.loads(signals)

            problems = generate_ai_problems(
                post_id=row["post_id"],
                title=row["title"] or "",
                cite=float(row["ai_citability_score"] or 0),
                eeat=float(row["eeat_score"] or 0),
                schema=float(row["schema_score"] or 0),
                extract=float(row["extraction_score"] or 0),
                signals=signals,
            )
            for p in problems:
                problems_batch.append((
                    p["post_id"], site_id,
                    p["problem_type"], p["severity"],
                    p.get("metadata", {}),
                ))
                count += 1

        await self._insert_problems_batch(db, problems_batch)
        logger.info("AI readiness problems: %d issues detected for site %s", count, site_id)
        return count

    @staticmethod
    async def _group_related_problems(db: asyncpg.Connection, site_id: UUID) -> int:
        """Deduplicate related problems on the same post.

        When both problems in a SUPPRESS group exist on the same post,
        the secondary problem is deleted entirely (orphan subsumes
        seo_no_internal_links — same customer action: add internal links).

        For MARK groups, the secondary problem is kept but annotated with
        details.related_to pointing to the root problem.
        """
        # Groups where the secondary is suppressed (deleted) — same action for the user
        SUPPRESS_GROUPS = [
            {"types": {"seo_no_internal_links", "orphan"}, "root": "orphan"},
        ]
        # Groups where secondary is kept but marked as related
        MARK_GROUPS = [
            {"types": {"thin_content", "thin_below_cluster_avg"}, "root": "thin_content"},
        ]

        problems = await db.fetch("""
            SELECT id, post_id, problem_type, details
            FROM content_problems WHERE site_id = $1
            ORDER BY post_id
        """, site_id)

        from itertools import groupby
        ids_to_delete: list = []
        for _post_id, post_probs in groupby(problems, key=lambda x: x["post_id"]):
            post_probs = list(post_probs)
            prob_types = {p["problem_type"] for p in post_probs}

            # Suppress groups: delete the secondary problem entirely
            for group in SUPPRESS_GROUPS:
                overlap = prob_types & group["types"]
                if len(overlap) > 1:
                    for p in post_probs:
                        if p["problem_type"] in overlap and p["problem_type"] != group["root"]:
                            ids_to_delete.append(p["id"])

            # Mark groups: annotate secondary with related_to
            for group in MARK_GROUPS:
                overlap = prob_types & group["types"]
                if len(overlap) > 1:
                    for p in post_probs:
                        if p["problem_type"] in overlap and p["problem_type"] != group["root"]:
                            details = json.loads(p["details"]) if isinstance(p["details"], str) else (p["details"] or {})
                            details["related_to"] = group["root"]
                            await db.execute(
                                "UPDATE content_problems SET details = $1 WHERE id = $2",
                                json.dumps(details), p["id"],
                            )

        # Batch delete suppressed problems
        if ids_to_delete:
            await db.execute(
                "DELETE FROM content_problems WHERE id = ANY($1::uuid[])",
                ids_to_delete,
            )
            logger.info(
                "Suppressed %d redundant problems (orphan subsumes seo_no_internal_links) for site %s",
                len(ids_to_delete), site_id,
            )

        return len(ids_to_delete)

    # ═══════════════════════════════════════════════
    # 2.9: Content decay detection
    # ═══════════════════════════════════════════════

    async def _detect_content_decay(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect decaying content.

        Flags posts where:
        1. Clicks dropped >30% in last 90 days vs previous 90 days
        2. Post not updated in 12+ months AND ranking page 2+ (position >10)
        3. Post once ranked top 5 and now ranks 10+

        Severity:
        - severe: >60% drop OR (was top 3, now 20+)
        - moderate: >30% drop OR (was top 5, now 10+)
        - mild: 12+ months old on page 2+
        """
        now = datetime.now(UTC)
        ninety_days_ago = now - timedelta(days=90)
        one_eighty_days_ago = now - timedelta(days=180)
        twelve_months_ago = now - timedelta(days=365)

        found = 0

        # ── Signal 1: Traffic/click decline (90d vs previous 90d) ──
        decline_rows = await db.fetch(
            """
            WITH recent AS (
                SELECT post_id, COALESCE(SUM(clicks), 0) AS clicks
                FROM gsc_metrics
                WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                  AND date >= $2
                GROUP BY post_id
            ),
            previous AS (
                SELECT post_id, COALESCE(SUM(clicks), 0) AS clicks
                FROM gsc_metrics
                WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                  AND date >= $3 AND date < $2
                GROUP BY post_id
            )
            SELECT p.id, p.title,
                   COALESCE(r.clicks, 0) AS recent_clicks,
                   COALESCE(prev.clicks, 0) AS prev_clicks
            FROM posts p
            LEFT JOIN recent r ON r.post_id = p.id
            LEFT JOIN previous prev ON prev.post_id = p.id
            WHERE p.site_id = $1
              AND COALESCE(prev.clicks, 0) > 10
              AND COALESCE(r.clicks, 0) < COALESCE(prev.clicks, 0) * 0.7
            """,
            site_id, ninety_days_ago.date(), one_eighty_days_ago.date(),
        )

        for r in decline_rows:
            prev_c = r["prev_clicks"]
            recent_c = r["recent_clicks"]
            pct_drop = (prev_c - recent_c) / max(prev_c, 1) * 100

            severity = "severe" if pct_drop > 60 else "moderate"
            problem_type = f"decay_{severity}"

            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, problem_type, severity,
                json.dumps({
                    "signal": "click_decline_90d",
                    "recent_clicks": recent_c,
                    "previous_clicks": prev_c,
                    "drop_percent": round(pct_drop, 1),
                }), self._get_first_detected(r["id"], problem_type),
            )
            found += 1

        # ── Signal 2: Old + page 2+ ──
        stale_rows = await db.fetch(
            """
            SELECT p.id, p.title,
                   p.modified_date, p.publish_date,
                   AVG(g.avg_position) AS avg_pos
            FROM posts p
            JOIN gsc_metrics g ON g.post_id = p.id
            WHERE p.site_id = $1
              AND g.date >= $2
              AND COALESCE(p.modified_date, p.publish_date) < $3
            GROUP BY p.id
            HAVING AVG(g.avg_position) > 10
            """,
            site_id, ninety_days_ago.date(), twelve_months_ago,
        )

        for r in stale_rows:
            last_update = r["modified_date"] or r["publish_date"]
            months_old = (now - last_update.replace(tzinfo=UTC)).days / 30.44

            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, "decay_mild", "medium",
                json.dumps({
                    "signal": "stale_plus_low_ranking",
                    "months_since_update": round(months_old, 1),
                    "avg_position": round(float(r["avg_pos"]), 1),
                }), self._get_first_detected(r["id"], "decay_mild"),
            )
            found += 1

        # ── Signal 3: Was top 5, now 10+ ──
        position_drop_rows = await db.fetch(
            """
            WITH historical AS (
                SELECT post_id, MIN(avg_position) AS best_position
                FROM gsc_metrics
                WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                  AND date < $2
                GROUP BY post_id
                HAVING MIN(avg_position) <= 5
            ),
            current AS (
                SELECT post_id, AVG(avg_position) AS current_position
                FROM gsc_metrics
                WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                  AND date >= $2
                GROUP BY post_id
                HAVING AVG(avg_position) > 10
            )
            SELECT h.post_id AS id, h.best_position, c.current_position
            FROM historical h
            JOIN current c ON c.post_id = h.post_id
            """,
            site_id, ninety_days_ago.date(),
        )

        for r in position_drop_rows:
            best_pos = float(r["best_position"])
            cur_pos = float(r["current_position"])
            severity = "severe" if best_pos <= 3 and cur_pos > 20 else "moderate"

            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, f"decay_{severity}", severity,
                json.dumps({
                    "signal": "position_drop",
                    "best_historic_position": round(best_pos, 1),
                    "current_position": round(cur_pos, 1),
                }), self._get_first_detected(r["id"], f"decay_{severity}"),
            )
            found += 1

        return found

    # ═══════════════════════════════════════════════
    # 2.10: Thin content detection
    # ═══════════════════════════════════════════════

    async def _detect_proxy_decay(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect content decay without GSC/GA4 data.

        Uses proxy signals:
        1. Outdated year references in title (e.g. "2022 Guide" in 2026)
        2. Time-sensitive content (has year in title) older than 12 months
        3. General staleness — any post not updated in 18+ months

        Skips posts that already have a decay problem (from GSC-based detection)
        to avoid double-counting.
        """
        import re
        now = datetime.now(UTC)
        eighteen_months_ago = now - timedelta(days=548)  # ~18 months
        found = 0

        # Get post IDs already flagged with decay by GSC-based detection
        # (which runs before proxy decay in detect_all)
        already_decayed = await db.fetch(
            "SELECT post_id FROM content_problems WHERE problem_type LIKE 'decay_%' AND site_id = $1",
            site_id,
        )
        already_decayed_ids = {r["post_id"] for r in already_decayed}

        # Posts not updated in 18+ months (excluding already-flagged)
        stale_posts = await db.fetch("""
            SELECT p.id, p.title, p.url, p.publish_date, p.modified_date
            FROM posts p
            WHERE p.site_id = $1
            AND COALESCE(p.modified_date, p.publish_date) < $2
        """, site_id, eighteen_months_ago)

        problems_batch: list[tuple[UUID, UUID, str, str, dict]] = []
        for post in stale_posts:
            # Skip posts already flagged by GSC-based decay detection
            if post["id"] in already_decayed_ids:
                continue

            title = post["title"] or ""
            # Signal 1: Outdated year references (any 4-digit year 2000-2099 that's 2+ years old)
            year_match = re.search(r'((?:19|20)\d{2})', title)
            if year_match:
                ref_year = int(year_match.group(1))
                if 1990 <= ref_year <= now.year and ref_year < now.year - 1:
                    problems_batch.append((
                        post["id"], site_id, "decay_severe", "high",
                        {"issue": f"Outdated year reference ({ref_year}) in title", "proxy": True},
                    ))
                    found += 1
                    continue

            # Signal 2: Time-sensitive content not updated in 18+ months
            # Uses word boundaries to avoid false positives:
            # "stop" should NOT match "top", "preview" should NOT match "review"
            # "best" matches as standalone word (signals comparison/ranking content)
            # "top" only matches before a digit (listicle: "top 10", "top 3")
            if re.search(r'\bbest\b|\btop\s+\d|\breview\b|\bpricing\b|\bcompare\b|\bvs\b', title.lower()):
                last_update_s2 = post["modified_date"] or post["publish_date"]
                months_s2 = 0.0
                if last_update_s2:
                    if last_update_s2.tzinfo is None:
                        last_update_s2 = last_update_s2.replace(tzinfo=UTC)
                    months_s2 = (now - last_update_s2).days / 30.44
                problems_batch.append((
                    post["id"], site_id, "decay_moderate", "medium",
                    {
                        "issue": "Time-sensitive content not updated in 18+ months",
                        "months_stale": round(months_s2, 1),
                        "proxy": True,
                    },
                ))
                found += 1
                continue

            # Signal 3: General staleness — any post not updated in 18+ months.
            # Not flagged by Signals 1-2 above, but still very old content.
            last_update = post["modified_date"] or post["publish_date"]
            if last_update:
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=UTC)
                months_stale = (now - last_update).days / 30.44
                problems_batch.append((
                    post["id"], site_id, "decay_mild", "medium",
                    {
                        "issue": f"Content not updated in {round(months_stale)} months",
                        "months_stale": round(months_stale, 1),
                        "proxy": True,
                    },
                ))
                found += 1

        await self._insert_problems_batch(db, problems_batch)
        return found

    async def _detect_thin_content(
        self, db: asyncpg.Connection, site_id: UUID, has_ga4: bool = True,
    ) -> int:
        """Detect thin content.

        Flags posts with:
        1. word_count < 500 (crawl-only — always runs)
        2. word_count < 50% of cluster average (crawl-only — always runs)
        3. High bounce rate (>80%) + low time on page (<30s) (needs GA4)
        """
        found = 0
        now = datetime.now(UTC)
        ninety_days_ago = now - timedelta(days=90)

        # ── 1. Absolute thin content (content-type-aware thresholds) ──
        thin_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count, p.headings, p.body_html,
                   COALESCE(il.inbound_links, 0) AS inbound_links
            FROM posts p
            LEFT JOIN (
                SELECT target_post_id, COUNT(*) AS inbound_links
                FROM internal_links
                WHERE target_post_id IN (SELECT id FROM posts WHERE site_id = $1)
                GROUP BY target_post_id
            ) il ON il.target_post_id = p.id
            WHERE p.site_id = $1 AND p.word_count > 0
              AND COALESCE(p.page_type, 'blog') NOT IN ('landing', 'index')
            """,
            site_id,
        )
        for r in thin_rows:
            # Content-type-aware thin threshold
            url = (r["url"] or "").lower()
            title = (r["title"] or "").lower()
            if any(kw in url or kw in title for kw in ["/compare", "/vs-", " vs ", "comparison"]):
                threshold = 500  # Comparisons: OK to be shorter with tables
            elif any(kw in url or kw in title for kw in [
                "how-to", "guide", "tutorial", "step-by-step",
                "ultimate", "complete", "definitive", "checklist",
            ]):
                threshold = 800  # Tutorials/guides need depth
            elif any(kw in url or kw in title for kw in ["/glossary", "what-is", "definition"]):
                threshold = 200  # Definitions can be short
            else:
                threshold = 500  # Default

            if r["word_count"] >= threshold:
                continue

            # Multi-signal check: low word count alone is not enough if the post
            # has good structure (headings + images + inbound links)
            # A 600-word post with 3 H2s, images, and 8 inbound links is not thin
            headings_json = r.get("headings") or "[]"
            if isinstance(headings_json, str):
                import json as _json
                try:
                    headings_list = _json.loads(headings_json)
                except Exception:
                    logger.warning("Failed to parse headings JSON for post")
                    headings_list = []
            else:
                headings_list = headings_json or []
            h2_count = sum(1 for h in headings_list if isinstance(h, dict) and h.get("level") in ("h2", "h3"))
            has_images = "<img" in (r.get("body_html") or "")
            inbound = r.get("inbound_links", 0) or 0

            # If post has 2+ H2s AND images AND 5+ inbound links, it's probably not thin
            if h2_count >= 2 and has_images and inbound >= 5:
                continue

            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, "thin_content",
                "high" if r["word_count"] < threshold * 0.5 else "medium",
                json.dumps({"word_count": r["word_count"]}),
                self._get_first_detected(r["id"], "thin_content"),
            )
            found += 1

        # ── 2. Below cluster average (<50%) ──
        below_avg_rows = await db.fetch(
            """
            WITH cluster_avgs AS (
                SELECT pc.cluster_id, AVG(p.word_count) AS avg_wc
                FROM post_clusters pc
                JOIN posts p ON p.id = pc.post_id
                WHERE p.site_id = $1 AND p.word_count IS NOT NULL
                GROUP BY pc.cluster_id
            )
            SELECT p.id, p.title, p.word_count, ca.avg_wc AS cluster_avg
            FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            JOIN cluster_avgs ca ON ca.cluster_id = pc.cluster_id
            WHERE p.site_id = $1
              AND p.word_count IS NOT NULL
              AND p.word_count < ca.avg_wc * 0.5
              AND p.word_count < 800
              AND ca.avg_wc > 1500
            """,
            site_id,
        )
        for r in below_avg_rows:
            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, "thin_below_cluster_avg", "medium",
                json.dumps({
                    "word_count": r["word_count"],
                    "cluster_avg": round(float(r["cluster_avg"]), 0),
                    "ratio": round(r["word_count"] / float(r["cluster_avg"]), 2),
                }), self._get_first_detected(r["id"], "thin_below_cluster_avg"),
            )
            found += 1

        # ── 3. High bounce + low time (requires GA4) ──
        if not has_ga4:
            return found

        bounce_rows = await db.fetch(
            """
            SELECT p.id, p.title,
                   AVG(g.bounce_rate) AS avg_bounce,
                   AVG(g.avg_engagement_time_seconds) AS avg_time
            FROM posts p
            JOIN ga4_metrics g ON g.post_id = p.id
            WHERE p.site_id = $1 AND g.date >= $2
            GROUP BY p.id, p.title
            HAVING AVG(g.bounce_rate) > 0.8
               AND AVG(g.avg_engagement_time_seconds) < 30
            """,
            site_id, ninety_days_ago.date(),
        )
        for r in bounce_rows:
            await db.execute(
                """
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
                VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
                ON CONFLICT (post_id, problem_type) DO UPDATE SET
                    severity = $4, details = $5, detected_at = NOW(),
                    first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
                """,
                r["id"], site_id, "thin_high_bounce", "high",
                json.dumps({
                    "avg_bounce_rate": round(float(r["avg_bounce"]), 2),
                    "avg_time_seconds": round(float(r["avg_time"]), 1),
                }), self._get_first_detected(r["id"], "thin_high_bounce"),
            )
            found += 1

        return found

    # ═══════════════════════════════════════════════
    # 2.11: SEO issue detection
    # ═══════════════════════════════════════════════

    async def _detect_seo_issues(
        self, db: asyncpg.Connection, site_id: UUID,
        skip_link_check: bool = False,
    ) -> int:
        """Detect per-post SEO issues.

        Checks:
        1. Missing meta description
        2. Title too short (<30) or too long (>60)
        3. No H2+ headings
        4. No internal links to/from the post (skipped if skip_link_check=True)
        5. No images (check body_html for <img>)
        """
        found = 0

        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.meta_description, p.headings, p.body_html,
                   (SELECT COUNT(*) FROM internal_links il
                    WHERE il.source_post_id = p.id OR il.target_post_id = p.id) AS link_count
            FROM posts p
            WHERE p.site_id = $1
              AND COALESCE(p.page_type, 'blog') NOT IN ('landing', 'index')
            """,
            site_id,
        )

        problems_batch: list[tuple[UUID, UUID, str, str, dict]] = []
        for r in posts:
            # 1. Missing meta description
            if not r["meta_description"] or len(r["meta_description"].strip()) < 10:
                problems_batch.append((
                    r["id"], site_id, "seo_missing_meta", "medium",
                    {"issue": "No meta description or too short"},
                ))
                found += 1

            # 2. Title length
            title = r["title"] or ""
            title_len = len(title.strip())
            if title_len < 20 or title_len > 70:
                # Only flag truly problematic titles:
                # <20 chars: almost certainly truncated/broken
                # >70 chars: will be cut off in SERPs (Google shows ~55-60)
                # 60-70 range is intentional for descriptive SaaS titles
                severity = "medium" if title_len < 20 else "low"
                problems_batch.append((
                    r["id"], site_id, "seo_title_length", severity,
                    {
                        "issue": f"Title is {title_len} chars (ideal: 30-70)",
                        "title_length": title_len,
                    },
                ))
                found += 1

            # 3. No H2+ headings
            headings = r["headings"]
            if headings and isinstance(headings, str):
                try:
                    headings = json.loads(headings)
                except (json.JSONDecodeError, TypeError):
                    headings = []

            has_h2_plus = False
            if headings and isinstance(headings, list):
                has_h2_plus = any(
                    h.get("level") in ("h2", "h3", "h4")
                    for h in headings
                    if isinstance(h, dict)
                )

            if not has_h2_plus:
                problems_batch.append((
                    r["id"], site_id, "seo_no_headings", "medium",
                    {"issue": "No H2 or H3 headings found"},
                ))
                found += 1

            # 4. No internal links (skipped on capped crawls where link resolution < 20%)
            if not skip_link_check and r["link_count"] == 0:
                problems_batch.append((
                    r["id"], site_id, "seo_no_internal_links", "high",
                    {"issue": "No internal links to or from this post"},
                ))
                found += 1

            # 5. No images — check multiple image patterns (JS-rendered, lazy-loaded, etc.)
            # body_html is normally raw HTML from <main>/<article> (str(BeautifulSoup)),
            # which preserves <img> tags. In rare cases (manual import, alt code paths),
            # it may be trafilatura XML (<doc...>) which strips all media — skip check.
            body_html = r["body_html"] or ""
            html_lower = body_html.lower()
            is_trafilatura_xml = html_lower.startswith("<doc") or "<doc " in html_lower[:100]
            if is_trafilatura_xml:
                # Can't detect images from trafilatura XML — skip (don't create false positive)
                pass
            else:
                has_images = any(tag in html_lower for tag in [
                    '<img', '<picture', '<figure', '<svg',
                    'data-src=', 'srcset=', 'background-image:',
                    'loading="lazy"', "loading='lazy'",
                ])
                if not has_images and len(body_html) > 200:
                    # Only flag if body_html has substantial content (not just a stub)
                    problems_batch.append((
                        r["id"], site_id, "seo_no_images", "low",
                        {"issue": "No images found in content"},
                    ))
                    found += 1

        await self._insert_problems_batch(db, problems_batch)
        return found

    # ═══════════════════════════════════════════════
    # 2.12: Orphan content detection
    # ═══════════════════════════════════════════════

    async def _detect_orphans(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect orphan content — posts with zero inbound internal links.

        These are invisible to both users and search engines.
        Excludes pages under 200 words (likely index/hub/tool pages, not content).
        """
        orphans = await db.fetch(
            """
            SELECT p.id, p.title
            FROM posts p
            WHERE p.site_id = $1
              AND (p.word_count IS NULL OR p.word_count >= 200)
              AND COALESCE(p.page_type, 'blog') NOT IN ('landing', 'index')
              AND NOT EXISTS (
                  SELECT 1 FROM internal_links il
                  WHERE il.target_post_id = p.id
              )
            """,
            site_id,
        )

        problems_batch = [
            (r["id"], site_id, "orphan", "high",
             {"issue": "No inbound internal links — this post is an orphan"})
            for r in orphans
        ]
        await self._insert_problems_batch(db, problems_batch)

        return len(orphans)

    # ═══════════════════════════════════════════════
    # Readability issues (NEW)
    # ═══════════════════════════════════════════════

    async def _detect_readability_issues(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect posts with poor readability.

        Industry-adaptive thresholds:
        - B2B/Technical (SaaS, agency): Flesch < 35 (allow more complexity)
        - General (default): Flesch < 50
        - Consumer: Flesch < 55
        """
        # Detect industry from site metadata or cluster labels
        from app.services.industry_benchmarks import detect_industry
        clusters = await db.fetch(
            "SELECT label FROM clusters WHERE site_id = $1", site_id,
        )
        labels = [c["label"] for c in clusters]
        industry = detect_industry(labels, [])

        # Industry-adaptive threshold
        thresholds = {
            "saas": 35.0,
            "agency": 35.0,
            "ecommerce": 50.0,
            "media": 55.0,
            "default": 50.0,
        }
        threshold = thresholds.get(industry, 50.0)
        logger.info("Readability threshold for %s industry: Flesch < %.0f", industry, threshold)

        hard_to_read = await db.fetch(
            """
            SELECT id, title, readability_score, grade_level
            FROM posts
            WHERE site_id = $1
              AND readability_score IS NOT NULL
              AND readability_score < $2
            """,
            site_id, threshold,
        )

        problems_batch = []
        for r in hard_to_read:
            grade = r["grade_level"]
            flesch = round(r["readability_score"], 1)
            grade_str = f" (grade level {round(grade, 1)})" if grade is not None else ""
            problems_batch.append((
                r["id"], site_id, "readability_too_complex",
                "high" if r["readability_score"] < 30 else "medium",
                {
                    "readability_score": flesch,
                    "grade_level": round(grade, 1) if grade is not None else None,
                    "issue": (
                        f"Flesch Reading Ease score is {flesch}{grade_str}. "
                        f"63% of top-ranking content scores 60-80. "
                        f"Simplify sentences and break up paragraphs."
                    ),
                },
            ))
        await self._insert_problems_batch(db, problems_batch)

        return len(hard_to_read)

    # ═══════════════════════════════════════════════
    # Velocity decline (NEW)
    # ═══════════════════════════════════════════════

    async def _detect_velocity_decline(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect if publishing velocity has dropped significantly.

        Creates a single site-level problem if current velocity
        is < 50% of 90-day average. Includes peak velocity period
        for context (e.g., "peaked at 2.3 posts/week in 2019").
        """
        site = await db.fetchrow(
            """
            SELECT publishing_velocity, velocity_trend
            FROM sites WHERE id = $1
            """,
            site_id,
        )

        if not site or site["velocity_trend"] != "declining":
            return 0

        # We need a post_id for the problem — use the most recent post
        latest_post = await db.fetchrow(
            """
            SELECT id FROM posts
            WHERE site_id = $1
            ORDER BY publish_date DESC NULLS LAST
            LIMIT 1
            """,
            site_id,
        )

        if not latest_post:
            return 0

        velocity = site["publishing_velocity"] or 0.0

        # Compute peak velocity period (best 90-day window by year)
        peak_info = ""
        try:
            yearly_counts = await db.fetch(
                """
                SELECT EXTRACT(YEAR FROM publish_date)::int AS yr,
                       COUNT(*) AS cnt
                FROM posts
                WHERE site_id = $1 AND publish_date IS NOT NULL
                GROUP BY yr ORDER BY cnt DESC LIMIT 1
                """,
                site_id,
            )
            if yearly_counts:
                peak_year = yearly_counts[0]["yr"]
                peak_count = yearly_counts[0]["cnt"]
                peak_weekly = round(peak_count / 52, 1)
                peak_info = f" Peak: {peak_weekly} posts/week in {peak_year} ({peak_count} posts)."
        except Exception:
            pass  # Non-fatal — peak info is supplementary

        await self._insert_problem(
            db, latest_post["id"], site_id, "velocity_decline", "medium",
            {
                "current_velocity": round(velocity, 2),
                "trend": "declining",
                "issue": (
                    f"Publishing velocity dropped to {round(velocity, 1)} posts/week.{peak_info} "
                    f"Research shows consistent publishing (3+/week) drives 3.5x more traffic. "
                    f"Slowed publishing correlates with 25-40% traffic decline within 60 days."
                ),
            },
        )
        return 1

    # Problem type weights for severity scoring
    _PROBLEM_WEIGHTS: dict[str, float] = {
        # Traditional SEO problems
        "seo_missing_meta": 0.9,
        "seo_no_internal_links": 0.8,
        "thin_content": 0.7,
        "readability_too_complex": 0.6,
        "orphan": 0.6,
        "seo_no_headings": 0.5,
        "thin_below_cluster_avg": 0.5,
        "seo_title_length": 0.4,
        "seo_no_images": 0.3,
        "decay_severe": 0.95,
        "decay_moderate": 0.9,
        "decay_mild": 0.7,
        "velocity_decline": 0.7,
        "intent_mismatch": 0.8,
        "serp_opportunity_missed": 0.6,
        # AI readiness problems — product differentiator, weighted high
        "missing_schema": 0.9,           # Cornerstone cold-outreach finding
        "low_ai_citability": 0.85,       # Core product signal
        "weak_eeat": 0.8,                # Critical for AI citation
        "poor_ai_structure": 0.7,        # Impacts AI extraction
        # GEO-specific problems
        "geo_no_faq_section": 0.6,
        "geo_no_data_tables": 0.5,
        "geo_no_experience_markers": 0.5,
        "geo_no_question_headers": 0.5,
        "geo_low_data_density": 0.5,
        "geo_no_answer_first": 0.6,
        "geo_missing_faq_schema": 0.7,   # Schema-related, higher priority
        "geo_no_updated_date": 0.5,
    }

    async def _insert_problem(
        self,
        db: asyncpg.Connection,
        post_id: UUID,
        site_id: UUID,
        problem_type: str,
        severity: str,
        details: dict,
    ) -> None:
        """Insert or update a content problem.

        Automatically adds a severity_score (0-100) based on problem type weight.
        """
        type_weight = ProblemDetector._PROBLEM_WEIGHTS.get(problem_type, 0.5)
        details["severity_score"] = round(type_weight * 100)
        await db.execute(
            """
            INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
            VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
            ON CONFLICT (post_id, problem_type) DO UPDATE SET
                severity = $4, details = $5, detected_at = NOW(),
                first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
            """,
            post_id, site_id, problem_type, severity, json.dumps(details),
            self._get_first_detected(post_id, problem_type),
        )

    async def _insert_problems_batch(
        self,
        db: asyncpg.Connection,
        problems: list[tuple[UUID, UUID, str, str, dict]],
    ) -> None:
        """Batch insert/update content problems.

        Each tuple in problems is (post_id, site_id, problem_type, severity, details).
        Automatically adds severity_score to each details dict.
        """
        if not problems:
            return
        batch_data = []
        for post_id, site_id, problem_type, severity, details in problems:
            type_weight = ProblemDetector._PROBLEM_WEIGHTS.get(problem_type, 0.5)
            details["severity_score"] = round(type_weight * 100)
            batch_data.append((
                post_id, site_id, problem_type, severity, json.dumps(details),
                self._get_first_detected(post_id, problem_type),
            ))
        await db.executemany(
            """
            INSERT INTO content_problems (post_id, site_id, problem_type, severity, details, first_detected_at)
            VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()))
            ON CONFLICT (post_id, problem_type) DO UPDATE SET
                severity = $4, details = $5, detected_at = NOW(),
                first_detected_at = COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)
            """,
            batch_data,
        )
