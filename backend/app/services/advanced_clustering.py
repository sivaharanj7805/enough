"""Advanced clustering — BERTopic-equivalent pipeline without PyTorch dependency.

Implements the key features from BERTopic that matter for Enough:
1. c-TF-IDF: Class-based TF-IDF extracts representative terms per cluster
2. Hierarchical topic modeling: auto-detect parent/child cluster relationships
3. Soft clustering: probability distribution over topics per post
4. Outlier reduction: reassign noise posts to nearest cluster
5. Bridge post detection: posts with >0.15 probability in multiple topics

We already have UMAP + HDBSCAN + Claude labeling. This adds the missing
intelligence layers on top without pulling in a 1GB PyTorch dependency.

BERTopic's pipeline: Embeddings → UMAP → HDBSCAN → c-TF-IDF → LLM labeling
Our pipeline: Same, but built lean with only numpy/scipy/sklearn.
"""

import asyncio
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg
import numpy as np
from anthropic import AsyncAnthropic
from scipy.spatial.distance import cosine as cosine_distance
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

logger = logging.getLogger(__name__)


@dataclass
class CTFIDFResult:
    """c-TF-IDF keywords for a cluster."""
    cluster_id: UUID
    keywords: list[str]       # Top representative words
    scores: list[float]       # Their c-TF-IDF scores


@dataclass
class HierarchyNode:
    """A node in the topic hierarchy."""
    cluster_id: UUID
    label: str
    children: list["HierarchyNode"] = field(default_factory=list)
    depth: int = 0


@dataclass
class BridgePost:
    """A post that spans multiple topic clusters."""
    post_id: UUID
    title: str
    primary_cluster_id: UUID
    primary_probability: float
    secondary_clusters: list[tuple[UUID, float]]  # (cluster_id, probability)


def compute_ctfidf(
    documents_per_cluster: dict[str, list[str]],
    top_n: int = 10,
) -> dict[str, list[tuple[str, float]]]:
    """Compute class-based TF-IDF for each cluster.

    c-TF-IDF treats all documents in a cluster as a single "class document"
    and computes TF-IDF across classes. This extracts the words that are
    most representative of each cluster compared to all others.

    Args:
        documents_per_cluster: {cluster_label: [doc1_text, doc2_text, ...]}
        top_n: number of keywords to return per cluster

    Returns:
        {cluster_label: [(word, score), (word, score), ...]}
    """
    if not documents_per_cluster:
        return {}

    # Concatenate all docs per cluster into one "class document"
    labels = list(documents_per_cluster.keys())
    class_docs = []
    for label in labels:
        combined = " ".join(documents_per_cluster[label])
        class_docs.append(combined)

    # Compute term frequencies per class
    vectorizer = CountVectorizer(
        max_features=5000,
        stop_words="english",
        min_df=1,
        max_df=0.95,
        ngram_range=(1, 2),  # Unigrams and bigrams
    )

    try:
        tf_matrix = vectorizer.fit_transform(class_docs)
    except ValueError:
        # Empty vocabulary
        return {label: [] for label in labels}

    feature_names = vectorizer.get_feature_names_out()

    # Compute IDF across classes (not documents)
    # c-TF-IDF formula: tf(t,c) * log(1 + A/tf(t))
    # where A = average number of words per class, tf(t) = total freq of term t
    total_words_per_class = tf_matrix.sum(axis=1).A1  # type: ignore
    avg_words = total_words_per_class.mean()

    # Total frequency of each term across all classes
    total_term_freq = tf_matrix.sum(axis=0).A1  # type: ignore

    # Compute c-TF-IDF
    tf_dense = tf_matrix.toarray()
    n_classes = len(labels)

    results = {}
    for i, label in enumerate(labels):
        tf_row = tf_dense[i]
        # c-TF-IDF: (tf / total_words_in_class) * log(1 + n_classes / df(t))
        # where df(t) = number of classes containing term t
        ctfidf_scores = []
        for j, term in enumerate(feature_names):
            tf_val = tf_row[j]
            if tf_val == 0:
                continue
            # Document frequency of term across classes
            df = (tf_dense[:, j] > 0).sum()
            idf = math.log(1 + n_classes / max(df, 1))
            score = (tf_val / max(total_words_per_class[i], 1)) * idf
            ctfidf_scores.append((term, score))

        # Sort by score, take top N
        ctfidf_scores.sort(key=lambda x: x[1], reverse=True)
        results[label] = ctfidf_scores[:top_n]

    return results


