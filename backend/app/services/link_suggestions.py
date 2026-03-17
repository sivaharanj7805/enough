"""Automated internal link suggestions — actionable linking recommendations.

For each post, finds semantically similar posts in DIFFERENT clusters
that don't currently link to it. Suggests specific anchor text based
on overlapping keywords.

Strategy:
1. For Post A, find top 10 nearest neighbors by embedding similarity
2. Filter out posts already linked from Post A
3. Filter to posts in different clusters (cross-cluster links are most valuable)
4. Rank remaining by their own authority (link FROM strong posts TO weak posts)
5. Generate anchor text from overlapping keywords between the posts

Why cross-cluster links matter more:
- Same-cluster links reinforce topic signals (good but expected)
- Cross-cluster links distribute authority across the site
- They create topical bridges that help Google understand site structure
- Users discover related content they wouldn't otherwise find
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

# Configuration
MAX_SUGGESTIONS_PER_POST = 5
MIN_SIMILARITY_FOR_LINK = 0.25      # Must be somewhat related
MAX_SIMILARITY_FOR_CROSS = 0.85     # Too similar = same topic (use same-cluster links instead)
KEYWORD_OVERLAP_MIN = 2             # Need at least 2 shared keywords for anchor text


@dataclass
class LinkSuggestion:
    """A suggested internal link."""
    source_post_id: UUID          # Link FROM this post
    source_title: str
    target_post_id: UUID          # Link TO this post
    target_title: str
    target_url: str
    similarity: float             # Embedding similarity
    suggested_anchor_text: str    # What text to use for the link
    reason: str                   # Why this link helps
    source_cluster: str           # Cluster of source post
    target_cluster: str           # Cluster of target post
    priority: str                 # high/medium/low
    placement_hint: str = ""      # Where in the source post to add the link


def _find_placement_hint(source_text: str, target_keywords: list[str]) -> str:
    """Find the best paragraph in source post to place a link to target."""
    if not source_text or not target_keywords:
        return ""
    paragraphs = source_text.split("\n\n")
    best_para = ""
    best_score = 0
    for i, para in enumerate(paragraphs):
        if len(para.strip()) < 30:
            continue
        para_lower = para.lower()
        score = sum(1 for kw in target_keywords if kw in para_lower)
        if score > best_score:
            best_score = score
            best_para = para.strip()[:120]
    if best_para:
        return f"Near: \"{best_para}...\""
    return ""


def extract_keywords(text: str, top_n: int = 20) -> list[str]:
    """Extract top keywords from text using simple frequency analysis."""
    if not text:
        return []

    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    words = text.split()

    # Filter stop words and short words
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'can', 'shall', 'to', 'of',
        'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
        'through', 'during', 'before', 'after', 'about', 'up', 'it',
        'this', 'that', 'these', 'those', 'what', 'which', 'who',
        'your', 'you', 'we', 'they', 'not', 'but', 'and', 'or', 'if',
        'more', 'most', 'than', 'very', 'just', 'also', 'how', 'all',
        'each', 'every', 'some', 'such', 'like', 'make', 'use', 'get',
        'new', 'one', 'two', 'way', 'many', 'well', 'need', 'know',
    }

    filtered = [w for w in words if len(w) > 3 and w not in stop_words]
    counter = Counter(filtered)
    return [word for word, _ in counter.most_common(top_n)]


def generate_anchor_text(
    source_keywords: list[str],
    target_title: str,
    shared_keywords: list[str],
) -> str:
    """Generate natural anchor text for an internal link.

    Priority:
    1. Use a shared keyword phrase if it appears in the target title
    2. Use the most common shared keyword
    3. Fall back to a shortened version of the target title
    """
    target_lower = target_title.lower()

    # Try to find a shared keyword that appears in the target title
    for kw in shared_keywords:
        if kw in target_lower:
            # Find the phrase in the title containing this keyword
            words = target_title.split()
            for i, word in enumerate(words):
                if kw in word.lower():
                    # Take 2-4 words around the keyword
                    start = max(0, i - 1)
                    end = min(len(words), i + 3)
                    phrase = " ".join(words[start:end])
                    if 2 <= len(phrase.split()) <= 5:
                        return phrase.lower()

    # Use top shared keywords as anchor text
    if len(shared_keywords) >= 2:
        return " ".join(shared_keywords[:3])

    # Fall back to shortened title
    words = target_title.split()
    if len(words) > 5:
        return " ".join(words[:5]).lower()
    return target_title.lower()


class LinkSuggestionEngine:
    """Generates automated internal link suggestions."""

    async def generate_suggestions(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> list[LinkSuggestion]:
        """Generate internal link suggestions for all posts in a site.

        Returns a list of LinkSuggestion objects, also stores in DB
        (could be a dedicated table or returned via API).
        """
        logger.info("Generating link suggestions for site %s", site_id)

        # Load all posts with their clusters and embeddings
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.body_text,
                   pc.cluster_id,
                   c.label AS cluster_label,
                   ph.composite_score,
                   ph.internal_pagerank
            FROM posts p
            LEFT JOIN post_clusters pc ON pc.post_id = p.id
            LEFT JOIN clusters c ON c.id = pc.cluster_id
            LEFT JOIN post_health_scores ph ON ph.post_id = p.id
            WHERE p.site_id = $1
              AND p.body_text IS NOT NULL
            """,
            site_id,
        )

        if len(posts) < 3:
            return []

        # Load existing internal links
        existing_links: set[tuple[UUID, UUID]] = set()
        links = await db.fetch(
            """
            SELECT DISTINCT source_post_id, target_post_id
            FROM internal_links
            WHERE site_id = $1
            """,
            site_id,
        )
        for link in links:
            existing_links.add((link["source_post_id"], link["target_post_id"]))

        # Load embeddings
        embeddings: dict[UUID, np.ndarray] = {}
        for post in posts:
            row = await db.fetchrow(
                "SELECT embedding FROM post_embeddings WHERE post_id = $1",
                post["id"],
            )
            if row and row["embedding"]:
                emb = row["embedding"]
                if isinstance(emb, str):
                    embeddings[post["id"]] = np.array(
                        [float(x) for x in emb.strip("[]").split(",")],
                    )
                else:
                    embeddings[post["id"]] = np.array(emb)

        # Extract keywords per post
        post_keywords: dict[UUID, list[str]] = {}
        for post in posts:
            text = (post["title"] or "") + " " + (post["body_text"] or "")[:3000]
            post_keywords[post["id"]] = extract_keywords(text)

        # Build post lookup
        post_map = {p["id"]: p for p in posts}

        suggestions: list[LinkSuggestion] = []

        for post in posts:
            pid = post["id"]
            if pid not in embeddings:
                continue

            post_cluster = post["cluster_id"]
            post_emb = embeddings[pid]

            # Find nearest neighbors
            candidates = []
            for other_post in posts:
                oid = other_post["id"]
                if oid == pid or oid not in embeddings:
                    continue
                # Skip if already linked
                if (pid, oid) in existing_links:
                    continue

                sim = float(np.dot(post_emb, embeddings[oid]) / (
                    np.linalg.norm(post_emb) * np.linalg.norm(embeddings[oid]) + 1e-10
                ))

                # Filter by similarity range
                if sim < MIN_SIMILARITY_FOR_LINK or sim > MAX_SIMILARITY_FOR_CROSS:
                    continue

                # Prefer cross-cluster links
                is_cross_cluster = other_post["cluster_id"] != post_cluster
                authority = other_post["composite_score"] or 0

                candidates.append({
                    "post": other_post,
                    "similarity": sim,
                    "is_cross_cluster": is_cross_cluster,
                    "authority": authority,
                })

            # Sort: cross-cluster first, then by similarity × authority
            candidates.sort(
                key=lambda x: (
                    x["is_cross_cluster"],
                    x["similarity"] * 0.6 + (x["authority"] / 100) * 0.4,
                ),
                reverse=True,
            )

            # Ensure mix: at least 40% cross-cluster if available
            cross = [c for c in candidates if c["is_cross_cluster"]]
            within = [c for c in candidates if not c["is_cross_cluster"]]
            n = MAX_SUGGESTIONS_PER_POST
            n_cross = min(len(cross), max(2, int(n * 0.4)))
            n_within = min(len(within), n - n_cross)
            balanced = cross[:n_cross] + within[:n_within]
            # Fill remaining slots
            remaining = n - len(balanced)
            if remaining > 0:
                used_ids = {c["post"]["id"] for c in balanced}
                extra = [c for c in candidates if c["post"]["id"] not in used_ids]
                balanced.extend(extra[:remaining])

            for cand in balanced:
                other = cand["post"]

                # Find shared keywords for anchor text
                my_kw = set(post_keywords.get(pid, []))
                their_kw = set(post_keywords.get(other["id"], []))
                shared = list(my_kw & their_kw)

                anchor = generate_anchor_text(
                    list(my_kw), other["title"] or "", shared,
                )

                # Determine priority
                if cand["is_cross_cluster"] and cand["similarity"] > 0.40:
                    priority = "high"
                elif cand["is_cross_cluster"]:
                    priority = "medium"
                else:
                    priority = "low"

                # Generate reason
                if cand["is_cross_cluster"]:
                    reason = (
                        f"Cross-cluster link: connects your '{post['cluster_label'] or 'cluster'}' "
                        f"content to '{other['cluster_label'] or 'cluster'}'. "
                        f"Distributes authority and helps Google understand site topology."
                    )
                else:
                    reason = (
                        f"Same-cluster link: strengthens topical authority for "
                        f"'{post['cluster_label'] or 'cluster'}'."
                    )

                # Find best placement in source post
                target_kw = post_keywords.get(other["id"], [])[:5]
                placement = _find_placement_hint(post["body_text"] or "", target_kw)

                suggestions.append(LinkSuggestion(
                    source_post_id=pid,
                    source_title=post["title"] or "",
                    target_post_id=other["id"],
                    target_title=other["title"] or "",
                    target_url=other["url"] or "",
                    similarity=cand["similarity"],
                    suggested_anchor_text=anchor,
                    reason=reason,
                    source_cluster=post["cluster_label"] or "",
                    target_cluster=other["cluster_label"] or "",
                    priority=priority,
                    placement_hint=placement,
                ))

        # Flag circular link suggestions (A→B→C→A)
        try:
            import networkx as nx
            G = nx.DiGraph()
            # Add existing links
            for src, tgt in existing_links:
                G.add_edge(str(src), str(tgt))
            # Add suggested links and check for short cycles
            flagged = 0
            for s in suggestions:
                G.add_edge(str(s.source_post_id), str(s.target_post_id))
                # Check if this creates a short cycle
                try:
                    cycle = nx.shortest_path(G, str(s.target_post_id), str(s.source_post_id))
                    if len(cycle) <= 3:
                        s.reason += " ⚠️ Creates circular link path."
                        flagged += 1
                except nx.NetworkXNoPath:
                    pass
            if flagged:
                logger.info("Flagged %d suggestions that create circular paths", flagged)
        except ImportError:
            pass

        logger.info("Generated %d link suggestions for site %s",
                     len(suggestions), site_id)
        return suggestions
