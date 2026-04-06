"""Analysis diff — compare before/after when the pipeline re-runs.

Generates a structured diff showing:
- Score change (before → after)
- Factor changes (which factors improved/declined)
- Improvements (problems resolved, schema added, etc.)
- New issues (new problems, stale posts, etc.)
- Degradations (health drops, traffic loss indicators)
"""

import json
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def generate_and_store_diff(
    db: asyncpg.Connection,
    site_id: UUID,
    prev_score: float | None,
    prev_factors: dict | None,
    new_score: float,
    new_factors: dict,
) -> dict | None:
    """Compare previous and new analysis results, store the diff.

    Called after health scoring inserts a new health_score_history row.
    Returns the diff dict or None if no previous snapshot exists.
    """
    if prev_score is None or prev_factors is None:
        return None

    score_delta = round(new_score - prev_score, 2)

    # Factor changes — compare each factor
    factor_changes = []
    all_factor_keys = {"engagement", "freshness", "content_depth", "internal_links",
                       "technical_seo", "ranking", "traffic", "ai_readiness"}
    for key in all_factor_keys:
        before = prev_factors.get(key)
        after = new_factors.get(key)
        if before is not None and after is not None:
            delta = round(float(after) - float(before), 1)
            if abs(delta) >= 0.5:  # Only show meaningful changes
                factor_changes.append({
                    "factor": key,
                    "before": round(float(before), 1),
                    "after": round(float(after), 1),
                    "delta": delta,
                })
    # Sort by absolute delta descending
    factor_changes.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # Detect improvements, new issues, degradations from problem counts
    improvements = await _detect_improvements(db, site_id)
    new_issues = await _detect_new_issues(db, site_id)
    degradations = []

    # Add score-based degradation
    if score_delta < -3:
        degradations.append(f"Overall health score dropped {abs(score_delta):.0f} points")

    # Add factor-based degradations
    for fc in factor_changes:
        if fc["delta"] < -5:
            label = fc["factor"].replace("_", " ").title()
            degradations.append(f"{label} declined from {fc['before']:.0f} to {fc['after']:.0f}")

    diff = {
        "score_before": round(prev_score, 1),
        "score_after": round(new_score, 1),
        "score_delta": round(score_delta, 1),
        "factor_changes": factor_changes,
        "improvements": improvements,
        "new_issues": new_issues,
        "degradations": degradations,
    }

    # Store in database
    try:
        await db.execute(
            """INSERT INTO analysis_diffs
                   (site_id, score_before, score_after, score_delta,
                    factor_changes, improvements, new_issues, degradations)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)""",
            site_id, prev_score, new_score, score_delta,
            json.dumps(factor_changes), json.dumps(improvements),
            json.dumps(new_issues), json.dumps(degradations),
        )
    except Exception:
        logger.warning("Failed to store analysis diff for site %s", site_id, exc_info=True)

    return diff


async def _detect_improvements(db: asyncpg.Connection, site_id: UUID) -> list[str]:
    """Detect improvements since last analysis."""
    improvements: list[str] = []

    # Check for resolved problems (resolved_at within last 30 days)
    resolved = await db.fetchval(
        """SELECT COUNT(*) FROM content_problems cp
           JOIN posts p ON p.id = cp.post_id
           WHERE p.site_id = $1 AND cp.resolved_at IS NOT NULL
             AND cp.resolved_at > NOW() - INTERVAL '30 days'""",
        site_id,
    )
    if resolved and resolved > 0:
        improvements.append(f"{resolved} issue{'s' if resolved != 1 else ''} resolved since last analysis")

    # Check for posts that gained schema (schema_score went from 0 to >0)
    schema_gain = await db.fetchval(
        """SELECT COUNT(*) FROM post_health_scores phs
           JOIN posts p ON p.id = phs.post_id
           WHERE p.site_id = $1 AND phs.schema_score > 0""",
        site_id,
    )
    if schema_gain and schema_gain > 0:
        improvements.append(f"{schema_gain} post{'s' if schema_gain != 1 else ''} now have structured data")

    # Check for completed recommendations
    completed_recent = await db.fetchval(
        """SELECT COUNT(*) FROM recommendations
           WHERE site_id = $1 AND status = 'completed'
             AND updated_at > NOW() - INTERVAL '30 days'""",
        site_id,
    )
    if completed_recent and completed_recent > 0:
        improvements.append(f"{completed_recent} recommendation{'s' if completed_recent != 1 else ''} completed")

    return improvements


async def _detect_new_issues(db: asyncpg.Connection, site_id: UUID) -> list[str]:
    """Detect new issues found in this analysis."""
    new_issues: list[str] = []

    # New problems detected recently (within last 7 days = likely this run)
    new_problems = await db.fetch(
        """SELECT problem_type, COUNT(*) AS cnt
           FROM content_problems cp
           JOIN posts p ON p.id = cp.post_id
           WHERE p.site_id = $1 AND cp.resolved_at IS NULL
             AND cp.detected_at > NOW() - INTERVAL '7 days'
           GROUP BY problem_type""",
        site_id,
    )
    for row in new_problems:
        ptype = row["problem_type"].replace("_", " ")
        new_issues.append(f"{row['cnt']} new {ptype} issue{'s' if row['cnt'] != 1 else ''} detected")

    # Stale posts (modified_date > 12 months ago)
    stale = await db.fetchval(
        """SELECT COUNT(*) FROM posts
           WHERE site_id = $1 AND modified_date IS NOT NULL
             AND modified_date < NOW() - INTERVAL '12 months'""",
        site_id,
    )
    if stale and stale > 0:
        new_issues.append(f"{stale} post{'s' if stale != 1 else ''} haven't been updated in over 12 months")

    return new_issues
