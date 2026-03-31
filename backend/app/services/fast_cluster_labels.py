"""Tier 1 fast cluster labeling — zero Claude API calls.

Uses TF-IDF on bigram phrases extracted from titles, body text, and H2
headings to produce readable topic labels like "Link Building", "Email
Marketing", "Ecommerce SEO" instead of word-salad like "Seo For & Step".

Multi-signal approach:
1. Extract bigrams + unigrams from titles (3x weight), H2 headings (2x),
   and first 200 words of body text (1x) after stripping format markers
2. Score with TF-IDF, filtering site-common words and format words
3. Pick the best bigram as primary label, add qualifier if needed
4. Generate a one-sentence description from remaining top unigrams
5. Validate label differentiates this cluster from others
"""

import json
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
    "whom", "whose", "thee", "thou", "thy", "whereby", "thereof",
    "whether", "whereas", "hence", "thus", "therefore", "really",
    "actually", "literally", "basically", "simply", "always", "never",
    "because", "since", "until", "unless", "although", "though",
    "while", "often", "sometimes", "usually", "already", "enough",
    "almost", "quite", "rather", "perhaps", "maybe", "sure",
    "thing", "things", "stuff", "kind", "type", "lot", "lots",
    "said", "says", "went", "going", "done", "doing",
    "let", "lets", "put", "puts", "set", "run", "say",
    "true", "real", "right", "wrong", "big", "old",
})

# Format markers to strip from titles before phrase extraction
_FORMAT_MARKERS = [
    "the definitive guide", "a complete guide", "the complete guide",
    "the ultimate guide", "a comprehensive guide", "a beginner's guide",
    "the beginner's guide", "step by step guide", "step-by-step guide",
    "a step-by-step guide", "comprehensive checklist", "quick guide",
    "an in-depth guide", "in depth guide", "the complete beginner's guide",
    "everything you need to know",
]

# Format words — describe article type, not topic
_FORMAT_WORDS = frozenset({
    "definitive", "complete", "ultimate", "comprehensive", "step",
    "guide", "beginner", "beginners", "advanced", "simple",
    "easy", "quick", "proven", "essential", "actionable",
    "powerful", "effective", "practical", "updated", "review",
    "checklist", "template", "templates", "roundup", "list",
    "resource", "resources", "tutorial", "overview", "introduction",
    "explained", "basics", "fundamental", "fundamentals",
    "key", "important", "incredible", "awesome", "ways",
    "tips", "tricks", "hacks", "secrets", "examples", "report",
    "study", "case", "results", "here", "what", "learned",
    "better", "tried", "worth", "good", "tested", "comparison",
    # Ranking/enumeration words — describe article format, not topic
    "top", "bottom", "worst", "biggest", "greatest", "number",
    "reasons", "steps", "mistake", "mistakes", "common",
    # Creative/action words that leak from individual titles, not topic themes
    "remix", "remixed", "remixes", "rewrite", "revisited",
})

_WORD_RE = re.compile(r"[a-z]{3,}")

# Known acronyms that should be uppercased, not title-cased
_ACRONYMS = frozenset({
    "seo", "sem", "ppc", "cta", "roi", "b2b", "b2c", "saas", "api",
    "html", "css", "cro", "kpi", "url", "cpc", "cpm", "ctr",
    "serp", "eeat", "llm", "ux", "ui", "smm", "pr", "roas", "lp",
})


def _smart_title(word: str) -> str:
    """Title-case a word, preserving known acronyms as uppercase."""
    if word.lower() in _ACRONYMS:
        return word.upper()
    return word.title()


# Known compound nouns that flow naturally without "&" connector
_COMPOUND_NOUNS = frozenset({
    "link building", "email marketing", "content marketing", "content strategy",
    "social media", "keyword research", "search engine", "landing page",
    "lead generation", "affiliate marketing", "influencer marketing",
    "conversion rate", "pay per", "per click", "organic traffic",
    "guest posting", "digital marketing", "technical seo", "local seo",
    "video marketing", "brand awareness", "customer acquisition",
    "growth hacking", "product launch", "market research",
    "data analysis", "machine learning", "user experience",
    "mobile optimization", "site speed", "page speed", "core web",
    "web vitals", "schema markup", "structured data", "internal linking",
})


