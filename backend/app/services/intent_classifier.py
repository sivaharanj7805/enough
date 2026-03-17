"""Search intent classification for posts and queries.

Classifies every post as informational, transactional, commercial,
or navigational. Cross-references with GSC query intent to detect
intent mismatch — one of the most common underperformance reasons.

A "Best CRM Software 2024" post (commercial) ranking for
"what is CRM" (informational) → users bounce because the content
doesn't answer their question.

Uses Claude for post classification (batched) and rule-based
heuristics for query intent detection.
"""

import json
import logging
import re
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Query intent patterns (rule-based — fast, no API cost)
INFORMATIONAL_PATTERNS = [
    r'\bhow\s+to\b', r'\bwhat\s+is\b', r'\bwhat\s+are\b', r'\bwhy\b',
    r'\bguide\b', r'\btutorial\b', r'\bexplain\b', r'\bdefin(e|ition)\b',
    r'\bexample\b', r'\bmean(s|ing)\b', r'\btips\b', r'\blearn\b',
    r'\bunderstand\b', r'\bwhen\s+(to|should)\b',
]

TRANSACTIONAL_PATTERNS = [
    r'\bbuy\b', r'\bpurchas(e|ing)\b', r'\border\b', r'\bsubscri(be|ption)\b',
    r'\bdownload\b', r'\bsign\s*up\b', r'\bregister\b', r'\bfree\s+trial\b',
    r'\bpric(e|ing)\b', r'\bdiscount\b', r'\bcoupon\b', r'\bdeal\b',
    r'\bcheap\b', r'\baffordable\b',
]

COMMERCIAL_PATTERNS = [
    r'\bbest\b', r'\btop\s+\d+\b', r'\bvs\b', r'\bversus\b',
    r'\bcompar(e|ison)\b', r'\breview\b', r'\balternativ(e|es)\b',
    r'\bpros\s+and\s+cons\b', r'\bworth\s+it\b', r'\brecommend\b',
]

NAVIGATIONAL_PATTERNS = [
    r'\blogin\b', r'\bsign\s*in\b', r'\bdashboard\b', r'\baccount\b',
    r'\b(\.com|\.io|\.org)\b', r'\bofficial\b', r'\bwebsite\b',
]


def classify_query_intent(query: str) -> str:
    """Classify a search query's intent using rule-based patterns.

    Returns: informational, transactional, commercial, navigational
    """
    q = query.lower().strip()

    # Check patterns in priority order
    for pattern in TRANSACTIONAL_PATTERNS:
        if re.search(pattern, q):
            return "transactional"

    for pattern in COMMERCIAL_PATTERNS:
        if re.search(pattern, q):
            return "commercial"

    for pattern in NAVIGATIONAL_PATTERNS:
        if re.search(pattern, q):
            return "navigational"

    for pattern in INFORMATIONAL_PATTERNS:
        if re.search(pattern, q):
            return "informational"

    # Default: informational (most common intent for blog content)
    return "informational"


