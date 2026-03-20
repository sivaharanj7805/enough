"""RAG context retrieval for recommendations and content briefs.

Assembles relevant context from the user's own blog data before sending
to Claude. This is what makes recommendations impossibly specific —
they reference the user's own top performers, cluster patterns, and
internal link graph.

Queries:
1. pgvector: semantically similar posts
2. DB: top-performing posts in the same cluster
3. DB: cannibalization pairs involving this post
4. DB: posts linking TO this post (inbound context)
5. DB: cluster-level stats (avg word count, avg health, top keywords)
"""

import json
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def get_recommendation_context(
    db: asyncpg.Connection,
    site_id: UUID,
    post_id: UUID,
) -> dict:
    """Assemble RAG context for a single post's recommendation.

    Returns a dict with all retrieved context, ready to be formatted
    into a Claude prompt.
    """
    context: dict = {}

    # 1. Similar posts via pgvector
    context["similar_posts"] = await _get_similar_posts(db, site_id, post_id)

    # 2. Top performers in the same cluster
    context["cluster_top_posts"] = await _get_cluster_top_posts(db, post_id)

    # 3. Cluster stats
    context["cluster_stats"] = await _get_cluster_stats(db, post_id)

    # 4. Cannibalization pairs
    context["cannibalization_pairs"] = await _get_cannibalization_pairs(db, post_id)

    # 5. Inbound link context (what posts link TO this post)
    context["inbound_links"] = await _get_inbound_links(db, site_id, post_id)

    return context


async def get_brief_context(
    db: asyncpg.Connection,
    site_id: UUID,
    topic_embedding: str,
    target_keyword: str,
) -> dict:
    """Assemble RAG context for content brief generation.

    Args:
        db: Database connection.
        site_id: Site to analyze.
        topic_embedding: pgvector string for the topic embedding.
        target_keyword: The topic/keyword for the new post.

    Returns a dict with cannibalization pre-check, cluster context,
    internal link planning data, and gap analysis.
    """
    context: dict = {}

    # 1. Cannibalization pre-check — find similar existing posts
    context["similar_existing"] = await _find_similar_by_embedding(
        db, site_id, topic_embedding, limit=10,
    )

    # 2. Determine cannibalization risk
    max_similarity = 0.0
    for p in context["similar_existing"]:
        sim = p.get("similarity", 0)
        if sim > max_similarity:
            max_similarity = sim

    if max_similarity >= 0.80:
        context["cannibalization_risk"] = "high"
        context["risk_message"] = (
            f"WARNING: You already have a post that's {max_similarity:.0%} similar. "
            f"Consider updating '{context['similar_existing'][0]['title']}' instead."
        )
    elif max_similarity >= 0.50:
        context["cannibalization_risk"] = "medium"
        context["risk_message"] = (
            f"Related posts exist ({max_similarity:.0%} similar). "
            "The brief will differentiate from existing content."
        )
    else:
        context["cannibalization_risk"] = "low"
        context["risk_message"] = "No significant overlap with existing content."

    # 3. Nearest cluster context
    context["nearest_cluster"] = await _get_nearest_cluster(
        db, site_id, topic_embedding,
    )

    # 4. Cluster posts with stats (what works in this cluster)
    if context["nearest_cluster"]:
        cluster_id = context["nearest_cluster"]["id"]
        context["cluster_posts"] = await _get_cluster_posts_for_brief(
            db, cluster_id,
        )
        context["cluster_stats"] = await _get_cluster_stats_by_id(
            db, cluster_id,
        )
    else:
        context["cluster_posts"] = []
        context["cluster_stats"] = {}

    # 5. Internal link planning
    context["link_candidates"] = await _get_link_candidates(
        db, site_id, topic_embedding,
    )

    # 6. GSC keyword data for the topic
    context["existing_rankings"] = await _get_keyword_rankings(
        db, site_id, target_keyword,
    )

    return context


