"""Topical Authority Scoring per cluster.

Scores how authoritative the site is for each topic cluster.
A site might have 20 posts about "email marketing" but they're
all thin, poorly linked, and decaying. Topical authority =
quality × coverage × structure.

Formula (0-100):
  0.30 × avg_health_score
  0.20 × keyword_coverage (unique queries / expected queries)
  0.20 × link_density (internal links within cluster / possible links)
  0.15 × content_depth_ratio (avg word count vs ideal)
  0.15 × freshness_avg (average freshness score)

Uses Claude to generate "authority gap" recommendations:
what subtopics are missing from each cluster.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Weights
W_HEALTH = 0.30
W_KEYWORD_COVERAGE = 0.20
W_LINK_DENSITY = 0.20
W_CONTENT_DEPTH = 0.15
W_FRESHNESS = 0.15


class TopicalAuthorityScorer:
    """Score topical authority per cluster."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def score_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Score topical authority for all clusters in a site.

        Returns number of clusters scored.
        """
        logger.info("Computing topical authority for site %s", site_id)

        clusters = await db.fetch(
            """
            SELECT id, label, post_count, health_score
            FROM clusters
            WHERE site_id = $1
            """,
            site_id,
        )

        scored = 0
        for cluster in clusters:
            await self._score_cluster(db, site_id, cluster)
            scored += 1

        logger.info(
            "Topical authority scored for %d clusters in site %s",
            scored, site_id,
        )
        return scored

    async def _score_cluster(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        cluster: asyncpg.Record,
    ) -> None:
        """Score a single cluster's topical authority."""
        cluster_id = cluster["id"]
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)

        # Get cluster posts with health data
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.word_count, p.modified_date, p.publish_date,
                   ph.composite_score, ph.freshness_score
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE pc.cluster_id = $1
            """,
            cluster_id,
        )

        if not posts:
            return

        post_ids = [p["id"] for p in posts]
        n_posts = len(posts)

        # 1. Average health score (0-100)
        health_scores = [p["composite_score"] or 0.0 for p in posts]
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0.0

        # 2. Keyword coverage: unique queries / expected queries
        query_count = await db.fetchval(
            """
            SELECT COUNT(DISTINCT query)
            FROM gsc_metrics
            WHERE post_id = ANY($1::uuid[]) AND date >= $2
            """,
            post_ids, ninety_days_ago.date(),
        )
        # Expected: ~10-20 queries per post for a well-covered topic
        expected_queries = n_posts * 15
        keyword_coverage = min(100.0, ((query_count or 0) / max(expected_queries, 1)) * 100.0)

        # 3. Link density: internal links within cluster / possible links
        internal_links_count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM internal_links
            WHERE source_post_id = ANY($1::uuid[])
              AND target_post_id = ANY($1::uuid[])
            """,
            post_ids,
        )
        # Possible links = n * (n-1) for directed graph
        possible_links = n_posts * (n_posts - 1) if n_posts > 1 else 1
        link_density = min(100.0, ((internal_links_count or 0) / possible_links) * 100.0)

        # 4. Content depth ratio: avg word count vs ideal (1500 words)
        word_counts = [p["word_count"] or 0 for p in posts]
        avg_word_count = sum(word_counts) / len(word_counts) if word_counts else 0
        ideal_word_count = 1500.0
        depth_ratio = min(100.0, (avg_word_count / ideal_word_count) * 100.0)

        # 5. Average freshness score
        freshness_scores = [p["freshness_score"] or 50.0 for p in posts]
        avg_freshness = sum(freshness_scores) / len(freshness_scores)

        # Composite topical authority score
        authority = (
            W_HEALTH * avg_health
            + W_KEYWORD_COVERAGE * keyword_coverage
            + W_LINK_DENSITY * link_density
            + W_CONTENT_DEPTH * depth_ratio
            + W_FRESHNESS * avg_freshness
        )

        # Generate authority gap analysis via Claude
        authority_gaps = await self._find_authority_gaps(
            cluster["label"], [p["title"] for p in posts],
        )

        # Store results
        await db.execute(
            """
            UPDATE clusters
            SET topical_authority_score = $1,
                keyword_coverage_score = $2,
                link_density_score = $3,
                authority_gaps = $4,
                updated_at = NOW()
            WHERE id = $5
            """,
            authority, keyword_coverage, link_density,
            authority_gaps, cluster_id,
        )

    async def _find_authority_gaps(
        self, cluster_label: str, post_titles: list[str],
    ) -> list[str]:
        """Use Claude to identify missing subtopics in a cluster."""
        if not cluster_label or cluster_label == "Unclustered":
            return []

        titles_text = "\n".join(f"- {t}" for t in post_titles[:15])

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                temperature=0.2,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Topic cluster: \"{cluster_label}\"\n"
                        f"Existing posts:\n{titles_text}\n\n"
                        f"List 3-5 subtopics that are MISSING from this cluster "
                        f"but should be covered for complete topical authority. "
                        f"Only list topics that are clearly related and would "
                        f"strengthen the cluster. One subtopic per line, no bullets "
                        f"or numbers, just the topic name."
                    ),
                }],
            )
            text = response.content[0].text.strip()
            gaps = [line.strip() for line in text.split("\n") if line.strip()]
            return gaps[:5]
        except Exception as e:
            logger.error("Claude authority gap analysis failed: %s", e)
            return []
