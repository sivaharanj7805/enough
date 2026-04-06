"""Chunk-level cannibalization confirmation.

For existing post-level cannibalization pairs, confirms or denies overlap
using H2/H3-split chunk embeddings. Catches section-level overlap that
post-level similarity misses.

Memory-efficient: processes chunks sequentially, ~5K total for 958 posts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from uuid import UUID

import asyncpg
import numpy as np
import openai

from app.utils.llm_cost import log_llm_usage

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
CHUNK_OVERLAP_THRESHOLD = 0.88  # Chunk-level similarity above this = confirmed overlap


def split_into_chunks(body_html: str, title: str) -> list[str]:
    """Split post into H2/H3 sections. Returns list of text chunks.

    Includes a sanity check: if the page has < 300 words but produces > 5
    chunks, it's likely a homepage or index page with blog roll H2s — fall
    back to a single chunk to avoid junk comparisons.
    """
    if not body_html:
        return [title] if title else []

    # Remove script/style tags
    clean = re.sub(r"<script[^>]*>.*?</script>", "", body_html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)

    # Compute word count from stripped text for sanity check
    full_text = re.sub(r"<[^>]+>", " ", clean)
    full_text = re.sub(r"\s+", " ", full_text).strip()
    word_count = len(full_text.split())

    # Find H2/H3 boundaries
    heading_pattern = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.IGNORECASE | re.DOTALL)
    headings = [(m.start(), re.sub(r"<[^>]+>", "", m.group(1)).strip()) for m in heading_pattern.finditer(clean)]

    if not headings:
        # No headings — treat whole post as one chunk
        return [f"{title}: {full_text[:800]}"] if full_text else [title]

    # Sanity check: short page with many headings = homepage/index with blog roll
    # Fall back to single chunk to avoid 12+ junk chunks from listing H2s
    if word_count < 300 and len(headings) > 5:
        logger.debug(
            "Sanity check: %d words but %d headings — falling back to single chunk for '%s'",
            word_count, len(headings), title[:50],
        )
        return [f"{title}: {full_text[:800]}"] if full_text else [title]

    chunks = []
    # First chunk: intro (content before first heading)
    intro_end = headings[0][0]
    intro_html = clean[:intro_end]
    intro_text = re.sub(r"<[^>]+>", " ", intro_html)
    intro_text = re.sub(r"\s+", " ", intro_text).strip()
    if len(intro_text) > 100:
        chunks.append(f"{title} [intro]: {intro_text[:600]}")

    # Section chunks
    for i, (heading_pos, heading_text) in enumerate(headings):
        # Content from this heading to the next (or end)
        next_pos = headings[i + 1][0] if i + 1 < len(headings) else len(clean)
        # Find the heading tag end
        tag_end = clean.find(">", heading_pos) + 1
        section_html = clean[tag_end:next_pos]
        section_text = re.sub(r"<[^>]+>", " ", section_html)
        section_text = re.sub(r"\s+", " ", section_text).strip()

        if len(section_text) > 80:
            chunk_text = f"{heading_text}: {section_text[:700]}"
            chunks.append(chunk_text)

    return chunks if chunks else [title]


async def embed_chunks(texts: list[str], client: openai.AsyncOpenAI) -> tuple[list[list[float]], int]:
    """Embed a list of text chunks. Returns (embeddings, total_tokens)."""
    if not texts:
        return [], 0
    resp = await client.embeddings.create(
        model=EMBED_MODEL,
        input=[t[:1000] for t in texts],  # cap per chunk
    )
    return [item.embedding for item in resp.data], resp.usage.total_tokens


async def confirm_chunk_overlap(
    db: asyncpg.Connection,
    site_id: UUID,
    pair_limit: int = 200,
) -> dict:
    """
    For existing cannibalization pairs, check chunk-level overlap to confirm/deny.

    Returns stats dict. Updates cannibalization_pairs with chunk_overlap_confirmed field.
    """
    # Check if chunk_overlap_confirmed column exists
    try:
        await db.execute(
            "ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_overlap_confirmed BOOLEAN"
        )
        await db.execute(
            "ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_similarity FLOAT"
        )
    except Exception as e:
        logger.warning("Column add: %s", e)

    # Check if the site has body_html data (skip_body mode detection)
    body_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM posts p
        WHERE p.site_id = $1 AND p.body_html IS NOT NULL AND LENGTH(p.body_html) > 100
        """,
        site_id,
    )
    if not body_count or body_count == 0:
        logger.warning(
            "Site %s has no body_html data — skipping chunk confirmation "
            "(likely crawled with skip_body=True)",
            site_id,
        )
        return {"confirmed": 0, "denied": 0, "skipped": 0, "message": "No body_html — skip_body mode detected"}

    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Get unconfirmed cann pairs for this site
    pairs = await db.fetch("""
        SELECT cp.id, cp.post_a_id, cp.post_b_id, cp.cosine_similarity
        FROM cannibalization_pairs cp
        JOIN clusters cl ON cl.id = cp.cluster_id
        WHERE cl.site_id = $1
          AND cp.chunk_overlap_confirmed IS NULL
          AND cp.cosine_similarity >= 0.75
        ORDER BY cp.cosine_similarity DESC
        LIMIT $2
    """, site_id, pair_limit)

    if not pairs:
        return {"confirmed": 0, "denied": 0, "skipped": 0, "message": "No pairs to check"}

    logger.info("Checking chunk-level overlap for %d pairs", len(pairs))
    t0 = time.time()
    confirmed = 0
    denied = 0
    errors = 0

    for pair in pairs:
        try:
            # Fetch both posts' HTML
            post_a = await db.fetchrow(
                "SELECT title, body_html FROM posts WHERE id = $1", pair["post_a_id"]
            )
            post_b = await db.fetchrow(
                "SELECT title, body_html FROM posts WHERE id = $1", pair["post_b_id"]
            )

            if not post_a or not post_b:
                continue

            chunks_a = split_into_chunks(post_a["body_html"] or "", post_a["title"] or "")
            chunks_b = split_into_chunks(post_b["body_html"] or "", post_b["title"] or "")

            if not chunks_a or not chunks_b:
                continue

            # Embed all chunks for both posts in one batch
            all_chunks = chunks_a + chunks_b
            embeddings, tokens_used = await embed_chunks(all_chunks, client)
            await log_llm_usage(
                db, site_id=site_id, service="chunk_cannibalization",
                model=EMBED_MODEL, input_tokens=tokens_used,
            )

            emb_a = np.array(embeddings[:len(chunks_a)])
            emb_b = np.array(embeddings[len(chunks_a):])

            # Normalize
            emb_a = emb_a / (np.linalg.norm(emb_a, axis=1, keepdims=True) + 1e-9)
            emb_b = emb_b / (np.linalg.norm(emb_b, axis=1, keepdims=True) + 1e-9)

            # Max pairwise similarity
            sim_matrix = emb_a @ emb_b.T
            max_chunk_sim = float(sim_matrix.max())

            is_confirmed = max_chunk_sim >= CHUNK_OVERLAP_THRESHOLD

            await db.execute("""
                UPDATE cannibalization_pairs
                SET chunk_overlap_confirmed = $1, chunk_similarity = $2
                WHERE id = $3
            """, is_confirmed, max_chunk_sim, pair["id"])

            if is_confirmed:
                confirmed += 1
            else:
                denied += 1

            await asyncio.sleep(0.1)  # Rate limit

        except Exception as e:
            logger.error("Chunk check failed for pair %s: %s", pair["id"], e)
            errors += 1

    elapsed = time.time() - t0
    logger.info(
        "Chunk confirmation done in %.1fs: confirmed=%d, denied=%d, errors=%d",
        elapsed, confirmed, denied, errors
    )
    return {
        "confirmed": confirmed,
        "denied": denied,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "pairs_checked": len(pairs),
    }
