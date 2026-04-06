"""On-demand AI enrichment for individual recommendations — returns in ~3 seconds."""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

import anthropic
import asyncpg

from app.utils.llm_cost import log_llm_usage

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
_client: anthropic.AsyncAnthropic | None = None
_client_lock = asyncio.Lock()


def _smart_excerpt(text: str | None, max_chars: int = 800) -> str:
    """Extract first half + last half of text to capture both intro and unique deeper content.

    For cannibalization recs, similar posts often have identical introductions.
    Grabbing first 400 + last 400 chars exposes the parts that actually differ.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + "\n[...]\n" + text[-half:].lstrip()


async def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # double-check
                from app.config import get_settings
                settings = get_settings()
                _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
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
            logger.warning("Failed to parse specific_actions JSON, defaulting to empty dict")
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

    # Inject RAG context from the user's own blog data
    try:
        from app.services.rag_context import format_recommendation_context, get_recommendation_context
        rag_ctx = await get_recommendation_context(db, site_id, rec["post_id"])
        rag_text = format_recommendation_context(rag_ctx)
        if rag_text and rag_text != "(No additional context available)":
            context += f"\n\nBLOG CONTEXT (from this site's own data):\n{rag_text}"
    except Exception as e:
        logger.warning("RAG context retrieval failed for enrichment: %s", e)

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
            # Use first 400 + last 400 chars to capture both intro and unique
            # deeper content (first-800 often shows identical intros for similar posts)
            excerpt_a = _smart_excerpt(rec["body_excerpt"], 800)
            excerpt_b = _smart_excerpt(pair["body_excerpt"], 800)
            context += (
                f"\n\nOverlapping post: {pair['title']}\nURL: {pair['url']}\n"
                f"Word count: {pair['word_count']}\n\n"
                f"Post A excerpt:\n{excerpt_a}\n\n"
                f"Post B excerpt:\n{excerpt_b}"
            )
    else:
        context += f"\n\nContent excerpt:\n{rec['body_excerpt'][:1500]}"

    prompt = _build_prompt(rec_type, context)

    # Retry once on transient failures (rate limit, 5xx server errors)
    max_attempts = 2
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            client = await _get_client()
            message = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=800,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
            await log_llm_usage(
                db, site_id=site_id, service="on_demand_enrichment",
                model=CLAUDE_MODEL,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )

            # Parse JSON — strip markdown code fences if present
            if response_text.startswith("```"):
                response_text = re.sub(r'^```\w*\n?', '', response_text)
                response_text = re.sub(r'\n?```\s*$', '', response_text)
            try:
                enrichment = json.loads(response_text)
            except json.JSONDecodeError:
                enrichment = {"raw_response": response_text}
            break  # success — exit retry loop

        except (anthropic.RateLimitError, anthropic.InternalServerError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                logger.warning(
                    "Transient Claude error for rec %s (attempt %d/%d), retrying in 2s: %s",
                    rec_id, attempt + 1, max_attempts, e,
                )
                await asyncio.sleep(2)
                continue
            logger.error("Claude enrichment failed after %d attempts for rec %s: %s", max_attempts, rec_id, e)
            return {"error": str(e)}

        except Exception as e:
            logger.error("Claude enrichment failed for rec %s: %s", rec_id, e)
            return {"error": str(e)}
    else:
        # All retries exhausted (shouldn't reach here, but safety net)
        logger.error("Claude enrichment exhausted retries for rec %s: %s", rec_id, last_error)
        return {"error": str(last_error)}

    # Store enriched actions
    original_actions = rec["specific_actions"]
    if isinstance(original_actions, str):
        try:
            original_actions = json.loads(original_actions)
        except Exception:
            logger.warning("Failed to parse specific_actions JSON, using raw value")
            original_actions = [original_actions] if original_actions else []
    elif original_actions is None:
        original_actions = []

    enriched_actions = {
        "ai_enriched": True,
        "ai_guidance": enrichment,
        "original_actions": original_actions if isinstance(original_actions, list) else [],
    }

    # Write enriched actions to specific_actions AND mark ai_generated_content
    # so the NULL sentinel filter in auto_enrich_top_recs is semantically correct
    ai_marker = json.dumps({"enriched_at": datetime.now(UTC).isoformat()})
    await db.execute("""
        UPDATE recommendations
        SET specific_actions = $1, ai_generated_content = $2::jsonb, updated_at = NOW()
        WHERE id = $3
    """, json.dumps(enriched_actions), ai_marker, rec_id)

    logger.info("Enriched recommendation %s on-demand", rec_id)
    return {"enriched": True, "guidance": enrichment}


async def auto_enrich_top_recs(
    pool_or_db: asyncpg.Pool | asyncpg.Connection,
    site_id: UUID,
    limit: int = 10,
    max_concurrent: int = 3,
) -> int:
    """Auto-enrich the highest-priority recommendations that lack AI content.

    Called at the end of the intelligence pipeline to ensure top recs
    have rich, actionable AI-generated guidance without requiring
    the user to click "Get AI Analysis" manually.

    When passed a Pool, enrichments run concurrently (up to max_concurrent)
    for ~3x speedup. When passed a single Connection, falls back to sequential.
    """
    is_pool = isinstance(pool_or_db, asyncpg.Pool)

    # Fetch top recs — type-diverse selection to ensure enrichment budget
    # covers different recommendation types instead of all being add_schema
    MAX_PER_TYPE = 3

    async def _fetch_rows(db: asyncpg.Connection) -> list:
        # Fetch 3x candidates, then select up to MAX_PER_TYPE per type
        candidates = await db.fetch(
            """
            SELECT id, recommendation_type FROM recommendations
            WHERE site_id = $1
              AND ai_generated_content IS NULL
              AND status = 'pending'
            ORDER BY
                CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END,
                created_at DESC
            LIMIT $2
            """,
            site_id,
            limit * 3,
        )
        # Type-diverse selection
        type_counts: dict[str, int] = {}
        selected: list = []
        for row in candidates:
            rt = row["recommendation_type"]
            if type_counts.get(rt, 0) < MAX_PER_TYPE:
                selected.append(row)
                type_counts[rt] = type_counts.get(rt, 0) + 1
            if len(selected) >= limit:
                break
        # Fill remaining slots if we have room
        if len(selected) < limit:
            selected_ids = {r["id"] for r in selected}
            for row in candidates:
                if row["id"] not in selected_ids:
                    selected.append(row)
                    if len(selected) >= limit:
                        break
        return selected

    if is_pool:
        async with pool_or_db.acquire() as db:
            rows = await _fetch_rows(db)
    else:
        rows = await _fetch_rows(pool_or_db)

    if not rows:
        logger.info("No recs to auto-enrich for site %s", site_id)
        return 0

    # Concurrent path: each enrichment gets its own connection from the pool
    if is_pool:
        sem = asyncio.Semaphore(max_concurrent)
        results: list[bool] = []

        async def _enrich_one(rec_id: UUID) -> bool:
            async with sem:
                try:
                    async with pool_or_db.acquire() as db:
                        result = await enrich_recommendation(db, rec_id, site_id)
                        return "error" not in result
                except Exception as e:
                    logger.warning("Auto-enrich failed for rec %s: %s", rec_id, e)
                    return False

        results = await asyncio.gather(*[_enrich_one(row["id"]) for row in rows])
        enriched = sum(1 for ok in results if ok)
    else:
        # Sequential fallback for single-connection callers
        enriched = 0
        for row in rows:
            try:
                result = await enrich_recommendation(pool_or_db, row["id"], site_id)
                if "error" not in result:
                    enriched += 1
            except Exception as e:
                logger.warning("Auto-enrich failed for rec %s: %s", row["id"], e)
                continue

    logger.info(
        "Auto-enriched %d/%d top recs for site %s",
        enriched, len(rows), site_id,
    )
    return enriched
