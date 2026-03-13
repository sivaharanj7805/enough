"""SERP feature opportunity detection.

Identifies posts that could win featured snippets, People Also Ask,
or definition boxes with minor formatting changes.

Featured snippets get 42% of all clicks. If a post ranks #3-#8 for
a query that could trigger a featured snippet, reformatting that
section as a direct answer can jump it to position 0.

Detection approach:
1. Find queries where we rank 3-8 (prime snippet range)
2. Analyze post structure (has direct answer? FAQ? definitions?)
3. Generate specific formatting recommendations
"""

import json
import logging
import re
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Position range where featured snippet optimization is most impactful
SNIPPET_POSITION_MIN = 3.0
SNIPPET_POSITION_MAX = 8.0

# Query patterns that commonly trigger SERP features
DEFINITION_PATTERNS = [
    r'\bwhat\s+is\b', r'\bwhat\s+are\b', r'\bdefin(e|ition)\b',
    r'\bmean(s|ing)\b',
]
HOW_TO_PATTERNS = [
    r'\bhow\s+to\b', r'\bhow\s+do\b', r'\bstep(s)?\b',
    r'\bprocess\b', r'\bguide\b',
]
LIST_PATTERNS = [
    r'\bbest\b', r'\btop\s+\d+\b', r'\btypes\s+of\b',
    r'\bexamples?\b', r'\blist\b', r'\bways\s+to\b',
]
COMPARISON_PATTERNS = [
    r'\bvs\b', r'\bversus\b', r'\bcompar(e|ison)\b',
    r'\bdifference\b',
]


def detect_snippet_type(query: str) -> str | None:
    """Detect what type of SERP feature a query might trigger."""
    q = query.lower()

    for pattern in DEFINITION_PATTERNS:
        if re.search(pattern, q):
            return "definition_box"

    for pattern in HOW_TO_PATTERNS:
        if re.search(pattern, q):
            return "featured_snippet"

    for pattern in LIST_PATTERNS:
        if re.search(pattern, q):
            return "featured_snippet"

    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, q):
            return "featured_snippet"

    return None


def check_post_has_format(
    body_text: str | None,
    headings: list | str | None,
    snippet_type: str,
) -> bool:
    """Check if a post already has the formatting needed for a SERP feature."""
    if not body_text:
        return False

    body_lower = body_text.lower()

    if snippet_type == "definition_box":
        # Check for a definition pattern: "X is a/an/the..." or "X refers to..."
        # Must look like an actual definition, not just any sentence with "is"
        has_definition = bool(re.search(
            r'(?:is\s+(?:a|an|the|defined\s+as)|are\s+(?:a|an|the|defined\s+as)|refers?\s+to|means?\s+(?:a|an|the))[^.]{20,200}\.',
            body_lower,
        ))
        return has_definition

    if snippet_type == "featured_snippet":
        # Check for structured lists or step-by-step content
        has_list = body_lower.count('\n- ') >= 3 or body_lower.count('\n* ') >= 3
        has_numbered = bool(re.search(r'\n\d+[\.\)]\s', body_text))
        has_h2_structure = False
        if headings:
            if isinstance(headings, str):
                try:
                    headings = json.loads(headings)
                except (json.JSONDecodeError, TypeError):
                    headings = []
            if isinstance(headings, list):
                h2_count = sum(
                    1 for h in headings
                    if isinstance(h, dict) and h.get("level") in ("h2", "h3")
                )
                has_h2_structure = h2_count >= 3

        return has_list or has_numbered or has_h2_structure

    return False


class SERPFeatureDetector:
    """Detect SERP feature opportunities for a site."""

    async def detect_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Find SERP feature opportunities across all posts.

        Returns number of opportunities found.
        """
        logger.info("Detecting SERP feature opportunities for site %s", site_id)

        # Clear old opportunities
        await db.execute(
            "DELETE FROM serp_opportunities WHERE site_id = $1", site_id,
        )

        # Find queries where we rank 3-8 (prime snippet territory)
        candidates = await db.fetch(
            """
            SELECT g.post_id, g.query,
                   AVG(g.avg_position) AS avg_pos,
                   SUM(g.impressions) AS total_impressions,
                   p.title, p.body_text, p.headings
            FROM gsc_metrics g
            JOIN posts p ON p.id = g.post_id
            WHERE p.site_id = $1
              AND g.date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY g.post_id, g.query, p.title, p.body_text, p.headings
            HAVING AVG(g.avg_position) BETWEEN $2 AND $3
               AND SUM(g.impressions) >= 20
            ORDER BY SUM(g.impressions) DESC
            LIMIT 100
            """,
            site_id, SNIPPET_POSITION_MIN, SNIPPET_POSITION_MAX,
        )

        found = 0
        for cand in candidates:
            snippet_type = detect_snippet_type(cand["query"])
            if not snippet_type:
                continue

            has_format = check_post_has_format(
                cand["body_text"], cand["headings"], snippet_type,
            )

            # Generate recommendation
            if has_format:
                recommendation = (
                    f"Your post already has {snippet_type} formatting for "
                    f"\"{cand['query']}\". Ensure your answer is within the "
                    f"first 100 words after the relevant heading."
                )
            else:
                recommendation = self._generate_recommendation(
                    cand["query"], snippet_type, cand["title"],
                )

            await db.execute(
                """
                INSERT INTO serp_opportunities
                    (post_id, site_id, query, current_position,
                     opportunity_type, has_required_format,
                     recommendation, estimated_impact)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (post_id, query, opportunity_type) DO UPDATE SET
                    current_position = $4, has_required_format = $6,
                    recommendation = $7, detected_at = NOW()
                """,
                cand["post_id"], site_id, cand["query"],
                float(cand["avg_pos"]),
                snippet_type, has_format, recommendation,
                "high" if not has_format else "medium",
            )
            found += 1

        logger.info(
            "SERP feature detection complete for site %s: %d opportunities",
            site_id, found,
        )
        return found

    @staticmethod
    def _generate_recommendation(
        query: str, snippet_type: str, title: str,
    ) -> str:
        """Generate a specific formatting recommendation."""
        if snippet_type == "definition_box":
            return (
                f"Add a 40-60 word definition paragraph directly after your H1 "
                f"or relevant H2 heading. Start with \"{query.split()[0].title()} "
                f"is...\" or \"A {query} is...\". Google pulls concise definitions "
                f"for featured snippets."
            )

        if snippet_type == "featured_snippet":
            if any(re.search(p, query.lower()) for p in HOW_TO_PATTERNS):
                return (
                    f"Add a numbered step-by-step section (5-8 steps) with an H2 "
                    f"heading like \"How to {query.replace('how to ', '')}\". "
                    f"Each step should be a short paragraph (1-2 sentences)."
                )
            if any(re.search(p, query.lower()) for p in LIST_PATTERNS):
                return (
                    f"Add a bulleted list section with 5-10 items under an H2 "
                    f"heading that matches the query. Keep each item to 1-2 lines."
                )
            return (
                f"Restructure the relevant section of \"{title}\" with clear H2 "
                f"headings and concise paragraphs (40-60 words each). Google "
                f"favors well-structured content for featured snippets."
            )

        return f"Optimize formatting for {snippet_type} opportunity on \"{query}\"."