def format_recommendation_context(context: dict) -> str:
    """Format RAG context into a structured text block for Claude prompts."""
    parts: list[str] = []

    # Similar posts
    similar = context.get("similar_posts", [])
    if similar:
        lines = []
        for p in similar[:5]:
            lines.append(
                f"  - \"{p['title']}\" ({p['url']}) — "
                f"{p.get('word_count', '?')} words, "
                f"health: {p.get('health_score', '?')}/100, "
                f"role: {p.get('role', '?')}"
            )
        parts.append(
            "SIMILAR POSTS ON THIS BLOG (by embedding similarity):\n"
            + "\n".join(lines)
        )

    # Cluster top performers
    top_posts = context.get("cluster_top_posts", [])
    if top_posts:
        lines = []
        for p in top_posts[:3]:
            lines.append(
                f"  - \"{p['title']}\" — "
                f"{p.get('word_count', '?')} words, "
                f"health: {p.get('health_score', '?')}/100"
            )
        parts.append(
            "TOP PERFORMERS IN THIS CLUSTER (benchmark for quality):\n"
            + "\n".join(lines)
        )

    # Cluster stats
    stats = context.get("cluster_stats", {})
    if stats:
        parts.append(
            f"CLUSTER BENCHMARKS:\n"
            f"  - Average word count: {stats.get('avg_word_count', '?')}\n"
            f"  - Average health score: {stats.get('avg_health_score', '?')}\n"
            f"  - Post count: {stats.get('post_count', '?')}\n"
            f"  - Cluster label: {stats.get('label', '?')}\n"
            f"  - Ecosystem state: {stats.get('ecosystem_state', '?')}"
        )

    # Cannibalization pairs
    cann = context.get("cannibalization_pairs", [])
    if cann:
        lines = []
        for pair in cann[:3]:
            lines.append(
                f"  - Overlaps with \"{pair['other_title']}\" "
                f"(similarity: {pair.get('similarity', '?')}, "
                f"shared queries: {', '.join(pair.get('queries', [])[:3])})"
            )
        parts.append("CANNIBALIZATION PAIRS:\n" + "\n".join(lines))

    # Inbound links
    inbound = context.get("inbound_links", [])
    if inbound:
        lines = []
        for link in inbound[:5]:
            lines.append(
                f"  - \"{link['source_title']}\" links here "
                f"with anchor: \"{link.get('anchor_text', '?')}\""
            )
        parts.append(
            "POSTS LINKING TO THIS POST (what referrers expect):\n"
            + "\n".join(lines)
        )

    return "\n\n".join(parts) if parts else "(No additional context available)"