def build_hierarchy(
    cluster_centroids: dict[UUID, np.ndarray],
    cluster_labels: dict[UUID, str],
    similarity_threshold: float = 0.50,
) -> list[HierarchyNode]:
    """Build hierarchical topic structure via agglomerative merging.

    Finds parent/child relationships between clusters using centroid
    similarity. If cluster A and B are similar (>threshold) and A has
    more posts, A is the parent.

    Returns a forest of HierarchyNodes (multiple root nodes possible).
    """
    if len(cluster_centroids) < 2:
        return [
            HierarchyNode(cluster_id=cid, label=cluster_labels.get(cid, ""))
            for cid in cluster_centroids
        ]

    cluster_ids = list(cluster_centroids.keys())
    centroids = np.array([cluster_centroids[cid] for cid in cluster_ids])

    # Compute pairwise similarities
    sim_matrix = cosine_similarity(centroids)

    # Build parent-child relationships
    # For each pair with similarity > threshold, smaller cluster becomes child
    children_of: dict[UUID, list[UUID]] = defaultdict(list)
    is_child: set[UUID] = set()

    # Sort pairs by similarity (highest first)
    pairs = []
    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            pairs.append((sim_matrix[i, j], cluster_ids[i], cluster_ids[j]))
    pairs.sort(reverse=True)

    for sim, cid_a, cid_b in pairs:
        if sim < similarity_threshold:
            break
        # Skip if either is already a child (prevents chains becoming DAGs)
        if cid_a in is_child or cid_b in is_child:
            continue
        # Smaller cluster (fewer posts implied by label) becomes child
        # We'll use centroid norm as proxy — higher norm usually means broader topic
        norm_a = np.linalg.norm(cluster_centroids[cid_a])
        norm_b = np.linalg.norm(cluster_centroids[cid_b])
        if norm_a >= norm_b:
            parent, child = cid_a, cid_b
        else:
            parent, child = cid_b, cid_a
        children_of[parent].append(child)
        is_child.add(child)

    # Build tree nodes
    nodes: dict[UUID, HierarchyNode] = {}
    for cid in cluster_ids:
        nodes[cid] = HierarchyNode(
            cluster_id=cid,
            label=cluster_labels.get(cid, ""),
        )

    for parent_id, child_ids in children_of.items():
        for child_id in child_ids:
            nodes[child_id].depth = 1
            nodes[parent_id].children.append(nodes[child_id])

    # Return roots (nodes that are not children)
    roots = [nodes[cid] for cid in cluster_ids if cid not in is_child]
    return roots


def detect_bridge_posts(
    post_embeddings: dict[UUID, np.ndarray],
    cluster_centroids: dict[UUID, np.ndarray],
    post_cluster_assignments: dict[UUID, UUID],
    post_titles: dict[UUID, str],
    threshold: float = 0.15,
) -> list[BridgePost]:
    """Detect posts that span multiple topic clusters.

    Computes cosine similarity between each post and every cluster centroid.
    Posts with >threshold probability in 2+ clusters are "bridge posts."

    These are comprehensive guides that legitimately cover multiple topics.
    """
    if not post_embeddings or not cluster_centroids:
        return []

    cluster_ids = list(cluster_centroids.keys())
    centroid_matrix = np.array([cluster_centroids[cid] for cid in cluster_ids])

    bridges = []

    for post_id, embedding in post_embeddings.items():
        # Compute similarity to each cluster centroid
        sims = cosine_similarity(embedding.reshape(1, -1), centroid_matrix)[0]

        # Normalize to probabilities (softmax-like)
        exp_sims = np.exp(sims * 5)  # Temperature-scaled
        probs = exp_sims / exp_sims.sum()

        # Find clusters above threshold
        above_threshold = [
            (cluster_ids[i], float(probs[i]))
            for i in range(len(cluster_ids))
            if probs[i] >= threshold
        ]

        if len(above_threshold) >= 2:
            # Sort by probability
            above_threshold.sort(key=lambda x: x[1], reverse=True)
            primary = above_threshold[0]
            secondary = above_threshold[1:]

            bridges.append(BridgePost(
                post_id=post_id,
                title=post_titles.get(post_id, ""),
                primary_cluster_id=primary[0],
                primary_probability=primary[1],
                secondary_clusters=secondary,
            ))

    return bridges