# UI/navigation words commonly found in HTML body but not in actual content
_UI_NOISE = frozenset({
    "tweet", "share", "pin", "facebook", "twitter", "linkedin", "pinterest",
    "instagram", "reddit", "email", "print", "copy", "link", "subscribe",
    "comment", "comments", "reply", "cancel", "submit", "search", "menu",
    "close", "open", "toggle", "click", "next", "previous", "prev",
    "read", "reading", "min", "ago", "posted", "author", "written",
    "category", "categories", "tag", "tags", "related", "popular",
    "recent", "sidebar", "footer", "header", "nav", "navigation",
    "cookie", "cookies", "privacy", "policy", "terms", "login", "signup",
    "register", "password", "account", "profile", "settings", "loading",
    "advertisement", "sponsored", "affiliate", "disclosure",
    "class", "swp", "div", "span", "href", "src", "alt", "img",
    "width", "height", "style", "script", "https", "http", "www",
    "com", "org", "net", "php", "jpg", "png", "gif",
    "wordpress", "theme", "plugin", "widget", "shortcode",
    "rdf", "xml", "json", "api", "schema", "xmlns", "meta",
    "viewport", "charset", "utf", "doctype",
    "don", "didn", "doesn", "isn", "wasn", "aren", "won", "wouldn",
    "couldn", "shouldn", "hasn", "hadn", "haven", "mustn", "needn",
})


def _extract_body_phrases(
    body_html: str | None,
    headings: str | list | None,
    max_body_unigrams: int = 10,
    max_body_bigrams: int = 5,
) -> tuple[list[str], list[str]]:
    """Extract top phrases from body text and H2 headings.

    Returns (body_phrases, heading_phrases) separately so callers can
    weight them differently (body 1x, headings 2x vs title 3x).

    Body phrases are capped to the top N unigrams and M bigrams (by raw
    frequency in this post) to prevent body text from drowning out title
    and heading signals. Without capping, 200 body words produce ~350
    phrases per post vs ~7 from titles, making body 94% of the pool.
    With capping (10 uni + 5 bi = 15 per post), body is ~43% of the
    weighted pool, restoring the intended hierarchy: titles > headings > body.
    """
    body_phrases: list[str] = []
    heading_phrases: list[str] = []
    all_noise = _STOP_WORDS | _FORMAT_WORDS | _UI_NOISE

    # Extract from body text — cap to top-N by frequency to prevent dominance
    if body_html:
        text = re.sub(r"<[^>]+>", " ", body_html[:5000]).lower()
        words = [w for w in _WORD_RE.findall(text) if w not in all_noise][:200]
        # Rank unigrams and bigrams by frequency, keep top N
        uni_counts = Counter(words)
        top_unis = [w for w, _ in uni_counts.most_common(max_body_unigrams)]
        body_phrases.extend(top_unis)
        bi_list = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
        bi_counts = Counter(bi_list)
        top_bis = [b for b, _ in bi_counts.most_common(max_body_bigrams)]
        body_phrases.extend(top_bis)

    # Extract from H2+ headings
    if headings:
        h_list: list[dict] = []
        if isinstance(headings, str):
            try:
                h_list = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(headings, list):
            h_list = headings
        for h in h_list:
            if not isinstance(h, dict):
                continue
            level = h.get("level", "")
            text = h.get("text", "")
            if level in ("h2", "h3") and text:
                words = [w for w in _WORD_RE.findall(text.lower())
                         if w not in all_noise]
                heading_phrases.extend(words)
                for i in range(len(words) - 1):
                    heading_phrases.append(f"{words[i]} {words[i + 1]}")

    return body_phrases, heading_phrases


