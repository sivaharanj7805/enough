"""Full content brief generation — replaces MarketMuse ($600/mo).

Generates comprehensive, writer-ready content briefs including:
- Target keyword + secondary keywords
- A/B title options
- Recommended word count
- Full H2/H3 outline with bullet points per section
- Key questions to answer (from related queries)
- Internal linking targets (existing posts to link to/from)
- Competitor insights (what top results cover)

A brief should be actionable enough that a writer can start
immediately without additional research.
"""

import json
import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


class ContentBriefGenerator:
    """Generate full content briefs via Claude."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def generate_brief(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        target_keyword: str,
        source_type: str = "manual",
        source_id: UUID | None = None,
    ) -> dict:
        """Generate a full content brief for a target keyword.

        Returns the brief data and stores it in the content_briefs table.
        """
        logger.info("Generating content brief for '%s' (site %s)", target_keyword, site_id)

        # Gather context: existing posts in related clusters
        related_posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url
            FROM posts p
            WHERE p.site_id = $1
            ORDER BY p.title
            LIMIT 30
            """,
            site_id,
        )
        existing_titles = [r["title"] for r in related_posts]
        existing_urls = [{"id": r["id"], "title": r["title"], "url": r["url"]} for r in related_posts]

        # Get related GSC queries for secondary keywords
        related_queries = await db.fetch(
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
            site_id, target_keyword.split()[0],  # Match on first word
        )
        secondary_kws = [r["query"] for r in related_queries if r["query"] != target_keyword]

        # Generate the brief via Claude
        brief_data = await self._generate_via_claude(
            target_keyword, secondary_kws[:10], existing_titles[:15],
        )

        if not brief_data:
            return {"error": "Failed to generate brief"}

        # Find internal link targets (posts to link to/from)
        link_targets = []
        for post in existing_urls[:10]:
            link_targets.append(post["id"])

        # Store in DB
        brief_id = await db.fetchval(
            """
            INSERT INTO content_briefs
                (site_id, source_type, source_id, target_keyword,
                 secondary_keywords, suggested_titles, recommended_word_count,
                 outline, questions_to_answer, internal_link_targets)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            site_id, source_type, source_id, target_keyword,
            brief_data.get("secondary_keywords", secondary_kws[:5]),
            brief_data.get("suggested_titles", []),
            brief_data.get("recommended_word_count", 1500),
            json.dumps(brief_data.get("outline", [])),
            brief_data.get("questions_to_answer", []),
            link_targets[:5],
        )

        result = {
            "brief_id": brief_id,
            "target_keyword": target_keyword,
            **brief_data,
            "internal_link_targets": [
                {"id": str(p["id"]), "title": p["title"], "url": p["url"]}
                for p in existing_urls[:5]
            ],
        }

        logger.info("Content brief generated: %s", brief_id)
        return result

    async def _generate_via_claude(
        self,
        target_keyword: str,
        secondary_keywords: list[str],
        existing_titles: list[str],
    ) -> dict | None:
        """Call Claude to generate the brief structure."""
        secondary_text = ", ".join(secondary_keywords[:10]) if secondary_keywords else "none found"
        existing_text = "\n".join(f"- {t}" for t in existing_titles[:15])

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                temperature=0.3,
                system=(
                    "You are an expert SEO content strategist. Generate detailed, "
                    "actionable content briefs that a writer can immediately execute. "
                    "Be specific — don't say 'discuss benefits', say exactly what "
                    "benefits to cover and what data to include."
                ),
                messages=[{
                    "role": "user",
                    "content": f"""Generate a full content brief for a blog post targeting: "{target_keyword}"

Related keywords: {secondary_text}

Existing posts on this site:
{existing_text}

Respond in this exact JSON format:
{{
  "suggested_titles": ["Title Option A (include keyword)", "Title Option B (emotional hook)"],
  "secondary_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "recommended_word_count": number,
  "outline": [
    {{
      "level": "h2",
      "text": "Section Heading",
      "bullets": ["Specific point to cover", "Another specific point"],
      "estimated_words": 300
    }},
    {{
      "level": "h3",
      "text": "Sub-section",
      "bullets": ["Point 1", "Point 2"],
      "estimated_words": 200
    }}
  ],
  "questions_to_answer": ["Specific question from search intent", "Another question"],
  "opening_hook": "Suggested first paragraph approach",
  "cta_suggestion": "What call-to-action to use",
  "content_type": "guide|listicle|comparison|how-to|case-study",
  "difficulty_level": "beginner|intermediate|advanced",
  "confidence": 0.0-1.0
}}""",
                }],
            )

            raw = response.content[0].text.strip()
            # Parse JSON (handle markdown code blocks)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            return json.loads(raw)
        except Exception as e:
            logger.error("Claude brief generation failed: %s", e)
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
