"""Cannibalization detection via embedding cosine similarity + GSC query overlap.

Research-informed approach (two-signal detection):
1. Embedding cosine similarity between posts in the same cluster
2. GSC query overlap — posts ranking for the same search queries

THRESHOLD CALIBRATION:
Thresholds are auto-calibrated per site using the pairwise similarity
distribution. This handles niche sites (higher baseline similarity)
vs general blogs (lower baseline). Calibration uses 85th/92nd/97th
percentiles with absolute floors of 0.30/0.40/0.50.

Default thresholds (text-embedding-3-small):
- flag: 0.40 (review), high: 0.50 (action needed), critical: 0.60 (near-duplicate)

PERFORMANCE:
For clusters with 20+ posts, uses HNSW index pre-filtering to avoid
O(n²) pair scans. Finds top-10 nearest neighbors per post via pgvector's
HNSW index, then only evaluates those candidate pairs.

The "stronger post" is determined by composite health score + traffic.
"""

import logging
import re
from itertools import combinations
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Cosine similarity thresholds for text-embedding-3-small
# CRITICAL: This model produces LOWER similarity scores than ada-002.
# Research (OpenAI community, 2024): content that scored 0.70+ with ada-002
# scores ~0.40 with text-embedding-3-small. Thresholds must be calibrated
# accordingly. Same-topic content typically scores 0.45-0.55.
#
# These defaults should be tuned per-site after initial embedding generation.
# Run: SELECT 1 - (a.embedding <=> b.embedding) FROM post_embeddings a, b
# on known-cannibalized pairs to calibrate.
COSINE_THRESHOLD_FLAG = 0.45    # Flag for review (raised from 0.40 to reduce false positives on niche sites)
COSINE_THRESHOLD_HIGH = 0.55    # High confidence cannibalization
COSINE_THRESHOLD_CRITICAL = 0.65  # Near-duplicate content

# Min shared queries for query-only cannibalization
MIN_SHARED_QUERIES = 3  # Require 3+ shared queries — single shared query is too weak a signal


# ── Blended cannibalization scoring ──────────────────────────────────────────
#
# Cannibalization = Google doesn't know which page to show for a given query.
# The ground truth test: "Would a human typing a single search query be
# satisfied by either post?"
#
# Without GSC data, we approximate this by checking whether two posts target
# the same inferred keyword (from URL slug + title), serve the same search
# intent, and cover the same subtopics (from H2 headings).
#
# The blended score replaces raw cosine similarity as the primary signal.
# Cosine captures topical similarity but NOT keyword competition.
# Two SEO tool reviews are topically similar but never compete for the
# same query if they review different products.

_SLUG_STOPS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "is", "are", "how", "what", "why",
    "your", "you", "that", "this", "from", "it", "its", "can",
    "www", "com", "html", "php", "blog", "post", "page",
})

# Intent modifier groups — posts only cannibalize when they share both the
# same entity AND the same intent group
_INTENT_GROUPS = {
    "learning": {"guide", "how", "tutorial", "strategies", "tips", "techniques",
                 "ways", "steps", "explained", "introduction", "basics",
                 "beginners", "learn", "definitive", "complete", "ultimate",
                 "simple", "comprehensive", "checklist", "course", "lessons",
                 "mistakes", "secrets", "principles", "rules", "formula"},
    "browsing": {"examples", "templates", "inspiration", "ideas", "samples",
                 "list", "collection", "roundup", "showcase", "gallery"},
    "evaluation": {"review", "comparison", "versus", "alternative", "alternatives",
                   "pricing", "pros", "cons", "worth"},
    "research": {"statistics", "stats", "report", "study", "data", "survey",
                 "analyzed", "analysis", "research", "findings", "benchmark",
                 "trends", "state", "results", "insights"},
    "shopping": {"tools", "software", "resources", "platforms", "services",
                 "products", "apps", "programs", "deals", "picks", "recommendations"},
    "case_study": {"case", "success", "story", "interview", "behind", "journey",
                   "experience", "profile", "spotlight"},
    "opinion": {"why", "think", "believe", "opinion", "wrong", "myth", "myths",
                "truth", "dead", "overrated", "underrated", "controversial",
                "unpopular", "debate", "rant", "problem"},
    "reference": {"glossary", "dictionary", "definitions", "terminology", "cheat",
                  "sheet", "reference", "index", "directory", "hub", "wiki",
                  "database", "library", "catalog"},
}

# Review template H2 keywords
_REVIEW_H2S = frozenset({
    "features", "pricing", "pros", "cons", "verdict", "alternatives",
    "overview", "review", "summary", "plans", "integrations",
    "key features", "who is it for", "bottom line",
    "free trial", "customer support", "ease of use",
})

# Common title suffixes to strip when extracting the core keyword
_TITLE_SUFFIXES = re.compile(
    r"\s*[-–:|]\s*.+$"  # Strip "Title - Site Name" / "Title: Subtitle"
)
_TITLE_FORMAT_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "is", "are", "how", "what", "why",
    "your", "you", "that", "this", "from", "it", "its", "can",
    "get", "best", "top", "new", "most", "more", "here", "our",
    "guide", "complete", "definitive", "ultimate", "simple", "step",
})


def _heading_text(h) -> str:
    """Extract text from a heading (handles both dict and string formats)."""
    if isinstance(h, dict):
        return (h.get("text") or "").lower().strip()
    return str(h).lower().strip() if h else ""


# Format words in URL slugs that indicate article type, not topic
_SLUG_FORMAT_WORDS = frozenset({
    "review", "guide", "tutorial", "tips", "strategies", "examples",
    "comparison", "alternative", "alternatives", "report", "study",
    "statistics", "stats", "tools", "best", "free", "hub",
})


def _extract_slug_core(url: str) -> set[str]:
    """Extract core topic keywords from URL slug, stripping format words.

    /serpstat-review → {"serpstat"}
    /link-building-strategies → {"link", "building"}
    /ecommerce-website-examples → {"ecommerce", "website"}
    """
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1] if "/" in path else path
    words = set(re.findall(r"[a-z]{3,}", slug.lower()))
    return words - _SLUG_STOPS - _SLUG_FORMAT_WORDS