def _strip_format(title: str) -> str:
    """Strip format markers from a title, leaving the topic."""
    lower = title.lower()
    for marker in _FORMAT_MARKERS:
        lower = lower.replace(marker, " ")
    # Strip leading "How to", "What Is", "N Best/Top/Ways..."
    lower = re.sub(r"^\d+\s+(?:best|top|key|most\s+important|awesome|incredible)\s+", "", lower)
    lower = re.sub(r"^(?:how\s+to|what\s+(?:is|are)|why\s+you\s+should)\s+", "", lower)
    # Strip trailing year, site name
    lower = re.sub(r"\s*(?:in|for)\s+\d{4}\b.*$", "", lower)
    # Strip trailing subtitle/site-name after colon/dash/pipe, but only if
    # enough content remains (avoid stripping legitimate subtitle content)
    candidate = re.sub(r"\s*[-–|:].{0,30}$", "", lower)
    if len(candidate.split()) >= 3:
        lower = candidate
    return lower.strip()


def _extract_phrases(title: str) -> list[str]:
    """Extract meaningful unigrams and bigrams from a title after stripping format."""
    stripped = _strip_format(title)
    words = [w for w in _WORD_RE.findall(stripped) if w not in _STOP_WORDS and w not in _FORMAT_WORDS]

    phrases = list(words)  # unigrams
    # Bigrams from consecutive content words
    for i in range(len(words) - 1):
        phrases.append(f"{words[i]} {words[i + 1]}")
    return phrases


def _compute_site_stops(all_titles: list[str], top_n: int = 12) -> frozenset[str]:
    """Auto-detect site-common words that shouldn't appear in labels.

    Words appearing in a significant fraction of titles are site-level
    vocabulary. Threshold adapts to site size:
      < 100 posts:  15% (aggressive — small niche sites need heavy filtering)
      100-299 posts: 20% (moderate — covers most B2B content blogs)
      300+ posts:    30% (standard — large sites have enough diversity)
    """
    doc_freq: Counter = Counter()
    for t in all_titles:
        stripped = _strip_format(t)
        words = set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS
        doc_freq.update(words)
    n_docs = len(all_titles) or 1
    # Adaptive threshold based on site size
    if n_docs < 100:
        threshold = n_docs * 0.15
    elif n_docs < 300:
        threshold = n_docs * 0.20
    else:
        threshold = n_docs * 0.30
    return frozenset(w for w, count in doc_freq.items() if count >= threshold)


def _build_corpus_stats(
    all_titles: list[str],
    site_stops: frozenset[str] = frozenset(),
) -> tuple[Counter, Counter, int]:
    """Pre-compute corpus-level phrase and word frequencies for IDF.

    Returns (corpus_phrase_freq, corpus_word_freq, n_docs).
    Called once per site, shared across all cluster labeling calls.
    """
    noise = _FORMAT_WORDS | site_stops
    corpus_phrases: Counter = Counter()
    corpus_words: Counter = Counter()
    for t in all_titles:
        corpus_phrases.update(set(_extract_phrases(t)))
        stripped = _strip_format(t)
        corpus_words.update(set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS - noise)
    return corpus_phrases, corpus_words, len(all_titles) or 1


def _connect_label_parts(primary: str, qualifier: str) -> str:
    """Intelligently connect two label parts.

    Uses no connector for known compound nouns ("Content Marketing"),
    "&" for unrelated terms ("Sales & SEO"), and natural phrasing
    where possible.
    """
    # Check if these form a known compound noun in either order
    pair_lower = f"{primary.lower()} {qualifier.lower()}"
    pair_reverse = f"{qualifier.lower()} {primary.lower()}"
    if pair_lower in _COMPOUND_NOUNS:
        return f"{primary} {qualifier}"
    if pair_reverse in _COMPOUND_NOUNS:
        return f"{qualifier} {primary}"
    return f"{primary} & {qualifier}"


def _min_doc_freq(cluster_size: int) -> int:
    """Adaptive minimum document frequency for label words.

    Words must appear in at least 15% of cluster titles (minimum 2) to be
    considered topic-level vocabulary. This prevents rare words from creative
    individual titles from leaking into labels while still allowing compound
    labels for well-represented topics. E.g., for a 12-post cluster, a word
    must appear in 2+ titles; for a 20-post cluster, 3+ titles.
    """
    import math
    return max(2, math.ceil(cluster_size * 0.15))


