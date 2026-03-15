"""BM25 keyword overlap signal for cannibalization detection.

Completes the triple-signal approach:
1. Cosine similarity on embeddings → semantic overlap
2. GSC query overlap (Jaccard) → ranking overlap
3. BM25 keyword overlap → exact keyword match overlap

Fusion: Reciprocal Rank Fusion (RRF) with k=60 combines all three
signals without requiring score normalization.

A pair must score high on at least 2 of 3 signals to be flagged
as true cannibalization. This triangulation eliminates false positives.
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

import asyncpg
import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# RRF parameter — standard value, no tuning needed
RRF_K = 60

# Minimum BM25 score to consider as keyword overlap
BM25_THRESHOLD = 5.0


@dataclass
class TripleSignalScore:
    """Combined cannibalization score from 3 signals."""
    post_a_id: UUID
    post_b_id: UUID
    cosine_score: float       # 0-1, from embeddings
    jaccard_score: float      # 0-1, from GSC query overlap
    bm25_score: float         # Raw BM25, higher = more keyword overlap
    rrf_score: float          # Combined RRF score
    signals_triggered: int    # How many of the 3 signals exceeded threshold
    severity: str             # critical/high/medium/low


def tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, remove punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = text.split()
    # Remove very short tokens and common stop words
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'can', 'shall',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'out', 'off', 'over', 'under', 'again',
        'further', 'then', 'once', 'here', 'there', 'when', 'where',
        'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'just', 'because',
        'but', 'and', 'or', 'if', 'while', 'about', 'up', 'it', 'its',
        'this', 'that', 'these', 'those', 'what', 'which', 'who',
        'whom', 'your', 'you', 'we', 'they', 'he', 'she', 'i', 'me',
        'my', 'our', 'their', 'his', 'her',
    }
    return [t for t in tokens if len(t) > 2 and t not in stop_words]


def compute_bm25_pairwise(
    post_ids: list[UUID],
    post_texts: dict[UUID, str],
) -> dict[tuple[UUID, UUID], float]:
    """Compute BM25 scores between all pairs of posts.

    For each pair (A, B):
    - Use A as the "query" against corpus excluding A
    - Use B as the "query" against corpus excluding B
    - Take the average of both scores for the pair

    Returns: {(post_a, post_b): bm25_score}
    """
    if len(post_ids) < 2:
        return {}

    # Tokenize all posts
    tokenized = {pid: tokenize(post_texts.get(pid, "")) for pid in post_ids}

    # Build BM25 index from all posts
    corpus = [tokenized[pid] for pid in post_ids]
    bm25 = BM25Okapi(corpus)

    scores: dict[tuple[UUID, UUID], float] = {}

    for i, pid_a in enumerate(post_ids):
        # Query BM25 with post A's tokens
        query_tokens = tokenized[pid_a]
        if not query_tokens:
            continue

        doc_scores = bm25.get_scores(query_tokens)

        for j in range(i + 1, len(post_ids)):
            pid_b = post_ids[j]
            # Score of post B when queried with post A's content
            score_ab = float(doc_scores[j])

            # Also query with B against A
            query_tokens_b = tokenized[pid_b]
            if query_tokens_b:
                doc_scores_b = bm25.get_scores(query_tokens_b)
                score_ba = float(doc_scores_b[i])
            else:
                score_ba = 0.0

            # Average both directions
            avg_score = (score_ab + score_ba) / 2.0
            scores[(pid_a, pid_b)] = avg_score

    return scores


def reciprocal_rank_fusion(
    cosine_ranks: dict[tuple[UUID, UUID], int],
    jaccard_ranks: dict[tuple[UUID, UUID], int],
    bm25_ranks: dict[tuple[UUID, UUID], int],
    k: int = RRF_K,
) -> dict[tuple[UUID, UUID], float]:
    """Combine three ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank_i)) for each signal.
    No score normalization needed. Resilient to scale differences.
    """
    all_pairs = set(cosine_ranks.keys()) | set(jaccard_ranks.keys()) | set(bm25_ranks.keys())
    max_rank = len(all_pairs) + 1  # Default rank for missing pairs

    rrf_scores = {}
    for pair in all_pairs:
        score = 0.0
        score += 1.0 / (k + cosine_ranks.get(pair, max_rank))
        score += 1.0 / (k + jaccard_ranks.get(pair, max_rank))
        score += 1.0 / (k + bm25_ranks.get(pair, max_rank))
        rrf_scores[pair] = score

    return rrf_scores


def classify_triple_signal(
    cosine_score: float,
    jaccard_score: float,
    bm25_score: float,
    cosine_threshold: float = 0.40,
    jaccard_threshold: float = 0.10,
    bm25_threshold: float = BM25_THRESHOLD,
) -> tuple[int, str]:
    """Classify cannibalization severity based on how many signals trigger.

    Returns (signals_triggered, severity).
    """
    signals = 0
    if cosine_score >= cosine_threshold:
        signals += 1
    if jaccard_score >= jaccard_threshold:
        signals += 1
    if bm25_score >= bm25_threshold:
        signals += 1

    if signals >= 3:
        severity = "critical"
    elif signals == 2:
        severity = "high"
    elif signals == 1:
        severity = "medium"
    else:
        severity = "low"

    return signals, severity


async def compute_bm25_for_cluster(
    db: asyncpg.Connection,
    cluster_id: UUID,
) -> dict[tuple[UUID, UUID], float]:
    """Compute BM25 pairwise scores for all posts in a cluster.

    Returns: {(post_a, post_b): bm25_score}
    """
    posts = await db.fetch(
        """
        SELECT p.id, p.title, p.body_text
        FROM posts p
        JOIN post_clusters pc ON pc.post_id = p.id
        WHERE pc.cluster_id = $1
          AND p.body_text IS NOT NULL
        """,
        cluster_id,
    )

    if len(posts) < 2:
        return {}

    post_ids = [p["id"] for p in posts]
    post_texts = {
        p["id"]: (p["title"] or "") + " " + (p["body_text"] or "")
        for p in posts
    }

    return compute_bm25_pairwise(post_ids, post_texts)