# Format markers in titles — strip these to extract the topic entity.
# "SEO Copywriting: The Definitive Guide" → strip ": The Definitive Guide" → "seo copywriting"
_TITLE_FORMAT_MARKERS = re.compile(
    r"(?:"
    r":\s*(?:the|a|an)?\s*(?:definitive|complete|comprehensive|ultimate|essential|practical)\s+guide"
    r"|:\s*(?:a\s+)?step[- ]by[- ]step\s+guide"
    r"|:\s*(?:a\s+)?beginner'?s?\s+guide"
    r"|:\s*(?:a\s+)?comprehensive\s+checklist"
    r"|:\s*how\s+to\s+.+"
    r"|:\s*what\s+(?:is|are)\s+.+"
    r"|:\s*everything\s+you\s+need\s+to\s+know"
    r"|:\s*(?:a\s+)?case\s+study"
    r"|:\s*(?:a\s+)?complete\s+list"
    r")"
    r"\s*(?:[-–|].+)?$",  # Also strip trailing " - Site Name"
    re.IGNORECASE,
)

# Leading format patterns: "How to X", "What Is X", "N Ways to X"
_TITLE_LEADING_FORMAT = re.compile(
    r"^(?:"
    r"how\s+to\s+"
    r"|what\s+(?:is|are)\s+"
    r"|\d+\s+(?:ways?|tips?|steps?|methods?|strategies|techniques|examples?|types?)\s+(?:to|of|for)\s+"
    r")",
    re.IGNORECASE,
)


def _extract_title_entity(title: str) -> str | None:
    """Extract the topic entity from a title by stripping format markers.

    Works for any title format, not just reviews:
    "Serpstat Review: Is This SEO Tool Worth It?" → "serpstat"
    "SEO Copywriting: The Definitive Guide" → "seo copywriting"
    "Google RankBrain: The Definitive Guide" → "google rankbrain"
    "Link Building: A Complete Guide" → "link building"
    "How to Build Links With Content Marketing" → "build links content marketing"
    "9 Ecommerce Website Examples" → "ecommerce website"
    """
    t = title.lower().strip()

    # Pattern 1: "X Review" / "X vs Y"
    m = re.match(r"^(.+?)\s+(review|vs\.?|versus|comparison|alternative)", t)
    if m:
        entity = m.group(1).strip().rstrip(":").strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 2: "Review of X"
    m = re.match(r"^review\s*[:of]+\s*(.+?)(\s*[-–|]|$)", t)
    if m:
        return m.group(1).strip()

    # Pattern 3: "Topic: The Definitive Guide" / "Topic: A Complete Guide" etc.
    m = _TITLE_FORMAT_MARKERS.search(t)
    if m:
        entity = t[:m.start()].strip().rstrip(":").strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 3b: "X Case Study: ..." — format word BEFORE the colon
    m = re.match(r"^(.+?)\s+(?:case\s+study|report|checklist|cheat\s+sheet)\s*:", t)
    if m:
        entity = m.group(1).strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 4: "How to X..." / "What Is X..." / "N Ways to X..."
    m = _TITLE_LEADING_FORMAT.match(t)
    if m:
        remainder = t[m.end():].strip()
        # Strip trailing site name / subtitle
        remainder = re.sub(r"\s*[-–|:].+$", "", remainder)
        # Strip trailing format words
        remainder = re.sub(
            r"\s+(?:in\s+\d{4}|for\s+\d{4}|guide|tutorial|tips|strategies)$",
            "", remainder,
        )
        if len(remainder) >= 3:
            # Cap at first 4 meaningful words to avoid sentence-length entities
            words = remainder.split()
            return " ".join(words[:4]) if len(words) > 4 else remainder

    # Pattern 5: "N Best/Top/Most Important X..." — extract X
    m = re.match(r"^\d+\s+(?:best|top|key|essential|proven|incredible|awesome|most\s+important)\s+(.+?)(?:\s+(?:in|for)\s+\d{4})?$", t)
    if m:
        entity = m.group(1).strip()
        # Strip trailing format words
        entity = re.sub(r"\s+(?:to\s+try|you\s+should|for\s+.+)$", "", entity)
        return entity if len(entity) >= 3 else None

    # Pattern 6: "Title: Subtitle" without format marker — topic is everything before colon
    m = re.match(r"^([^:]{4,30}):\s+.+", t)
    if m:
        entity = m.group(1).strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        # Only return if it's not just a single common word
        entity_words = [w for w in entity.split() if len(w) >= 3]
        if len(entity_words) >= 1 and entity not in {"how", "what", "why", "the"}:
            return entity

    # Pattern 7 (fallback): No format pattern matched. Extract meaningful words
    # from the title as a rough entity. Strips leading articles, trailing year/site name,
    # question markers, and common filler.
    #
    # Quality gate: only return if the result contains at least one "topic word" — a noun
    # or domain term someone might actually search for. Filters out garbage like
    # "end adsense know feel" or "whom tips tips thee" (creative phrasing fragments).
    fallback = re.sub(r"\s+[-–|]\s+.+$", "", t)  # Strip trailing " - Site Name" (requires spaces around separator)
    fallback = re.sub(r"\?+$", "", fallback).strip()  # Strip trailing ?
    fallback = re.sub(r"^(the|a|an|why|when|where|who)\s+", "", fallback)
    fallback = re.sub(r"\s+(?:in|for|of)\s+\d{4}$", "", fallback)  # Strip year

    # Verbs/adverbs/filler that appear in creative titles but aren't searchable entities.
    # ONLY verbs, adverbs, and filler — NOT adjectives or nouns that could be B2B topics.
    # Words like "strategic", "development", "approach" are legitimate topic words.
    _fallback_noise = {
        # Verbs
        "has", "have", "had", "was", "were", "will", "would", "could", "should",
        "been", "being", "does", "did", "got", "get", "let", "don",
        "know", "feel", "tell", "find", "make", "take", "give", "come",
        "keep", "think", "want", "need", "look", "like", "love", "hate",
        "say", "says", "said", "told", "read", "try", "use", "put",
        "become", "became", "attract", "mean", "means", "meant",
        "start", "stop", "run", "set", "show", "help", "turn",
        # Adverbs/filler
        "just", "really", "actually", "about", "here", "there",
        "ever", "never", "still", "also", "too", "very",
        "once", "twice", "much", "more", "less", "enough",
        # Pronouns/archaic
        "whom", "thee", "thou",
        # Adjectives/quantifiers that are pure filler (not topic-relevant)
        "right", "wrong", "true", "first", "last", "next",
        "most", "some", "every", "each", "many", "few", "whole", "both",
        "fine", "dead",
        # Structure/format words that indicate article type, not topic
        "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "step", "steps", "approach", "process", "method", "methods",
        "way", "ways", "thing", "things", "reason", "reasons",
        "secret", "secrets", "lesson", "lessons", "rule", "rules",
        "trick", "tricks", "hack", "hacks", "works", "worked",
    }
    fallback_words = [
        w for w in re.findall(r"[a-z]{3,}", fallback)
        if w not in _SLUG_STOPS and w not in _fallback_noise
    ]
    if len(fallback_words) < 2:
        return None

    # Quality gate: at least one word must be a plausible topic/noun, not just
    # verbs/adjectives. Check against known SEO/content domain terms or require
    # a word that's 5+ chars (longer words are more likely nouns/proper terms).
    has_topic_word = any(
        len(w) >= 5 or w in {
            "seo", "blog", "link", "page", "site", "web", "ads", "ppc",
            "copy", "lead", "sale", "rank", "data", "code", "api", "app",
            "tool", "plan", "test", "user", "team", "roi", "crm", "cms",
            "cta", "ux", "ai", "b2b", "saas", "ecommerce",
        }
        for w in fallback_words
    )
    if not has_topic_word:
        return None

    return " ".join(fallback_words[:3])  # Cap at 3 words — shorter = fewer false overlaps


