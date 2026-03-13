"""Topic clustering via HDBSCAN with UMAP dimensionality reduction.

Groups post embeddings into topic clusters, labels and describes them via
Claude API, calculates 2D map positions, and stores everything in DB.

Research-informed parameter choices:
- UMAP n_components: 15 (research consensus for 1536-dim embeddings:
  "no less than 15 dimensions", 5-20 range optimal)
- UMAP n_neighbors: min(15, n_posts-1) — preserves local structure
- UMAP min_dist: 0.0 — tighter clusters for HDBSCAN
- UMAP metric: cosine — matches embedding space geometry
- HDBSCAN min_cluster_size: adaptive (max(2, n_posts//10) for small,
  max(3, n_posts//20) for large sites)
- HDBSCAN min_samples: decoupled from min_cluster_size, set lower
  to be less conservative about noise (avoids over-pruning small sites)
- random_state=42 for reproducibility

CPU-bound ML operations are offloaded to asyncio.to_thread().
"""

import asyncio
import logging
from uuid import UUID

import asyncpg
import numpy as np
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
UMAP_N_COMPONENTS_CLUSTER = 15  # For clustering (research: 5-20 optimal)
UMAP_N_COMPONENTS_2D = 2       # For visualization map


class TopicClusterer:
    """Cluster site posts by embedding similarity using HDBSCAN."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def cluster_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run full clustering pipeline for a site.

        Steps:
          1. Fetch all embeddings
          2. UMAP reduction (1536 → 15 dims) + HDBSCAN clustering
          3. UMAP reduction (1536 → 2D) for map positions
          4. Label and describe clusters via Claude
          5. Store results (idempotent — clears old data first)

        Returns the number of clusters created.
        """
        logger.info("Starting clustering for site %s", site_id)

        # 1. Fetch embeddings
        rows = await db.fetch(
            """
            SELECT p.id AS post_id, p.title, p.url, p.word_count,
                   pe.embedding::text AS embedding_text
            FROM post_embeddings pe
            JOIN posts p ON p.id = pe.post_id
            WHERE p.site_id = $1
            ORDER BY p.id
            """,
            site_id,
        )

        if not rows:
            logger.warning("No embeddings found for site %s — skipping clustering", site_id)
            return 0

        post_ids = [r["post_id"] for r in rows]
        titles = [r["title"] for r in rows]
        urls = [r["url"] for r in rows]
        embeddings = np.array([
            _parse_pgvector(r["embedding_text"]) for r in rows
        ], dtype=np.float32)

        n_posts = len(post_ids)
        logger.info("Fetched %d post embeddings for site %s", n_posts, site_id)

        if n_posts < 5:
            # Too few posts — single cluster, simple 2D layout
            logger.info("< 5 posts — creating single cluster for site %s", site_id)
            labels = np.zeros(n_posts, dtype=int)
            positions_2d = self._simple_2d_layout(n_posts)
        else:
            # Offload CPU-bound ML to thread
            labels, positions_2d = await asyncio.to_thread(
                self._run_clustering_and_2d, embeddings, n_posts,
            )

        # 3. Clear old data (idempotent)
        await self._clear_old_clusters(db, site_id)

        # 4. Store 2D positions on posts
        for idx, post_id in enumerate(post_ids):
            await db.execute(
                "UPDATE posts SET x_pos = $1, y_pos = $2 WHERE id = $3",
                float(positions_2d[idx, 0]),
                float(positions_2d[idx, 1]),
                post_id,
            )

        # 5. Prepare cluster groups
        cluster_groups: dict[int, list[int]] = {}
        unclustered_indices: list[int] = []
        for idx, label in enumerate(labels):
            if label == -1:
                unclustered_indices.append(idx)
            else:
                cluster_groups.setdefault(int(label), []).append(idx)

        # 6. Create clusters with labels and descriptions
        cluster_count = 0

        for cluster_label_id, member_indices in cluster_groups.items():
            member_titles = [titles[i] for i in member_indices]
            member_urls = [urls[i] for i in member_indices]
            member_post_ids = [post_ids[i] for i in member_indices]

            # Label + describe via Claude (single API call)
            label, description = await self._label_and_describe_cluster(
                member_titles, member_urls,
            )

            cluster_id = await db.fetchval(
                """
                INSERT INTO clusters (site_id, label, description, post_count)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                site_id, label, description, len(member_post_ids),
            )

            # Assign posts
            for pid in member_post_ids:
                await db.execute(
                    "INSERT INTO post_clusters (post_id, cluster_id) VALUES ($1, $2)",
                    pid, cluster_id,
                )

            cluster_count += 1

        # Handle unclustered posts
        if unclustered_indices:
            unclustered_post_ids = [post_ids[i] for i in unclustered_indices]
            cluster_id = await db.fetchval(
                """
                INSERT INTO clusters (site_id, label, description, post_count)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                site_id,
                "Unclustered",
                "Posts that don't fit neatly into any topic group. May be unique topics or need more related content.",
                len(unclustered_post_ids),
            )
            for pid in unclustered_post_ids:
                await db.execute(
                    "INSERT INTO post_clusters (post_id, cluster_id) VALUES ($1, $2)",
                    pid, cluster_id,
                )
            cluster_count += 1

        logger.info(
            "Clustering complete for site %s — %d clusters (%d unclustered posts), 2D positions stored",
            site_id, cluster_count, len(unclustered_indices),
        )
        return cluster_count

    def _run_clustering_and_2d(
        self, embeddings: np.ndarray, n_posts: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Reduce dimensions with UMAP, cluster with HDBSCAN, and compute 2D positions.

        Returns (cluster_labels, positions_2d).
        """
        import umap
        import hdbscan

        # ── Step 1: UMAP reduction for clustering (1536 → 15 dims) ──
        n_components = min(UMAP_N_COMPONENTS_CLUSTER, n_posts - 2)
        n_neighbors = min(15, n_posts - 1)

        logger.info(
            "UMAP clustering: %d dims → %d dims (n_neighbors=%d)",
            embeddings.shape[1], n_components, n_neighbors,
        )
        reducer_cluster = umap.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        )
        reduced = reducer_cluster.fit_transform(embeddings)

        # ── Step 2: HDBSCAN clustering ──
        # Adaptive min_cluster_size based on site size
        if n_posts < 20:
            min_cluster_size = max(2, n_posts // 5)
            min_samples = 1  # Very permissive for small sites
        elif n_posts < 100:
            min_cluster_size = max(3, n_posts // 10)
            min_samples = 2  # Slightly conservative
        else:
            min_cluster_size = max(5, n_posts // 20)
            min_samples = 3  # More conservative for large sites

        logger.info(
            "HDBSCAN: min_cluster_size=%d, min_samples=%d",
            min_cluster_size, min_samples,
        )
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = int(np.sum(labels == -1))
        logger.info("HDBSCAN found %d clusters, %d noise points", n_clusters, n_noise)

        # ── Step 3: UMAP reduction for 2D visualization ──
        logger.info("UMAP 2D: %d dims → 2 dims for map positions", embeddings.shape[1])
        reducer_2d = umap.UMAP(
            n_components=UMAP_N_COMPONENTS_2D,
            n_neighbors=n_neighbors,
            min_dist=0.3,  # Slightly spread out for visual clarity
            metric="cosine",
            random_state=42,
        )
        positions_2d = reducer_2d.fit_transform(embeddings)

        return labels, positions_2d

    @staticmethod
    def _simple_2d_layout(n_posts: int) -> np.ndarray:
        """Generate simple circular layout for < 5 posts."""
        positions = np.zeros((n_posts, 2), dtype=np.float32)
        for i in range(n_posts):
            angle = 2 * np.pi * i / max(n_posts, 1)
            positions[i, 0] = np.cos(angle) * 2.0
            positions[i, 1] = np.sin(angle) * 2.0
        return positions

    async def _clear_old_clusters(self, db: asyncpg.Connection, site_id: UUID) -> None:
        """Remove existing clusters and related data for idempotent re-runs."""
        old_cluster_ids = await db.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id,
        )
        if old_cluster_ids:
            ids = [r["id"] for r in old_cluster_ids]
            await db.execute(
                "DELETE FROM cannibalization_pairs WHERE cluster_id = ANY($1::uuid[])",
                ids,
            )
            await db.execute(
                """
                DELETE FROM post_health_scores
                WHERE post_id IN (
                    SELECT DISTINCT post_id FROM post_clusters WHERE cluster_id = ANY($1::uuid[])
                )
                """,
                ids,
            )
            await db.execute(
                "DELETE FROM post_clusters WHERE cluster_id = ANY($1::uuid[])",
                ids,
            )
            await db.execute(
                "DELETE FROM clusters WHERE site_id = $1", site_id,
            )
        logger.info("Cleared old cluster data for site %s", site_id)

    async def _label_and_describe_cluster(
        self, titles: list[str], urls: list[str],
    ) -> tuple[str, str]:
        """Generate a short label AND one-sentence description for a cluster.

        Single API call for both to save tokens and latency.
        """
        sample_titles = titles[:7]
        titles_text = "\n".join(f"- {t}" for t in sample_titles)

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": (
                        f"These blog posts are grouped in the same topic cluster:\n"
                        f"{titles_text}\n\n"
                        f"Respond with exactly two lines:\n"
                        f"Line 1: A short 2-4 word topic label\n"
                        f"Line 2: A one-sentence description of what this cluster covers\n"
                        f"No quotes, no bullets, no extra formatting."
                    ),
                }],
            )
            text = response.content[0].text.strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            label = lines[0][:80] if lines else f"Cluster ({len(titles)} posts)"
            description = lines[1][:500] if len(lines) > 1 else ""

            return label, description
        except Exception as e:
            logger.error("Claude API cluster labeling failed: %s", e)
            return f"Cluster ({len(titles)} posts)", ""


def _parse_pgvector(text: str) -> list[float]:
    """Parse pgvector's [x,y,z,...] text format into a list of floats."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [float(x) for x in text.split(",")]
