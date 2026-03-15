"""Intent-aware cannibalization filtering — eliminates false positives.

Two posts targeting the same keyword but different intents are NOT
cannibalizing. "API Authentication Tutorial" (informational) and
"API Authentication Service Pricing" (transactional) can coexist
in SERPs because Google serves different intents in different positions.

This filter:
1. Takes cannibalization pairs from the detection pipeline
2. Looks up content_intent for both posts
3. If intents differ → downgrade cannibalization score by 50%
4. If intents are the same → keep original score (true cannibalization)

Applied as a post-processing step after the main cannibalization detector.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# How much to downgrade score when intents differ
INTENT_MISMATCH_PENALTY = 0.50

# Intent compatibility matrix: which pairs are truly competing
# Same intent = 1.0 (full cannibalization risk)
# Compatible intents = 0.7 (some overlap)
# Different intents = 0.5 (low risk, downgrade)
INTENT_OVERLAP: dict[tuple[str, str], float] = {
    # Same intent — full risk
    ("informational", "informational"): 1.0,
    ("commercial", "commercial"): 1.0,
    ("transactional", "transactional"): 1.0,
    ("navigational", "navigational"): 1.0,

    # Compatible — some overlap
    ("informational", "commercial"): 0.7,
    ("commercial", "informational"): 0.7,
    ("commercial", "transactional"): 0.7,
    ("transactional", "commercial"): 0.7,

    # Different — low risk
    ("informational", "transactional"): 0.5,
    ("transactional", "informational"): 0.5,
    ("informational", "navigational"): 0.3,
    ("navigational", "informational"): 0.3,
    ("commercial", "navigational"): 0.4,
    ("navigational", "commercial"): 0.4,
    ("transactional", "navigational"): 0.3,
    ("navigational", "transactional"): 0.3,
}


def get_intent_multiplier(intent_a: str | None, intent_b: str | None) -> float:
    """Get the cannibalization score multiplier based on intent pair.

    Returns:
        1.0 = same intent, full cannibalization risk
        0.7 = compatible intents, some overlap
        0.5 = different intents, reduced risk
        0.3 = very different intents, minimal risk
    """
    if not intent_a or not intent_b:
        # Unknown intent — don't filter, keep original score
        return 1.0

    intent_a = intent_a.lower().strip()
    intent_b = intent_b.lower().strip()

    return INTENT_OVERLAP.get((intent_a, intent_b), 0.5)


@dataclass
class FilteredPair:
    """A cannibalization pair after intent filtering."""
    post_a_id: UUID
    post_b_id: UUID
    original_score: float
    filtered_score: float
    intent_a: str | None
    intent_b: str | None
    multiplier: float
    was_downgraded: bool


async def filter_cannibalization_by_intent(
    db: asyncpg.Connection,
    site_id: UUID,
) -> dict[str, int]:
    """Apply intent-aware filtering to all cannibalization pairs.

    For each pair:
    1. Look up content_intent for both posts
    2. Compute intent multiplier
    3. If different intents → reduce similarity score
    4. Update severity based on new score

    Returns: {"total": N, "downgraded": M, "unchanged": K}
    """
    pairs = await db.fetch(
        """
        SELECT cp.id, cp.post_a_id, cp.post_b_id, cp.similarity,
               cp.severity,
               pa.content_intent AS intent_a,
               pb.content_intent AS intent_b
        FROM cannibalization_pairs cp
        JOIN posts pa ON pa.id = cp.post_a_id
        JOIN posts pb ON pb.id = cp.post_b_id
        WHERE pa.site_id = $1
        """,
        site_id,
    )

    total = len(pairs)
    downgraded = 0
    unchanged = 0

    for pair in pairs:
        multiplier = get_intent_multiplier(
            pair["intent_a"], pair["intent_b"],
        )

        if multiplier < 1.0:
            new_score = pair["similarity"] * multiplier

            # Reclassify severity based on new score
            if new_score >= 0.60:
                new_severity = "critical"
            elif new_score >= 0.50:
                new_severity = "high"
            elif new_score >= 0.40:
                new_severity = "medium"
            else:
                new_severity = "low"

            await db.execute(
                """
                UPDATE cannibalization_pairs
                SET similarity = $1, severity = $2
                WHERE id = $3
                """,
                new_score, new_severity, pair["id"],
            )
            downgraded += 1

            logger.info(
                "Downgraded pair %s↔%s: %s(%s) vs %s(%s), "
                "score %.3f→%.3f, severity %s→%s",
                pair["post_a_id"], pair["post_b_id"],
                pair["intent_a"], pair["intent_b"],
                pair["similarity"], new_score,
                pair["severity"], new_severity,
            )
        else:
            unchanged += 1

    result = {"total": total, "downgraded": downgraded, "unchanged": unchanged}
    logger.info("Intent filter applied to %d pairs: %s", total, result)
    return result
