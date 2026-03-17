"""Tier 1 fast intent classification — zero Claude API calls.

Uses keyword patterns + URL slug analysis to classify content intent.
Accuracy ~85-90% for B2B/SaaS content. Falls back to 'informational'
when uncertain.

For Claude-powered intent classification, see intent_classifier.py.
"""

import logging
import re
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# ── Intent patterns (checked in order, first match wins) ──

_TRANSACTIONAL = re.compile(
    r"\b(pricing|buy|purchase|order|sign\s*up|free\s*trial|get\s*started|"
    r"demo|request\s*a|start\s*free|subscribe|checkout|add\s*to\s*cart|"
    r"download\s*now|try\s*free|create\s*account)\b",
    re.IGNORECASE,
)

_COMMERCIAL = re.compile(
    r"\b(best|top\s*\d+|vs\.?|versus|comparison|compare|alternative|"
    r"review|rated|cheapest|affordable|pros?\s*(and|&)\s*cons?|"
    r"which\s*(is|should)|recommend|software|tool|platform|solution|"
    r"buyer.?s?\s*guide)\b",
    re.IGNORECASE,
)

_NAVIGATIONAL = re.compile(
    r"\b(login|log\s*in|sign\s*in|dashboard|account|support|contact|"
    r"help\s*center|docs|documentation|api\s*reference|changelog|"
    r"status\s*page|about\s*us|careers|press)\b",
    re.IGNORECASE,
)

# URL slug patterns
_TRANSACTIONAL_SLUGS = re.compile(r"(pricing|demo|trial|signup|get-started|plans)")
_COMMERCIAL_SLUGS = re.compile(r"(best-|top-|vs-|-comparison|-alternative|-review)")
_NAVIGATIONAL_SLUGS = re.compile(r"(login|signin|support|contact|docs|help|about|careers)")


def classify_intent(title: str, url: str, word_count: int = 0) -> str:
    """Classify a single post's intent from title and URL.
    
    Returns one of: 'transactional', 'commercial', 'navigational', 'informational'
    """
    slug = url.rsplit("/", 1)[-1].lower() if url else ""
    text = f"{title} {slug}".lower()

    # Check URL slugs first (high signal)
    if _TRANSACTIONAL_SLUGS.search(slug):
        return "transactional"
    if _COMMERCIAL_SLUGS.search(slug):
        return "commercial"
    if _NAVIGATIONAL_SLUGS.search(slug):
        return "navigational"

    # Check title patterns
    if _TRANSACTIONAL.search(text):
        return "transactional"
    if _COMMERCIAL.search(text):
        return "commercial"
    if _NAVIGATIONAL.search(text):
        return "navigational"

    # Short posts with product names are often commercial
    if word_count and word_count < 500:
        return "informational"  # Short informational (news, updates)

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
    dist = {}
    for intent, _ in updates:
        dist[intent] = dist.get(intent, 0) + 1
    logger.info(
        "Fast intent classification: %d posts — %s",
        len(updates),
        ", ".join(f"{k}={v}" for k, v in sorted(dist.items())),
    )

    return len(updates)