def _extract_title_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title, stripping format words."""
    # Remove site name suffix ("Title - Site Name")
    t = _TITLE_SUFFIXES.sub("", title)
    words = set(re.findall(r"[a-zA-Z]{3,}", t.lower()))
    return words - _TITLE_FORMAT_WORDS


def _classify_intent_group(title: str, url: str) -> str | None:
    """Classify a post's search intent group from title + URL.

    Returns one of: learning, browsing, evaluation, research, shopping, or None.
    """
    combined = f"{title} {url}".lower()
    words = set(re.findall(r"[a-z]{3,}", combined))
    best_group = None
    best_overlap = 0
    for group, keywords in _INTENT_GROUPS.items():
        overlap = len(words & keywords)
        if overlap > best_overlap:
            best_overlap = overlap
            best_group = group
    return best_group if best_overlap >= 1 else None


def _h2_subtopic_jaccard(headings_a: list, headings_b: list) -> float:
    """Compute Jaccard similarity on H2 heading content keywords.

    Strips entity names (from title) so that "Serpstat Features" and
    "Ahrefs Features" don't match on the entity, only on the subtopic word.
    """
    def _kw_set(headings: list) -> set[str]:
        words = set()
        for h in headings:
            text = _heading_text(h)
            if text:
                words.update(w for w in re.findall(r"[a-z]{3,}", text)
                             if w not in _TITLE_FORMAT_WORDS)
        return words

    kw_a = _kw_set(headings_a)
    kw_b = _kw_set(headings_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union) if union else 0.0


def _is_review_template(headings: list) -> bool:
    """Check if headings follow a review article template."""
    h_keywords = set()
    for h in headings:
        text = _heading_text(h)
        if text:
            h_keywords.update(re.findall(r"[a-z]+", text))
    return len(h_keywords & _REVIEW_H2S) >= 3


def _title_topic_overlap(title_a: str, title_b: str) -> float:
    """Compute topic-word Jaccard between two titles, ignoring format markers.

    Strips format words (guide, tips, review, etc.) and stop words,
    then computes Jaccard on the remaining topic words.
    "17 SEO Tips" vs "Google RankBrain Guide" → topics {"seo","tips","rankings"} vs {"google","rankbrain"} → 0.0
    "Meta Tags" vs "HTML Tags for SEO" → topics {"meta","tags"} vs {"html","tags","seo"} → 0.25
    """
    format_noise = _SLUG_FORMAT_WORDS | {"most", "important", "here", "what", "learned",
                                          "need", "know", "really", "actually", "things",
                                          "much", "does", "cost", "work", "better", "good",
                                          "ways", "steps", "methods", "techniques", "used",
                                          "simple", "easy", "quick", "fast", "using",
                                          "tried", "tested", "worth", "results", "case",
                                          "million", "billion", "analyzed", "data"}

    def _topic_words(title: str) -> set[str]:
        t = re.sub(r"\s*[-–|:].{0,30}$", "", title.lower())  # strip trailing suffix
        t = re.sub(r"^\d+\s+", "", t)  # strip leading numbers
        words = set(re.findall(r"[a-z]{3,}", t))
        return words - _SLUG_STOPS - format_noise

    topics_a = _topic_words(title_a)
    topics_b = _topic_words(title_b)

    if not topics_a or not topics_b:
        return 0.3  # Can't determine — lean conservative

    union = topics_a | topics_b
    intersection = topics_a & topics_b
    return len(intersection) / len(union) if union else 0.0


def compute_blended_cannibalization_score(
    post_a: dict, post_b: dict,
    headings_a: list, headings_b: list,
    cosine_sim: float | None,
) -> tuple[float, str]:
    """Compute a blended cannibalization score (0.0 to 1.0) and severity tier.

    The blended score answers: "Would a human typing a single search query
    be satisfied by either post?" — which is the real definition of cannibalization.

    Signals and weights:
      - Cosine embedding similarity:  25% (broad topical overlap baseline)
      - URL slug keyword overlap:     25% (same inferred target keyword)
      - Title entity + intent match:  30% (same topic + same search purpose)
      - H2 subtopic Jaccard:          20% (posts cover the same specific subtopics)

    Returns (blended_score, severity_tier).

    Severity tiers:
      critical: blended > 0.80 — near-duplicates, merge or redirect
      high:     blended > 0.55 — genuine query competition, differentiate
      medium:   blended > 0.35 — potential overlap, monitor
      low:      blended <= 0.35 — content series, don't flag
    """
    title_a = post_a.get("title", "")
    title_b = post_b.get("title", "")
    url_a = post_a.get("url", "")
    url_b = post_b.get("url", "")

    # ── Signal 1: Cosine similarity (25%) ──
    cosine_component = min((cosine_sim or 0.0), 1.0)

    # ── Signal 2: URL slug keyword overlap (25%) ──
    slug_a = _extract_slug_core(url_a)
    slug_b = _extract_slug_core(url_b)
    if slug_a and slug_b:
        slug_intersection = slug_a & slug_b
        slug_union = slug_a | slug_b
        slug_overlap = len(slug_intersection) / len(slug_union) if slug_union else 0.0
    else:
        slug_overlap = 0.0

    # ── Signal 3: Title entity + intent match (30%) ──
    entity_a = _extract_title_entity(title_a)
    entity_b = _extract_title_entity(title_b)

    # Entity match score: 1.0 if same entity, 0.0 if different named entities,
    # 0.5 if no entity detected (can't tell).
    # For multi-word fallback entities (Pattern 7), use word overlap instead of
    # exact match — "coercive copywriting techniques" and "copywriting 101" share
    # "copywriting" and should be treated as related, not different entities.
    entities_are_different = False
    if entity_a and entity_b:
        if entity_a == entity_b:
            entity_match = 1.0
        else:
            # Check word overlap for multi-word entities (fallback extractions)
            words_a = set(entity_a.split())
            words_b = set(entity_b.split())
            if len(words_a) >= 2 or len(words_b) >= 2:
                # At least one is a multi-word fallback entity — use Jaccard
                intersection = words_a & words_b
                union = words_a | words_b
                word_overlap = len(intersection) / len(union) if union else 0.0
                if word_overlap >= 0.2:
                    # Meaningful word overlap — treat as related entities (partial match).
                    # 0.2 = sharing 1 word out of 5, e.g., "copywriting" in
                    # "coercive copywriting techniques" vs "copywriting 101"
                    entity_match = word_overlap
                else:
                    # Low word overlap — genuinely different entities
                    entity_match = 0.0
                    entities_are_different = True
            else:
                # Both are single-word entities (clean Pattern 1-6 matches)
                # e.g., "serpstat" vs "ahrefs" — definitely different
                entity_match = 0.0
                entities_are_different = True
    elif entity_a or entity_b:
        # One has an entity, the other doesn't — probably different content types
        entity_match = 0.2
    else:
        # Neither has a clear entity — fall back to title keyword overlap
        title_kw_a = _extract_title_keywords(title_a)
        title_kw_b = _extract_title_keywords(title_b)
        if title_kw_a and title_kw_b:
            title_union = title_kw_a | title_kw_b
            entity_match = len(title_kw_a & title_kw_b) / len(title_union) if title_union else 0.0
        else:
            entity_match = 0.0

    # Intent group match: 1.0 if same group, 0.3 if different groups, 0.5 if unknown
    # BUT: if entities are explicitly different, intent match is irrelevant —
    # "Serpstat Review" and "Ahrefs Review" have the same intent (evaluation)
    # but they don't compete because they're about different products.
    intent_a = _classify_intent_group(title_a, url_a)
    intent_b = _classify_intent_group(title_b, url_b)
    if entities_are_different:
        # Different named entities → intent match doesn't matter
        intent_match = 0.0
    elif intent_a and intent_b:
        intent_match = 1.0 if intent_a == intent_b else 0.3
    else:
        intent_match = 0.5

    # Combined entity+intent: both must match for high score
    entity_intent_score = entity_match * 0.6 + intent_match * 0.4

    # ── Signal 4: H2 subtopic Jaccard (20%) ──
    h2_jaccard = _h2_subtopic_jaccard(headings_a, headings_b)

    # If both posts are review templates reviewing different entities, zero out H2 score
    # (structurally identical H2s about different products shouldn't count)
    if entity_a and entity_b and entity_a != entity_b:
        if _is_review_template(headings_a) and _is_review_template(headings_b):
            h2_jaccard = 0.0

    # ── Signal 5: Title topic word overlap (strips format words) ──
    title_topic = _title_topic_overlap(title_a, title_b)

    # ── Blended score ──
    # Cosine alone is insufficient — two "Definitive Guide" posts about different topics
    # score 0.85+ cosine but 0.0 title topic overlap. The title topic signal catches this.
    blended = (
        0.15 * cosine_component       # Broad topical overlap (baseline)
        + 0.20 * slug_overlap          # Same inferred target keyword
        + 0.25 * entity_intent_score   # Same entity + same search purpose
        + 0.20 * title_topic           # Title topic words actually overlap
        + 0.20 * h2_jaccard            # Cover the same specific subtopics
    )

    # ── Severity tier ──
    if blended > 0.80:
        tier = "critical"
    elif blended > 0.55:
        tier = "high"
    elif blended > 0.35:
        tier = "medium"
    else:
        tier = "low"  # Content series — don't flag

    return blended, tier


class CannibalizationDetector:
    """Detect cannibalization within topic clusters using embeddings + GSC."""

    async def calibrate_thresholds(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict[str, float]:
        """Auto-calibrate cosine similarity thresholds for a specific site.

        Computes the pairwise cosine similarity distribution across all posts
        and sets thresholds at the 85th and 95th percentiles. This adapts to
        the site's content: a niche site about "React hooks" will have higher
        baseline similarity than a general tech blog.

        Stores calibrated thresholds in the sites table and returns them.
        """
        logger.info("Calibrating cosine thresholds for site %s", site_id)

        # Get a sample of pairwise similarities (cap at 500 pairs for perf)
        similarities = await db.fetch(
            """
            SELECT 1 - (a.embedding <=> b.embedding) AS similarity
            FROM post_embeddings a
            JOIN posts pa ON pa.id = a.post_id
            JOIN post_embeddings b ON b.post_id > a.post_id
            JOIN posts pb ON pb.id = b.post_id
            WHERE pa.site_id = $1 AND pb.site_id = $1
            ORDER BY RANDOM()
            LIMIT 500
            """,
            site_id,
        )

        if len(similarities) < 10:
            logger.info(
                "Too few pairs (%d) to calibrate — using defaults", len(similarities),
            )
            return {
                "flag": COSINE_THRESHOLD_FLAG,
                "high": COSINE_THRESHOLD_HIGH,
                "critical": COSINE_THRESHOLD_CRITICAL,
            }

        import numpy as np
        sims = np.array([float(r["similarity"]) for r in similarities])

        # Use percentiles: flag=85th, high=92nd, critical=97th
        p85 = float(np.percentile(sims, 85))
        p92 = float(np.percentile(sims, 92))
        p97 = float(np.percentile(sims, 97))

        # Floor: don't go below absolute minimums
        # Floors calibrated for text-embedding-3-small which produces lower absolute
        # cosine similarities (~0.35-0.45 for same-topic content vs 0.60+ in ada-002).
        # Original floors of 0.50/0.70/0.85 systematically missed real cannibalization.
        flag = max(p85, 0.40)
        high = max(p92, 0.50)
        critical = max(p97, 0.60)

        logger.info(
            "Calibrated thresholds for site %s: flag=%.3f (p85), high=%.3f (p92), "
            "critical=%.3f (p97) | distribution: min=%.3f, median=%.3f, max=%.3f",
            site_id, flag, high, critical,
            float(np.min(sims)), float(np.median(sims)), float(np.max(sims)),
        )

        # Store in sites table metadata
        import json
        calibration_meta = json.dumps({
            "cosine_threshold_flag": round(flag, 4),
            "cosine_threshold_high": round(high, 4),
            "cosine_threshold_critical": round(critical, 4),
        })
        await db.execute(
            """
            UPDATE sites SET metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            calibration_meta,
            site_id,
        )

        return {"flag": flag, "high": high, "critical": critical}

    async def detect_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
        max_pairs: int = 500,
        on_progress: "Callable[[str], None] | None" = None,
    ) -> int:
        """Run cannibalization detection across all clusters for a site.

        Auto-calibrates thresholds on first run, then uses site-specific
        thresholds stored in the sites table. Limits output to max_pairs
        most severe pairs for actionability.

        on_progress: optional callback for progress updates (e.g., "Scanning cluster 5/40")

        Returns the number of cannibalization pairs found.
        """
        try:
            return await self._detect_for_site_impl(db, site_id, max_pairs, on_progress=on_progress)
        except Exception as e:
            logger.error("Cannibalization detection failed for site %s: %s", site_id, e, exc_info=True)
            raise

    async def _detect_for_site_impl(
        self, db: asyncpg.Connection, site_id: UUID,
        max_pairs: int = 500,
        on_progress: "Callable[[str], None] | None" = None,
    ) -> int:
        logger.info("Starting cannibalization detection for site %s", site_id)

        # Pre-filter: detect and flag duplicate content (different URLs, same content)
        dupes = await db.fetch("""
            SELECT p1.id as id1, p2.id as id2, p1.url as url1, p2.url as url2
            FROM posts p1
            JOIN posts p2 ON p1.content_hash = p2.content_hash
                AND p1.id < p2.id AND p1.site_id = p2.site_id
            WHERE p1.site_id = $1 AND p1.content_hash IS NOT NULL
        """, site_id)
        if dupes:
            logger.info("Found %d duplicate content pairs (same content, different URLs)", len(dupes))
            for d in dupes[:5]:
                logger.info("  Duplicate: %s ↔ %s", d["url1"][:50], d["url2"][:50])

        # Always recalibrate thresholds from current embeddings (~8ms, negligible).
        # Cached thresholds become stale after content changes or embedding model upgrades.
        thresholds = await self.calibrate_thresholds(db, site_id)

        # Only scan leaf clusters (no children) to avoid redundant pairwise work
        # on parent clusters whose posts are already covered by child clusters
        clusters = await db.fetch(
            """SELECT id, post_count FROM clusters WHERE site_id = $1
               AND id NOT IN (
                   SELECT parent_cluster_id FROM clusters
                   WHERE parent_cluster_id IS NOT NULL AND site_id = $1
               )""",
            site_id,
        )

        if not clusters:
            logger.warning("No clusters for site %s — run clustering first", site_id)
            return 0

        # Clear old pairs
        cluster_ids = [r["id"] for r in clusters]
        await db.execute(
            "DELETE FROM cannibalization_pairs WHERE cluster_id = ANY($1::uuid[])",
            cluster_ids,
        )

        total_pairs = 0
        scannable_clusters = [c for c in clusters if c["post_count"] >= 2]
        for idx, cluster_row in enumerate(scannable_clusters, 1):
            if on_progress:
                on_progress(f"Scanning cluster {idx}/{len(scannable_clusters)} for cannibalization")
            pairs = await self._detect_in_cluster(
                db, cluster_row["id"], site_id, thresholds=thresholds,
            )
            total_pairs += pairs

        # Cross-cluster detection: find high-similarity pairs across different clusters
        # using global HNSW scan. Catches pairs at cluster boundaries that within-cluster
        # scanning misses (e.g., "SEO tips" in cluster A vs "SEO strategies" in cluster B).
        if on_progress:
            on_progress("Scanning cross-cluster pairs")
        cross_pairs = await self._detect_cross_cluster(
            db, site_id, thresholds=thresholds,
        )
        total_pairs += cross_pairs

        # Scale max_pairs with site size (500 minimum, up to 1500 for large sites)
        total_posts = sum(r["post_count"] for r in clusters if r.get("post_count"))
        if max_pairs == 500:  # default, not user-overridden
            max_pairs = max(500, min(total_posts * 3, 1500))

        # Prune to max_pairs — keep only the most severe (by blended severity_score,
        # not raw cosine — a pair with high slug/title overlap but moderate cosine
        # is more actionable than a pair with high cosine but zero keyword overlap)
        if total_pairs > max_pairs:
            await db.execute("""
                DELETE FROM cannibalization_pairs
                WHERE id NOT IN (
                    SELECT cp.id FROM cannibalization_pairs cp
                    JOIN posts p ON cp.post_a_id = p.id
                    WHERE p.site_id = $1
                    ORDER BY cp.severity_score DESC NULLS LAST
                    LIMIT $2
                )
                AND post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
            """, site_id, max_pairs)
            pruned = total_pairs - max_pairs
            logger.info("Pruned %d low-severity pairs, keeping top %d", pruned, max_pairs)
            total_pairs = max_pairs

        logger.info(
            "Cannibalization detection complete for site %s — %d pairs found",
            site_id, total_pairs,
        )
        return total_pairs

    async def _detect_in_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
        thresholds: dict[str, float] | None = None,
    ) -> int:
        """Detect cannibalization pairs within a single cluster.

        Uses:
        1. pgvector cosine distance between all post pairs (via embedding)
        2. GSC query overlap between post pairs

        thresholds: site-specific calibrated thresholds (flag/high/critical)

        Returns the number of pairs found.
        """
        t_flag = thresholds["flag"] if thresholds else COSINE_THRESHOLD_FLAG
        t_high = thresholds["high"] if thresholds else COSINE_THRESHOLD_HIGH
        t_critical = thresholds["critical"] if thresholds else COSINE_THRESHOLD_CRITICAL
        # Get posts with their embeddings (using pgvector for cosine distance)
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count,
                   p.content_hash, p.content_intent, p.language, p.headings,
                   pe.embedding::text AS embedding_text
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE pc.cluster_id = $1
              AND COALESCE(p.page_type, 'blog') NOT IN ('landing', 'index')
            ORDER BY p.id
            """,
            cluster_id,
        )

        if len(posts) < 2:
            return 0

        # Build maps for language, intent, and headings
        lang_map: dict = {p["id"]: p["language"] for p in posts}
        intent_map: dict = {p["id"]: p["content_intent"] for p in posts}
        headings_map: dict = {p["id"]: (p["headings"] or []) for p in posts}

        # Get health scores for "stronger post" determination
        health_rows = await db.fetch(
            """
            SELECT post_id, composite_score, traffic_contribution
            FROM post_health_scores
            WHERE post_id = ANY($1::uuid[])
            """,
            [p["id"] for p in posts],
        )
        health_map: dict[UUID, dict] = {
            r["post_id"]: {
                "score": r["composite_score"] or 0.0,
                "traffic": r["traffic_contribution"] or 0.0,
            }
            for r in health_rows
        }

        # Get GSC queries per post (recent 90 days)
        query_rows = await db.fetch(
            """
            SELECT post_id, query
            FROM gsc_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY post_id, query
            """,
            [p["id"] for p in posts],
        )
        queries_by_post: dict[UUID, set[str]] = {}
        for r in query_rows:
            queries_by_post.setdefault(r["post_id"], set()).add(r["query"].lower())

        pairs_found = 0
        post_list = list(posts)
        post_id_set = {p["id"] for p in post_list}

        # ── HNSW pre-filter: only compare posts above similarity threshold ──
        # Instead of O(n²) pair scan, use pgvector's HNSW index to find
        # nearest neighbors for each post. Much faster for large clusters.
        # For small clusters (< 20 posts), full scan is fine.
        use_hnsw = len(post_list) >= 20

        # Build pre-filtered candidate pairs via HNSW
        hnsw_candidates: dict[tuple[UUID, UUID], float] = {}
        if use_hnsw:
            for post in post_list:
                if not post["embedding_text"]:
                    continue
                # Use HNSW index to find nearest neighbors within threshold
                neighbors = await db.fetch(
                    """
                    SELECT pe2.post_id,
                           1 - (pe1.embedding <=> pe2.embedding) AS similarity
                    FROM post_embeddings pe1, post_embeddings pe2
                    WHERE pe1.post_id = $1
                      AND pe2.post_id != $1
                      AND pe2.post_id = ANY($2::uuid[])
                    ORDER BY pe1.embedding <=> pe2.embedding
                    LIMIT 10
                    """,
                    post["id"], list(post_id_set),
                )
                for n in neighbors:
                    sim = float(n["similarity"])
                    if sim >= t_flag:
                        pair_key = tuple(sorted([post["id"], n["post_id"]]))
                        hnsw_candidates[pair_key] = max(
                            hnsw_candidates.get(pair_key, 0), sim,
                        )
            logger.info(
                "HNSW pre-filter: %d candidate pairs from %d posts in cluster %s",
                len(hnsw_candidates), len(post_list), cluster_id,
            )

        # Build post lookup for iteration
        post_by_id = {p["id"]: p for p in post_list}

        # Determine which pairs to evaluate
        if use_hnsw:
            # Only evaluate HNSW candidates + all query-overlap pairs
            pair_iter = set(hnsw_candidates.keys())
            # Also add all pairs where posts share GSC queries
            for i, j in combinations(range(len(post_list)), 2):
                pa, pb = post_list[i], post_list[j]
                qa = queries_by_post.get(pa["id"], set())
                qb = queries_by_post.get(pb["id"], set())
                if qa & qb:
                    pair_iter.add(tuple(sorted([pa["id"], pb["id"]])))
        else:
            # Small cluster: full scan
            pair_iter = set()
            for i, j in combinations(range(len(post_list)), 2):
                pair_iter.add(tuple(sorted([post_list[i]["id"], post_list[j]["id"]])))

        for pair_key in pair_iter:
            pid_a, pid_b = pair_key
            post_a = post_by_id[pid_a]
            post_b = post_by_id[pid_b]

            # ── Skip duplicate content (same hash = redirect issue, not cannibalization) ──
            hash_a = post_a.get("content_hash")
            hash_b = post_b.get("content_hash")
            if hash_a and hash_b and hash_a == hash_b:
                continue

            # ── Skip cross-language pairs (e.g. EN vs UK tool pages) ──
            lang_a = lang_map.get(pid_a)
            lang_b = lang_map.get(pid_b)
            if lang_a and lang_b and lang_a != lang_b:
                continue

            # ── Signal 1: Embedding cosine similarity ──
            cosine_sim = hnsw_candidates.get(pair_key) if use_hnsw else None
            if cosine_sim is None and post_a["embedding_text"] and post_b["embedding_text"]:
                row = await db.fetchrow(
                    """
                    SELECT 1 - (a.embedding <=> b.embedding) AS similarity
                    FROM post_embeddings a, post_embeddings b
                    WHERE a.post_id = $1 AND b.post_id = $2
                    """,
                    post_a["id"], post_b["id"],
                )
                if row:
                    cosine_sim = float(row["similarity"])

            # ── Signal 2: GSC query overlap ──
            queries_a = queries_by_post.get(post_a["id"], set())
            queries_b = queries_by_post.get(post_b["id"], set())
            shared_queries = queries_a & queries_b
            n_shared = len(shared_queries)

            # ── Determine if this is a cannibalization pair ──
            # Intent-aware: raise threshold when intents differ (different search purposes)
            intent_a = intent_map.get(post_a["id"])
            intent_b = intent_map.get(post_b["id"])
            effective_flag = t_flag
            if intent_a and intent_b and intent_a != intent_b:
                effective_flag = t_flag + 0.10

            is_cannibal = False
            if cosine_sim is not None and cosine_sim >= effective_flag:
                is_cannibal = True
            if n_shared >= MIN_SHARED_QUERIES:
                is_cannibal = True

            if not is_cannibal:
                continue

            # ── Compute blended cannibalization score ──
            # Replaces raw cosine as the primary scoring signal.
            # Answers: "Would a human typing a single search query be
            # satisfied by either post?"
            h_a = headings_map.get(post_a["id"], [])
            h_b = headings_map.get(post_b["id"], [])

            if n_shared > 0:
                # With GSC data, we have ground truth — query overlap proves cannibalization
                # Boost the blended score proportionally to shared queries
                blended, severity = self._compute_severity(
                    cosine_sim, n_shared,
                    t_flag=t_flag, t_high=t_high, t_critical=t_critical,
                ), None
                blended_score, blended_tier = compute_blended_cannibalization_score(
                    post_a, post_b, h_a, h_b, cosine_sim,
                )
                # GSC query overlap overrides the blended tier — shared queries = real cannibalization
                severity = self._compute_severity(
                    cosine_sim, n_shared,
                    t_flag=t_flag, t_high=t_high, t_critical=t_critical,
                )
                # Floor overlap_score at 0.5 when GSC confirms cannibalization.
                # Rationale: GSC shared queries are ground truth — if Google ranks both
                # posts for 3+ identical queries, they're cannibalizing regardless of what
                # the blended score says. The 0.5 floor ensures these pairs always appear
                # as "medium" severity or higher in the blended tier system (>0.35 = medium,
                # >0.55 = high), even if slug/entity/H2 signals are weak. Without this
                # floor, a pair sharing 5 GSC queries but with creative titles and different
                # URL structures could score 0.20 blended and be incorrectly filtered out.
                overlap_score = max(blended_score, 0.5)
            else:
                # No GSC data — use the blended score as the sole arbiter
                blended_score, blended_tier = compute_blended_cannibalization_score(
                    post_a, post_b, h_a, h_b, cosine_sim,
                )
                # Filter out "content series" (blended score too low)
                if blended_tier == "low":
                    continue
                severity = blended_tier
                overlap_score = blended_score

            # ── Determine stronger post ──
            # Normalize both signals to [0,1] so traffic doesn't completely dominate.
            # 70% traffic (rank-based percentile), 30% health score.
            # In crawl-only mode (no traffic), falls back to health score alone.
            health_a = health_map.get(post_a["id"], {"score": 0, "traffic": 0})
            health_b = health_map.get(post_b["id"], {"score": 0, "traffic": 0})

            traffic_a = health_a["traffic"]
            traffic_b = health_b["traffic"]
            has_traffic = traffic_a > 0 or traffic_b > 0

            if has_traffic:
                # Compute max traffic across all posts in health_map for normalization
                all_traffic = [h["traffic"] for h in health_map.values() if h["traffic"] > 0]
                max_traffic = max(all_traffic) if all_traffic else 1.0
                traffic_pct_a = traffic_a / max_traffic
                traffic_pct_b = traffic_b / max_traffic
                strength_a = (health_a["score"] / 100.0) * 0.3 + traffic_pct_a * 0.7
                strength_b = (health_b["score"] / 100.0) * 0.3 + traffic_pct_b * 0.7
            else:
                # Crawl-only: strength = health score alone
                strength_a = health_a["score"]
                strength_b = health_b["score"]

            stronger_id = post_a["id"] if strength_a >= strength_b else post_b["id"]

            # Numeric severity score (0-100)
            severity_score = min(100.0, blended_score * 100)

            # Resolution recommendation using blended score signals
            _slug_a = _extract_slug_core(post_a.get("url", ""))
            _slug_b = _extract_slug_core(post_b.get("url", ""))
            _slug_ov = len(_slug_a & _slug_b) / len(_slug_a | _slug_b) if (_slug_a | _slug_b) else 0.0
            _h2_jac = _h2_subtopic_jaccard(h_a, h_b)
            _title_tp = _title_topic_overlap(post_a.get("title", ""), post_b.get("title", ""))
            resolution = self._recommend_resolution(
                cosine_sim, severity,
                post_a.get("content_intent"), post_b.get("content_intent"),
                slug_overlap=_slug_ov, h2_jaccard=_h2_jac, title_topic=_title_tp,
            )

            # ── Insert pair ──
            await db.execute(
                """
                INSERT INTO cannibalization_pairs
                    (cluster_id, post_a_id, post_b_id, overlap_score, severity,
                     overlapping_queries, cosine_similarity, stronger_post_id,
                     severity_score, resolution)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                cluster_id,
                post_a["id"],
                post_b["id"],
                overlap_score,
                severity,
                list(shared_queries)[:50] if shared_queries else None,
                cosine_sim,
                stronger_id,
                severity_score,
                resolution,
            )

            pairs_found += 1

        return pairs_found

    async def _detect_cross_cluster(
        self, db: asyncpg.Connection, site_id: UUID,
        thresholds: dict[str, float] | None = None,
    ) -> int:
        """Detect cannibalization across different clusters using global HNSW scan.

        For each post, finds top 5 nearest neighbors across ALL posts (not just same
        cluster). For pairs in different clusters with cosine >= high threshold, evaluates
        the blended score and inserts if it passes. Adds O(5n) HNSW lookups.

        Returns the number of cross-cluster pairs found.
        """
        t_high = thresholds["high"] if thresholds else COSINE_THRESHOLD_HIGH

        # Fetch all posts with embeddings and their cluster assignments
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count,
                   p.content_hash, p.content_intent, p.language, p.headings,
                   pc.cluster_id
            FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE p.site_id = $1
              AND COALESCE(p.page_type, 'blog') NOT IN ('landing', 'index')
            ORDER BY p.id
            """,
            site_id,
        )

        if len(posts) < 2:
            return 0

        # Build lookup maps
        post_by_id = {p["id"]: p for p in posts}
        cluster_by_post = {p["id"]: p["cluster_id"] for p in posts}
        all_post_ids = [p["id"] for p in posts]

        # Get health scores for stronger post determination
        health_rows = await db.fetch(
            """
            SELECT post_id, composite_score, traffic_contribution
            FROM post_health_scores
            WHERE post_id = ANY($1::uuid[])
            """,
            all_post_ids,
        )
        health_map = {
            r["post_id"]: {
                "score": r["composite_score"] or 0.0,
                "traffic": r["traffic_contribution"] or 0.0,
            }
            for r in health_rows
        }

        # Existing pairs (avoid duplicates with per-cluster results)
        existing_pairs = set()
        existing_rows = await db.fetch(
            """
            SELECT post_a_id, post_b_id FROM cannibalization_pairs cp
            JOIN posts p ON cp.post_a_id = p.id
            WHERE p.site_id = $1
            """,
            site_id,
        )
        for r in existing_rows:
            existing_pairs.add(tuple(sorted([r["post_a_id"], r["post_b_id"]])))

        # Global HNSW scan: for each post, find top 5 nearest neighbors across ALL posts
        cross_candidates: dict[tuple[UUID, UUID], float] = {}
        for post in posts:
            neighbors = await db.fetch(
                """
                SELECT pe2.post_id,
                       1 - (pe1.embedding <=> pe2.embedding) AS similarity
                FROM post_embeddings pe1, post_embeddings pe2
                WHERE pe1.post_id = $1
                  AND pe2.post_id != $1
                  AND pe2.post_id = ANY($2::uuid[])
                ORDER BY pe1.embedding <=> pe2.embedding
                LIMIT 5
                """,
                post["id"], all_post_ids,
            )
            for n in neighbors:
                neighbor_id = n["post_id"]
                sim = float(n["similarity"])
                # Only interested in cross-cluster pairs above the high threshold
                if sim < t_high:
                    continue
                if cluster_by_post.get(post["id"]) == cluster_by_post.get(neighbor_id):
                    continue  # Same cluster — already handled by per-cluster detection
                pair_key = tuple(sorted([post["id"], neighbor_id]))
                if pair_key in existing_pairs:
                    continue  # Already detected in per-cluster scan
                cross_candidates[pair_key] = max(
                    cross_candidates.get(pair_key, 0), sim,
                )

        if not cross_candidates:
            return 0

        logger.info(
            "Cross-cluster HNSW scan: %d candidate pairs from %d posts",
            len(cross_candidates), len(posts),
        )

        pairs_found = 0
        for pair_key, cosine_sim in cross_candidates.items():
            pid_a, pid_b = pair_key
            post_a = post_by_id[pid_a]
            post_b = post_by_id[pid_b]

            # Skip duplicate content
            hash_a = post_a.get("content_hash")
            hash_b = post_b.get("content_hash")
            if hash_a and hash_b and hash_a == hash_b:
                continue

            # Skip cross-language
            lang_a = post_a.get("language")
            lang_b = post_b.get("language")
            if lang_a and lang_b and lang_a != lang_b:
                continue

            # Compute blended score
            h_a = post_a.get("headings") or []
            h_b = post_b.get("headings") or []
            blended_score, blended_tier = compute_blended_cannibalization_score(
                post_a, post_b, h_a, h_b, cosine_sim,
            )

            # Filter low-tier
            if blended_tier == "low":
                continue

            severity = blended_tier
            overlap_score = blended_score

            # Stronger post (normalized: 70% traffic percentile, 30% health)
            health_a = health_map.get(post_a["id"], {"score": 0, "traffic": 0})
            health_b = health_map.get(post_b["id"], {"score": 0, "traffic": 0})
            traffic_a = health_a["traffic"]
            traffic_b = health_b["traffic"]
            has_traffic = traffic_a > 0 or traffic_b > 0
            if has_traffic:
                all_traffic = [h["traffic"] for h in health_map.values() if h["traffic"] > 0]
                max_traffic = max(all_traffic) if all_traffic else 1.0
                strength_a = (health_a["score"] / 100.0) * 0.3 + (traffic_a / max_traffic) * 0.7
                strength_b = (health_b["score"] / 100.0) * 0.3 + (traffic_b / max_traffic) * 0.7
            else:
                strength_a = health_a["score"]
                strength_b = health_b["score"]
            stronger_id = post_a["id"] if strength_a >= strength_b else post_b["id"]

            severity_score = min(100.0, blended_score * 100)
            _slug_a = _extract_slug_core(post_a.get("url", ""))
            _slug_b = _extract_slug_core(post_b.get("url", ""))
            _slug_ov = len(_slug_a & _slug_b) / len(_slug_a | _slug_b) if (_slug_a | _slug_b) else 0.0
            _h2_jac = _h2_subtopic_jaccard(h_a, h_b)
            _title_tp = _title_topic_overlap(post_a.get("title", ""), post_b.get("title", ""))
            resolution = self._recommend_resolution(
                cosine_sim, severity,
                post_a.get("content_intent"), post_b.get("content_intent"),
                slug_overlap=_slug_ov, h2_jaccard=_h2_jac, title_topic=_title_tp,
            )

            # Use post_a's cluster_id for the pair (cluster_id is NOT NULL)
            cluster_id = cluster_by_post[pid_a]

            await db.execute(
                """
                INSERT INTO cannibalization_pairs
                    (cluster_id, post_a_id, post_b_id, overlap_score, severity,
                     overlapping_queries, cosine_similarity, stronger_post_id,
                     severity_score, resolution)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                cluster_id,
                post_a["id"],
                post_b["id"],
                overlap_score,
                severity,
                None,  # No GSC queries for cross-cluster
                cosine_sim,
                stronger_id,
                severity_score,
                resolution,
            )
            pairs_found += 1

        if pairs_found:
            logger.info(
                "Cross-cluster detection found %d additional pairs for site %s",
                pairs_found, site_id,
            )
        return pairs_found

    @staticmethod
    def _recommend_resolution(
        cosine_sim: float,
        severity: str,
        intent_a: str | None = None,
        intent_b: str | None = None,
        *,
        slug_overlap: float = 0.0,
        h2_jaccard: float = 0.0,
        title_topic: float = 0.0,
    ) -> str:
        """Recommend a resolution action for a cannibalization pair.

        Uses both raw cosine and blended score signals for more nuanced
        recommendations. Signal-aware rules take priority over generic ones.
        """
        if cosine_sim >= 0.95:
            return "redirect"  # Near-identical → 301 redirect shorter to longer
        if h2_jaccard > 0.7:
            return "merge"  # Same subtopics covered → combine into stronger
        if slug_overlap > 0.6:
            return "differentiate"  # Same target keyword but different content → refocus
        if intent_a and intent_b and intent_a != intent_b:
            return "differentiate"  # Different intents → refocus each on its intent
        if title_topic > 0.8 and cosine_sim < 0.7:
            return "differentiate"  # Same topic, different depth → refocus angles
        if severity == "critical" or cosine_sim >= 0.85:
            return "merge"  # High overlap, same intent → merge into stronger
        return "monitor"  # Moderate overlap → add internal link, monitor

    @staticmethod
    def _compute_severity(
        cosine_sim: float | None,
        n_shared: int,
        t_flag: float = COSINE_THRESHOLD_FLAG,
        t_high: float = COSINE_THRESHOLD_HIGH,
        t_critical: float = COSINE_THRESHOLD_CRITICAL,
    ) -> str:
        """Determine cannibalization severity from both signals.

        Accepts site-specific thresholds for calibrated detection.
        Falls back to module-level defaults if not provided.
        """
        has_cosine = cosine_sim is not None

        # Critical: very high cosine + shared queries
        if has_cosine and cosine_sim >= t_critical and n_shared > 0:
            return "critical"

        # High: high cosine, or moderate cosine + shared queries
        if has_cosine and cosine_sim >= t_high:
            return "high"
        if has_cosine and cosine_sim >= t_flag and n_shared > 0:
            return "high"

        # Medium: cosine above threshold, or many shared queries
        if has_cosine and cosine_sim >= t_flag:
            return "medium"
        if n_shared >= 3:
            return "medium"

        # Low: few shared queries only
        return "low"

    @staticmethod
    def _compute_overlap_score(
        cosine_sim: float | None,
        n_shared: int,
        queries_a: set[str],
        queries_b: set[str],
    ) -> float:
        """Compute combined overlap score (0.0-1.0) from both signals.

        Weighted average of cosine similarity and Jaccard similarity on queries.
        """
        scores = []

        if cosine_sim is not None:
            scores.append(cosine_sim)

        if queries_a or queries_b:
            union_size = len(queries_a | queries_b)
            if union_size > 0:
                jaccard = n_shared / union_size
                scores.append(jaccard)

        if not scores:
            return 0.0

        # If both signals present, weight cosine higher (70/30)
        if len(scores) == 2:
            return 0.7 * scores[0] + 0.3 * scores[1]

        return scores[0]
