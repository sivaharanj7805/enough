"""Tier 1 fast intent classification — zero Claude API calls.

Uses keyword patterns + URL slug analysis to classify content intent.
Accuracy ~85-90% for B2B/SaaS content. Falls back to 'informational'
when uncertain.

Known limitation: uses only title + URL, zero body text analysis.
This means clickbait/opinion titles with transactional words ("Why I Won't
Buy...") can trigger false positives. A two-stage classifier with body text
verification would fix this but adds latency. Only implement if intent
drives downstream recommendations.

For Claude-powered intent classification, see intent_classifier.py.
"""

import logging
import re
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# ── Negation patterns — detected BEFORE intent classification ──
# If the title contains a negation near a transactional/commercial keyword,
# the keyword is opinion/editorial context, not actual purchase intent.
_NEGATION_PREFIX = re.compile(
    r"\b(won't|don't|can't|shouldn't|isn't|aren't|not|never|stop|avoid|"
    r"quit|hate|refuse|why i (won't|don't|didn't|can't))\s+",
    re.IGNORECASE,
)

# ── Intent patterns (checked in order, first match wins) ──

_TRANSACTIONAL = re.compile(
    r"\b(pricing|purchase|order|sign\s*up|free\s*trial|get\s*started|"
    r"demo|request\s*a|start\s*free|subscribe|checkout|add\s*to\s*cart|"
    r"download\s*now|try\s*free|create\s*account)\b",
    re.IGNORECASE,
)

# "buy" handled separately with negation check (see classify_intent)

_COMMERCIAL = re.compile(
    r"\b(vs\.?|versus|comparison|compare|alternative|"
    r"rated|cheapest|affordable|pros?\s*(and|&)\s*cons?|"
    r"which\s*(is|should)|buyer.?s?\s*guide)\b",
    re.IGNORECASE,
)

# "best" and "top N" and "review" handled separately — they need
# position/context checks to avoid matching opinion/editorial titles.

_NAVIGATIONAL = re.compile(
    r"\b(login|log\s*in|sign\s*in|dashboard|account|support|contact|"
    r"help\s*center|docs|documentation|api\s*reference|changelog|"
    r"status\s*page|about\s*us|careers|press)\b",
    re.IGNORECASE,
)

# URL slug patterns (high confidence — URL structure is intentional)
_TRANSACTIONAL_SLUGS = re.compile(r"(pricing|demo|trial|signup|get-started|plans)")
# Require best-/top-N at slug START to avoid matching mid-slug ("aristotles-top-3-tips")
_COMMERCIAL_SLUGS = re.compile(r"(^best-|^top-\d+-|vs-|-comparison|-alternative|-review$)")
# Require navigational keywords at the START of the slug to avoid
# matching prepositions like "about" in "know-about-writing-successfully"
# or "help" in "helpful-tips". True nav pages: /about, /about-us, /login
_NAVIGATIONAL_SLUGS = re.compile(r"^(?:login|signin|support|contact|docs|help|about|careers)(?:$|-)")


def _normalize_apostrophes(text: str) -> str:
    """Normalize curly/typographic apostrophes to ASCII straight apostrophe."""
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')


def _has_negation_before(text: str, keyword: str) -> bool:
    """Check if a negation word appears within 5 words before the keyword."""
    # Normalize curly apostrophes so "Won\u2019t" matches "won't" in the regex
    normalized = _normalize_apostrophes(text)
    idx = normalized.lower().find(keyword.lower())
    if idx <= 0:
        return False
    # Look at the 50 chars before the keyword for negation patterns
    prefix = normalized[max(0, idx - 50):idx]
    return bool(_NEGATION_PREFIX.search(prefix))


def classify_intent(title: str, url: str, word_count: int = 0) -> str:
    """Classify a single post's intent from title and URL.

    Known limitation: uses title + URL only, no body text.
    Returns one of: 'transactional', 'commercial', 'navigational', 'informational'
    """
    slug = url.rsplit("/", 1)[-1].lower() if url else ""
    # Normalize curly apostrophes before all matching
    title = _normalize_apostrophes(title)
    text = f"{title} {slug}".lower()

    # Check URL slugs first (high signal — URL structure is intentional)
    if _TRANSACTIONAL_SLUGS.search(slug):
        return "transactional"
    if _COMMERCIAL_SLUGS.search(slug):
        return "commercial"
    if _NAVIGATIONAL_SLUGS.search(slug):
        return "navigational"

    # Check title patterns with negation awareness
    # "buy" needs special handling:
    # - "Why I Won't Buy..." → informational (negation)
    # - "Makes People Buy" → informational (narrative/editorial)
    # - "Buy Now" / "Buy This Product" → transactional (imperative)
    # Only classify as transactional if "buy" is in a purchase context:
    # preceded by a call-to-action or followed by a product/now/today.
    if re.search(r"\bbuy\b", text, re.IGNORECASE):
        if not _has_negation_before(title, "buy"):
            # Narrative "buy" (people buy, customers buy, makes them buy) is informational
            if re.search(r"\b(?:people|customers?|them|makes?|helps?|gets?)\s+buy\b", text, re.IGNORECASE):
                pass  # Informational — editorial context
            elif re.search(r"\bbuy\s+(?:now|today|this|here|the|our|my)\b", text, re.IGNORECASE):
                return "transactional"  # Imperative — clear purchase intent
            elif "buy" in slug:
                return "transactional"  # Slug signal — intentional purchase page

    if _TRANSACTIONAL.search(text):
        return "transactional"

    # "best" / "top N" / "review" need position/context checks:
    # - "Best SEO Tools for 2026" → commercial (comparison intent)
    # - "Aristotle's Top 3 Tips for Blogging" → informational (editorial)
    # - "Don't Like Top 10 Lists?" → informational (opinion)
    # Heuristic: only classify as commercial if "best/top N" appears in
    # the first 3 words of the title (signals it's a listicle/comparison).
    title_words = title.split()[:4]
    title_start = " ".join(title_words).lower()
    if re.search(r"^(best|top\s*\d+|(\d+\s+)?best)", title_start):
        return "commercial"
    if re.search(r"\breview\b", text, re.IGNORECASE) and slug.endswith("-review"):
        return "commercial"
    # "recommend" is commercial only in "we recommend" / "I recommend" context
    if re.search(r"\b(i|we)\s+recommend\b", text, re.IGNORECASE):
        return "commercial"

    if _COMMERCIAL.search(text):
        return "commercial"

    if _NAVIGATIONAL.search(text):
        return "navigational"

    return "informational"


async def classify_site_fast(db: asyncpg.Connection, site_id: UUID) -> int:
    """Classify intent for all posts in a site using pattern matching.

    Returns number of posts classified.
    """
    posts = await db.fetch(
        "SELECT id, title, url, word_count FROM posts WHERE site_id = $1",
        site_id,
    )

    updates = []
    for post in posts:
        intent = classify_intent(
            post["title"] or "",
            post["url"] or "",
            post["word_count"] or 0,
        )
        updates.append((intent, post["id"]))

    await db.executemany(
        "UPDATE posts SET content_intent = $1 WHERE id = $2",
        updates,
    )

    # Log distribution
    dist: dict[str, int] = {}
    for intent, _ in updates:
        dist[intent] = dist.get(intent, 0) + 1
    logger.info(
        "Fast intent classification: %d posts — %s",
        len(updates),
        ", ".join(f"{k}={v}" for k, v in sorted(dist.items())),
    )

    return len(updates)
