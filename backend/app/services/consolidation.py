"""Consolidation ranking, priority scoring, AI draft generation, and redirect maps.

Identifies swamp clusters, ranks consolidation opportunities by impact,
generates merged content drafts via Claude API, and produces redirect maps.
"""

import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.llm_cost import log_llm_usage
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

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
        # Sum traffic from all non-pillar posts involved in cannibalization
        pillar_id = pillar["id"]
        cannibal_traffic = await db.fetchval(
            """
            SELECT COALESCE(SUM(g.pageviews), 0)
            FROM ga4_metrics g
            WHERE g.post_id IN (
                SELECT DISTINCT
                    CASE WHEN cp.post_a_id = $2 THEN cp.post_b_id ELSE cp.post_a_id END
                FROM cannibalization_pairs cp
                WHERE cp.cluster_id = $1
            )
            AND g.date >= CURRENT_DATE - INTERVAL '90 days'
            """,
            cluster_id, pillar_id,
        )
        estimated_traffic_recovery = int(cannibal_traffic * 0.35)

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
        *, site_id: UUID | None = None,
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
            body = truncate_for_api(mr["body_text"] or "", max_chars=3000, label=f"merge:{mr['title']}")
            merge_texts.append(f"### {mr['title']}\n{body}")

        merge_section = "\n\n---\n\n".join(merge_texts) if merge_texts else "(no merge candidates)"
        pillar_body = truncate_for_api(pillar_row["body_text"] or "", max_chars=5000, label="pillar")

        # Calculate word counts for summary
        pillar_word_count = len((pillar_row["body_text"] or "").split())
        merge_word_counts = {
            mr["title"]: len((mr["body_text"] or "").split()) for mr in merge_rows
        }
        total_input_words = pillar_word_count + sum(merge_word_counts.values())
        recommended_output_words = max(1500, int(total_input_words * 0.4))

        # Build source list for annotations
        source_titles = [mr["title"] for mr in merge_rows]

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
5. Output the complete merged post in markdown format
6. When integrating content from a merge post, add a source annotation \
comment: <!-- Integrated from: "Post Title" -->
7. At the end, suggest an SEO-optimized title tag (under 60 chars) and \
meta description (under 155 chars) for the consolidated post"""

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            draft_markdown = response.content[0].text
            await log_llm_usage(
                db, site_id=site_id, service="consolidation",
                model=CLAUDE_MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            logger.error("Claude draft generation failed: %s", e)
            raise

        # Build redirect map
        redirect_map = [
            {"old_url": mr["url"], "new_url": pillar_row["url"]}
            for mr in merge_rows
        ]

        # Generate HTML version from markdown
        draft_html = self._markdown_to_html(draft_markdown)

        # Extract SEO metadata from the draft (Claude appends it at the end)
        seo_metadata = self._extract_seo_metadata(draft_markdown)

        return {
            "draft_markdown": draft_markdown,
            "draft_html": draft_html,
            "redirect_map": redirect_map,
            "word_count_summary": {
                "pillar_words": pillar_word_count,
                "merge_source_words": merge_word_counts,
                "total_input_words": total_input_words,
                "recommended_output_words": recommended_output_words,
                "source_posts": [pillar_row["title"]] + source_titles,
            },
            "seo_metadata": seo_metadata,
        }

    @staticmethod
    def _markdown_to_html(markdown_text: str) -> str:
        """Convert markdown draft to basic HTML for content managers."""
        import re
        html = markdown_text

        # Convert headings
        for level in range(6, 0, -1):
            pattern = r'^' + '#' * level + r'\s+(.+)$'
            html = re.sub(pattern, rf'<h{level}>\1</h{level}>', html, flags=re.MULTILINE)

        # Convert bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Convert links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)

        # Convert unordered lists
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        # Wrap consecutive <li> in <ul>
        html = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul>\1</ul>', html)

        # Wrap remaining paragraphs
        lines = html.split('\n\n')
        wrapped = []
        for block in lines:
            block = block.strip()
            if not block:
                continue
            if block.startswith(('<h', '<ul', '<ol', '<!--')):
                wrapped.append(block)
            else:
                wrapped.append(f'<p>{block}</p>')

        return '\n\n'.join(wrapped)

    @staticmethod
    def _extract_seo_metadata(draft_text: str) -> dict:
        """Extract SEO title and meta description from the draft tail."""
        import re
        title_tag = ""
        meta_desc = ""

        # Look for title tag suggestion
        title_match = re.search(
            r'(?:title\s*tag|seo\s*title)[:\s]*["\']?(.{10,60}?)["\']?\s*$',
            draft_text, re.IGNORECASE | re.MULTILINE,
        )
        if title_match:
            title_tag = title_match.group(1).strip().strip('"\'')

        # Look for meta description suggestion
        meta_match = re.search(
            r'(?:meta\s*description)[:\s]*["\']?(.{30,160}?)["\']?\s*$',
            draft_text, re.IGNORECASE | re.MULTILINE,
        )
        if meta_match:
            meta_desc = meta_match.group(1).strip().strip('"\'')

        return {"title_tag": title_tag, "meta_description": meta_desc}

    @staticmethod
    def export_redirect_map(
        redirect_map: list[dict[str, str]],
        fmt: str = "htaccess",
    ) -> str:
        """Export a redirect map in various formats.

        Args:
            redirect_map: List of {"old_url": ..., "new_url": ...}
            fmt: "htaccess", "wordpress", or "csv"

        Returns:
            Formatted redirect map string ready for download/paste.
        """
        if fmt == "htaccess":
            lines = [
                "# Generated by Tended — paste into your .htaccess file",
                "# Make sure mod_rewrite is enabled",
                "",
            ]
            for entry in redirect_map:
                old = entry["old_url"]
                new = entry["new_url"]
                # Use relative paths for RewriteRule
                old_path = old.split("//", 1)[-1].split("/", 1)[-1] if "//" in old else old
                if not old_path.startswith("/"):
                    old_path = "/" + old_path
                lines.append(
                    f"Redirect 301 {old_path} {new}"
                )
            return "\n".join(lines) + "\n"

        elif fmt == "wordpress":
            # WordPress Redirection plugin CSV import format:
            # source,target,regex,type
            lines = ["source,target,regex,type"]
            for entry in redirect_map:
                old = entry["old_url"]
                new = entry["new_url"]
                lines.append(f'"{old}","{new}",0,301')
            return "\n".join(lines) + "\n"

        else:  # csv
            lines = ["old_url,new_url"]
            for entry in redirect_map:
                lines.append(f'"{entry["old_url"]}","{entry["new_url"]}"')
            return "\n".join(lines) + "\n"
