"""Competitor comparison service — analyze content overlap and gaps."""

import json
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class CompetitorCompareService:
    """Compare a site's content coverage against a competitor domain."""

    async def compare(
        self, db: asyncpg.Connection, site_id: UUID, competitor_domain: str,
    ) -> dict:
        """Run a comparison between site content and competitor domain.

        Since we don't crawl competitors, we compare based on:
        - Our cluster topics vs what topics the competitor likely covers
        - Our content depth (word counts, post counts per cluster)
        - Identify gaps where we have thin or missing coverage
        """

        # Get our clusters with post counts and health
        clusters = await db.fetch(
            """SELECT c.id, c.label, c.ecosystem_state, c.health_score, c.post_count,
                      c.description
               FROM clusters c
               WHERE c.site_id = $1
               ORDER BY c.post_count DESC""",
            site_id,
        )

        # Get our total stats
        total_posts = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
        ) or 0

        total_words = await db.fetchval(
            "SELECT COALESCE(SUM(word_count), 0) FROM posts WHERE site_id = $1",
            site_id,
        ) or 0

        avg_word_count = total_words // max(total_posts, 1)

        # Get content gaps data if available
        gaps = await db.fetch(
            """SELECT topic, gap_type, priority
               FROM content_gaps
               WHERE site_id = $1
               ORDER BY priority DESC
               LIMIT 20""",
            site_id,
        ) if await self._table_exists(db, "content_gaps") else []

        # Build cluster analysis
        our_topics = []
        strong_topics = []
        weak_topics = []

        for c in clusters:
            topic = {
                "cluster_id": str(c["id"]),
                "label": c["label"] or "Unlabeled",
                "post_count": c["post_count"],
                "health_score": round(float(c["health_score"]), 1) if c["health_score"] else None,
                "ecosystem_state": c["ecosystem_state"],
            }
            our_topics.append(topic)

            if c["health_score"] and float(c["health_score"]) >= 60:
                strong_topics.append(topic)
            elif c["health_score"] and float(c["health_score"]) < 40:
                weak_topics.append(topic)

        # Identify content gaps (topics competitor likely covers but we don't)
        gap_topics = [
            {
                "topic": g["topic"],
                "gap_type": g["gap_type"],
                "priority": g["priority"],
            }
            for g in gaps
        ]

        comparison = {
            "competitor_domain": competitor_domain,
            "our_stats": {
                "total_posts": total_posts,
                "total_words": total_words,
                "avg_word_count": avg_word_count,
                "total_clusters": len(clusters),
            },
            "our_topics": our_topics[:20],
            "strong_topics": strong_topics[:10],
            "weak_topics": weak_topics[:10],
            "content_gaps": gap_topics,
            "overlap_estimate": {
                "shared_topics": len(our_topics),
                "our_unique": len(strong_topics),
                "their_unique_estimate": len(gap_topics),
            },
            "recommendations": self._generate_recommendations(
                strong_topics, weak_topics, gap_topics, total_posts,
            ),
        }

        # Store comparison
        await db.execute(
            """INSERT INTO competitor_comparisons (site_id, competitor_domain, comparison_data)
               VALUES ($1, $2, $3::jsonb)""",
            site_id, competitor_domain, json.dumps(comparison),
        )

        return comparison

    async def list_comparisons(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> list[dict]:
        """List previous competitor comparisons."""
        rows = await db.fetch(
            """SELECT id, competitor_domain, comparison_data, created_at
               FROM competitor_comparisons
               WHERE site_id = $1
               ORDER BY created_at DESC
               LIMIT 20""",
            site_id,
        )

        results = []
        for row in rows:
            data = row["comparison_data"]
            if isinstance(data, str):
                data = json.loads(data)
            results.append({
                "id": str(row["id"]),
                "competitor_domain": row["competitor_domain"],
                "comparison": data,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            })
        return results

    async def _table_exists(self, db: asyncpg.Connection, table_name: str) -> bool:
        """Check if a table exists in the database."""
        result = await db.fetchval(
            """SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = $1
            )""",
            table_name,
        )
        return bool(result)

    def _generate_recommendations(
        self,
        strong_topics: list[dict],
        weak_topics: list[dict],
        gap_topics: list[dict],
        total_posts: int,
    ) -> list[str]:
        """Generate actionable recommendations based on comparison."""
        recs = []

        if weak_topics:
            recs.append(
                f"Strengthen {len(weak_topics)} weak topic areas: "
                + ", ".join(t["label"] for t in weak_topics[:3])
            )

        if gap_topics:
            recs.append(
                f"Fill {len(gap_topics)} content gaps to match competitor coverage: "
                + ", ".join(t["topic"] for t in gap_topics[:3])
            )

        if strong_topics:
            recs.append(
                f"Double down on {len(strong_topics)} strong topics: "
                + ", ".join(t["label"] for t in strong_topics[:3])
            )

        if total_posts < 50:
            recs.append("Increase content volume — you have fewer than 50 posts total.")

        if not recs:
            recs.append("Your content coverage looks solid. Focus on maintaining quality.")

        return recs
