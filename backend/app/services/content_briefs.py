"""RAG-powered content brief generation.

Generates comprehensive, writer-ready content briefs that:
1. Pre-check for cannibalization against the existing blog
2. Pull cluster context to set word count/structure benchmarks
3. Plan internal links to/from the new post
4. Generate an outline that covers gaps NOT already in existing content
5. Specify what to AVOID to prevent cannibalization

The brief references the user's own data — their top performers, cluster
patterns, and keyword rankings. No generic advice.
"""

import json
import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import get_settings
from app.services.rag_context import get_brief_context, format_brief_context
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
EMBEDDING_MODEL = "text-embedding-3-small"


class ContentBriefGenerator:
    """Generate RAG-powered content briefs."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def generate_brief(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        target_keyword: str,
        source_type: str = "manual",
        source_id: UUID | None = None,
    ) -> dict:
        """Generate a full RAG-powered content brief.

        Steps:
        1. Embed the topic keyword
        2. Retrieve blog context (similar posts, cluster stats, link candidates)
        3. Check cannibalization risk
        4. Generate brief via Claude with all context
        5. Store in DB

        Returns the complete brief data dict.
        """
        logger.info("Generating RAG content brief for '%s' (site %s)", target_keyword, site_id)

        # Step 1: Generate embedding for the topic
        topic_embedding = await self._embed_topic(target_keyword)
        if not topic_embedding:
            return {"error": "Failed to generate topic embedding"}

        # Step 2: Retrieve RAG context
        rag_context = await get_brief_context(
            db, site_id, topic_embedding, target_keyword,
        )

        # Step 3: Get GSC secondary keywords
        secondary_kws = await self._get_secondary_keywords(db, site_id, target_keyword)

        # Step 4: Format context and generate brief via Claude
        context_text = format_brief_context(rag_context)
        brief_data = await self._generate_via_claude(
            target_keyword, secondary_kws, context_text, rag_context,
        )

        if not brief_data:
            return {"error": "Failed to generate brief"}

        # Step 5: Build internal link plan from RAG data
        link_candidates = rag_context.get("link_candidates", [])
        links_to = [
            {"post_id": c["id"], "title": c["title"], "url": c["url"]}
            for c in link_candidates if c.get("direction") == "to"
        ][:5]
        links_from = [
            {"post_id": c["id"], "title": c["title"], "url": c["url"]}
            for c in link_candidates if c.get("direction") == "from"
        ][:5]

        # Step 6: Store in DB
        cannibalization_risk = rag_context.get("cannibalization_risk", "unknown")
        avoid_topics = brief_data.get("avoid_topics", [])
        content_angle = brief_data.get("content_angle", "")
        difficulty_level = brief_data.get("difficulty_level", "intermediate")

        internal_link_target_ids = [UUID(c["id"]) for c in link_candidates[:5]]

        brief_id = await db.fetchval(
            """
            INSERT INTO content_briefs
                (site_id, source_type, source_id, target_keyword,
                 secondary_keywords, suggested_titles, recommended_word_count,
                 outline, questions_to_answer, internal_link_targets,
                 cannibalization_risk, differentiation_notes,
                 avoid_topics, internal_links_from, internal_links_to,
                 content_angle, difficulty_level)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            RETURNING id
            """,
            site_id, source_type, source_id, target_keyword,
            brief_data.get("secondary_keywords", secondary_kws[:5]),
            brief_data.get("suggested_titles", []),
            brief_data.get("recommended_word_count", 1500),
            json.dumps(brief_data.get("outline", [])),
            brief_data.get("questions_to_answer", []),
            internal_link_target_ids,
            cannibalization_risk,
            rag_context.get("risk_message", ""),
            avoid_topics,
            json.dumps(links_from),
            json.dumps(links_to),
            content_angle,
            difficulty_level,
        )

        result = {
            "brief_id": str(brief_id),
            "target_keyword": target_keyword,
            "cannibalization_risk": cannibalization_risk,
            "risk_message": rag_context.get("risk_message", ""),
            **brief_data,
            "internal_links_to": links_to,
            "internal_links_from": links_from,
            "avoid_topics": avoid_topics,
        }

        logger.info("RAG content brief generated: %s (risk: %s)", brief_id, cannibalization_risk)
        return result

    async def _embed_topic(self, topic: str) -> str | None:
        """Generate an embedding for the topic keyword."""
        try:
            resp = await self.openai.embeddings.create(
                model=EMBEDDING_MODEL,
                input=topic,
            )
            embedding = resp.data[0].embedding
            return "[" + ",".join(str(v) for v in embedding) + "]"
        except Exception as e:
            logger.error("Failed to embed topic '%s': %s", topic, e)
            return None

    async def _get_secondary_keywords(
        self, db: asyncpg.Connection, site_id: UUID, keyword: str,
    ) -> list[str]:
        """Get related keywords from GSC data."""
        rows = await db.fetch(
            """
            SELECT DISTINCT query, SUM(impressions) AS total_imp
            FROM gsc_metrics
            WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
              AND query ILIKE '%' || $2 || '%'
              AND date >= CURRENT_DATE - 90
            GROUP BY query
            ORDER BY total_imp DESC
            LIMIT 15
            """,
            site_id, keyword.split()[0],
        )
        return [r["query"] for r in rows if r["query"].lower() != keyword.lower()]

    async def _generate_via_claude(
        self,
        target_keyword: str,
        secondary_keywords: list[str],
        context_text: str,
        rag_context: dict,
    ) -> dict | None:
        """Generate the brief using Claude with full RAG context."""
        secondary_text = ", ".join(secondary_keywords[:10]) if secondary_keywords else "none found in GSC"

        # Build the list of existing posts to explicitly avoid overlapping with
        similar = rag_context.get("similar_existing", [])
        avoid_section = ""
        if similar:
            avoid_lines = []
            for p in similar[:5]:
                if p.get("similarity", 0) > 0.40:
                    avoid_lines.append(
                        f"  - \"{p['title']}\" (similarity: {p['similarity']:.0%})"
                    )
            if avoid_lines:
                avoid_section = (
                    "\n\nEXISTING POSTS TO DIFFERENTIATE FROM:\n"
                    + "\n".join(avoid_lines)
                )

        cluster_stats = rag_context.get("cluster_stats", {})
        word_count_benchmark = cluster_stats.get("avg_word_count", 1500)

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                temperature=0.3,
                system=(
                    "You are an expert SEO content strategist generating a content brief "
                    "for a specific blog. You have access to the blog's own data — use it. "
                    "Reference their top performers as benchmarks. Set word count targets "
                    "based on what works in their cluster. Name specific existing posts to "
                    "link to/from. Be specific — don't say 'discuss benefits', say exactly "
                    "what benefits to cover. Specify what to AVOID to prevent cannibalization "
                    "with existing content."
                ),
                messages=[{
                    "role": "user",
                    "content": f"""Generate a full content brief for a new blog post targeting: "{target_keyword}"

