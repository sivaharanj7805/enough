"""AI Recommendation Engine — the core product value.

Generates specific, actionable recommendations for every detected problem.
Each recommendation includes:
- type (merge, refresh, optimize, delete, expand, interlink, growth)
- priority (critical/high/medium/low)
- estimated_effort (hours)
- estimated_impact (high/medium/low)
- specific_actions (array of concrete steps)
- ai_generated_content (meta descriptions, titles, outlines, etc.)

Uses Claude API with structured prompting. Rate-limited to 3 req/s.
"""

import json
import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


class RecommendationEngine:
    """Generate AI-powered recommendations for content problems."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def generate_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Generate recommendations for all detected problems in a site.

        Clears old pending recommendations first (idempotent).
        Returns number of recommendations generated.
        """
        logger.info("Generating recommendations for site %s", site_id)

        # Clear old pending recommendations (keep completed/dismissed)
        await db.execute(
            """
            DELETE FROM recommendations
            WHERE site_id = $1 AND status = 'pending'
            """,
            site_id,
        )

        # Get all problems
        problems = await db.fetch(
            """
            SELECT cp.id, cp.post_id, cp.problem_type, cp.severity, cp.details,
                   p.title, p.url, p.word_count, p.body_text, p.meta_description,
                   p.headings, p.publish_date, p.modified_date
            FROM content_problems cp
            JOIN posts p ON p.id = cp.post_id
            WHERE cp.site_id = $1 AND cp.resolved_at IS NULL
            ORDER BY
                CASE cp.severity
                    WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3 ELSE 4
                END
            """,
            site_id,
        )

        if not problems:
            logger.info("No problems found for site %s", site_id)
            return 0

        generated = 0
        for problem in problems:
            try:
                rec = await self._generate_recommendation(db, site_id, problem)
                if rec:
                    generated += 1
            except Exception as e:
                logger.error(
                    "Failed to generate recommendation for problem %s: %s",
                    problem["id"], e,
                )

        # Also generate growth recommendations for healthy posts
        growth_count = await self._generate_growth_recommendations(db, site_id)
        generated += growth_count

        logger.info(
            "Generated %d recommendations for site %s", generated, site_id,
        )
        return generated

    async def _generate_recommendation(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        problem: asyncpg.Record,
    ) -> bool:
        """Generate a recommendation for a single problem."""
        ptype = problem["problem_type"]

        if ptype.startswith("decay_"):
            return await self._recommend_decay(db, site_id, problem)
        elif ptype.startswith("thin_"):
            return await self._recommend_thin(db, site_id, problem)
        elif ptype.startswith("seo_"):
            return await self._recommend_seo(db, site_id, problem)
        elif ptype == "orphan":
            return await self._recommend_orphan(db, site_id, problem)
        elif ptype == "cannibalization":
            return await self._recommend_cannibalization(db, site_id, problem)

        return False

    # ═══════════════════════════════════════════════
    # 2.14: Cannibalization recommendations
    # ═══════════════════════════════════════════════

    async def generate_cannibalization_recommendation(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        pair_id: UUID,
    ) -> dict:
        """Generate detailed cannibalization recommendation for a specific pair.

        Called when a user clicks on a cannibalization pair.
        """
        pair = await db.fetchrow(
            """
            SELECT cp.*,
                   pa.title AS title_a, pa.url AS url_a, pa.word_count AS wc_a,
                   pa.body_text AS body_a, pa.headings AS headings_a,
                   pb.title AS title_b, pb.url AS url_b, pb.word_count AS wc_b,
                   pb.body_text AS body_b, pb.headings AS headings_b
            FROM cannibalization_pairs cp
            JOIN posts pa ON pa.id = cp.post_a_id
            JOIN posts pb ON pb.id = cp.post_b_id
            WHERE cp.id = $1
            """,
            pair_id,
        )

        if not pair:
            raise ValueError(f"Cannibalization pair {pair_id} not found")

        # Get GSC data for both posts
        gsc_a = await self._get_post_gsc_summary(db, pair["post_a_id"])
        gsc_b = await self._get_post_gsc_summary(db, pair["post_b_id"])

        # Get headings as readable text
        headings_a = self._format_headings(pair["headings_a"])
        headings_b = self._format_headings(pair["headings_b"])

        body_a = truncate_for_api(pair["body_a"] or "", max_chars=4000, label="cannibal_post_a")
        body_b = truncate_for_api(pair["body_b"] or "", max_chars=4000, label="cannibal_post_b")

        prompt = f"""Two posts on the same site are cannibalizing each other — competing for the same search queries and splitting ranking signals.

EXAMPLE (for format reference):
Given two posts about "React State Management" and "React useState Guide" with cosine similarity 0.52, you might respond:
{{
  "primary_post": "A",
  "primary_reason": "Post A covers state management comprehensively (2400 words, 45 clicks/month) while Post B is a narrow subset (800 words, 12 clicks). Merging B's unique useState examples into A creates a definitive guide.",
  "merge_sections": ["Move Post B's 'Common useState Pitfalls' section with code examples into Post A under a new H2"],
  "new_sections_to_add": ["Add 'useState vs useReducer Decision Framework' — neither post covers when to choose which"],
  "redirect_strategy": "301 redirect /react-usestate-guide → /react-state-management#usestate",
  "estimated_effort_hours": 3,
  "estimated_impact": "high",
  "priority": "high",
  "confidence": 0.85
}}

NOW ANALYZE THESE POSTS:

POST A:
- Title: {pair['title_a']}
- URL: {pair['url_a']}
- Word count: {pair['wc_a']}
- Headings: {headings_a}
- Top queries & positions: {gsc_a}
- Content excerpt: {body_a}

POST B:
- Title: {pair['title_b']}
- URL: {pair['url_b']}
- Word count: {pair['wc_b']}
- Headings: {headings_b}
- Top queries & positions: {gsc_b}
- Content excerpt: {body_b}

Cosine similarity: {pair['cosine_similarity'] or 'N/A'}
Shared queries: {', '.join(pair['overlapping_queries'][:10]) if pair['overlapping_queries'] else 'None detected'}

ANALYZE AND RECOMMEND:
1. Which post should be the PRIMARY (keeper)? Why?
2. What unique content from the secondary post should be merged into the primary?
3. What new sections should be added that NEITHER post currently covers?
4. What is the redirect strategy? (301 from secondary → primary)
5. Reference SPECIFIC section headings and content from both posts.

Respond in this exact JSON format:
{{
  "primary_post": "A" or "B",
  "primary_reason": "Why this post is stronger...",
  "merge_sections": ["Section/content from the other post to merge in"],
  "new_sections_to_add": ["New sections neither covers"],
  "redirect_strategy": "Specific redirect instructions",
  "estimated_effort_hours": number,
  "estimated_impact": "high" or "medium" or "low",
  "priority": "critical" or "high" or "medium" or "low",
  "confidence": 0.0-1.0,
  "confidence_note": "Any caveats about this recommendation (omit if confident)"
}}"""

        result = await self._call_claude(prompt)

        # Store as recommendation
        primary = pair["post_a_id"] if result.get("primary_post") == "A" else pair["post_b_id"]
        secondary = pair["post_b_id"] if primary == pair["post_a_id"] else pair["post_a_id"]

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            secondary, site_id, "merge",
            result.get("priority", "high"),
            result.get("estimated_effort_hours", 3.0),
            result.get("estimated_impact", "high"),
            f"Merge into: {pair['title_a'] if primary == pair['post_a_id'] else pair['title_b']}",
            result.get("primary_reason", ""),
            json.dumps(result.get("merge_sections", []) + result.get("new_sections_to_add", [])),
            json.dumps(result),
        )

        return result

    async def _recommend_cannibalization(
        self, db: asyncpg.Connection, site_id: UUID, problem: asyncpg.Record,
    ) -> bool:
        """Lightweight cannibalization recommendation (batch mode)."""
        details = json.loads(problem["details"]) if problem["details"] else {}
        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            problem["post_id"], site_id, problem["id"], "merge",
            problem["severity"],
            3.0, "high",
            f"Resolve cannibalization: {problem['title']}",
            "This post is competing with another post for the same queries. Click for detailed merge recommendation.",
            json.dumps(["Click 'Get Recommendation' for AI-generated merge plan"]),
        )
        return True

    # ═══════════════════════════════════════════════
    # 2.15: Content decay recommendations
    # ═══════════════════════════════════════════════

    async def _recommend_decay(
        self, db: asyncpg.Connection, site_id: UUID, problem: asyncpg.Record,
    ) -> bool:
        """Generate content refresh recommendation for decaying posts."""
        details = json.loads(problem["details"]) if problem["details"] else {}
        gsc_data = await self._get_post_gsc_summary(db, problem["post_id"])
        body = truncate_for_api(problem["body_text"] or "", max_chars=5000, label="decay_post")
        headings = self._format_headings(problem["headings"])

        signal = details.get("signal", "unknown")
        context = ""
        if signal == "click_decline_90d":
            context = f"Clicks dropped {details.get('drop_percent', '?')}% (from {details.get('previous_clicks', '?')} to {details.get('recent_clicks', '?')}) over the last 90 days."
        elif signal == "position_drop":
            context = f"Was ranking at position {details.get('best_historic_position', '?')}, now at position {details.get('current_position', '?')}."
        elif signal == "stale_plus_low_ranking":
            context = f"Not updated in {details.get('months_since_update', '?')} months, currently at average position {details.get('avg_position', '?')}."

        prompt = f"""You are an SEO content strategist. This blog post is decaying — losing rankings and traffic.

POST:
- Title: {problem['title']}
- URL: {problem['url']}
- Word count: {problem['word_count'] or 'unknown'}
- Last updated: {problem['modified_date'] or problem['publish_date'] or 'unknown'}
- Headings: {headings}
- Top queries & positions: {gsc_data}

DECAY SIGNAL: {context}

CONTENT EXCERPT:
{body}

Generate a specific content refresh brief. Only reference sections and facts you can actually see in the excerpt — do not make up content that might be there.

Respond in JSON:
{{
  "outdated_sections": ["Specific sections/paragraphs that need updating"],
  "new_sections_to_add": ["Sections to add based on current search intent"],
  "facts_to_update": ["Specific outdated facts, stats, or references found in the excerpt"],
  "target_keywords": ["Keywords to optimize for based on current GSC data"],
  "suggested_new_title": "An optimized title if the current one is weak",
  "estimated_effort_hours": number,
  "estimated_impact": "high" or "medium" or "low",
  "priority": "critical" or "high" or "medium" or "low",
  "confidence": 0.0-1.0,
  "confidence_note": "Any caveats (e.g. 'Only saw excerpt, full post may differ')"
}}"""

        result = await self._call_claude(prompt)

        actions = []
        for section in result.get("outdated_sections", []):
            actions.append(f"Update: {section}")
        for section in result.get("new_sections_to_add", []):
            actions.append(f"Add new section: {section}")
        for fact in result.get("facts_to_update", []):
            actions.append(f"Update fact: {fact}")

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "refresh",
            result.get("priority", problem["severity"]),
            result.get("estimated_effort_hours", 2.0),
            result.get("estimated_impact", "medium"),
            f"Refresh: {problem['title']}",
            context,
            json.dumps(actions),
            json.dumps(result),
        )
        return True

    # ═══════════════════════════════════════════════
    # 2.16: Thin content recommendations
    # ═══════════════════════════════════════════════

    async def _recommend_thin(
        self, db: asyncpg.Connection, site_id: UUID, problem: asyncpg.Record,
    ) -> bool:
        """Generate expand/consolidate recommendation for thin content."""
        details = json.loads(problem["details"]) if problem["details"] else {}
        body = truncate_for_api(problem["body_text"] or "", max_chars=3000, label="thin_post")

        # Find the closest post in the same cluster that could absorb this
        similar_post = await db.fetchrow(
            """
            SELECT p2.id, p2.title, p2.url, p2.word_count
            FROM post_clusters pc1
            JOIN post_clusters pc2 ON pc1.cluster_id = pc2.cluster_id
            JOIN posts p2 ON p2.id = pc2.post_id
            WHERE pc1.post_id = $1 AND p2.id != $1
            ORDER BY p2.word_count DESC
            LIMIT 1
            """,
            problem["post_id"],
        )

        cluster_avg = details.get("cluster_avg", 1000)
        similar_info = ""
        if similar_post:
            similar_info = f"\nRelated post that could absorb this: '{similar_post['title']}' ({similar_post['url']}, {similar_post['word_count']} words)"

        prompt = f"""You are an SEO content strategist. This post is thin — too short to rank well.

POST:
- Title: {problem['title']}
- URL: {problem['url']}
- Word count: {problem['word_count'] or 0}
- Cluster average: {cluster_avg} words
{similar_info}

CONTENT:
{body}

Should this post be EXPANDED with new sections, or CONSOLIDATED into the related post? Base your decision only on what you can see.

Respond in JSON:
{{
  "action": "expand" or "consolidate",
  "reason": "Why this action...",
  "expansion_sections": ["If expanding: specific sections to add with brief descriptions"],
  "consolidation_target": "If consolidating: which post to merge into and why",
  "target_word_count": number,
  "estimated_effort_hours": number,
  "estimated_impact": "high" or "medium" or "low",
  "confidence": 0.0-1.0
}}"""

        result = await self._call_claude(prompt)

        action = result.get("action", "expand")
        rec_type = "expand" if action == "expand" else "merge"
        actions = result.get("expansion_sections", []) if action == "expand" else [result.get("consolidation_target", "")]

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], rec_type,
            problem["severity"],
            result.get("estimated_effort_hours", 2.0),
            result.get("estimated_impact", "medium"),
            f"{'Expand' if action == 'expand' else 'Consolidate'}: {problem['title']}",
            result.get("reason", ""),
            json.dumps(actions),
            json.dumps(result),
        )
        return True

    # ═══════════════════════════════════════════════
    # 2.17: SEO fix recommendations
    # ═══════════════════════════════════════════════

    async def _recommend_seo(
        self, db: asyncpg.Connection, site_id: UUID, problem: asyncpg.Record,
    ) -> bool:
        """Generate specific SEO fix with actual generated content."""
        ptype = problem["problem_type"]
        gsc_data = await self._get_post_gsc_summary(db, problem["post_id"])
        body = truncate_for_api(problem["body_text"] or "", max_chars=2000, label="seo_post")

        if ptype == "seo_missing_meta":
            return await self._recommend_meta_description(db, site_id, problem, gsc_data, body)
        elif ptype == "seo_title_length":
            return await self._recommend_title_fix(db, site_id, problem, gsc_data, body)
        elif ptype == "seo_no_headings":
            return await self._recommend_headings(db, site_id, problem, body)
        elif ptype == "seo_no_internal_links":
            return await self._recommend_interlinks(db, site_id, problem)
        elif ptype == "seo_no_images":
            return await self._recommend_images(db, site_id, problem)

        return False

    async def _recommend_meta_description(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record, gsc_data: str, body: str,
    ) -> bool:
        prompt = f"""Write a meta description for this blog post. It must be 150-160 characters, include the primary keyword, and be compelling enough to earn clicks.

Title: {problem['title']}
Top search queries: {gsc_data}
Content excerpt: {body[:500]}

Respond in JSON:
{{
  "meta_description": "The actual meta description to use",
  "primary_keyword": "The keyword it targets",
  "character_count": number,
  "confidence": 0.0-1.0
}}"""

        result = await self._call_claude(prompt)
        meta = result.get("meta_description", "")

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "optimize",
            "medium", 0.1, "medium",
            f"Add meta description: {problem['title']}",
            f"Generated meta description: \"{meta}\"",
            json.dumps([f"Set meta description to: \"{meta}\""]),
            json.dumps(result),
        )
        return True

    async def _recommend_title_fix(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record, gsc_data: str, body: str,
    ) -> bool:
        details = json.loads(problem["details"]) if problem["details"] else {}
        title_len = details.get("title_length", len(problem["title"] or ""))

        prompt = f"""This blog post title is {title_len} characters (ideal is 30-60). Rewrite it.

Current title: {problem['title']}
Top search queries: {gsc_data}
Content excerpt: {body[:300]}

Respond in JSON:
{{
  "new_title": "The optimized title (30-60 chars)",
  "character_count": number,
  "reason": "Why this title is better",
  "confidence": 0.0-1.0
}}"""

        result = await self._call_claude(prompt)
        new_title = result.get("new_title", "")

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "optimize",
            "low", 0.1, "low",
            f"Fix title: {problem['title']}",
            f"Change title to: \"{new_title}\"",
            json.dumps([f"Change title from \"{problem['title']}\" to \"{new_title}\""]),
            json.dumps(result),
        )
        return True

    async def _recommend_headings(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record, body: str,
    ) -> bool:
        prompt = f"""This blog post has no H2 or H3 headings. Suggest a heading structure.

Title: {problem['title']}
Content excerpt: {body}

Respond in JSON:
{{
  "suggested_headings": [
    {{"level": "h2", "text": "Heading text"}},
    {{"level": "h3", "text": "Sub-heading text"}}
  ],
  "reason": "Why this structure works",
  "confidence": 0.0-1.0
}}"""

        result = await self._call_claude(prompt)
        headings = result.get("suggested_headings", [])

        actions = [f"Add {h['level'].upper()}: {h['text']}" for h in headings]

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "optimize",
            "medium", 0.5, "medium",
            f"Add headings: {problem['title']}",
            f"Restructure content with {len(headings)} headings",
            json.dumps(actions),
            json.dumps(result),
        )
        return True

    async def _recommend_interlinks(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record,
    ) -> bool:
        """Find posts to interlink with."""
        related = await db.fetch(
            """
            SELECT p2.title, p2.url
            FROM post_clusters pc1
            JOIN post_clusters pc2 ON pc1.cluster_id = pc2.cluster_id
            JOIN posts p2 ON p2.id = pc2.post_id
            WHERE pc1.post_id = $1 AND p2.id != $1
            ORDER BY p2.word_count DESC
            LIMIT 5
            """,
            problem["post_id"],
        )

        if not related:
            # Fallback: find by embedding similarity
            related = await db.fetch(
                """
                SELECT p.title, p.url
                FROM post_embeddings pe1
                JOIN post_embeddings pe2 ON pe1.post_id != pe2.post_id
                JOIN posts p ON p.id = pe2.post_id
                WHERE pe1.post_id = $1 AND p.site_id = $2
                ORDER BY pe1.embedding <=> pe2.embedding
                LIMIT 5
                """,
                problem["post_id"], site_id,
            )

        actions = []
        for r in related:
            actions.append(f"Add link to \"{r['title']}\" ({r['url']})")

        actions.append(f"Add a link FROM one of those posts back to this post ({problem['url']})")

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "interlink",
            "high", 0.5, "medium",
            f"Add internal links: {problem['title']}",
            f"This post has no internal links. Link it to {len(related)} related posts.",
            json.dumps(actions),
            json.dumps({"related_posts": [{"title": r["title"], "url": r["url"]} for r in related]}),
        )
        return True

    async def _recommend_images(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record,
    ) -> bool:
        # Get body text for context-aware image suggestions
        body = await db.fetchval(
            "SELECT body_text FROM posts WHERE id = $1",
            problem["post_id"],
        )
        body_excerpt = truncate_for_api(body or "", max_chars=800, label="image_post")

        prompt = f"""This blog post has NO images. Suggest 3-4 SPECIFIC images that would improve this particular post. Don't be generic — reference actual content from the post.

Title: {problem['title']}
Content: {body_excerpt}

Respond in JSON:
{{
  "suggestions": [
    "Specific image suggestion referencing actual post content"
  ],
  "most_impactful": "Which single image would help SEO the most and why",
  "confidence": 0.0-1.0
}}"""

        try:
            result = await self._call_claude(prompt)
            suggestions = result.get("suggestions", [])
            most_impactful = result.get("most_impactful", "")
            summary = f"Add visuals: {most_impactful[:150]}" if most_impactful else "Add relevant images to improve engagement."
        except Exception:
            # Fallback to basic recommendation if Claude fails
            suggestions = ["Add a relevant visual that illustrates the main concept"]
            summary = "This post has no images. Adding relevant visuals improves engagement."
            result = {}

        await db.execute(
            """
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            problem["post_id"], site_id, problem["id"], "optimize",
            "low", 0.5, "low",
            f"Add images: {problem['title']}",
            summary,
            json.dumps(suggestions),
            json.dumps(result),
        )
        return True

    async def _recommend_orphan(
        self, db: asyncpg.Connection, site_id: UUID,
        problem: asyncpg.Record,
    ) -> bool:
        """Recommend interlinking for orphan content."""
        return await self._recommend_interlinks(db, site_id, problem)

    # ═══════════════════════════════════════════════
    # 2.18: Growth recommendations
    # ═══════════════════════════════════════════════

    async def _generate_growth_recommendations(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Generate growth recommendations for healthy/pillar posts.

        For each pillar post: suggest 3 supporting posts to build
        a topic cluster around it.
        """
        pillars = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count, p.body_text,
                   ph.composite_score, c.label AS cluster_label
            FROM post_health_scores ph
            JOIN posts p ON p.id = ph.post_id
            LEFT JOIN post_clusters pc ON pc.post_id = p.id
            LEFT JOIN clusters c ON c.id = pc.cluster_id
            WHERE p.site_id = $1 AND ph.role = 'pillar'
            ORDER BY ph.composite_score DESC
            LIMIT 5
            """,
            site_id,
        )

        generated = 0
        for pillar in pillars:
            # Check if growth recommendation already exists
            existing = await db.fetchval(
                """
                SELECT COUNT(*) FROM recommendations
                WHERE post_id = $1 AND recommendation_type = 'growth' AND status = 'pending'
                """,
                pillar["id"],
            )
            if existing > 0:
                continue

            gsc_data = await self._get_post_gsc_summary(db, pillar["id"])
            body = truncate_for_api(pillar["body_text"] or "", max_chars=2000, label="growth_pillar")

            prompt = f"""You are an SEO content strategist. This is a pillar post performing well. Suggest 3 supporting posts to build a topic cluster around it.

PILLAR POST:
- Title: {pillar['title']}
- URL: {pillar['url']}
- Word count: {pillar['word_count']}
- Cluster topic: {pillar['cluster_label'] or 'Unknown'}
- Top queries & positions: {gsc_data}
- Content excerpt: {body}

For each supporting post, provide:
1. Target keyword
2. Suggested title
3. Brief outline (3-5 bullet points)
4. How it should link to the pillar post

Respond in JSON:
{{
  "supporting_posts": [
    {{
      "target_keyword": "keyword",
      "suggested_title": "Title",
      "outline": ["Point 1", "Point 2", "Point 3"],
      "linking_strategy": "How to link to pillar"
    }}
  ],
  "estimated_effort_hours": number,
  "estimated_impact": "high" or "medium" or "low",
  "confidence": 0.0-1.0
}}"""

            result = await self._call_claude(prompt)
            posts = result.get("supporting_posts", [])

            actions = []
            for sp in posts:
                actions.append(
                    f"Write: \"{sp.get('suggested_title', 'Untitled')}\" "
                    f"targeting \"{sp.get('target_keyword', '')}\""
                )

            await db.execute(
                """
                INSERT INTO recommendations
                    (post_id, site_id, recommendation_type, priority,
                     estimated_effort_hours, estimated_impact, title, summary,
                     specific_actions, ai_generated_content)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                pillar["id"], site_id, "growth",
                "medium",
                result.get("estimated_effort_hours", 8.0),
                result.get("estimated_impact", "high"),
                f"Grow cluster: {pillar['title']}",
                f"Write {len(posts)} supporting posts to strengthen this pillar's topic cluster.",
                json.dumps(actions),
                json.dumps(result),
            )
            generated += 1

        return generated

    # ═══════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════

    async def _get_post_gsc_summary(
        self, db: asyncpg.Connection, post_id: UUID,
    ) -> str:
        """Get a summary of GSC queries and positions for a post."""
        rows = await db.fetch(
            """
            SELECT query, SUM(clicks) AS clicks, AVG(avg_position) AS pos
            FROM gsc_metrics
            WHERE post_id = $1 AND date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY query
            ORDER BY SUM(clicks) DESC
            LIMIT 10
            """,
            post_id,
        )
        if not rows:
            return "No GSC data available"

        parts = []
        for r in rows:
            parts.append(f"\"{r['query']}\" (pos {float(r['pos']):.1f}, {r['clicks']} clicks)")
        return "; ".join(parts)

    @staticmethod
    def _format_headings(headings) -> str:
        """Format headings list/JSON into readable string."""
        if not headings:
            return "None"
        if isinstance(headings, str):
            try:
                headings = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                return "None"
        if not isinstance(headings, list):
            return "None"

        parts = []
        for h in headings[:15]:
            if isinstance(h, dict):
                parts.append(f"{h.get('level', '?')}: {h.get('text', '')}")
        return "; ".join(parts) if parts else "None"

    async def _call_claude(self, prompt: str, temperature: float = 0.2) -> dict:
        """Call Claude API and parse JSON response.

        Uses temperature=0.2 by default for factual/analytical tasks.
        Lower temperature reduces hallucination and improves consistency.
        """
        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                temperature=temperature,
                system=(
                    "You are an SEO content strategist. You give specific, actionable "
                    "recommendations grounded in the data provided. "
                    "Never fabricate data, statistics, or facts. "
                    "Always include a 'confidence' field (0.0-1.0) indicating how "
                    "confident you are in this recommendation based on the data available. "
                    "Include a 'confidence_note' ONLY if there is a recommendation-specific "
                    "caveat (e.g. 'content may have changed since crawl', 'topic overlap is "
                    "borderline'). Do NOT repeat generic data availability caveats like "
                    "'without GSC data' or 'without traffic data' — the system already "
                    "accounts for missing data sources at the site level."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            return self._parse_json(raw)
        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            return {"error": str(e), "confidence": 0.0}

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Parse JSON from Claude response, handling markdown code blocks."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_response": raw}