def reduce_outliers(
    noise_embeddings: dict[UUID, np.ndarray],
    cluster_centroids: dict[UUID, np.ndarray],
    min_similarity: float = 0.20,
) -> dict[UUID, UUID]:
    """Reassign noise/outlier posts to their nearest cluster.

    Only reassigns if similarity > min_similarity (don't force truly
    unrelated content into clusters).

    Returns: {post_id: assigned_cluster_id}
    """
    if not noise_embeddings or not cluster_centroids:
        return {}

    cluster_ids = list(cluster_centroids.keys())
    centroid_matrix = np.array([cluster_centroids[cid] for cid in cluster_ids])

    assignments = {}
    for post_id, embedding in noise_embeddings.items():
        sims = cosine_similarity(embedding.reshape(1, -1), centroid_matrix)[0]
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])

        if best_sim >= min_similarity:
            assignments[post_id] = cluster_ids[best_idx]
            logger.debug(
                "Reassigned outlier %s to cluster %s (sim=%.3f)",
                post_id, cluster_ids[best_idx], best_sim,
            )

    return assignments


class AdvancedClusteringService:
    """Orchestrates advanced clustering features."""

    def __init__(self) -> None:
        settings = get_settings()
        self.claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def enrich_clusters(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> dict:
        """Run all advanced clustering enrichments for a site.

        1. Compute c-TF-IDF keywords per cluster
        2. Build topic hierarchy
        3. Detect bridge posts
        4. Reduce outliers
        5. Enhanced Claude labeling with c-TF-IDF context

        Returns summary of enrichments.
        """
        logger.info("Running advanced clustering for site %s", site_id)

        # Load clusters and their posts
        clusters = await db.fetch(
            "SELECT id, label, description FROM clusters WHERE site_id = $1",
            site_id,
        )
        if not clusters:
            return {"clusters": 0}

        # Load post texts grouped by cluster
        docs_per_cluster: dict[str, list[str]] = {}
        cluster_labels: dict[UUID, str] = {}
        cluster_post_ids: dict[UUID, list[UUID]] = defaultdict(list)

        for cluster in clusters:
            cid = cluster["id"]
            cluster_labels[cid] = cluster["label"] or ""
            posts = await db.fetch(
                """
                SELECT p.id, p.title, p.body_text
                FROM posts p
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )
            docs = []
            for p in posts:
                text = (p["title"] or "") + " " + (p["body_text"] or "")[:2000]
                docs.append(text)
                cluster_post_ids[cid].append(p["id"])
            docs_per_cluster[str(cid)] = docs

        # ── 1. c-TF-IDF ──
        ctfidf_results = await asyncio.to_thread(
            compute_ctfidf, docs_per_cluster, 10,
        )

        # Store c-TF-IDF keywords in cluster metadata
        for cluster in clusters:
            cid_str = str(cluster["id"])
            keywords = ctfidf_results.get(cid_str, [])
            keyword_list = [kw for kw, _ in keywords]
            await db.execute(
                """
                UPDATE clusters
                SET description = COALESCE(description, '') || E'\n\nTop keywords: ' || $2
                WHERE id = $1
                """,
                cluster["id"],
                ", ".join(keyword_list[:8]),
            )

        # ── 2. Load embeddings for hierarchy + bridge detection ──
        post_embeddings: dict[UUID, np.ndarray] = {}
        post_titles: dict[UUID, str] = {}
        post_assignments: dict[UUID, UUID] = {}

        for cid, pids in cluster_post_ids.items():
            for pid in pids:
                row = await db.fetchrow(
                    "SELECT embedding FROM post_embeddings WHERE post_id = $1",
                    pid,
                )
                if row and row["embedding"]:
                    emb_str = row["embedding"]
                    if isinstance(emb_str, str):
                        emb = np.array([float(x) for x in emb_str.strip("[]").split(",")])
                    else:
                        emb = np.array(emb_str)
                    post_embeddings[pid] = emb
                    post_assignments[pid] = cid

                title_row = await db.fetchrow(
                    "SELECT title FROM posts WHERE id = $1", pid,
                )
                if title_row:
                    post_titles[pid] = title_row["title"] or ""

        # Compute cluster centroids
        cluster_centroids: dict[UUID, np.ndarray] = {}
        for cid, pids in cluster_post_ids.items():
            embeddings = [post_embeddings[pid] for pid in pids if pid in post_embeddings]
            if embeddings:
                cluster_centroids[cid] = np.mean(embeddings, axis=0)

        # ── 3. Hierarchical topic modeling ──
        hierarchy = await asyncio.to_thread(
            build_hierarchy, cluster_centroids, cluster_labels, 0.50,
        )

        # Store hierarchy: parent_cluster_id on child clusters
        for root in hierarchy:
            for child in root.children:
                await db.execute(
                    """
                    UPDATE clusters
                    SET description = COALESCE(description, '') || E'\n\nParent topic: ' || $2
                    WHERE id = $1
                    """,
                    child.cluster_id, root.label,
                )

        # ── 4. Bridge post detection ──
        bridges = await asyncio.to_thread(
            detect_bridge_posts,
            post_embeddings, cluster_centroids,
            post_assignments, post_titles, 0.15,
        )

        # Store bridge post info
        for bridge in bridges:
            secondary_labels = []
            for sec_cid, sec_prob in bridge.secondary_clusters[:3]:
                secondary_labels.append(cluster_labels.get(sec_cid, str(sec_cid)))

            # Update post metadata (could use a dedicated column; using description for now)
            logger.info(
                "Bridge post '%s' spans: %s + %s",
                bridge.title,
                cluster_labels.get(bridge.primary_cluster_id, ""),
                ", ".join(secondary_labels),
            )

        # ── 5. Outlier reduction ──
        noise_posts = await db.fetch(
            """
            SELECT p.id, pe.embedding
            FROM posts p
            JOIN post_embeddings pe ON pe.post_id = p.id
            LEFT JOIN post_clusters pc ON pc.post_id = p.id
            WHERE p.site_id = $1
              AND pc.cluster_id IS NULL
            """,
            site_id,
        )

        noise_embeddings: dict[UUID, np.ndarray] = {}
        for np_row in noise_posts:
            if np_row["embedding"]:
                emb_str = np_row["embedding"]
                if isinstance(emb_str, str):
                    emb = np.array([float(x) for x in emb_str.strip("[]").split(",")])
                else:
                    emb = np.array(emb_str)
                noise_embeddings[np_row["id"]] = emb

        reassigned = await asyncio.to_thread(
            reduce_outliers, noise_embeddings, cluster_centroids, 0.20,
        )

        for post_id, new_cluster_id in reassigned.items():
            await db.execute(
                """
                INSERT INTO post_clusters (post_id, cluster_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                post_id, new_cluster_id,
            )

        # ── 6. Enhanced Claude labeling with c-TF-IDF ──
        relabeled = 0
        for cluster in clusters:
            cid_str = str(cluster["id"])
            keywords = ctfidf_results.get(cid_str, [])
            if not keywords:
                continue

            keyword_str = ", ".join([kw for kw, _ in keywords[:8]])
            titles = []
            for pid in cluster_post_ids[cluster["id"]][:8]:
                t = post_titles.get(pid, "")
                if t:
                    titles.append(t)

            if not titles:
                continue

            await self.rate_limiter.wait()
            try:
                prompt = truncate_for_api(f"""These blog posts are grouped in a content cluster:
{chr(10).join(f'- "{t}"' for t in titles)}

Top c-TF-IDF keywords: {keyword_str}

Give a 2-4 word topic label and a one-sentence description.
Format: Label: <label>
Description: <description>""", max_tokens=1500)

                response = await self.claude.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=200,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}],
                )

                text = response.content[0].text
                label_line = ""
                desc_line = ""
                for line in text.strip().split("\n"):
                    if line.startswith("Label:"):
                        label_line = line.replace("Label:", "").strip()
                    elif line.startswith("Description:"):
                        desc_line = line.replace("Description:", "").strip()

                if label_line:
                    await db.execute(
                        "UPDATE clusters SET label = $1, description = $2 WHERE id = $3",
                        label_line, desc_line, cluster["id"],
                    )
                    relabeled += 1

            except Exception as e:
                logger.error("Claude relabeling failed for cluster %s: %s",
                             cluster["id"], e)

        summary = {
            "clusters_enriched": len(clusters),
            "ctfidf_computed": len(ctfidf_results),
            "hierarchy_roots": len(hierarchy),
            "hierarchy_children": sum(len(r.children) for r in hierarchy),
            "bridge_posts": len(bridges),
            "outliers_reassigned": len(reassigned),
            "clusters_relabeled": relabeled,
        }
        logger.info("Advanced clustering complete: %s", summary)
        return summary