Related keywords from GSC: {secondary_text}

BLOG CONTEXT:
{context_text}
{avoid_section}

The cluster average word count is {word_count_benchmark}. Use this as your baseline.

Respond in this exact JSON format:
{{
  "suggested_titles": ["Title Option A (include keyword)", "Title Option B (different angle)"],
  "secondary_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "recommended_word_count": number,
  "outline": [
    {{
      "level": "h2",
      "text": "Section Heading",
      "bullets": ["Specific point to cover", "Another specific point"],
      "estimated_words": 300
    }}
  ],
  "questions_to_answer": ["Specific question from search intent"],
  "avoid_topics": ["Topics covered by existing posts — DO NOT cover these"],
  "content_angle": "How this post differentiates from existing content",
  "difficulty_level": "beginner|intermediate|advanced",
  "opening_hook": "Suggested first paragraph approach",
  "cta_suggestion": "What call-to-action to use",
  "internal_links_suggested": [
    {{"post_title": "Existing Post Title", "anchor_text": "suggested anchor", "direction": "to|from"}}
  ],
  "content_type": "guide|listicle|comparison|how-to|case-study",
  "confidence": 0.0-1.0
}}""",
                }],
            )

            raw = response.content[0].text.strip()
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error("Claude brief generation failed: %s", e)
            return None

    @staticmethod
    def _parse_json_response(raw: str) -> dict | None:
        """Parse JSON from Claude response, handling markdown code blocks."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
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
            logger.error("Failed to parse brief JSON: %s", text[:200])
            return None

    async def generate_briefs_for_gaps(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        limit: int = 5,
    ) -> int:
        """Auto-generate briefs for top content gaps.

        Returns number of briefs generated.
        """
        gaps = await db.fetch(
            """
            SELECT id, query
            FROM content_gaps
            WHERE site_id = $1 AND status = 'open'
            ORDER BY impressions DESC
            LIMIT $2
            """,
            site_id, limit,
        )

        generated = 0
        for gap in gaps:
            result = await self.generate_brief(
                db, site_id, gap["query"],
                source_type="content_gap",
                source_id=gap["id"],
            )
            if "error" not in result:
                generated += 1

        logger.info("Generated %d briefs from content gaps for site %s", generated, site_id)
        return generated
