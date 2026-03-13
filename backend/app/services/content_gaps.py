"""Content gap analysis — find what's MISSING from the site.

Identifies topics the site SHOULD cover but doesn't. Uses:
1. GSC impressions with zero/low clicks (queries the site shows for
   but users don't click on — likely because no targeted content exists)
2. Embedding similarity to find which cluster each gap belongs to
3. Claude to generate content briefs for gap topics

This is proactive growth intelligence — not just fixing problems
but telling users exactly what to write next.
"""

import json
import logging
from datetime import timedelta, timezone, datetime
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Thresholds
MIN_IMPRESSIONS_FOR_GAP = 50      # Must have enough impressions to matter
MAX_CTR_FOR_GAP = 0.02            # CTR < 2% suggests no targeted content
MAX_POSITION_FOR_GAP = 30.0       # Must be showing somewhere (not page 4+)
MIN_POSITION_FOR_GAP = 5.0        # If already top 5, it's not a gap


class ContentGapAnalyzer:
    """Find content gaps and generate briefs."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def analyze_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Find content gaps for a site.

        Returns number of gaps found.
        """
        logger.info("Analyzing content gaps for site %s", site_id)

        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)

        # Clear old gaps (idempotent)
        await db.execute(
            "DELETE FROM content_gaps WHERE site_id = $1 AND status = 'open'",
            site_id,
        )

        # Find queries with high impressions but low CTR
        # These are queries where Google shows the site but users don't click
        gap_queries = await db.fetch(
            """
            SELECT query,
                   SUM(impressions) AS total_impressions,
                   SUM(clicks) AS total_clicks,
                   AVG(avg_position) AS avg_pos
            FROM gsc_metrics
            WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
              AND date >= $2
            GROUP BY query
            HAVING SUM(impressions) >= $3
               AND (SUM(clicks)::float / NULLIF(SUM(impressions), 0)) < $4
               AND AVG(avg_position) BETWEEN $5 AND $6
            ORDER BY SUM(impressions) DESC
            LIMIT 50
            """,
            site_id, ninety_days_ago.date(),
            MIN_IMPRESSIONS_FOR_GAP, MAX_CTR_FOR_GAP,
            MIN_POSITION_FOR_GAP, MAX_POSITION_FOR_GAP,
        )

        if not gap_queries:
            logger.info("No content gaps found for site %s", site_id)
            return 0

        # Find the closest cluster for each gap query using embedding similarity
        gaps_found = 0
        for gq in gap_queries:
            query = gq["query"]

            # Find closest cluster by checking which cluster's posts
            # have the most similar content to this query
            closest = await db.fetchrow(
                """
                SELECT c.id AS cluster_id, c.label,
                       MIN(pe.embedding <=> (
                           SELECT embedding FROM post_embeddings
                           WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                           LIMIT 1
                       )) AS min_distance
                FROM clusters c
                JOIN post_clusters pc ON pc.cluster_id = c.id
                JOIN post_embeddings pe ON pe.post_id = pc.post_id
                WHERE c.site_id = $1
                GROUP BY c.id, c.label
                ORDER BY MIN(pe.embedding <=> (
                    SELECT embedding FROM post_embeddings
                    WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
                    LIMIT 1
                ))
                LIMIT 1
                """,
                site_id,
            )

            cluster_id = closest["cluster_id"] if closest else None
            similarity = 1.0 - float(closest["min_distance"]) if closest else None

            await db.execute(
                """
                INSERT INTO content_gaps
                    (site_id, query, impressions, avg_position,
                     closest_cluster_id, similarity_to_cluster, gap_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (site_id, query) DO UPDATE SET
                    impressions = $3, avg_position = $4,
                    closest_cluster_id = $5, similarity_to_cluster = $6,
                    detected_at = NOW()
                """,
                site_id, query, gq["total_impressions"],
                float(gq["avg_pos"]),
                cluster_id, similarity,
                "missing" if (similarity is None or similarity < 0.3) else "weak",
            )
            gaps_found += 1

        # Generate AI briefs for top gaps
        top_gaps = await db.fetch(
            """
            SELECT id, query, impressions, avg_position,
                   closest_cluster_id, gap_type
            FROM content_gaps
            WHERE site_id = $1 AND status = 'open' AND brief IS NULL
            ORDER BY impressions DESC
            LIMIT 10
            """,
            site_id,
        )

        for gap in top_gaps:
            brief = await self._generate_brief(
                db, site_id, gap["query"], gap["closest_cluster_id"],
            )
            if brief:
                await db.execute(
                    "UPDATE content_gaps SET brief = $1 WHERE id = $2",
                    brief, gap["id"],
                )

        logger.info(
            "Content gap analysis complete for site %s: %d gaps found",
            site_id, gaps_found,
        )
        return gaps_found

    async def _generate_brief(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        query: str,
        cluster_id: UUID | None,
    ) -> str | None:
        """Generate a content brief for a gap topic."""
        # Get existing cluster context
        cluster_context = ""
        if cluster_id:
            cluster = await db.fetchrow(
                "SELECT label, description FROM clusters WHERE id = $1",
                cluster_id,
            )
            if cluster:
                cluster_context = (
                    f"\nRelated topic cluster: \"{cluster['label']}\"\n"
                    f"Cluster description: {cluster['description'] or 'N/A'}"
                )

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=400,
                temperature=0.2,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Users are searching for \"{query}\" and this blog shows in results "
                        f"but has no dedicated content for it.{cluster_context}\n\n"
                        f"Write a brief content plan (3-4 sentences) for a new blog post "
                        f"targeting this query. Include: suggested title, 3 key sections "
                        f"to cover, and target word count. Be specific and actionable."
                    ),
                }],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error("Claude brief generation failed for '%s': %s", query, e)
            return None
