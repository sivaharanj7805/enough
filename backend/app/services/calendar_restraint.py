"""Calendar Restraint — Data-backed publishing cadence recommendations per cluster."""

import logging
import math
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class CalendarRestraint:
    """Generate publishing cadence recommendations based on cluster state."""

    async def generate_for_site(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> list[dict]:
        """Generate recommendations for all clusters in a site."""
        clusters = await db.fetch(
            """
            SELECT c.id, c.label, c.ecosystem_state, c.post_count
            FROM clusters c
            WHERE c.site_id = $1
            ORDER BY c.post_count DESC
            """,
            site_id,
        )

        results: list[dict] = []
        for cluster in clusters:
            try:
                rec = await self._generate_for_cluster(db, cluster)
                results.append(rec)
            except Exception as e:
                logger.error(
                    "Failed to generate recommendation for cluster %s: %s",
                    cluster["id"],
                    e,
                )

        # Generate site-wide summary
        summary = self._build_summary(results)
        logger.info(
            "Generated %d recommendations for site %s", len(results), site_id
        )
        return results

    async def _generate_for_cluster(
        self, db: asyncpg.Connection, cluster: asyncpg.Record
    ) -> dict:
        """Generate recommendation for a single cluster."""
        cluster_id = cluster["id"]
        state = cluster["ecosystem_state"] or "meadow"
        label = cluster["label"] or "Unlabeled"
        post_count = cluster["post_count"] or 0

        rec_type: str
        rec_text: str
        suggested_keywords: list[str] | None = None
        pause_months: int | None = None

        if state == "forest":
            rec_type = "maintain"
            rec_text = (
                f"This cluster is healthy. Recommended: maintain current cadence. "
                f"Consider 1 supporting post per quarter to keep it fresh."
            )

        elif state == "swamp":
            # Calculate cannibalization rate
            cannibal_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM cannibalization_pairs
                WHERE cluster_id = $1
                """,
                cluster_id,
            ) or 0
            rate = cannibal_count / max(post_count, 1)
            pause_months = max(1, math.ceil(rate * 6))
            top_n = max(2, min(post_count // 3, 5))

            rec_type = "pause"
            rec_text = (
                f"This cluster is oversaturated. Recommended: publish NOTHING new "
                f"for {pause_months} months. Focus on consolidating the top "
                f"{top_n} posts instead."
            )

        elif state == "desert":
            # Find keyword gaps from GSC
            gap_rows = await db.fetch(
                """
                SELECT DISTINCT g.query
                FROM gsc_metrics g
                JOIN posts p ON p.id = g.post_id
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1
                  AND g.impressions > 50
                  AND g.clicks < 5
                ORDER BY g.query
                LIMIT 5
                """,
                cluster_id,
            )
            suggested_keywords = [r["query"] for r in gap_rows] if gap_rows else None
            top_n = max(1, min(post_count // 2, 3))

            keywords_str = ""
            if suggested_keywords:
                keywords_str = f" targeting these keyword gaps: {', '.join(suggested_keywords)}"

            rec_type = "revive"
            rec_text = (
                f"This cluster needs revival. Recommended: update the top "
                f"{top_n} existing posts first, then add {top_n} new posts"
                f"{keywords_str}."
            )

        elif state == "seedbed":
            # Check for early traction signals
            avg_clicks = await db.fetchval(
                """
                SELECT COALESCE(AVG(g.clicks), 0)
                FROM gsc_metrics g
                JOIN posts p ON p.id = g.post_id
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1
                """,
                cluster_id,
            ) or 0
            weeks = 6 if avg_clicks > 2 else 8

            rec_type = "grow"
            rec_text = (
                f"This cluster is new. Recommended: wait {weeks} weeks "
                f"before publishing anything else nearby. Let the seedlings take root."
            )

        else:  # meadow
            # Find suggested keywords
            gap_rows = await db.fetch(
                """
                SELECT DISTINCT g.query
                FROM gsc_metrics g
                JOIN posts p ON p.id = g.post_id
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1
                  AND g.impressions > 20
                  AND g.clicks < 3
                ORDER BY g.query
                LIMIT 5
                """,
                cluster_id,
            )
            suggested_keywords = [r["query"] for r in gap_rows] if gap_rows else None
            new_posts = max(1, min(post_count, 3))

            keywords_str = ""
            if suggested_keywords:
                keywords_str = f" targeting: {', '.join(suggested_keywords)}"

            rec_type = "grow"
            rec_text = (
                f"This cluster has room to grow. Recommended: {new_posts} new posts "
                f"this quarter{keywords_str}."
            )

        # Store/upsert recommendation
        await db.execute(
            """
            INSERT INTO cluster_recommendations
                (cluster_id, recommendation_type, recommendation_text,
                 suggested_keywords, pause_months, generated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (cluster_id) DO UPDATE SET
                recommendation_type = EXCLUDED.recommendation_type,
                recommendation_text = EXCLUDED.recommendation_text,
                suggested_keywords = EXCLUDED.suggested_keywords,
                pause_months = EXCLUDED.pause_months,
                generated_at = EXCLUDED.generated_at
            """,
            cluster_id,
            rec_type,
            rec_text,
            suggested_keywords,
            pause_months,
            datetime.now(timezone.utc),
        )

        return {
            "cluster_id": cluster_id,
            "cluster_label": label,
            "ecosystem_state": state,
            "recommendation_type": rec_type,
            "recommendation_text": rec_text,
            "suggested_keywords": suggested_keywords,
            "pause_months": pause_months,
        }

    def _build_summary(self, recommendations: list[dict]) -> str:
        """Build a site-wide calendar summary."""
        groups: dict[str, list[str]] = {
            "pause": [],
            "maintain": [],
            "revive": [],
            "grow": [],
        }
        for rec in recommendations:
            label = rec.get("cluster_label", "Unlabeled")
            groups.get(rec["recommendation_type"], []).append(label)

        lines = ["Your content calendar for the next quarter:"]
        if groups["pause"]:
            lines.append(f"  - Pause: {', '.join(groups['pause'])} (oversaturated)")
        if groups["maintain"]:
            lines.append(
                f"  - Maintain: {', '.join(groups['maintain'])} (healthy)"
            )
        if groups["revive"]:
            lines.append(
                f"  - Revive: {', '.join(groups['revive'])} (needs updating)"
            )
        if groups["grow"]:
            lines.append(
                f"  - Grow: {', '.join(groups['grow'])} (room for new content)"
            )

        return "\n".join(lines)

    async def get_recommendations(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> dict:
        """Fetch stored recommendations for a site."""
        rows = await db.fetch(
            """
            SELECT cr.cluster_id, c.label AS cluster_label,
                   c.ecosystem_state, cr.recommendation_type,
                   cr.recommendation_text, cr.suggested_keywords,
                   cr.pause_months
            FROM cluster_recommendations cr
            JOIN clusters c ON c.id = cr.cluster_id
            WHERE c.site_id = $1
            ORDER BY
                CASE cr.recommendation_type
                    WHEN 'pause' THEN 1
                    WHEN 'revive' THEN 2
                    WHEN 'grow' THEN 3
                    WHEN 'maintain' THEN 4
                END
            """,
            site_id,
        )

        recommendations = [dict(r) for r in rows]
        summary = self._build_summary(recommendations)

        return {
            "site_id": site_id,
            "recommendations": recommendations,
            "summary": summary,
        }
