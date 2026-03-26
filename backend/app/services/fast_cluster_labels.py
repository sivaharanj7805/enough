"""Tier 1 fast cluster labeling — zero Claude API calls.

Uses TF-IDF to extract distinguishing terms from each cluster,
then generates a readable label from the top terms.

Domain-adaptive: auto-detects site-common words (e.g. "seo" on an SEO blog)
and filters them so labels reflect what makes each cluster DIFFERENT,
not what the whole site is about.
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

# Format words describe article type, not topic. Filter from labels.
_FORMAT_WORDS = frozenset({
    "definitive", "complete", "ultimate", "comprehensive", "step",
    "guide", "beginner", "beginners", "advanced", "simple",
    "easy", "quick", "proven", "essential", "actionable",
    "powerful", "effective", "practical", "updated", "review",
    "checklist", "template", "templates", "roundup", "list",
    "resource", "resources", "tutorial", "overview", "introduction",
    "explained", "basics", "fundamental", "fundamentals",
    "key", "important", "incredible", "awesome",
})

_WORD_RE = re.compile(r"[a-z]{3,}")


def _tokenize(text: str) -> list[str]:
    """Extract lowercase words, filter stop words."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS]


def _compute_site_stops(all_titles: list[str], top_n: int = 15) -> frozenset[str]:
    """Compute the top-N most frequent words across all titles for a site.

    These are the site's vocabulary baseline — words that appear so often
    across titles that they don't differentiate clusters. For an SEO blog,
    this auto-filters "seo", "content", "marketing", "search", etc.
    """
    doc_freq: Counter = Counter()
    for t in all_titles:
        # Count document frequency (unique words per title)
        doc_freq.update(set(_tokenize(t)))
    n_docs = len(all_titles) or 1
    # Words appearing in >40% of titles are site-level vocabulary, not cluster signals
    threshold = n_docs * 0.4
    site_common = frozenset(w for w, count in doc_freq.items() if count >= threshold)
    # Also take top_n most frequent as a fallback for small sites
    top = frozenset(w for w, _ in doc_freq.most_common(top_n))
    return site_common | top


def _tfidf_label(
    cluster_titles: list[str],
    all_titles: list[str],
    site_stops: frozenset[str] = frozenset(),
    top_n: int = 3,
) -> str:
    """Generate a readable topic label from TF-IDF top terms.

    Filters out format words ("definitive", "guide") and site-common words
    ("seo", "content" on an SEO blog) so labels reflect the cluster's
    distinguishing topic, not the site's domain or article format.
    """
    noise = _FORMAT_WORDS | site_stops

    cluster_words = []
    for t in cluster_titles:
        cluster_words.extend(_tokenize(t))

    if not cluster_words:
        return "Miscellaneous"

    # Term frequency in cluster
    cluster_tf = Counter(cluster_words)
    total_cluster = len(cluster_words)

    # Document frequency across all titles
    doc_freq: Counter = Counter()
    for t in all_titles:
        doc_freq.update(set(_tokenize(t)))
    n_docs = len(all_titles) or 1

    # TF-IDF scores, filtering noise
    scores = {}
    for word, count in cluster_tf.items():
        if word in noise:
            continue
        tf = count / total_cluster
        idf = np.log(n_docs / (1 + doc_freq.get(word, 0)))
        scores[word] = tf * idf

    if not scores:
        # All words were filtered — fall back to most frequent non-stop word
        fallback = [w for w in cluster_words if w not in _STOP_WORDS and w not in _FORMAT_WORDS]
        if fallback:
            return Counter(fallback).most_common(1)[0][0].title()
        return "General Content"

    # Top terms
    top = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
    terms = [t[0].title() for t in top]

    if not terms:
        return "General Content"

    # Build label: "Term1 & Term2" or "Term1, Term2 & Term3"
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} & {terms[1]}"
    return f"{terms[0]}, {terms[1]} & {terms[2]}"


async def label_clusters_fast(db: asyncpg.Connection, site_id: UUID) -> int:
    """Label all clusters using TF-IDF — no API calls.

    Returns number of clusters labeled.
    """
    # Get all post titles for corpus
    all_titles = await db.fetch(
        "SELECT title FROM posts WHERE site_id = $1", site_id,
    )
    all_title_list = [r["title"] or "" for r in all_titles]

    # Compute site-adaptive stop words once
    site_stops = _compute_site_stops(all_title_list)

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

        label = _tfidf_label(cluster_titles, all_title_list, site_stops=site_stops)

        await db.execute(
            "UPDATE clusters SET label = $1 WHERE id = $2",
            label, cluster["id"],
        )
        labeled += 1
        logger.debug("Cluster %s (%d posts) → %s", cluster["id"], cluster["post_count"], label)

    logger.info("Fast cluster labeling: %d clusters labeled for site %s", labeled, site_id)
    return labeled