def format_brief_context(context: dict) -> str:
    """Format RAG context into a structured text block for brief generation."""
    parts: list[str] = []

    # Cannibalization risk
    risk = context.get("cannibalization_risk", "unknown")
    risk_msg = context.get("risk_message", "")
    parts.append(f"CANNIBALIZATION RISK: {risk.upper()}\n  {risk_msg}")

    # Similar existing posts
    similar = context.get("similar_existing", [])
    if similar:
        lines = []
        for p in similar[:5]:
            lines.append(
                f"  - \"{p['title']}\" ({p['url']}) — "
                f"{p.get('word_count', '?')} words, "
                f"health: {p.get('health_score', '?')}/100, "
                f"similarity: {p.get('similarity', 0):.0%}"
            )
        parts.append(
            "EXISTING SIMILAR POSTS (avoid overlap with these):\n"
            + "\n".join(lines)
        )

    # Cluster context
    cluster = context.get("nearest_cluster", {})
    stats = context.get("cluster_stats", {})
    if cluster:
        parts.append(
            f"TARGET CLUSTER: \"{cluster.get('label', '?')}\" "
            f"(state: {cluster.get('ecosystem_state', '?')})\n"
            f"  - Avg word count: {stats.get('avg_word_count', '?')}\n"
            f"  - Avg health score: {stats.get('avg_health_score', '?')}\n"
            f"  - Posts in cluster: {stats.get('post_count', '?')}"
        )

    # What works in this cluster
    cluster_posts = context.get("cluster_posts", [])
    if cluster_posts:
        lines = []
        for p in cluster_posts[:5]:
            lines.append(
                f"  - \"{p['title']}\" — "
                f"{p.get('word_count', '?')} words, "
                f"health: {p.get('health_score', '?')}/100"
            )
        parts.append(
            "TOP POSTS IN THIS CLUSTER (what works here):\n"
            + "\n".join(lines)
        )

    # Internal link candidates
    links = context.get("link_candidates", [])
    if links:
        to_lines = []
        from_lines = []
        for link in links[:8]:
            entry = f"  - \"{link['title']}\" ({link['url']})"
            if link.get("direction") == "from":
                from_lines.append(entry)
            else:
                to_lines.append(entry)
        if to_lines:
            parts.append(
                "POSTS THIS NEW POST SHOULD LINK TO:\n" + "\n".join(to_lines[:4])
            )
        if from_lines:
            parts.append(
                "POSTS THAT SHOULD LINK TO THIS NEW POST:\n"
                + "\n".join(from_lines[:4])
            )

    # Existing keyword rankings
    rankings = context.get("existing_rankings", [])
    if rankings:
        lines = []
        for r in rankings[:5]:
            lines.append(
                f"  - \"{r['query']}\" — "
                f"post: \"{r['title']}\", "
                f"position: {r.get('avg_position', '?')}, "
                f"clicks: {r.get('clicks', '?')}"
            )
        parts.append(
            "EXISTING RANKINGS FOR THIS KEYWORD:\n" + "\n".join(lines)
        )

    return "\n\n".join(parts) if parts else "(No context available)"


# ── Private retrieval functions ────────────────────────────────────────────────


async def _get_similar_posts(
    db: asyncpg.Connection, site_id: UUID, post_id: UUID, limit: int = 5,
) -> list[dict]:
    """Find semantically similar posts via pgvector."""
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url, p.word_count,
               phs.composite_score AS health_score,
               phs.role,
               1 - (pe2.embedding <=> pe1.embedding) AS similarity
        FROM post_embeddings pe1
        JOIN post_embeddings pe2 ON pe2.post_id != pe1.post_id
        JOIN posts p ON p.id = pe2.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE pe1.post_id = $1
          AND p.site_id = $2
        ORDER BY pe2.embedding <=> pe1.embedding
        LIMIT $3
        """,
        post_id, site_id, limit,
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "health_score": round(float(r["health_score"]), 1) if r["health_score"] else None,
            "role": r["role"],
            "similarity": round(float(r["similarity"]), 3),
        }
        for r in rows
    ]


async def _get_cluster_top_posts(
    db: asyncpg.Connection, post_id: UUID, limit: int = 3,
) -> list[dict]:
    """Get the highest health-scored posts in the same cluster."""
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url, p.word_count,
               phs.composite_score AS health_score,
               phs.role
        FROM post_clusters pc1
        JOIN post_clusters pc2 ON pc1.cluster_id = pc2.cluster_id
        JOIN posts p ON p.id = pc2.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE pc1.post_id = $1
          AND pc2.post_id != $1
        ORDER BY phs.composite_score DESC NULLS LAST
        LIMIT $2
        """,
        post_id, limit,
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "health_score": round(float(r["health_score"]), 1) if r["health_score"] else None,
            "role": r["role"],
        }
        for r in rows
    ]


async def _get_cluster_stats(db: asyncpg.Connection, post_id: UUID) -> dict:
    """Get cluster-level statistics for the post's cluster."""
    row = await db.fetchrow(
        """
        SELECT c.id, c.label, c.ecosystem_state, c.health_score,
               c.post_count,
               AVG(p.word_count) AS avg_word_count,
               AVG(phs.composite_score) AS avg_health_score
        FROM post_clusters pc
        JOIN clusters c ON c.id = pc.cluster_id
        JOIN post_clusters pc2 ON pc2.cluster_id = c.id
        JOIN posts p ON p.id = pc2.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE pc.post_id = $1
        GROUP BY c.id, c.label, c.ecosystem_state, c.health_score, c.post_count
        LIMIT 1
        """,
        post_id,
    )
    if not row:
        return {}
    return {
        "id": str(row["id"]),
        "label": row["label"],
        "ecosystem_state": row["ecosystem_state"],
        "health_score": round(float(row["health_score"]), 1) if row["health_score"] else None,
        "post_count": row["post_count"],
        "avg_word_count": int(row["avg_word_count"]) if row["avg_word_count"] else None,
        "avg_health_score": round(float(row["avg_health_score"]), 1) if row["avg_health_score"] else None,
    }


