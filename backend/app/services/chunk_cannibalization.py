"""Chunk-level cannibalization detection.

Compares content chunks across posts to find section-level overlap.
More precise than whole-post similarity — catches cases like
"Post A's 'Pricing' section says the same thing as Post B's 'Cost' section."
"""

from __future__ import annotations

import asyncpg
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

CHUNK_SIMILARITY_THRESHOLD = 0.85


async def detect_chunk_overlap(
    db: asyncpg.Connection,
    post_a_id: UUID,
    post_b_id: UUID,
    threshold: float = CHUNK_SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Find overlapping chunks between two posts using pgvector cosine.

    Returns list of chunk pairs with similarity > threshold.
    """
    pairs = await db.fetch("""
        SELECT ca.id as chunk_a_id, cb.id as chunk_b_id,
               ca.heading as heading_a, cb.heading as heading_b,
               ca.chunk_index as idx_a, cb.chunk_index as idx_b,
               1 - (cea.embedding <=> ceb.embedding) as similarity
        FROM content_chunks ca
        JOIN chunk_embeddings cea ON ca.id = cea.chunk_id
        JOIN content_chunks cb ON cb.post_id = $2
        JOIN chunk_embeddings ceb ON cb.id = ceb.chunk_id
        WHERE ca.post_id = $1
          AND 1 - (cea.embedding <=> ceb.embedding) > $3
        ORDER BY similarity DESC
        LIMIT 10
    """, post_a_id, post_b_id, threshold)

    return [
        {
            "heading_a": r["heading_a"] or f"Section {r['idx_a']}",
            "heading_b": r["heading_b"] or f"Section {r['idx_b']}",
            "similarity": float(r["similarity"]),
        }
        for r in pairs
    ]


async def detect_chunk_cannibalization_for_site(
    db: asyncpg.Connection,
    site_id: UUID,
    max_pairs: int = 100,
    threshold: float = CHUNK_SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Find section-level overlap across all post pairs in a site.

    Only checks pairs already flagged as cannibalization pairs (post-level).
    Returns enriched data with specific section overlaps.
    """
    # Get existing cannibalization pairs
    pairs = await db.fetch("""
        SELECT cp.post_a_id, cp.post_b_id,
               pa.title as title_a, pb.title as title_b,
               cp.cosine_similarity
        FROM cannibalization_pairs cp
        JOIN posts pa ON cp.post_a_id = pa.id
        JOIN posts pb ON cp.post_b_id = pb.id
        WHERE pa.site_id = $1
        ORDER BY cp.cosine_similarity DESC
        LIMIT $2
    """, site_id, max_pairs)

    results = []
    for pair in pairs:
        chunk_overlaps = await detect_chunk_overlap(
            db, pair["post_a_id"], pair["post_b_id"], threshold,
        )
        if chunk_overlaps:
            results.append({
                "post_a": pair["title_a"],
                "post_b": pair["title_b"],
                "post_similarity": float(pair["cosine_similarity"]),
                "overlapping_sections": chunk_overlaps,
            })

    logger.info(
        "Chunk cannibalization: found %d pairs with section-level overlap (site %s)",
        len(results), site_id,
    )
    return results
