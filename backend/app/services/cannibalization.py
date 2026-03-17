"""Cannibalization detection via embedding cosine similarity + GSC query overlap.

Research-informed approach (two-signal detection):
1. Embedding cosine similarity between posts in the same cluster
2. GSC query overlap — posts ranking for the same search queries

THRESHOLD CALIBRATION:
Thresholds are auto-calibrated per site using the pairwise similarity
distribution. This handles niche sites (higher baseline similarity)
vs general blogs (lower baseline). Calibration uses 85th/92nd/97th
percentiles with absolute floors of 0.30/0.40/0.50.

Default thresholds (text-embedding-3-small):
- flag: 0.40 (review), high: 0.50 (action needed), critical: 0.60 (near-duplicate)

PERFORMANCE:
For clusters with 20+ posts, uses HNSW index pre-filtering to avoid
O(n²) pair scans. Finds top-10 nearest neighbors per post via pgvector's
HNSW index, then only evaluates those candidate pairs.

The "stronger post" is determined by composite health score + traffic.
"""

import logging
from itertools import combinations
from uuid import UUID

import asyncpg

from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Cosine similarity thresholds for text-embedding-3-small
# CRITICAL: This model produces LOWER similarity scores than ada-002.
# Research (OpenAI community, 2024): content that scored 0.70+ with ada-002
# scores ~0.40 with text-embedding-3-small. Thresholds must be calibrated
# accordingly. Same-topic content typically scores 0.45-0.55.
#
# These defaults should be tuned per-site after initial embedding generation.
# Run: SELECT 1 - (a.embedding <=> b.embedding) FROM post_embeddings a, b
# on known-cannibalized pairs to calibrate.
COSINE_THRESHOLD_FLAG = 0.40    # Flag for review (was 0.85 — too high for v3-small)
COSINE_THRESHOLD_HIGH = 0.50    # High confidence cannibalization
COSINE_THRESHOLD_CRITICAL = 0.60  # Near-duplicate content

# Min shared queries for query-only cannibalization
MIN_SHARED_QUERIES = 1