async def _get_cannibalization_pairs(
    db: asyncpg.Connection, post_id: UUID, limit: int = 3,
) -> list[dict]:
    """Get cannibalization pairs involving this post."""
    rows = await db.fetch(
        """
        SELECT
            CASE WHEN cp.post_a_id = $1 THEN pb.title ELSE pa.title END AS other_title,
            CASE WHEN cp.post_a_id = $1 THEN pb.url ELSE pa.url END AS other_url,
            cp.cosine_similarity AS similarity,
            cp.overlapping_queries AS queries
        FROM cannibalization_pairs cp
        JOIN posts pa ON pa.id = cp.post_a_id
        JOIN posts pb ON pb.id = cp.post_b_id
        WHERE cp.post_a_id = $1 OR cp.post_b_id = $1
        ORDER BY cp.cosine_similarity DESC
        LIMIT $2
        """,
        post_id, limit,
    )
    return [
        {
            "other_title": r["other_title"],
            "other_url": r["other_url"],
            "similarity": round(float(r["similarity"]), 3) if r["similarity"] else None,
            "queries": r["queries"] or [],
        }
        for r in rows
    ]


async def _get_inbound_links(
    db: asyncpg.Connection, site_id: UUID, post_id: UUID, limit: int = 5,
) -> list[dict]:
    """Get posts that link TO this post."""
    rows = await db.fetch(
        """
        SELECT p.title AS source_title, p.url AS source_url,
               il.anchor_text
        FROM internal_links il
        JOIN posts p ON p.id = il.source_post_id
        WHERE il.target_post_id = $1
          AND p.site_id = $2
        LIMIT $3
        """,
        post_id, site_id, limit,
    )
    return [
        {
            "source_title": r["source_title"],
            "source_url": r["source_url"],
            "anchor_text": r["anchor_text"] or "",
        }
        for r in rows
    ]


# ── Brief-specific retrieval functions ─────────────────────────────────────────


async def _find_similar_by_embedding(
    db: asyncpg.Connection, site_id: UUID, embedding_str: str, limit: int = 10,
) -> list[dict]:
    """Find existing posts similar to a topic embedding."""
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url, p.word_count,
               phs.composite_score AS health_score,
               phs.role,
               1 - (pe.embedding <=> $1::vector) AS similarity
        FROM post_embeddings pe
        JOIN posts p ON p.id = pe.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE p.site_id = $2
        ORDER BY pe.embedding <=> $1::vector
        LIMIT $3
        """,
        embedding_str, site_id, limit,
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "health_score": round(float(r["health_score"]), 1) if r["health_score"] else None,
            "role": r["role"],
            "similarity": round(float(r["similarity"]), 3),
        }
        for r in rows
    ]


async def _get_nearest_cluster(
    db: asyncpg.Connection, site_id: UUID, embedding_str: str,
) -> dict | None:
    """Find the cluster whose centroid is nearest to the topic embedding."""
    # Find the most similar post and use its cluster
    row = await db.fetchrow(
        """
        SELECT c.id, c.label, c.ecosystem_state, c.health_score, c.post_count
        FROM post_embeddings pe
        JOIN posts p ON p.id = pe.post_id
        JOIN post_clusters pc ON pc.post_id = p.id
        JOIN clusters c ON c.id = pc.cluster_id
        WHERE p.site_id = $1
        ORDER BY pe.embedding <=> $2::vector
        LIMIT 1
        """,
        site_id, embedding_str,
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "ecosystem_state": row["ecosystem_state"],
        "health_score": round(float(row["health_score"]), 1) if row["health_score"] else None,
        "post_count": row["post_count"],
    }


async def _get_cluster_posts_for_brief(
    db: asyncpg.Connection, cluster_id: UUID, limit: int = 10,
) -> list[dict]:
    """Get all posts in a cluster, sorted by health score."""
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url, p.word_count,
               phs.composite_score AS health_score,
               phs.role
        FROM post_clusters pc
        JOIN posts p ON p.id = pc.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE pc.cluster_id = $1
        ORDER BY phs.composite_score DESC NULLS LAST
        LIMIT $2
        """,
        cluster_id, limit,
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "health_score": round(float(r["health_score"]), 1) if r["health_score"] else None,
            "role": r["role"],
        }
        for r in rows
    ]