class IntentClassifier:
    """Classify content intent and detect mismatches."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def classify_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict[str, int]:
        """Classify intent for all posts and detect mismatches.

        Returns dict of intent → count.
        """
        logger.info("Classifying content intent for site %s", site_id)

        posts = await db.fetch(
            """
            SELECT id, title, body_text, meta_description
            FROM posts
            WHERE site_id = $1
            ORDER BY id
            """,
            site_id,
        )

        if not posts:
            return {}

        # Batch classify via Claude (10 posts per batch)
        intent_counts: dict[str, int] = {}
        batch_size = 10

        for i in range(0, len(posts), batch_size):
            batch = posts[i:i + batch_size]
            intents = await self._classify_batch(batch)

            for post, intent in zip(batch, intents):
                await db.execute(
                    "UPDATE posts SET content_intent = $1 WHERE id = $2",
                    intent, post["id"],
                )
                intent_counts[intent] = intent_counts.get(intent, 0) + 1

        # Detect intent mismatches
        mismatch_count = await self._detect_mismatches(db, site_id)

        logger.info(
            "Intent classification complete for site %s: %s, %d mismatches",
            site_id, intent_counts, mismatch_count,
        )
        return intent_counts

    async def _classify_batch(
        self, posts: list[asyncpg.Record],
    ) -> list[str]:
        """Classify intent for a batch of posts via Claude."""
        posts_text = ""
        for idx, post in enumerate(posts):
            title = post["title"] or "Untitled"
            meta = (post["meta_description"] or "")[:200]
            body_preview = (post["body_text"] or "")[:300]
            posts_text += f"\n[{idx + 1}] Title: {title}\nMeta: {meta}\nPreview: {body_preview}\n"

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=200,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classify each blog post's search intent.\n\n"
                        f"{posts_text}\n\n"
                        f"For each post, respond with one line in this format:\n"
                        f"primary_intent|sub_intent|confidence\n\n"
                        f"Where:\n"
                        f"- primary_intent: informational, transactional, commercial, or navigational\n"
                        f"- sub_intent: educational, tutorial, comparison, review, listicle, news, opinion, case_study, tool, or pricing\n"
                        f"- confidence: 0.0-1.0\n\n"
                        f"Example: informational|tutorial|0.9\n"
                        f"No numbers, no explanations, just the three values per line."
                    ),
                }],
            )
            text = response.content[0].text.strip()
            intents = []
            self._last_batch_details = []  # Store sub-intent + confidence
            for line in text.split("\n"):
                line = line.strip().lower()
                parts = line.split("|")
                primary = parts[0].strip() if parts else "informational"
                sub = parts[1].strip() if len(parts) > 1 else ""
                conf = float(parts[2].strip()) if len(parts) > 2 else 0.7

                if primary not in ("informational", "transactional", "commercial", "navigational"):
                    primary = "informational"
                intents.append(primary)
                self._last_batch_details.append({"sub_intent": sub, "confidence": conf})

            # Pad with "informational" if Claude returned fewer results
            while len(intents) < len(posts):
                intents.append("informational")
                self._last_batch_details.append({"sub_intent": "", "confidence": 0.5})

            return intents[:len(posts)]
        except Exception as e:
            logger.error("Claude intent classification failed: %s", e)
            return ["informational"] * len(posts)

    async def _detect_mismatches(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect intent mismatches between post content and ranking queries.

        A mismatch occurs when a post's content intent doesn't match
        the intent of its top-ranking queries.
        """
        # Get posts with their intent and top queries
        rows = await db.fetch(
            """
            SELECT p.id, p.title, p.content_intent,
                   array_agg(DISTINCT g.query) AS queries
            FROM posts p
            JOIN gsc_metrics g ON g.post_id = p.id
            WHERE p.site_id = $1
              AND p.content_intent IS NOT NULL
              AND g.date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY p.id, p.title, p.content_intent
            """,
            site_id,
        )

        mismatch_count = 0
        for row in rows:
            post_intent = row["content_intent"]
            queries = row["queries"] or []

            # Classify each query's intent
            query_intents = [classify_query_intent(q) for q in queries if q]
            if not query_intents:
                continue

            # Find dominant query intent
            from collections import Counter
            intent_counter = Counter(query_intents)
            dominant_query_intent = intent_counter.most_common(1)[0][0]

            # Mismatch if post intent ≠ dominant query intent
            if post_intent != dominant_query_intent:
                # Insert as a content problem
                await db.execute(
                    """
                    INSERT INTO content_problems
                        (post_id, site_id, problem_type, severity, details)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (post_id, problem_type) DO UPDATE SET
                        severity = $4, details = $5, detected_at = NOW()
                    """,
                    row["id"], site_id, "intent_mismatch", "high",
                    json.dumps({
                        "post_intent": post_intent,
                        "dominant_query_intent": dominant_query_intent,
                        "sample_queries": queries[:5],
                        "query_intent_breakdown": dict(intent_counter),
                    }),
                )
                mismatch_count += 1

        return mismatch_count
