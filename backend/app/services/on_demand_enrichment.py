"""On-demand AI enrichment for individual recommendations — returns in ~3 seconds."""
from __future__ import annotations

import json
import logging
import os
from uuid import UUID

import anthropic
import asyncpg

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _build_prompt(rec_type: str, context: str) -> str:
    """Build enrichment prompt based on recommendation type."""
    if rec_type in ("merge", "redirect"):
        return f"""You are a content strategist. Based on these two overlapping blog posts, provide a specific merge plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"merge_plan": "Which post to keep as primary and why (1 sentence)",
"keep_url": "URL of the post to keep",
"redirect_url": "URL to 301 redirect",
"sections_to_merge": ["Specific sections from secondary post to incorporate"],
"estimated_word_count": "Target word count for merged post",
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "differentiate":
        return f"""You are a content strategist. These posts overlap. Provide a specific differentiation plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"differentiation_plan": "How to make these posts distinct (1-2 sentences)",
"post_a_angle": "Specific angle/focus for post A",
"post_b_angle": "Specific angle/focus for post B",
"keywords_post_a": ["3-5 specific target keywords for post A"],
"keywords_post_b": ["3-5 specific target keywords for post B"],
"sections_to_rewrite": ["Specific overlapping sections that need rewriting"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "expand":
        return f"""You are a content strategist. This thin blog post needs expansion. Provide specific guidance.

{context}

Respond with ONLY a JSON object (no markdown):
{{"expansion_plan": "What this post needs (1-2 sentences)",
"sections_to_add": ["3-5 specific new sections with suggested H2 headings"],
"target_word_count": "Recommended final word count",
"content_gaps": ["Specific topics/questions the current post doesn't address"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "optimize":
        return f"""You are an SEO content strategist. This blog post needs optimization.

{context}

Respond with ONLY a JSON object (no markdown):
{{"optimization_plan": "What needs to change (1-2 sentences)",
"title_suggestion": "Improved title or 'Current title is good'",
"meta_description": "Suggested meta description (150-160 chars)",
"content_improvements": ["2-3 specific improvements with details"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "interlink":
        return f"""You are a content strategist. This blog post is an orphan with no inbound internal links.

{context}

Respond with ONLY a JSON object (no markdown):
{{"interlink_plan": "Why this post deserves more internal links (1 sentence)",
"suggested_anchor_texts": ["3-5 natural anchor text phrases"],
"likely_linking_posts": ["3-5 post types that should link here"],
"placement_tips": "Where in linking posts the link should be placed",
"estimated_impact": "Expected impact on crawl depth and rankings"}}"""

    else:
        return f"""You are a content strategist. Provide specific, actionable guidance for this recommendation.

{context}

Respond with ONLY a JSON object (no markdown):
{{"action_plan": "Specific steps to implement",
"priority_rationale": "Why this matters",
"estimated_impact": "Expected SEO impact",
"time_estimate": "Estimated implementation time"}}"""


async def enrich_recommendation(
    db: asyncpg.Connection,
    rec_id: UUID,
    site_id: UUID,
) -> dict:
    """Enrich a single recommendation on-demand. Returns enriched data in ~3s."""

    # Fetch rec + post data
    rec = await db.fetchrow("""
        SELECT r.id, r.post_id, r.recommendation_type, r.title, r.summary,
               r.specific_actions, r.priority,
               p.title AS post_title, p.url, p.word_count,
               LEFT(p.body_text, 2000) AS body_excerpt
        FROM recommendations r
        JOIN posts p ON p.id = r.post_id
        WHERE r.id = $1 AND r.site_id = $2
    """, rec_id, site_id)

    if not rec:
        return {"error": "Recommendation not found"}

    # Check if already enriched
    existing = rec["specific_actions"]
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except Exception:
            existing = {}
    if isinstance(existing, dict) and existing.get("ai_enriched"):
        return {"already_enriched": True, "guidance": existing.get("ai_guidance", {})}

    # Build context
    context = (
        f"Post: {rec['post_title']}\n"
        f"URL: {rec['url']}\n"
        f"Word count: {rec['word_count']}\n"
        f"Recommendation: {rec['title']}\n"
        f"{rec['summary'] or ''}"
    )

    rec_type = rec["recommendation_type"]

    # For cann recs, fetch the overlapping post
    if rec_type in ("merge", "differentiate", "redirect"):
        pair = await db.fetchrow("""
            SELECT p.title, p.url, p.word_count, LEFT(p.body_text, 1500) AS body_excerpt
            FROM cannibalization_pairs cp
            JOIN posts p ON p.id = CASE
                WHEN cp.post_a_id = $1 THEN cp.post_b_id
                ELSE cp.post_a_id END
            WHERE (cp.post_a_id = $1 OR cp.post_b_id = $1)
            ORDER BY cp.cosine_similarity DESC
            LIMIT 1
        """, rec["post_id"])
        if pair:
            context += (
                f"\n\nOverlapping post: {pair['title']}\nURL: {pair['url']}\n"
                f"Word count: {pair['word_count']}\n\n"
                f"Post A excerpt:\n{rec['body_excerpt'][:800]}\n\n"
                f"Post B excerpt:\n{pair['body_excerpt'][:800]}"
            )
    else:
        context += f"\n\nContent excerpt:\n{rec['body_excerpt'][:1500]}"

    prompt = _build_prompt(rec_type, context)

    try:
        client = _get_client()
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()

        # Parse JSON
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        try:
            enrichment = json.loads(response_text)
        except json.JSONDecodeError:
            enrichment = {"raw_response": response_text}

    except Exception as e:
        logger.error("Claude enrichment failed for rec %s: %s", rec_id, e)
        return {"error": str(e)}

    # Store enriched actions
    original_actions = rec["specific_actions"]
    if isinstance(original_actions, str):
        try:
            original_actions = json.loads(original_actions)
        except Exception:
            original_actions = [original_actions] if original_actions else []
    elif original_actions is None:
        original_actions = []

    enriched_actions = {
        "ai_enriched": True,
        "ai_guidance": enrichment,
        "original_actions": original_actions if isinstance(original_actions, list) else [],
    }

    await db.execute("""
        UPDATE recommendations SET specific_actions = $1, updated_at = NOW()
        WHERE id = $2
    """, json.dumps(enriched_actions), rec_id)

    logger.info("Enriched recommendation %s on-demand", rec_id)
    return {"enriched": True, "guidance": enrichment}
