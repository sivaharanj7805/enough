"""Tier 1 fast cluster labeling — zero Claude API calls.

Uses TF-IDF to extract distinguishing terms from each cluster,
then generates a readable label from the top terms.
"""

import logging
import re
from collections import Counter
from uuid import UUID

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "you", "your", "we", "our", "they",
    "their", "how", "what", "when", "where", "why", "which", "who",
    "more", "most", "very", "just", "also", "than", "then", "about",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "each", "every", "all", "both", "few", "some", "any",
    "other", "new", "one", "two", "first", "last", "many", "much",
    "get", "got", "use", "make", "like", "need", "want", "know",
    "think", "come", "take", "see", "look", "find", "give", "tell",
    "work", "way", "even", "well", "back", "only", "still", "here",
    "there", "not", "no", "so", "up", "out", "if", "my", "me", "him",
    "her", "them", "us", "she", "he", "as", "his",
})

_WORD_RE = re.compile(r"[a-z]{3,}")


def _tokenize(text: str) -> list[str]:
    """Extract lowercase words, filter stop words."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS]


def _tfidf_label(cluster_titles: list[str], all_titles: list[str], top_n: int = 3) -> str:
    """Generate a label from TF-IDF top terms of cluster vs corpus."""
    cluster_words = []
    for t in cluster_titles:
        cluster_words.extend(_tokenize(t))

    corpus_words = []
    for t in all_titles:
        corpus_words.extend(_tokenize(t))

    if not cluster_words:
        return "Miscellaneous"

    # Term frequency in cluster
    cluster_tf = Counter(cluster_words)
    total_cluster = len(cluster_words)

    # Document frequency across all titles
    doc_freq = Counter()
    for t in all_titles:
        doc_freq.update(set(_tokenize(t)))
    n_docs = len(all_titles) or 1

    # TF-IDF scores
    scores = {}
    for word, count in cluster_tf.items():
        tf = count / total_cluster
        idf = np.log(n_docs / (1 + doc_freq.get(word, 0)))
        scores[word] = tf * idf

    # Top terms
    top = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
    terms = [t[0].title() for t in top]

    if not terms:
        return "General Content"

    return " & ".join(terms[:2]) + (f" ({terms[2]})" if len(terms) > 2 else "")


async def label_clusters_fast(db: asyncpg.Connection, site_id: UUID) -> int:
    """Label all clusters using TF-IDF — no API calls.
    
    Returns number of clusters labeled.
    """
    # Get all post titles for corpus
    all_titles = await db.fetch(
        "SELECT title FROM posts WHERE site_id = $1", site_id,
    )
    all_title_list = [r["title"] or "" for r in all_titles]

    # Get clusters with their posts
    clusters = await db.fetch(
        "SELECT id, post_count FROM clusters WHERE site_id = $1",
        site_id,
    )

    labeled = 0
    for cluster in clusters:
        # Get titles for this cluster
        titles = await db.fetch("""
            SELECT p.title FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            WHERE pc.cluster_id = $1
        """, cluster["id"])
        cluster_titles = [t["title"] or "" for t in titles]

        label = _tfidf_label(cluster_titles, all_title_list)

        await db.execute(
            "UPDATE clusters SET label = $1 WHERE id = $2",
            label, cluster["id"],
        )
        labeled += 1
        logger.debug("Cluster %s (%d posts) → %s", cluster["id"], cluster["post_count"], label)

    logger.info("Fast cluster labeling: %d clusters labeled for site %s", labeled, site_id)
    return labeled
