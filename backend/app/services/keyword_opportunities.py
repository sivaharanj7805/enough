"""Keyword opportunity scoring — find where to focus effort.

Scores every query the site ranks for by:
  opportunity = volume_score × position_proximity × intent_value

A query with 10K impressions at position 12 is gold (close to page 1).
A query with 50 impressions at position 90 is a waste of time.

Uses GSC impressions as a volume proxy (no external API needed).

Scoring:
  volume_score: log-scaled impressions (0-40 points)
  position_proximity: closer to page 1 = higher (0-40 points)
  intent_value: transactional > commercial > informational (0-20 points)

Difficulty estimate: based on current position stability + competition
(how many other posts from the same site rank for it).
"""

import logging
import math
from uuid import UUID

import asyncpg

from app.services.intent_classifier import classify_query_intent

logger = logging.getLogger(__name__)


def score_opportunity(
    impressions: int,
    position: float,
    intent: str,
) -> float:
    """Score a keyword opportunity (0-100).

    Higher = better opportunity to pursue.
    """
    # Volume score (0-40): log-scaled impressions
    # 10 imp → ~13, 100 imp → ~27, 1000 imp → ~40
    if impressions <= 0:
        volume_score = 0.0
    else:
        volume_score = min(40.0, math.log10(impressions) * 13.3)

    # Position proximity (0-40): closer to top = higher opportunity
    # Position 1-3: already winning (lower opportunity for improvement)
    # Position 4-10: prime opportunity (highest score)
    # Position 11-20: good opportunity
    # Position 21-50: possible but harder
    # Position 50+: long shot
    if position <= 3:
        proximity_score = 20.0  # Already winning, less upside
    elif position <= 10:
        proximity_score = 40.0  # Prime position — small push = page 1
    elif position <= 20:
        proximity_score = 35.0  # Close to page 1
    elif position <= 50:
        proximity_score = 20.0 - (position - 20) * 0.5
        proximity_score = max(5.0, proximity_score)
    else:
        proximity_score = 2.0  # Long shot

    # Intent value (0-20)
    intent_scores = {
        "transactional": 20.0,   # Highest value — ready to buy
        "commercial": 15.0,      # Researching options
        "informational": 10.0,   # Learning
        "navigational": 5.0,     # Looking for specific site
    }
    intent_score = intent_scores.get(intent, 10.0)

    return volume_score + proximity_score + intent_score


def estimate_difficulty(position: float, site_posts_for_query: int) -> str:
    """Estimate keyword difficulty based on current position.

    This is a rough heuristic — real difficulty would need
    backlink data from Ahrefs/Moz.
    """
    if position <= 5:
        return "low"  # Already ranking well
    elif position <= 15:
        return "medium"
    elif position <= 30:
        return "high"
    else:
        return "very_high"


class KeywordOpportunityScorer:
    """Score keyword opportunities for a site."""

    async def score_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Score all keyword opportunities for a site.

        Returns number of opportunities scored.
        """
        logger.info("Scoring keyword opportunities for site %s", site_id)

        # Clear old opportunities
        await db.execute(
            "DELETE FROM keyword_opportunities WHERE site_id = $1", site_id,
        )

        # Get all queries with aggregated metrics
        queries = await db.fetch(
            """
            SELECT g.query, g.post_id,
                   SUM(g.impressions) AS total_impressions,
                   SUM(g.clicks) AS total_clicks,
                   AVG(g.avg_position) AS avg_position
            FROM gsc_metrics g
            JOIN posts p ON p.id = g.post_id
            WHERE p.site_id = $1
              AND g.date >= CURRENT_DATE - 90
            GROUP BY g.query, g.post_id
            HAVING SUM(g.impressions) >= 10
            ORDER BY SUM(g.impressions) DESC
            LIMIT 200
            """,
            site_id,
        )

        scored = 0
        for q in queries:
            intent = classify_query_intent(q["query"])
            position = float(q["avg_position"] or 50)
            impressions = q["total_impressions"] or 0

            opp_score = score_opportunity(impressions, position, intent)
            difficulty = estimate_difficulty(position, 1)

            # Determine action
            if position <= 10:
                action = "optimize_existing"
            elif position <= 30:
                action = "expand_content"
            else:
                action = "create_new"

            await db.execute(
                """
                INSERT INTO keyword_opportunities
                    (site_id, post_id, query, estimated_volume,
                     current_position, opportunity_score,
                     difficulty_estimate, action)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (site_id, query) DO UPDATE SET
                    post_id = $2, estimated_volume = $4,
                    current_position = $5, opportunity_score = $6,
                    difficulty_estimate = $7, action = $8,
                    detected_at = NOW()
                """,
                site_id, q["post_id"], q["query"],
                impressions, position, opp_score,
                difficulty, action,
            )
            scored += 1

        logger.info(
            "Scored %d keyword opportunities for site %s", scored, site_id,
        )
        return scored