def _validate_bigram(bigram: str, cluster_titles: list[str], min_freq: int = 2) -> bool:
    """Both words in bigram must appear in at least min_freq cluster titles.

    Uses word-level matching (not substring) to avoid false positives.
    """
    words = bigram.lower().split()
    for word in words:
        count = 0
        for t in cluster_titles:
            title_words = set(_WORD_RE.findall(t.lower())) - _STOP_WORDS - _FORMAT_WORDS
            if word in title_words:
                count += 1
        if count < min_freq:
            return False
    return True


def _is_semantic_redundant(word_a: str, word_b: str) -> bool:
    """Check if two words/phrases are semantically redundant.

    Returns True if one is a substring of the other (e.g., "copy" in "copywriting",
    "blog" in "blogging"), making the pair uninformative as a label.
    """
    a, b = word_a.lower(), word_b.lower()
    # Check both directions: "copy" in "copywriting" OR "copywriting" contains "copy"
    a_words = a.split()
    b_words = b.split()
    # Direct containment: "copy" inside "copywriting"
    for wa in a_words:
        for wb in b_words:
            if len(wa) >= 3 and len(wb) >= 3:
                if wa in wb or wb in wa:
                    return True
    return False


def _tfidf_label(
    cluster_titles: list[str],
    all_titles: list[str],
    site_stops: frozenset[str] = frozenset(),
    corpus_phrases: Counter | None = None,
    corpus_words: Counter | None = None,
    n_docs: int | None = None,
    extra_phrases: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Generate a readable topic label using TF-IDF on phrases.

    Extracts bigrams and unigrams from titles after stripping format markers.
    Optionally incorporates extra_phrases from body text and headings.
    Filters site-common words and format words. Picks the best bigram as
    the primary label to produce "Link Building" instead of "Link & Building".

    Pass pre-computed corpus_phrases/corpus_words/n_docs to avoid redundant
    IDF computation across multiple clusters.

    Returns (label, alternative_labels, description_words) where:
    - label: the primary 2-4 word topic label
    - alternative_labels: up to 3 alternative labels for metadata
    - description_words: top unigrams not in label, for description generation
    """
    noise = _FORMAT_WORDS | site_stops

    # Extract phrases from cluster titles (3x weight via repetition)
    cluster_phrases_list: list[str] = []
    for t in cluster_titles:
        phrases = _extract_phrases(t)
        cluster_phrases_list.extend(phrases * 3)  # 3x weight for titles

    # Add extra phrases from body text (1x) and headings (2x already weighted by caller)
    if extra_phrases:
        cluster_phrases_list.extend(extra_phrases)

    if not cluster_phrases_list:
        return "Miscellaneous", [], []

    # Separate bigrams and unigrams
    bigrams = [p for p in cluster_phrases_list if " " in p]
    unigrams = [p for p in cluster_phrases_list if " " not in p and p not in noise]

    # Use pre-computed corpus stats or compute on demand (backward compat)
    if corpus_phrases is None or corpus_words is None or n_docs is None:
        corpus_phrases, corpus_words, n_docs = _build_corpus_stats(all_titles, site_stops)

    # Score bigrams by TF-IDF
    bigram_tf = Counter(bigrams)
    total_bigrams = len(bigrams) or 1
    bigram_scores: dict[str, float] = {}
    for phrase, count in bigram_tf.items():
        parts = phrase.split()
        if all(p in noise for p in parts):
            continue
        tf = count / total_bigrams
        idf = np.log(n_docs / (1 + corpus_phrases.get(phrase, 0)))
        bigram_scores[phrase] = tf * idf

    # Score unigrams by TF-IDF
    unigram_tf = Counter(unigrams)
    total_unigrams = len(unigrams) or 1
    unigram_scores: dict[str, float] = {}
    for word, count in unigram_tf.items():
        tf = count / total_unigrams
        idf = np.log(n_docs / (1 + corpus_words.get(word, 0)))
        unigram_scores[word] = tf * idf

    # Pick the best bigram as primary label
    # Small clusters (< 5 posts) use freq >= 1 since bigrams rarely repeat in 2-4 titles
    min_bigram_freq = 1 if len(cluster_titles) < 5 else 2

    # Adaptive doc frequency threshold — 20% of cluster size, min 2.
    # For 12-post cluster: 3 titles. For 7-post: 2. For 20-post: 4.
    _adaptive_min = _min_doc_freq(len(cluster_titles))

    # Count which words appear across multiple titles (not just one creative title)
    _title_word_doc_freq: Counter = Counter()
    for t in cluster_titles:
        _title_word_doc_freq.update(set(_WORD_RE.findall(t.lower())) - _STOP_WORDS - _FORMAT_WORDS)

    best_bigram = None
    sorted_bigrams = sorted(bigram_scores.items(), key=lambda x: -x[1])
    for bg_phrase, bg_score in sorted_bigrams:
        if bg_score <= 0 or bigram_tf[bg_phrase] < min_bigram_freq:
            continue
        # Validate: both words in the bigram must appear in enough cluster
        # titles to be representative of the cluster theme (not from a single
        # creative title like "Aristotle's Tips" or "Teaching Sells").
        if not _validate_bigram(bg_phrase, cluster_titles, _adaptive_min):
            continue
        best_bigram = " ".join(_smart_title(w) for w in bg_phrase.split())
        break

    # Pick top unigrams — filter by adaptive cluster title doc frequency to
    # prevent outlier words from leaking into labels. Qualifiers (single words
    # added to bigram labels) need stricter filtering than bigram words since
    # they stand alone. Use adaptive_min + 1 for qualifier-eligible unigrams.
    _qualifier_min = _adaptive_min + 1  # e.g., 3 for 12-post, 4 for 20-post
    top_unigrams = sorted(unigram_scores.items(), key=lambda x: -x[1])[:10]
    top_unigrams = [
        (w, s) for w, s in top_unigrams
        if s > 0 and _title_word_doc_freq.get(w, 0) >= _qualifier_min
    ][:5]
    top_words = [_smart_title(w) for w, score in top_unigrams]

    # Build primary label with smart connectors
    label: str
    if best_bigram:
        qualifiers = [w for w in top_words if w.lower() not in best_bigram.lower()
                      and not _is_semantic_redundant(w, best_bigram)]
        if qualifiers:
            label = _connect_label_parts(best_bigram, qualifiers[0])
        else:
            label = best_bigram
    elif top_words:
        if len(top_words) == 1:
            label = top_words[0]
        else:
            # Skip semantically redundant pairs (e.g., "Copy" + "Copywriting")
            second = next(
                (w for w in top_words[1:] if not _is_semantic_redundant(w, top_words[0])),
                None,
            )
            if second:
                label = _connect_label_parts(top_words[0], second)
            else:
                label = top_words[0]
    else:
        fallback = [w for w in unigrams if w not in noise]
        if fallback:
            label = _smart_title(Counter(fallback).most_common(1)[0][0])
        else:
            return "General Content", [], []

    # Build alternative labels (top 3 different options)
    # Build cluster title word frequency for validation
    _cluster_title_word_freq: Counter = Counter()
    for t in cluster_titles:
        _cluster_title_word_freq.update(set(_WORD_RE.findall(t.lower())))

    def _is_valid_alt(alt_label: str) -> bool:
        alt_words = set(_WORD_RE.findall(alt_label.lower()))
        if not alt_words:
            return False
        # Reject if any word is in UI noise (HTML artifacts)
        if alt_words & _UI_NOISE:
            return False
        # Reject if fewer than 2 content words
        if len(alt_words) < 2:
            return False
        # Reject if it's the same as the primary label
        if alt_label.lower() == label.lower():
            return False
        # Reject if ANY word appears in fewer than the adaptive threshold of
        # cluster titles. Both words must be grounded in the cluster's vocabulary
        # to avoid garbage like "Copywriter Curse" or "People & Naked" from
        # creative titles. Uses _adaptive_min (20% of cluster size, min 2).
        if not all(_cluster_title_word_freq.get(w, 0) >= _adaptive_min for w in alt_words):
            return False
        # Reject likely proper noun phrases: if the raw bigram appears with both
        # words capitalized in cluster titles (e.g., "Teaching Sells", "Chris Garrett")
        alt_lower = alt_label.lower()
        for t in cluster_titles:
            if alt_lower in t.lower():
                # Find the actual casing in the title
                idx = t.lower().find(alt_lower)
                raw = t[idx:idx + len(alt_lower)]
                words_raw = raw.split()
                if len(words_raw) >= 2 and all(w[0].isupper() for w in words_raw if w):
                    return False  # Proper noun phrase
                break
        return True

    alternatives: list[str] = []
    # Alt from 2nd-best bigram
    for bg_phrase, bg_score in sorted_bigrams[1:6]:
        if bg_score > 0 and bigram_tf[bg_phrase] >= min_bigram_freq:
            alt = " ".join(_smart_title(w) for w in bg_phrase.split())
            if _is_valid_alt(alt):
                alternatives.append(alt)
            if len(alternatives) >= 3:
                break
    # Alt from top unigrams if not enough bigram alternatives
    if len(alternatives) < 3 and len(top_words) >= 2:
        for i in range(min(len(top_words) - 1, 4)):
            alt = _connect_label_parts(top_words[i], top_words[i + 1])
            if _is_valid_alt(alt) and alt not in alternatives:
                alternatives.append(alt)
            if len(alternatives) >= 3:
                break
    alternatives = alternatives[:3]

    # Collect description words (unigrams not in the label)
    # Filter: word must meet adaptive doc freq threshold to prevent single-post
    # outlier noise words like "muse", "naked", "fear" from creative individual titles
    desc_words = [
        w for w, _ in top_unigrams
        if _ > 0
        and w.lower() not in label.lower()
        and _cluster_title_word_freq.get(w, 0) >= _adaptive_min
    ][:5]
    desc_words = [_smart_title(w) for w in desc_words]

    return label, alternatives, desc_words


def _generate_description(label: str, desc_words: list[str]) -> str:
    """Generate a one-sentence description from leftover TF-IDF unigrams.

    Fills the clusters.description field that's empty in fast mode.
    """
    if not desc_words:
        return ""
    words_lower = [w.lower() for w in desc_words]
    # Filter out words already in the label
    filtered = [w for w, wl in zip(desc_words, words_lower, strict=True) if wl not in label.lower()]
    if not filtered:
        return ""
    if len(filtered) == 1:
        return f"Posts covering {filtered[0].lower()}."
    if len(filtered) == 2:
        return f"Posts covering {filtered[0].lower()} and {filtered[1].lower()}."
    return (
        f"Posts covering {', '.join(w.lower() for w in filtered[:-1])}, "
        f"and {filtered[-1].lower()}."
    )


def _validate_label_specificity(
    label: str,
    cluster_idx: int,
    all_cluster_titles: list[list[str]],
) -> bool:
    """Check if a label actually differentiates this cluster from others.

    Returns False if the label's words appear equally in other clusters,
    meaning the stop-word detector missed site-wide vocabulary.
    """
    label_words = set(_WORD_RE.findall(label.lower())) - _STOP_WORDS - _FORMAT_WORDS
    if not label_words:
        return True  # Can't validate, assume ok

    # Count how many other clusters contain ALL label words in their titles
    hits = 0
    for i, titles in enumerate(all_cluster_titles):
        if i == cluster_idx:
            continue
        combined = " ".join(t.lower() for t in titles)
        combined_words = set(_WORD_RE.findall(combined))
        if label_words.issubset(combined_words):
            hits += 1

    # If label words appear in more than half of other clusters, it's not specific
    n_other = len(all_cluster_titles) - 1
    if n_other > 0 and hits / n_other > 0.5:
        return False
    return True


async def label_clusters_fast(db: asyncpg.Connection, site_id: UUID) -> int:
    """Label all clusters using TF-IDF on phrases — no API calls.

    Uses titles (3x weight), H2 headings (2x), and body text (1x) for
    phrase extraction. Generates labels, descriptions, and alternative
    labels for each cluster.

    Returns number of clusters labeled.
    """
    all_titles = await db.fetch(
        "SELECT title FROM posts WHERE site_id = $1", site_id,
    )
    all_title_list = [r["title"] or "" for r in all_titles]

    site_stops = _compute_site_stops(all_title_list)
    logger.debug("Site stops for %s: %s", site_id, site_stops)

    # Pre-compute corpus stats once
    corpus_phrases, corpus_words, n_docs = _build_corpus_stats(
        all_title_list, site_stops,
    )

    clusters = await db.fetch(
        "SELECT id, post_count FROM clusters WHERE site_id = $1",
        site_id,
    )
    cluster_ids = [c["id"] for c in clusters]

    # Batch fetch cluster→title mappings (avoids N+1)
    titles_by_cluster: dict[UUID, list[str]] = {cid: [] for cid in cluster_ids}
    # Batch fetch cluster→body_html and headings for multi-signal labeling
    body_by_cluster: dict[UUID, list[tuple[str | None, str | None]]] = {
        cid: [] for cid in cluster_ids
    }
    if cluster_ids:
        rows = await db.fetch(
            """
            SELECT pc.cluster_id, p.title, p.body_html, p.headings
            FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            WHERE pc.cluster_id = ANY($1::uuid[])
            """,
            cluster_ids,
        )
        for row in rows:
            cid = row["cluster_id"]
            titles_by_cluster[cid].append(row["title"] or "")
            body_by_cluster[cid].append((row["body_html"], row["headings"]))

    # Generate labels, alternatives, and description data for all clusters
    labels: list[str] = []
    all_alternatives: list[list[str]] = []
    all_desc_words: list[list[str]] = []
    all_cluster_title_lists: list[list[str]] = []

    for cluster in clusters:
        cid = cluster["id"]
        cluster_titles = titles_by_cluster.get(cid, [])
        all_cluster_title_lists.append(cluster_titles)

        # Build extra phrases from body text (1x) and headings (2x)
        extra_phrases: list[str] = []
        for body_html, headings in body_by_cluster.get(cid, []):
            body_ph, heading_ph = _extract_body_phrases(body_html, headings)
            extra_phrases.extend(body_ph)          # 1x weight
            extra_phrases.extend(heading_ph * 2)   # 2x weight

        label, alternatives, desc_words = _tfidf_label(
            cluster_titles, all_title_list, site_stops=site_stops,
            corpus_phrases=corpus_phrases, corpus_words=corpus_words,
            n_docs=n_docs, extra_phrases=extra_phrases,
        )
        labels.append(label)
        all_alternatives.append(alternatives)
        all_desc_words.append(desc_words)

    # Negative label validation: if a label isn't specific to its cluster,
    # try the first alternative that is specific
    for i, label in enumerate(labels):
        if not _validate_label_specificity(label, i, all_cluster_title_lists):
            for alt in all_alternatives[i]:
                if _validate_label_specificity(alt, i, all_cluster_title_lists):
                    logger.debug(
                        "Label '%s' not specific, replaced with '%s'", label, alt,
                    )
                    labels[i] = alt
                    break

    # Near-duplicate dedup: if two labels share the same first 2 words
    # (primary bigram), replace the second one with its top alternative
    def _primary_bigram(lbl: str) -> str:
        parts = lbl.replace(" & ", " ").split()[:2]
        return " ".join(p.lower() for p in parts)

    seen_primaries: dict[str, int] = {}
    for i, label in enumerate(labels):
        primary = _primary_bigram(label)
        if primary in seen_primaries:
            # This label's primary bigram duplicates an earlier label
            for alt in all_alternatives[i]:
                alt_primary = _primary_bigram(alt)
                if alt_primary not in seen_primaries:
                    logger.debug(
                        "Near-duplicate '%s' replaced with alt '%s'", label, alt,
                    )
                    labels[i] = alt
                    primary = alt_primary
                    break
        seen_primaries[primary] = i

    # Exact-duplicate dedup — append qualifying word for remaining duplicates
    label_counts = Counter(labels)
    for i, label in enumerate(labels):
        if label_counts[label] > 1:
            cluster_titles = titles_by_cluster.get(clusters[i]["id"], [])
            noise = _FORMAT_WORDS | site_stops
            cluster_word_list: list[str] = []
            for t in cluster_titles:
                phrases = _extract_phrases(t)
                cluster_word_list.extend([
                    p for p in phrases if " " not in p and p not in noise
                ])
            word_counts = Counter(cluster_word_list)
            for word, _ in word_counts.most_common():
                if word.lower() not in label.lower():
                    labels[i] = f"{label} ({_smart_title(word)})"
                    break

    # Generate descriptions
    descriptions: list[str] = []
    for i, label in enumerate(labels):
        desc = _generate_description(label, all_desc_words[i])
        descriptions.append(desc)

    # Batch UPDATE labels and descriptions in single round trip
    if cluster_ids:
        await db.execute(
            """
            UPDATE clusters SET label = u.label, description = u.description
            FROM unnest($1::uuid[], $2::text[], $3::text[]) AS u(id, label, description)
            WHERE clusters.id = u.id
            """,
            cluster_ids,
            labels,
            descriptions,
        )

    labeled = len(labels)
    logger.info("Fast cluster labeling: %d clusters labeled for site %s", labeled, site_id)
    return labeled


# ── Claude cluster labeling (async backfill) ─────────────────────────────────

CLAUDE_MODEL = "claude-sonnet-4-20250514"


async def _claude_label_cluster(client, titles: list[str], site_domain: str) -> str:
    """Ask Claude to produce a 2-4 word topic label from post titles."""
    prompt = (
        f"These are {len(titles)} blog post titles from {site_domain}, all in the same topic cluster.\n\n"
        f"Titles:\n"
        + "\n".join(f"- {t}" for t in titles[:15])
        + "\n\nWhat topic do these posts share? Respond with ONLY a 2-4 word topic label.\n"
        "Examples of good labels: \"Email Marketing\", \"Link Building Guides\", "
        "\"Vegetarian Soup Recipes\", \"JavaScript Tutorials\", \"Personal Finance Tips\"\n"
        "Do not include the site name. Do not include format words like \"guide\" or \"post\" "
        "unless the topic IS about guides/posts."
    )
    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip().strip('"').strip("'")


async def backfill_claude_labels(db: asyncpg.Connection, site_id: UUID) -> int:
    """Relabel clusters using Claude — runs after TF-IDF labels as quality upgrade.

    TF-IDF labels serve as fallback if Claude fails for any cluster.
    Cost: ~$0.02 per site (25 clusters × ~500 tokens each).
    Time: ~10-15 seconds parallelized.
    """
    from anthropic import AsyncAnthropic

    from app.config import get_settings

    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping Claude cluster labels")
        return 0

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    site = await db.fetchrow("SELECT domain FROM sites WHERE id = $1", site_id)
    domain = site["domain"] if site else ""

    clusters = await db.fetch(
        """SELECT id, post_count FROM clusters WHERE site_id = $1
           AND post_count > 0
           AND id NOT IN (
               SELECT parent_cluster_id FROM clusters
               WHERE parent_cluster_id IS NOT NULL AND site_id = $1
           )""",
        site_id,
    )

    labeled = 0
    for cluster in clusters:
        titles = await db.fetch(
            """SELECT p.title FROM posts p
               JOIN post_clusters pc ON pc.post_id = p.id
               WHERE pc.cluster_id = $1
               ORDER BY p.word_count DESC LIMIT 15""",
            cluster["id"],
        )
        title_list = [t["title"] for t in titles if t["title"]]
        if not title_list:
            continue

        try:
            label = await _claude_label_cluster(client, title_list, domain)
            if label and len(label) >= 3:
                await db.execute(
                    "UPDATE clusters SET label = $1 WHERE id = $2",
                    label, cluster["id"],
                )
                labeled += 1
                logger.debug("Claude label: cluster %s → %s", cluster["id"], label)
        except Exception as e:
            logger.warning("Claude label failed for cluster %s: %s", cluster["id"], e)

    logger.info("Claude cluster labeling: %d clusters relabeled for site %s", labeled, site_id)
    return labeled