async def _get_cluster_stats_by_id(db: asyncpg.Connection, cluster_id: UUID) -> dict:
    """Get cluster-level statistics by cluster ID."""
    row = await db.fetchrow(
        """
        SELECT c.label, c.ecosystem_state, c.post_count,
               AVG(p.word_count) AS avg_word_count,
               AVG(phs.composite_score) AS avg_health_score
        FROM clusters c
        JOIN post_clusters pc ON pc.cluster_id = c.id
        JOIN posts p ON p.id = pc.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE c.id = $1
        GROUP BY c.label, c.ecosystem_state, c.post_count
        """,
        cluster_id,
    )
    if not row:
        return {}
    return {
        "label": row["label"],
        "ecosystem_state": row["ecosystem_state"],
        "post_count": row["post_count"],
        "avg_word_count": int(row["avg_word_count"]) if row["avg_word_count"] else None,
        "avg_health_score": round(float(row["avg_health_score"]), 1) if row["avg_health_score"] else None,
    }


async def _get_link_candidates(
    db: asyncpg.Connection, site_id: UUID, embedding_str: str, limit: int = 8,
) -> list[dict]:
    """Find posts that should link to/from the new post.

    Returns high-authority similar posts (should link TO the new post)
    and topically related posts (new post should link TO them).
    """
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url, p.word_count,
               phs.composite_score AS health_score,
               phs.role,
               phs.internal_pagerank,
               1 - (pe.embedding <=> $1::vector) AS similarity
        FROM post_embeddings pe
        JOIN posts p ON p.id = pe.post_id
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE p.site_id = $2
        ORDER BY pe.embedding <=> $1::vector
        LIMIT $3
        """,
        embedding_str, site_id, limit,
    )

    candidates = []
    for r in rows:
        pagerank = float(r["internal_pagerank"]) if r["internal_pagerank"] else 0
        # High-authority posts → should link TO this new post (from)
        # Lower-authority related posts → new post should link TO them (to)
        direction = "from" if pagerank > 0.5 else "to"
        candidates.append({
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "health_score": round(float(r["health_score"]), 1) if r["health_score"] else None,
            "similarity": round(float(r["similarity"]), 3),
            "direction": direction,
        })
    return candidates


async def _get_keyword_rankings(
    db: asyncpg.Connection, site_id: UUID, keyword: str, limit: int = 5,
) -> list[dict]:
    """Find existing posts ranking for the target keyword."""
    rows = await db.fetch(
        """
        SELECT p.id, p.title, p.url,
               g.query,
               AVG(g.avg_position) AS avg_position,
               SUM(g.clicks) AS clicks
        FROM gsc_metrics g
        JOIN posts p ON p.id = g.post_id
        WHERE p.site_id = $1
          AND g.query ILIKE $2
          AND g.date >= CURRENT_DATE - 90
        GROUP BY p.id, p.title, p.url, g.query
        ORDER BY clicks DESC
        LIMIT $3
        """,
        site_id, f"%{keyword}%", limit,
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "query": r["query"],
            "avg_position": round(float(r["avg_position"]), 1) if r["avg_position"] else None,
            "clicks": int(r["clicks"]) if r["clicks"] else 0,
        }
        for r in rows
    ]
