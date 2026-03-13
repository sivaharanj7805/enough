"""Cannibalization detection via embedding cosine similarity + GSC query overlap.

Research-informed approach (two-signal detection):
1. Embedding cosine similarity > 0.85 between posts in the same cluster
2. GSC query overlap — posts ranking for the same search queries

A pair is flagged as cannibalization when EITHER condition is met,
with higher severity when BOTH signals are present.

Severity levels:
- critical: cosine > 0.95 AND shared queries
- high: cosine > 0.90 OR (cosine > 0.85 AND shared queries)
- medium: cosine > 0.85 OR 3+ shared queries
- low: 1-2 shared queries only

The "stronger post" is determined by composite health score + traffic.
"""

import logging
from itertools import combinations
from uuid import UUID

import asyncpg

from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Cosine similarity thresholds (using similarity = 1 - distance)
COSINE_THRESHOLD_FLAG = 0.85
COSINE_THRESHOLD_HIGH = 0.90
COSINE_THRESHOLD_CRITICAL = 0.95

# Min shared queries for query-only cannibalization
MIN_SHARED_QUERIES = 1


class CannibalizationDetector:
    """Detect cannibalization within topic clusters using embeddings + GSC."""

    async def detect_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Run cannibalization detection across all clusters for a site.

        Returns the number of cannibalization pairs found.
        """
        logger.info("Starting cannibalization detection for site %s", site_id)

        clusters = await db.fetch(
            "SELECT id, post_count FROM clusters WHERE site_id = $1",
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
        for cluster_row in clusters:
            if cluster_row["post_count"] < 2:
                continue
            pairs = await self._detect_in_cluster(db, cluster_row["id"], site_id)
            total_pairs += pairs

        logger.info(
            "Cannibalization detection complete for site %s — %d pairs found",
            site_id, total_pairs,
        )
        return total_pairs

    async def _detect_in_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
    ) -> int:
        """Detect cannibalization pairs within a single cluster.

        Uses:
        1. pgvector cosine distance between all post pairs (via embedding)
        2. GSC query overlap between post pairs

        Returns the number of pairs found.
        """
        # Get posts with their embeddings (using pgvector for cosine distance)
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count,
                   pe.embedding::text AS embedding_text
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE pc.cluster_id = $1
            ORDER BY p.id
            """,
            cluster_id,
        )

        if len(posts) < 2:
            return 0

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

        # Calculate cosine similarity between all pairs using pgvector
        pairs_found = 0
        post_list = list(posts)

        for i, j in combinations(range(len(post_list)), 2):
            post_a = post_list[i]
            post_b = post_list[j]

            # ── Signal 1: Embedding cosine similarity ──
            cosine_sim = None
            if post_a["embedding_text"] and post_b["embedding_text"]:
                # Use pgvector's cosine distance operator
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
            is_cannibal = False
            if cosine_sim is not None and cosine_sim >= COSINE_THRESHOLD_FLAG:
                is_cannibal = True
            if n_shared >= MIN_SHARED_QUERIES:
                is_cannibal = True

            if not is_cannibal:
                continue

            # ── Determine severity ──
            severity = self._compute_severity(cosine_sim, n_shared)

            # ── Determine stronger post ──
            health_a = health_map.get(post_a["id"], {"score": 0, "traffic": 0})
            health_b = health_map.get(post_b["id"], {"score": 0, "traffic": 0})

            # Stronger = higher composite score; tie-break by traffic
            strength_a = health_a["score"] + health_a["traffic"] * 10
            strength_b = health_b["score"] + health_b["traffic"] * 10
            stronger_id = post_a["id"] if strength_a >= strength_b else post_b["id"]

            # ── Calculate combined overlap score ──
            overlap_score = self._compute_overlap_score(cosine_sim, n_shared, queries_a, queries_b)

            # ── Insert pair ──
            await db.execute(
                """
                INSERT INTO cannibalization_pairs
                    (cluster_id, post_a_id, post_b_id, overlap_score, severity,
                     overlapping_queries, cosine_similarity, stronger_post_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                cluster_id,
                post_a["id"],
                post_b["id"],
                overlap_score,
                severity,
                list(shared_queries)[:50] if shared_queries else None,
                cosine_sim,
                stronger_id,
            )

            pairs_found += 1

        return pairs_found

    @staticmethod
    def _compute_severity(cosine_sim: float | None, n_shared: int) -> str:
        """Determine cannibalization severity from both signals."""
        has_cosine = cosine_sim is not None

        # Critical: very high cosine + shared queries
        if has_cosine and cosine_sim >= COSINE_THRESHOLD_CRITICAL and n_shared > 0:
            return "critical"

        # High: high cosine, or moderate cosine + shared queries
        if has_cosine and cosine_sim >= COSINE_THRESHOLD_HIGH:
            return "high"
        if has_cosine and cosine_sim >= COSINE_THRESHOLD_FLAG and n_shared > 0:
            return "high"

        # Medium: cosine above threshold, or many shared queries
        if has_cosine and cosine_sim >= COSINE_THRESHOLD_FLAG:
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
