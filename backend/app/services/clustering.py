"""Topic clustering via HDBSCAN with UMAP dimensionality reduction.

Groups post embeddings into topic clusters, labels them via Claude API,
and stores results in the clusters/post_clusters tables.
"""

import logging
from uuid import UUID

import asyncpg
import numpy as np
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
UMAP_N_COMPONENTS = 50
HDBSCAN_MIN_CLUSTER_SIZE = 3


class TopicClusterer:
    """Cluster site posts by embedding similarity using HDBSCAN."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=5)

    async def cluster_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Run full clustering pipeline for a site.

        Steps:
          1. Fetch all embeddings for the site
          2. UMAP dimensionality reduction (1536 → 50 dims)
          3. HDBSCAN clustering
          4. Label clusters via Claude API
          5. Store results (idempotent — clears old data first)

        Returns the number of clusters created.
        """
        logger.info("Starting clustering for site %s", site_id)

        # 1. Fetch embeddings
        rows = await db.fetch(
            """
            SELECT p.id AS post_id, p.title, pe.embedding::text AS embedding_text
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
        embeddings = np.array([
            _parse_pgvector(r["embedding_text"]) for r in rows
        ], dtype=np.float32)

        n_posts = len(post_ids)
        logger.info("Fetched %d post embeddings for site %s", n_posts, site_id)

        if n_posts < 5:
            # Too few posts — put everything in one cluster
            logger.info("< 5 posts — creating single cluster for site %s", site_id)
            labels = np.zeros(n_posts, dtype=int)
        else:
            labels = self._run_clustering(embeddings, n_posts)

        # 4. Prepare cluster groups
        cluster_groups: dict[int, list[int]] = {}
        unclustered_indices: list[int] = []
        for idx, label in enumerate(labels):
            if label == -1:
                unclustered_indices.append(idx)
            else:
                cluster_groups.setdefault(int(label), []).append(idx)

        # 5. Clear old clusters for this site (idempotent)
        await self._clear_old_clusters(db, site_id)

        # 6. Create clusters and assign posts
        cluster_count = 0

        for cluster_label_id, member_indices in cluster_groups.items():
            member_titles = [titles[i] for i in member_indices]
            member_post_ids = [post_ids[i] for i in member_indices]

            # Label via Claude
            label = await self._label_cluster(member_titles)

            cluster_id = await db.fetchval(
                """
                INSERT INTO clusters (site_id, label, post_count)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                site_id, label, len(member_post_ids),
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
                INSERT INTO clusters (site_id, label, post_count)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                site_id, "Unclustered", len(unclustered_post_ids),
            )
            for pid in unclustered_post_ids:
                await db.execute(
                    "INSERT INTO post_clusters (post_id, cluster_id) VALUES ($1, $2)",
                    pid, cluster_id,
                )
            cluster_count += 1

        logger.info(
            "Clustering complete for site %s — %d clusters created (%d unclustered posts)",
            site_id, cluster_count, len(unclustered_indices),
        )
        return cluster_count

    def _run_clustering(self, embeddings: np.ndarray, n_posts: int) -> np.ndarray:
        """Reduce dimensions with UMAP and cluster with HDBSCAN."""
        import umap
        import hdbscan

        # UMAP reduction
        n_components = min(UMAP_N_COMPONENTS, n_posts - 2)
        n_neighbors = min(15, n_posts - 1)

        logger.info(
            "Running UMAP: %d dims → %d dims (n_neighbors=%d)",
            embeddings.shape[1], n_components, n_neighbors,
        )
        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        )
        reduced = reducer.fit_transform(embeddings)

        # HDBSCAN clustering
        min_cluster_size = min(HDBSCAN_MIN_CLUSTER_SIZE, max(2, n_posts // 5))
        logger.info("Running HDBSCAN with min_cluster_size=%d", min_cluster_size)
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        logger.info("HDBSCAN found %d clusters", n_clusters)
        return labels

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
                "DELETE FROM post_clusters WHERE cluster_id = ANY($1::uuid[])",
                ids,
            )
            # Delete health scores for posts in these clusters
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
                "DELETE FROM clusters WHERE site_id = $1", site_id,
            )
        logger.info("Cleared old cluster data for site %s", site_id)

    async def _label_cluster(self, titles: list[str]) -> str:
        """Generate a short label for a cluster using Claude API."""
        # Use top 5 titles (by position in list — caller should sort by traffic)
        sample_titles = titles[:5]
        titles_text = "\n".join(f"- {t}" for t in sample_titles)

        await self.rate_limiter.acquire()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": (
                        f"These are blog post titles from the same topic cluster:\n"
                        f"{titles_text}\n\n"
                        f"Generate a short 2-4 word label for this topic cluster. "
                        f"Reply with ONLY the label, nothing else."
                    ),
                }],
            )
            label = response.content[0].text.strip().strip('"').strip("'")
            return label[:80]  # Safety truncation
        except Exception as e:
            logger.error("Claude API label generation failed: %s", e)
            return f"Cluster ({len(titles)} posts)"


def _parse_pgvector(text: str) -> list[float]:
    """Parse pgvector's [x,y,z,...] text format into a list of floats."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [float(x) for x in text.split(",")]
