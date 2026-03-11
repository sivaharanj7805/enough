"""Cannibalization detection between posts within topic clusters.

Detects keyword overlap using Jaccard similarity on GSC query sets,
scores severity based on position proximity and traffic split factors.
"""

import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

OVERLAP_THRESHOLD = 0.30  # Minimum Jaccard similarity to flag as cannibalizing
MAX_QUERIES_PER_POST = 50  # Limit queries to avoid O(n²) explosion


class CannibalizationDetector:
    """Detect keyword cannibalization within topic clusters."""

    async def detect_for_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run cannibalization detection across all clusters for a site.

        Requires clusters to exist (run clustering first).
        Returns the number of cannibalization pairs found.
        """
        logger.info("Starting cannibalization detection for site %s", site_id)

        # Clear old cannibalization data for this site
        await db.execute(
            """
            DELETE FROM cannibalization_pairs
            WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
            """,
            site_id,
        )

        clusters = await db.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id,
        )
        if not clusters:
            logger.warning("No clusters found for site %s — run clustering first", site_id)
            return 0

        total_pairs = 0
        for cluster_row in clusters:
            cluster_id = cluster_row["id"]
            pairs = await self._detect_in_cluster(db, cluster_id)
            total_pairs += pairs

        logger.info(
            "Cannibalization detection complete for site %s — %d pairs found",
            site_id, total_pairs,
        )
        return total_pairs

    async def _detect_in_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID,
    ) -> int:
        """Detect cannibalization pairs within a single cluster."""
        # Get all posts in this cluster
        post_rows = await db.fetch(
            """
            SELECT p.id, p.title
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            WHERE pc.cluster_id = $1
            """,
            cluster_id,
        )

        if len(post_rows) < 2:
            return 0

        # Build query sets and metrics for each post
        post_data: dict[UUID, dict] = {}
        for row in post_rows:
            post_id = row["id"]
            # Fetch top queries with aggregated metrics
            query_rows = await db.fetch(
                """
                SELECT query,
                       SUM(clicks) AS total_clicks,
                       AVG(avg_position) AS avg_pos
                FROM gsc_metrics
                WHERE post_id = $1
                GROUP BY query
                ORDER BY SUM(clicks) DESC
                LIMIT $2
                """,
                post_id, MAX_QUERIES_PER_POST,
            )
            post_data[post_id] = {
                "title": row["title"],
                "queries": {r["query"] for r in query_rows},
                "query_clicks": {r["query"]: r["total_clicks"] for r in query_rows},
                "avg_position": (
                    sum(r["avg_pos"] for r in query_rows) / len(query_rows)
                    if query_rows else 100.0
                ),
                "total_clicks": sum(r["total_clicks"] for r in query_rows),
            }

        # Compare all pairs
        post_ids = list(post_data.keys())
        pairs_found = 0

        for i in range(len(post_ids)):
            for j in range(i + 1, len(post_ids)):
                pid_a = post_ids[i]
                pid_b = post_ids[j]
                data_a = post_data[pid_a]
                data_b = post_data[pid_b]

                queries_a = data_a["queries"]
                queries_b = data_b["queries"]

                if not queries_a or not queries_b:
                    continue

                # Jaccard similarity
                intersection = queries_a & queries_b
                union = queries_a | queries_b
                jaccard = len(intersection) / len(union) if union else 0.0

                if jaccard < OVERLAP_THRESHOLD:
                    continue

                # Calculate severity factors
                pos_a = data_a["avg_position"]
                pos_b = data_b["avg_position"]
                pos_factor = _position_proximity_factor(pos_a, pos_b)

                clicks_a = data_a["total_clicks"]
                clicks_b = data_b["total_clicks"]
                split_factor = _traffic_split_factor(clicks_a, clicks_b)

                severity_score = jaccard * pos_factor * split_factor
                severity_label = _severity_label(severity_score)

                overlapping = sorted(intersection)[:50]  # Cap stored queries

                await db.execute(
                    """
                    INSERT INTO cannibalization_pairs
                        (cluster_id, post_a_id, post_b_id, overlap_score,
                         severity, overlapping_queries)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    cluster_id, pid_a, pid_b, severity_score,
                    severity_label, overlapping,
                )
                pairs_found += 1

        return pairs_found


def _position_proximity_factor(pos_a: float, pos_b: float) -> float:
    """Calculate position proximity factor for severity scoring."""
    if pos_a <= 5 and pos_b <= 5:
        return 0.8
    if pos_a <= 20 and pos_b <= 20:
        return 1.0
    low = min(pos_a, pos_b)
    high = max(pos_a, pos_b)
    if low <= 10 and high <= 50:
        return 0.5
    if low <= 10 and high > 50:
        return 0.2
    return 0.3  # Default moderate


def _traffic_split_factor(clicks_a: int, clicks_b: int) -> float:
    """Calculate traffic split factor based on click distribution."""
    total = clicks_a + clicks_b
    if total == 0:
        return 0.5  # No data — assume moderate

    ratio = min(clicks_a, clicks_b) / total  # 0.0 = 100/0, 0.5 = 50/50

    if ratio >= 0.45:
        return 1.0  # ~50/50
    if ratio >= 0.25:
        return 0.7  # ~70/30
    if ratio >= 0.08:
        return 0.3  # ~90/10
    return 0.1  # ~95/5


def _severity_label(score: float) -> str:
    """Map severity score to label."""
    if score > 0.7:
        return "critical"
    if score > 0.5:
        return "high"
    if score > 0.3:
        return "medium"
    return "low"