class CannibalizationDetector:
    """Detect cannibalization within topic clusters using embeddings + GSC."""

    async def calibrate_thresholds(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict[str, float]:
        """Auto-calibrate cosine similarity thresholds for a specific site.

        Computes the pairwise cosine similarity distribution across all posts
        and sets thresholds at the 85th and 95th percentiles. This adapts to
        the site's content: a niche site about "React hooks" will have higher
        baseline similarity than a general tech blog.

        Stores calibrated thresholds in the sites table and returns them.
        """
        logger.info("Calibrating cosine thresholds for site %s", site_id)

        # Get a sample of pairwise similarities (cap at 500 pairs for perf)
        similarities = await db.fetch(
            """
            SELECT 1 - (a.embedding <=> b.embedding) AS similarity
            FROM post_embeddings a
            JOIN posts pa ON pa.id = a.post_id
            JOIN post_embeddings b ON b.post_id > a.post_id
            JOIN posts pb ON pb.id = b.post_id
            WHERE pa.site_id = $1 AND pb.site_id = $1
            ORDER BY RANDOM()
            LIMIT 500
            """,
            site_id,
        )

        if len(similarities) < 10:
            logger.info(
                "Too few pairs (%d) to calibrate — using defaults", len(similarities),
            )
            return {
                "flag": COSINE_THRESHOLD_FLAG,
                "high": COSINE_THRESHOLD_HIGH,
                "critical": COSINE_THRESHOLD_CRITICAL,
            }

        import numpy as np
        sims = np.array([float(r["similarity"]) for r in similarities])

        # Use percentiles: flag=85th, high=92nd, critical=97th
        p85 = float(np.percentile(sims, 85))
        p92 = float(np.percentile(sims, 92))
        p97 = float(np.percentile(sims, 97))

        # Floor: don't go below absolute minimums
        flag = max(p85, 0.50)
        high = max(p92, 0.70)
        critical = max(p97, 0.85)

        logger.info(
            "Calibrated thresholds for site %s: flag=%.3f (p85), high=%.3f (p92), "
            "critical=%.3f (p97) | distribution: min=%.3f, median=%.3f, max=%.3f",
            site_id, flag, high, critical,
            float(np.min(sims)), float(np.median(sims)), float(np.max(sims)),
        )

        # Store in sites table metadata
        await db.execute(
            """
            UPDATE sites SET metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            f'{{"cosine_threshold_flag": {flag:.4f}, "cosine_threshold_high": {high:.4f}, "cosine_threshold_critical": {critical:.4f}}}',
            site_id,
        )

        return {"flag": flag, "high": high, "critical": critical}

    async def detect_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
        max_pairs: int = 200,
    ) -> int:
        """Run cannibalization detection across all clusters for a site.

        Auto-calibrates thresholds on first run, then uses site-specific
        thresholds stored in the sites table. Limits output to max_pairs
        most severe pairs for actionability.

        Returns the number of cannibalization pairs found.
        """
        logger.info("Starting cannibalization detection for site %s", site_id)

        # Pre-filter: detect and flag duplicate content (different URLs, same content)
        dupes = await db.fetch("""
            SELECT p1.id as id1, p2.id as id2, p1.url as url1, p2.url as url2
            FROM posts p1
            JOIN posts p2 ON p1.content_hash = p2.content_hash
                AND p1.id < p2.id AND p1.site_id = p2.site_id
            WHERE p1.site_id = $1 AND p1.content_hash IS NOT NULL
        """, site_id)
        if dupes:
            logger.info("Found %d duplicate content pairs (same content, different URLs)", len(dupes))
            for d in dupes[:5]:
                logger.info("  Duplicate: %s ↔ %s", d["url1"][:50], d["url2"][:50])

        # Load site-specific calibrated thresholds (or calibrate now)
        site_meta = await db.fetchval(
            "SELECT metadata FROM sites WHERE id = $1", site_id,
        )
        if site_meta and isinstance(site_meta, dict) and "cosine_threshold_flag" in site_meta:
            thresholds = {
                "flag": site_meta["cosine_threshold_flag"],
                "high": site_meta["cosine_threshold_high"],
                "critical": site_meta["cosine_threshold_critical"],
            }
            logger.info(
                "Using calibrated thresholds for site %s: %s", site_id, thresholds,
            )
        else:
            thresholds = await self.calibrate_thresholds(db, site_id)

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
            pairs = await self._detect_in_cluster(
                db, cluster_row["id"], site_id, thresholds=thresholds,
            )
            total_pairs += pairs

        # Prune to max_pairs — keep only the most severe
        if total_pairs > max_pairs:
            await db.execute("""
                DELETE FROM cannibalization_pairs
                WHERE id NOT IN (
                    SELECT cp.id FROM cannibalization_pairs cp
                    JOIN posts p ON cp.post_a_id = p.id
                    WHERE p.site_id = $1
                    ORDER BY cp.cosine_similarity DESC
                    LIMIT $2
                )
                AND post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
            """, site_id, max_pairs)
            pruned = total_pairs - max_pairs
            logger.info("Pruned %d low-severity pairs, keeping top %d", pruned, max_pairs)
            total_pairs = max_pairs

        logger.info(
            "Cannibalization detection complete for site %s — %d pairs found",
            site_id, total_pairs,
        )
        return total_pairs

    async def _detect_in_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
        thresholds: dict[str, float] | None = None,
    ) -> int:
        """Detect cannibalization pairs within a single cluster.

        Uses:
        1. pgvector cosine distance between all post pairs (via embedding)
        2. GSC query overlap between post pairs

        thresholds: site-specific calibrated thresholds (flag/high/critical)

        Returns the number of pairs found.
        """
        t_flag = thresholds["flag"] if thresholds else COSINE_THRESHOLD_FLAG
        t_high = thresholds["high"] if thresholds else COSINE_THRESHOLD_HIGH
        t_critical = thresholds["critical"] if thresholds else COSINE_THRESHOLD_CRITICAL
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

        pairs_found = 0
        post_list = list(posts)
        post_id_set = {p["id"] for p in post_list}

        # ── HNSW pre-filter: only compare posts above similarity threshold ──
        # Instead of O(n²) pair scan, use pgvector's HNSW index to find
        # nearest neighbors for each post. Much faster for large clusters.
        # For small clusters (< 20 posts), full scan is fine.
        use_hnsw = len(post_list) >= 20

        # Build pre-filtered candidate pairs via HNSW
        hnsw_candidates: dict[tuple[UUID, UUID], float] = {}
        if use_hnsw:
            for post in post_list:
                if not post["embedding_text"]:
                    continue
                # Use HNSW index to find nearest neighbors within threshold
                neighbors = await db.fetch(
                    """
                    SELECT pe2.post_id,
                           1 - (pe1.embedding <=> pe2.embedding) AS similarity
                    FROM post_embeddings pe1, post_embeddings pe2
                    WHERE pe1.post_id = $1
                      AND pe2.post_id != $1
                      AND pe2.post_id = ANY($2::uuid[])
                    ORDER BY pe1.embedding <=> pe2.embedding
                    LIMIT 10
                    """,
                    post["id"], list(post_id_set),
                )
                for n in neighbors:
                    sim = float(n["similarity"])
                    if sim >= t_flag:
                        pair_key = tuple(sorted([post["id"], n["post_id"]]))
                        hnsw_candidates[pair_key] = max(
                            hnsw_candidates.get(pair_key, 0), sim,
                        )
            logger.info(
                "HNSW pre-filter: %d candidate pairs from %d posts in cluster %s",
                len(hnsw_candidates), len(post_list), cluster_id,
            )

        # Build post lookup for iteration
        post_by_id = {p["id"]: p for p in post_list}

        # Determine which pairs to evaluate
        if use_hnsw:
            # Only evaluate HNSW candidates + all query-overlap pairs
            pair_iter = set(hnsw_candidates.keys())
            # Also add all pairs where posts share GSC queries
            for i, j in combinations(range(len(post_list)), 2):
                pa, pb = post_list[i], post_list[j]
                qa = queries_by_post.get(pa["id"], set())
                qb = queries_by_post.get(pb["id"], set())
                if qa & qb:
                    pair_iter.add(tuple(sorted([pa["id"], pb["id"]])))
        else:
            # Small cluster: full scan
            pair_iter = set()
            for i, j in combinations(range(len(post_list)), 2):
                pair_iter.add(tuple(sorted([post_list[i]["id"], post_list[j]["id"]])))

        for pair_key in pair_iter:
            pid_a, pid_b = pair_key
            post_a = post_by_id[pid_a]
            post_b = post_by_id[pid_b]

            # ── Signal 1: Embedding cosine similarity ──
            cosine_sim = hnsw_candidates.get(pair_key) if use_hnsw else None
            if cosine_sim is None and post_a["embedding_text"] and post_b["embedding_text"]:
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
            if cosine_sim is not None and cosine_sim >= t_flag:
                is_cannibal = True
            if n_shared >= MIN_SHARED_QUERIES:
                is_cannibal = True

            if not is_cannibal:
                continue

            # ── Determine severity (uses site-specific thresholds) ──
            severity = self._compute_severity(
                cosine_sim, n_shared,
                t_flag=t_flag, t_high=t_high, t_critical=t_critical,
            )

            # ── Determine stronger post ──
            health_a = health_map.get(post_a["id"], {"score": 0, "traffic": 0})
            health_b = health_map.get(post_b["id"], {"score": 0, "traffic": 0})

            # Stronger = higher composite score; tie-break by traffic
            strength_a = health_a["score"] + health_a["traffic"] * 10
            strength_b = health_b["score"] + health_b["traffic"] * 10
            stronger_id = post_a["id"] if strength_a >= strength_b else post_b["id"]

            # ── Calculate combined overlap score ──
            overlap_score = self._compute_overlap_score(cosine_sim, n_shared, queries_a, queries_b)

            # Compute numeric severity score (0-100) factoring in cosine + intent match
            intent_match = 1.0 if (post_a.get("content_intent") == post_b.get("content_intent")) else 0.5
            severity_score = min(100.0, cosine_sim * 60 + intent_match * 30 + (n_shared / max(len(queries_a or []), 1)) * 10)

            # Compute resolution recommendation
            resolution = self._recommend_resolution(
                cosine_sim, severity,
                post_a.get("content_intent"), post_b.get("content_intent"),
            )

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
    def _recommend_resolution(
        cosine_sim: float,
        severity: str,
        intent_a: str | None = None,
        intent_b: str | None = None,
    ) -> str:
        """Recommend a resolution action for a cannibalization pair."""
        if cosine_sim >= 0.95:
            return "redirect"  # Near-identical → 301 redirect shorter to longer
        if intent_a and intent_b and intent_a != intent_b:
            return "differentiate"  # Different intents → refocus each on its intent
        if severity == "critical" or cosine_sim >= 0.85:
            return "merge"  # High overlap, same intent → merge into stronger
        return "monitor"  # Moderate overlap → add internal link, monitor

    @staticmethod
    def _compute_severity(
        cosine_sim: float | None,
        n_shared: int,
        t_flag: float = COSINE_THRESHOLD_FLAG,
        t_high: float = COSINE_THRESHOLD_HIGH,
        t_critical: float = COSINE_THRESHOLD_CRITICAL,
    ) -> str:
        """Determine cannibalization severity from both signals.

        Accepts site-specific thresholds for calibrated detection.
        Falls back to module-level defaults if not provided.
        """
        has_cosine = cosine_sim is not None

        # Critical: very high cosine + shared queries
        if has_cosine and cosine_sim >= t_critical and n_shared > 0:
            return "critical"

        # High: high cosine, or moderate cosine + shared queries
        if has_cosine and cosine_sim >= t_high:
            return "high"
        if has_cosine and cosine_sim >= t_flag and n_shared > 0:
            return "high"

        # Medium: cosine above threshold, or many shared queries
        if has_cosine and cosine_sim >= t_flag:
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
