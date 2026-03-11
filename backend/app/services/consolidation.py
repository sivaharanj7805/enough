"""Consolidation ranking, priority scoring, AI draft generation, and redirect maps.

Identifies swamp clusters, ranks consolidation opportunities by impact,
generates merged content drafts via Claude API, and produces redirect maps.
"""

import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


class ConsolidationPlanner:
    """Generate consolidation plans for swamp clusters."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=5)

    async def get_plans(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> list[dict]:
        """Generate ranked consolidation plans for all swamp clusters.

        Returns a list of consolidation plan dicts, sorted by priority_score desc.
        """
        logger.info("Generating consolidation plans for site %s", site_id)

        swamp_clusters = await db.fetch(
            """
            SELECT id, label, post_count, health_score
            FROM clusters
            WHERE site_id = $1 AND ecosystem_state = 'swamp'
            ORDER BY post_count DESC
            """,
            site_id,
        )

        if not swamp_clusters:
            logger.info("No swamp clusters for site %s", site_id)
            return []

        plans: list[dict] = []
        for cluster_row in swamp_clusters:
            plan = await self._build_plan(db, cluster_row)
            if plan:
                plans.append(plan)

        # Sort by priority score descending
        plans.sort(key=lambda p: p["priority_score"], reverse=True)

        # Tag quick win
        if plans:
            plans[0]["is_quick_win"] = True

        logger.info(
            "Generated %d consolidation plans for site %s", len(plans), site_id,
        )
        return plans

    async def _build_plan(
        self, db: asyncpg.Connection, cluster_row: asyncpg.Record,
    ) -> dict | None:
        """Build a consolidation plan for a single swamp cluster."""
        cluster_id = cluster_row["id"]

        # Get all posts with health scores
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count,
                   ph.composite_score, ph.role, ph.traffic_contribution
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE pc.cluster_id = $1
            ORDER BY COALESCE(ph.composite_score, 0) DESC
            """,
            cluster_id,
        )

        if not posts:
            return None

        # Identify pillar candidate (highest composite score)
        pillar = posts[0]

        # Categorize remaining posts
        merge_candidates: list[dict] = []
        dead_weight: list[dict] = []

        for post in posts[1:]:
            score = post["composite_score"] or 0.0
            role = post["role"] or "dead_weight"

            post_info = {
                "post_id": str(post["id"]),
                "title": post["title"],
                "url": post["url"],
                "composite_score": score,
                "word_count": post["word_count"] or 0,
            }

            if score < 15 or role == "dead_weight":
                dead_weight.append(post_info)
            else:
                merge_candidates.append(post_info)

        # Estimate traffic recovery
        cannibal_traffic = await db.fetchval(
            """
            SELECT COALESCE(SUM(g.pageviews), 0)
            FROM cannibalization_pairs cp
            JOIN ga4_metrics g ON g.post_id = cp.post_b_id
            WHERE cp.cluster_id = $1
              AND g.date >= CURRENT_DATE - INTERVAL '90 days'
            """,
            cluster_id,
        )
        estimated_traffic_recovery = int(cannibal_traffic * 0.6)

        # Estimate effort (hours)
        total_word_count = sum(
            mc["word_count"] for mc in merge_candidates
        )
        estimated_effort = max(1.0, total_word_count / 1000.0)

        # Priority score
        priority_score = (
            estimated_traffic_recovery / estimated_effort
            if estimated_effort > 0 else 0.0
        )

        # Build redirect map
        redirect_map = []
        for post in merge_candidates + dead_weight:
            redirect_map.append({
                "old_url": post["url"],
                "new_url": pillar["url"],
            })

        return {
            "cluster_id": str(cluster_id),
            "cluster_label": cluster_row["label"],
            "priority_score": priority_score,
            "pillar_post": {
                "post_id": str(pillar["id"]),
                "title": pillar["title"],
                "url": pillar["url"],
                "composite_score": pillar["composite_score"] or 0.0,
            },
            "merge_candidates": merge_candidates,
            "dead_weight": dead_weight,
            "merge_candidates_count": len(merge_candidates),
            "dead_weight_count": len(dead_weight),
            "estimated_traffic_recovery": estimated_traffic_recovery,
            "estimated_effort": estimated_effort,
            "is_quick_win": False,
            "redirect_map": redirect_map,
        }

    async def get_plan_detail(
        self, db: asyncpg.Connection, cluster_id: UUID,
    ) -> dict | None:
        """Get detailed consolidation plan for a specific cluster."""
        cluster_row = await db.fetchrow(
            "SELECT id, label, post_count, health_score FROM clusters WHERE id = $1",
            cluster_id,
        )
        if not cluster_row:
            return None
        return await self._build_plan(db, cluster_row)

    async def generate_draft(
        self, db: asyncpg.Connection, cluster_id: UUID,
    ) -> dict:
        """Generate an AI-merged consolidation draft for a cluster.

        Returns:
            {
                "draft_markdown": str,
                "redirect_map": list[{"old_url": str, "new_url": str}]
            }
        """
        logger.info("Generating consolidation draft for cluster %s", cluster_id)

        # Get pillar post
        pillar_row = await db.fetchrow(
            """
            SELECT p.id, p.title, p.url, p.body_text
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE pc.cluster_id = $1
            ORDER BY COALESCE(ph.composite_score, 0) DESC
            LIMIT 1
            """,
            cluster_id,
        )

        if not pillar_row:
            raise ValueError(f"No posts found in cluster {cluster_id}")

        # Get merge candidates (all non-pillar posts)
        merge_rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.body_text
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE pc.cluster_id = $1 AND p.id != $2
            ORDER BY COALESCE(ph.composite_score, 0) DESC
            """,
            cluster_id, pillar_row["id"],
        )

        # Build prompt
        merge_texts = []
        for mr in merge_rows:
            body = (mr["body_text"] or "")[:3000]  # Truncate for token limits
            merge_texts.append(f"### {mr['title']}\n{body}")

        merge_section = "\n\n---\n\n".join(merge_texts) if merge_texts else "(no merge candidates)"
        pillar_body = (pillar_row["body_text"] or "")[:5000]

        prompt = f"""You are a content strategist consolidating multiple blog posts into one \
authoritative piece.

PILLAR POST (keep this structure and voice):
Title: {pillar_row['title']}
Content: {pillar_body}

POSTS TO MERGE (extract unique insights, data, examples):
{merge_section}

Instructions:
1. Keep the pillar post's structure, tone, and primary angle
2. Integrate unique insights, statistics, examples, and perspectives \
from the merge posts that aren't already in the pillar
3. Remove redundancy — don't repeat the same point twice
4. Ensure the final piece is comprehensive and authoritative
5. Output the complete merged post in markdown format"""

        await self.rate_limiter.acquire()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            draft_markdown = response.content[0].text
        except Exception as e:
            logger.error("Claude draft generation failed: %s", e)
            raise

        # Build redirect map
        redirect_map = [
            {"old_url": mr["url"], "new_url": pillar_row["url"]}
            for mr in merge_rows
        ]

        return {
            "draft_markdown": draft_markdown,
            "redirect_map": redirect_map,
        }
