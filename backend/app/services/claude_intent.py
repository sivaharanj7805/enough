"""Claude-based intent classification for ambiguous posts.

The fast keyword classifier handles ~90% of cases. This service handles
the 10% where keyword signals are weak or contradictory.

Ambiguity detection: posts where the title has no strong intent keywords,
or where the post scores on multiple intent categories simultaneously.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from uuid import UUID

import anthropic
import asyncpg

logger = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-sonnet-4-20250514"

STRONG_COMMERCIAL = {"pricing", "cost", "demo", "alternative", "vs ", "review", "compare", "buy"}
STRONG_INFO = {"how to", "guide", "what is", "why ", "tips", "best practices", "tutorial"}
STRONG_TRANSACTIONAL = {"download", "template", "free trial", "sign up", "checklist", "worksheet"}
STRONG_NAVIGATIONAL = {"login", "contact", "about", "team", "careers", "sitemap"}


def _is_ambiguous(title: str, url: str) -> bool:
    """Return True if this post's intent is unclear from keywords alone."""
    title_lower = title.lower()
    url_lower = url.lower()
    combined = f"{title_lower} {url_lower}"

    hits = {
        "commercial": any(k in combined for k in STRONG_COMMERCIAL),
        "informational": any(k in combined for k in STRONG_INFO),
        "transactional": any(k in combined for k in STRONG_TRANSACTIONAL),
        "navigational": any(k in combined for k in STRONG_NAVIGATIONAL),
    }

    strong_hit_count = sum(hits.values())

    # Ambiguous if: no strong signals at all, OR multiple conflicting signals
    return strong_hit_count == 0 or strong_hit_count >= 2


async def classify_ambiguous_posts(
    db: asyncpg.Connection,
    site_id: UUID,
    limit: int = 150,
) -> dict:
    """Find ambiguous posts and classify intent with Claude. Batch in groups of 10."""
    # Fetch posts with weak intent signals
    posts = await db.fetch("""
        SELECT id, title, url, meta_description, LEFT(body_text, 300) AS excerpt
        FROM posts
        WHERE site_id = $1
        ORDER BY word_count DESC
        LIMIT 1000
    """, site_id)

    ambiguous = [
        p for p in posts
        if _is_ambiguous(p["title"] or "", p["url"] or "")
    ][:limit]

    if not ambiguous:
        return {"classified": 0, "message": "No ambiguous posts found"}

    logger.info("Found %d ambiguous posts for Claude classification", len(ambiguous))

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    classified = 0
    errors = 0

    # Batch in groups of 10 for efficiency
    batch_size = 10
    for i in range(0, len(ambiguous), batch_size):
        batch = ambiguous[i:i + batch_size]

        posts_text = "\n\n".join([
            f"Post {j+1}: \"{p['title']}\"\nURL: {p['url']}\nMeta: {p['meta_description'] or 'N/A'}\nExcerpt: {p['excerpt'] or 'N/A'}"
            for j, p in enumerate(batch)
        ])

        prompt = f"""Classify the search intent of each blog post. Choose ONE: informational, commercial, transactional, or navigational.

Definitions:
- informational: teaches something, answers a question (how-to, guide, what-is)  
- commercial: helps compare/evaluate options (reviews, alternatives, pricing research)
- transactional: drives immediate action (download, sign up, free trial, template)
- navigational: helps find a specific page (contact, login, about)

{posts_text}

Respond with ONLY a JSON array (no markdown), one object per post in the same order:
[{{"intent": "informational"}}, {{"intent": "commercial"}}, ...]"""

        try:
            message = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=200,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            response = message.content[0].text.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            results = json.loads(response)

            for j, result in enumerate(results):
                if j >= len(batch):
                    break
                intent = result.get("intent", "informational")
                if intent not in ("informational", "commercial", "transactional", "navigational"):
                    intent = "informational"
                await db.execute(
                    "UPDATE posts SET content_intent = $1 WHERE id = $2",
                    intent, batch[j]["id"],
                )
                classified += 1

        except Exception as e:
            logger.error("Claude intent batch %d failed: %s", i // batch_size, e)
            errors += 1

        await asyncio.sleep(0.5)

    logger.info("Claude intent: classified=%d errors=%d", classified, errors)
    return {"classified": classified, "errors": errors, "total_ambiguous": len(ambiguous)}
