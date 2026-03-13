"""Weighted embedding strategy for better topic representation.

Instead of embedding full body text equally, this module constructs
weighted text that emphasizes what a post is ABOUT:
  - Title: repeated 3× (highest signal for topic)
  - Headings (H2/H3): repeated 2× (structural topic markers)
  - First paragraph: repeated 1.5× (thesis/intro)
  - Body text: 1× (context and depth)

This produces embeddings that better capture post "aboutness" vs
incidental mentions. Better embeddings → better clusters →
better cannibalization detection → better everything.
"""

import json
import logging
import re
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


def construct_weighted_text(
    title: str | None,
    headings: list | str | None,
    body_text: str | None,
    max_chars: int = 8000,
) -> str:
    """Construct weighted text for embedding.

    Returns a string where title/headings/first_para are repeated
    for emphasis, producing better topic-focused embeddings.
    """
    parts: list[str] = []

    # Title × 3
    if title:
        clean_title = title.strip()
        parts.extend([clean_title] * 3)

    # Headings × 2
    if headings:
        if isinstance(headings, str):
            try:
                headings = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                headings = []
        if isinstance(headings, list):
            heading_texts = []
            for h in headings:
                if isinstance(h, dict):
                    text = h.get("text", "").strip()
                    if text:
                        heading_texts.append(text)
            if heading_texts:
                joined_headings = ". ".join(heading_texts)
                parts.extend([joined_headings] * 2)

    # First paragraph × 1.5 (repeat once + include in body)
    first_para = ""
    if body_text:
        # Extract first paragraph (up to first double newline or 500 chars)
        paras = re.split(r'\n\s*\n', body_text.strip(), maxsplit=1)
        if paras:
            first_para = paras[0][:500].strip()
            if first_para:
                parts.append(first_para)  # Extra copy (body already has it)

    # Full body × 1
    if body_text:
        parts.append(body_text.strip())

    result = "\n\n".join(parts)

    # Truncate to max_chars (embedding models have token limits)
    if len(result) > max_chars:
        result = result[:max_chars]

    return result


class WeightedEmbeddingBuilder:
    """Construct weighted text for all posts, ready for re-embedding."""

    async def prepare_weighted_texts(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> list[dict]:
        """Build weighted text for all posts in a site.

        Returns list of {post_id, weighted_text} for the embedding pipeline
        to process. Does NOT call the embedding API — that's done by the
        existing embeddings service.
        """
        logger.info("Preparing weighted texts for site %s", site_id)

        posts = await db.fetch(
            """
            SELECT id, title, headings, body_text
            FROM posts
            WHERE site_id = $1 AND body_text IS NOT NULL
            """,
            site_id,
        )

        results = []
        for post in posts:
            weighted = construct_weighted_text(
                title=post["title"],
                headings=post["headings"],
                body_text=post["body_text"],
            )
            if weighted:
                results.append({
                    "post_id": post["id"],
                    "weighted_text": weighted,
                })

        logger.info(
            "Prepared %d weighted texts for site %s", len(results), site_id,
        )
        return results

    async def mark_embeddings_as_weighted(
        self, db: asyncpg.Connection, post_ids: list[UUID],
    ) -> None:
        """Mark post embeddings as using the weighted strategy."""
        if post_ids:
            await db.execute(
                """
                UPDATE post_embeddings
                SET embedding_strategy = 'weighted'
                WHERE post_id = ANY($1::uuid[])
                """,
                post_ids,
            )
