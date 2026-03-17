"""Readability scoring for blog posts.

Computes Flesch Reading Ease and Flesch-Kincaid Grade Level.
Not a direct Google ranking factor (John Mueller confirmed), but
63% of top-ranking results score 60-80 on Flesch Reading Ease.
Poor readability → higher bounce → worse engagement → worse rankings.

Uses textstat library for computation (no API calls needed).

Scoring guide:
  90-100: Very easy (5th grade)
  80-89:  Easy (6th grade)
  70-79:  Fairly easy (7th grade)
  60-69:  Standard (8th-9th grade) ← sweet spot for most blogs
  50-59:  Fairly difficult (10th-12th grade)
  30-49:  Difficult (college)
  0-29:   Very confusing (graduate)
"""

import json
import logging
import re
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Thresholds for problem detection
READABILITY_TOO_COMPLEX = 40.0   # Below this = flag as problem
READABILITY_IDEAL_MIN = 60.0
READABILITY_IDEAL_MAX = 80.0


def compute_flesch_reading_ease(text: str) -> float:
    """Compute Flesch Reading Ease score (0-100).

    Formula: 206.835 - 1.015 × (words/sentences) - 84.6 × (syllables/words)

    Pure Python — no external dependency needed.
    """
    sentences = _count_sentences(text)
    words = _count_words(text)
    syllables = _count_syllables(text)

    if words == 0 or sentences == 0:
        return 0.0

    score = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    return max(0.0, min(100.0, score))


def compute_grade_level(text: str) -> float:
    """Compute Flesch-Kincaid Grade Level.

    Formula: 0.39 × (words/sentences) + 11.8 × (syllables/words) - 15.59

    Returns US school grade level (e.g., 8.0 = 8th grade).
    """
    sentences = _count_sentences(text)
    words = _count_words(text)
    syllables = _count_syllables(text)

    if words == 0 or sentences == 0:
        return 0.0

    grade = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    return max(0.0, round(grade, 1))


def _count_sentences(text: str) -> int:
    """Count sentences using punctuation markers."""
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    # Filter empty strings
    return max(1, len([s for s in sentences if s.strip()]))


def _count_words(text: str) -> int:
    """Count words in text."""
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    return len(words)


def _count_syllables(text: str) -> int:
    """Estimate syllable count using vowel groups."""
    text = text.lower()
    words = re.findall(r'\b[a-z]+\b', text)
    total = 0
    for word in words:
        total += _syllables_in_word(word)
    return max(1, total)


def _syllables_in_word(word: str) -> int:
    """Estimate syllables in a single word."""
    word = word.lower().strip()
    if len(word) <= 2:
        return 1

    # Remove trailing 'e' (silent e)
    if word.endswith('e') and not word.endswith('le'):
        word = word[:-1]

    # Count vowel groups
    count = len(re.findall(r'[aeiouy]+', word))
    return max(1, count)


class ReadabilityScorer:
    """Score readability for all posts in a site."""

    async def score_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Compute readability scores for all posts in a site.

        Returns the number of posts scored.
        """
        logger.info("Computing readability scores for site %s", site_id)

        posts = await db.fetch(
            """
            SELECT id, body_text
            FROM posts
            WHERE site_id = $1 AND body_text IS NOT NULL AND LENGTH(body_text) > 100
            """,
            site_id,
        )

        scored = 0
        for post in posts:
            text = post["body_text"]

            # Language detection — Flesch-Kincaid only valid for English
            try:
                from langdetect import detect as detect_lang
                lang = detect_lang(text[:1000])
                if lang != "en":
                    logger.debug("Skipping non-English post (detected: %s): %s", lang, post["id"])
                    continue
            except Exception:
                pass  # Default to scoring if detection fails

            fre = compute_flesch_reading_ease(text)
            grade = compute_grade_level(text)

            # Paragraph-level breakdown: find hardest paragraphs
            paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
            hard_paragraphs = []
            for i, para in enumerate(paragraphs):
                para_fre = compute_flesch_reading_ease(para)
                if para_fre < 30 and len(para.split()) > 20:  # Hard to read
                    hard_paragraphs.append({
                        "index": i,
                        "flesch": round(para_fre, 1),
                        "preview": para[:100],
                    })
            # Keep top 3 hardest
            hard_paragraphs.sort(key=lambda x: x["flesch"])
            readability_details = json.dumps(hard_paragraphs[:3]) if hard_paragraphs else None

            await db.execute(
                """
                UPDATE posts
                SET readability_score = $1, grade_level = $2
                WHERE id = $3
                """,
                fre, grade, post["id"],
            )
            scored += 1

        logger.info("Scored readability for %d posts in site %s", scored, site_id)
        return scored
