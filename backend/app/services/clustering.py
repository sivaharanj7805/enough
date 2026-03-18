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

    async def cluster_site(self, db: asyncpg.Connection, site_id: UUID, skip_labeling: bool = False) -> int:
        """Run full clustering pipeline for a site.

        Args:
            skip_labeling: If True, skip Claude API calls for cluster labels.
                           Use fast_cluster_labels.py for TF-IDF labels instead.

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

            # Label + describe (Claude API or placeholder for fast mode)
            if skip_labeling:
                label = f"Cluster {cluster_count + 1} ({len(member_post_ids)} posts)"
                description = ""
            else:
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

        # 8. Recursive sub-clustering for mega-clusters
        MAX_CLUSTER_SIZE = 50
        for cluster_label_id, member_indices in cluster_groups.items():
            if len(member_indices) > MAX_CLUSTER_SIZE:
                member_post_ids = [post_ids[i] for i in member_indices]
                member_embeddings = embeddings[member_indices]
                # Find the cluster_id we just saved
                parent_id = await db.fetchval(
                    """SELECT c.id FROM clusters c
                       JOIN post_clusters pc ON pc.cluster_id = c.id
                       WHERE c.site_id = $1 AND pc.post_id = $2
                       LIMIT 1""",
                    site_id, member_post_ids[0],
                )
                if parent_id:
                    sub_count = await self._recursive_subcluster(
                        db, site_id, parent_id,
                        member_embeddings,
                        member_post_ids,
                        [titles[i] for i in member_indices],
                        [urls[i] for i in member_indices],
                        skip_labeling=skip_labeling,
                    )
                    cluster_count += sub_count
                    logger.info(
                        "Sub-clustered mega-cluster (%d posts) into %d sub-clusters",
                        len(member_indices), sub_count,
                    )

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

        # Adaptive min_dist: compute mean pairwise cosine similarity on sample
        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        sample_size = min(100, n_posts)
        sample_indices = np.random.choice(n_posts, sample_size, replace=False)
        sample = embeddings[sample_indices]
        sim_matrix = cos_sim(sample)
        np.fill_diagonal(sim_matrix, 0)
        mean_sim = sim_matrix.mean()
        logger.info("Mean pairwise cosine similarity: %.3f", mean_sim)

        if mean_sim > 0.70:
            # Tight niche — spread more to find differences
            min_dist = 0.05
            n_neighbors = min(5, n_posts - 1)
            logger.info("Tight niche detected (%.3f) — using min_dist=0.05, n_neighbors=%d", mean_sim, n_neighbors)
        elif mean_sim > 0.50:
            min_dist = 0.1
        else:
            min_dist = 0.0  # Standard diverse content

        logger.info(
            "UMAP clustering: %d dims → %d dims (n_neighbors=%d, min_dist=%.2f)",
            embeddings.shape[1], n_components, n_neighbors, min_dist,
        )
        reducer_cluster = umap.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric="cosine",
            random_state=42,
        )
        reduced = reducer_cluster.fit_transform(embeddings)

        # ── Step 2: HDBSCAN clustering ──
        # Adaptive min_cluster_size — capped to avoid over-merging on large sites.
        # Rule: start at n_posts//20 but hard-cap at 20 so HDBSCAN can still find
        # meaningful sub-clusters on 1000+ post corpora.
        if n_posts < 20:
            min_cluster_size = max(2, n_posts // 5)
            min_samples = 1
        elif n_posts < 100:
            min_cluster_size = max(3, n_posts // 10)
            min_samples = 2
        elif n_posts < 500:
            min_cluster_size = max(5, n_posts // 20)
            min_samples = 3
        elif n_posts < 1000:
            min_cluster_size = 12
            min_samples = 3
        else:
            # Large sites (1000+): cap at 20 — lets HDBSCAN find dozens of clusters
            # rather than collapsing everything into 3 mega-clusters
            min_cluster_size = 20
            min_samples = 5

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

        # Compute silhouette scores for quality assessment
        if n_clusters >= 2:
            from sklearn.metrics import silhouette_score, silhouette_samples
            # Only score non-noise points
            mask = labels != -1
            if mask.sum() >= 2:
                avg_silhouette = float(silhouette_score(reduced[mask], labels[mask]))
                per_sample = silhouette_samples(reduced[mask], labels[mask])
                logger.info("Cluster quality — avg silhouette: %.3f", avg_silhouette)
                # Store per-cluster quality as attribute for later use
                self._cluster_silhouettes = {}
                for cl in set(labels[mask]):
                    cl_scores = per_sample[labels[mask] == cl]
                    self._cluster_silhouettes[int(cl)] = float(np.mean(cl_scores))
                    logger.info("  Cluster %d: silhouette %.3f", cl, self._cluster_silhouettes[int(cl)])
            else:
                self._cluster_silhouettes = {}
        else:
            self._cluster_silhouettes = {}

        # ── Step 2b: Assign noise posts to nearest cluster ──
        if n_noise > 0 and n_clusters > 0:
            from sklearn.metrics.pairwise import euclidean_distances
            noise_mask = labels == -1
            non_noise_mask = labels != -1
            if non_noise_mask.sum() > 0:
                # Compute centroids of each cluster
                unique_clusters = sorted(set(labels[non_noise_mask]))
                centroids = np.array([
                    reduced[labels == c].mean(axis=0)
                    for c in unique_clusters
                ])
                # For each noise point, find nearest centroid
                noise_indices = np.where(noise_mask)[0]
                noise_reduced = reduced[noise_indices]
                dists = euclidean_distances(noise_reduced, centroids)
                nearest = np.argmin(dists, axis=1)
                for i, idx in enumerate(noise_indices):
                    labels[idx] = unique_clusters[nearest[i]]
                logger.info("Assigned %d noise posts to nearest clusters", n_noise)

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

    async def _recursive_subcluster(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        parent_cluster_id: UUID,
        embeddings: np.ndarray,
        post_ids: list[UUID],
        titles: list[str],
        urls: list[str],
        depth: int = 0,
        max_depth: int = 3,
        max_cluster_size: int = 50,
        skip_labeling: bool = False,
    ) -> int:
        """Recursively sub-cluster a mega-cluster until all children < max_cluster_size."""
        import umap
        import hdbscan

        if len(post_ids) <= max_cluster_size or depth >= max_depth:
            return 0

        logger.info(
            "Sub-clustering %d posts at depth %d (parent %s)",
            len(post_ids), depth, parent_cluster_id,
        )

        n = len(post_ids)
        n_components = min(10, n - 2)
        n_neighbors = min(10, n - 1)

        # Tighter UMAP params for sub-clustering within a niche
        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=0.05,  # Tighter to separate similar content
            metric="cosine",
            random_state=42 + depth,
        )
        reduced = reducer.fit_transform(embeddings)

        # More aggressive clustering — smaller clusters
        min_cluster_size = max(3, n // 10)
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=2,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)

        unique_labels = set(labels) - {-1}
        if len(unique_labels) <= 1:
            # Can't split further — single sub-cluster or all noise
            logger.info("Sub-clustering at depth %d found only %d sub-clusters, stopping", depth, len(unique_labels))
            return 0

        sub_count = 0
        for sub_label in unique_labels:
            indices = [i for i, l in enumerate(labels) if l == sub_label]
            sub_post_ids = [post_ids[i] for i in indices]
            sub_titles = [titles[i] for i in indices]
            sub_urls = [urls[i] for i in indices]
            sub_embeddings = embeddings[indices]

            # Label (Claude API or placeholder for fast mode)
            if skip_labeling:
                label = f"Sub-cluster {sub_count + 1} ({len(sub_post_ids)} posts)"
                description = ""
            else:
                label, description = await self._label_and_describe_cluster(sub_titles, sub_urls)

            # Save as child cluster with parent_id reference
            child_id = await db.fetchval(
                """
                INSERT INTO clusters (site_id, label, description, post_count, parent_cluster_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                site_id, label, description, len(sub_post_ids), parent_cluster_id,
            )

            # Assign posts to sub-cluster (keep them in parent too)
            for pid in sub_post_ids:
                await db.execute(
                    "INSERT INTO post_clusters (post_id, cluster_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    pid, child_id,
                )

            sub_count += 1

            # Recurse if still too large
            if len(sub_post_ids) > max_cluster_size:
                deeper = await self._recursive_subcluster(
                    db, site_id, child_id, sub_embeddings,
                    sub_post_ids, sub_titles, sub_urls,
                    depth=depth + 1, max_depth=max_depth, max_cluster_size=max_cluster_size,
                    skip_labeling=skip_labeling,
                )
                sub_count += deeper

        return sub_count

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
        sample_titles = titles[:12]  # More samples for better labelling
        titles_text = "\n".join(f"- {t}" for t in sample_titles)

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": (
                        f"These {len(titles)} blog posts are grouped in the same topic cluster:\n"
                        f"{titles_text}\n"
                        f"{'...' if len(titles) > 12 else ''}\n\n"
                        f"Respond with exactly three lines:\n"
                        f"Line 1: A specific 2-5 word topic label (not generic like 'Sales Strategy')\n"
                        f"Line 2: A one-sentence description of what this cluster covers\n"
                        f"Line 3: 3-5 sub-themes separated by commas (e.g. 'cold calling scripts, objection handling, voicemail tactics')\n"
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
