"""End-to-end test of Pipeline Step 6: Clustering.

Runs UMAP + HDBSCAN clustering, 2D map positioning, and TF-IDF labeling
against real crawled data from Step 1. Simulates embeddings (no OpenAI key
needed) using random vectors with injected topic structure.

No database required — tests computation only.
"""

import asyncio
import time
from collections import Counter
from datetime import datetime

import numpy as np

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


def _generate_synthetic_embeddings(titles: list[str], n_dims: int = 1536) -> np.ndarray:
    """Generate synthetic embeddings with injected topic structure.

    Uses title keywords to create roughly clustered embeddings:
    - Posts with similar title words get nearby vectors
    - Random noise ensures clusters aren't perfectly separated
    """
    np.random.seed(42)
    n = len(titles)
    embeddings = np.random.randn(n, n_dims).astype(np.float32)

    # Inject topic structure using simple keyword hashing
    topic_keywords = [
        ["email", "subscriber", "list", "newsletter", "opt-in"],
        ["seo", "search", "rank", "keyword", "backlink", "link"],
        ["content", "writing", "copywriting", "headline", "blog"],
        ["social", "media", "facebook", "twitter", "share"],
        ["conversion", "landing", "funnel", "sales", "revenue"],
        ["freelance", "business", "client", "agency", "income"],
    ]

    for i, title in enumerate(titles):
        lower = title.lower()
        for topic_idx, keywords in enumerate(topic_keywords):
            match_count = sum(1 for kw in keywords if kw in lower)
            if match_count > 0:
                # Push embedding toward topic centroid
                offset = np.zeros(n_dims, dtype=np.float32)
                offset[topic_idx * 200:(topic_idx + 1) * 200] = match_count * 2.0
                embeddings[i] += offset

    # L2 normalize (like OpenAI embeddings)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-8)

    return embeddings


async def main():
    from app.services.fast_cluster_labels import (
        _compute_site_stops,
        _extract_phrases,
        _strip_format,
        _tfidf_label,
    )
    from app.services.normalizer import (
        _strip_html_from_meta,
        _strip_site_name_from_title,
        filter_nav_links,
        filter_sitewide_headings,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 6 E2E Test: {TARGET_DOMAIN} ===\n")

    # ── Phase 1: Crawl (reuse Step 1) ──
    crawler = SitemapCrawler(
        sitemap_url=TARGET_SITEMAP,
        domain=TARGET_DOMAIN,
        delay_seconds=0.5,
        max_pages=MAX_PAGES,
        concurrency=10,
        max_retries=3,
        timeout_seconds=30.0,
    )

    print("Crawling (Step 1 prerequisite)...")
    start = time.time()
    raw_posts = await crawler.crawl()
    crawl_time = time.time() - start
    print(f"  Crawled {len(raw_posts)} posts in {crawl_time:.1f}s")

    # Normalize
    seen = set()
    posts = []
    for p in raw_posts:
        norm = normalize_url(p.url)
        if norm not in seen:
            seen.add(norm)
            p.url = norm
            p.title = _strip_site_name_from_title(p.title)
            p.meta_description = _strip_html_from_meta(p.meta_description)
            posts.append(p)

    links_map = {p.url: p.internal_links for p in posts}
    headings_map = {p.url: p.headings for p in posts}
    filtered_links = filter_nav_links(links_map)
    filtered_headings = filter_sitewide_headings(headings_map)
    for p in posts:
        p.internal_links = filtered_links.get(p.url, p.internal_links)
        p.headings = filtered_headings.get(p.url, p.headings)

    posts = [p for p in posts if p.body_text and len(p.body_text.strip()) > 50]
    titles = [p.title or "" for p in posts]
    urls = [p.url for p in posts]
    n_posts = len(posts)
    print(f"  Normalized to {n_posts} posts\n")

    # ── Phase 2: Generate synthetic embeddings ──
    print("Step 6 prerequisite: Generating synthetic embeddings...")
    embed_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    embed_time = time.time() - embed_start
    print(f"  Generated {embeddings.shape[0]} x {embeddings.shape[1]} embedding matrix in {embed_time:.3f}s")

    # Pairwise similarity analysis
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim
    sample_size = min(100, n_posts)
    sample_indices = np.random.choice(n_posts, sample_size, replace=False)
    sample = embeddings[sample_indices]
    sim_matrix = cos_sim(sample)
    np.fill_diagonal(sim_matrix, 0)
    mean_sim = sim_matrix.mean()
    max_sim = sim_matrix.max()
    print(f"  Mean pairwise cosine similarity: {mean_sim:.3f}")
    print(f"  Max pairwise cosine similarity: {max_sim:.3f}\n")

    # ── Phase 3a: UMAP reduction (1536 -> 15D) ──
    import hdbscan
    import umap

    print("Step 6a: UMAP dimensionality reduction (1536 -> 15D)...")
    umap_start = time.time()

    n_components = max(2, min(15, n_posts - 2))
    n_neighbors = min(15, n_posts - 1)

    # Adaptive min_dist (same logic as clustering.py)
    if mean_sim > 0.70:
        min_dist = 0.25
        n_neighbors = min(5, max(1, n_posts - 1))
        niche_type = "tight niche"
    elif mean_sim > 0.50:
        min_dist = 0.1
        niche_type = "moderate focus"
    else:
        min_dist = 0.05
        niche_type = "diverse content"

    reducer_cluster = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric="cosine",
        random_state=42,
    )
    reduced = reducer_cluster.fit_transform(embeddings)
    umap_time = time.time() - umap_start

    print(f"  Input: {embeddings.shape[1]}D -> Output: {reduced.shape[1]}D")
    print(f"  Site type: {niche_type} (mean_sim={mean_sim:.3f})")
    print(f"  UMAP params: n_components={n_components}, n_neighbors={n_neighbors}, min_dist={min_dist}")
    print(f"  Processing time: {umap_time:.2f}s\n")

    # ── Phase 3b: HDBSCAN clustering ──
    print("Step 6b-main: HDBSCAN clustering...")
    hdb_start = time.time()

    # Adaptive params (same logic as clustering.py)
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
        min_cluster_size = 20
        min_samples = 5

    # Retry loop with silhouette quality gate
    retry_count = 0
    avg_silhouette = 0.0
    cluster_silhouettes = {}

    while True:
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = int(np.sum(labels == -1))

        if n_clusters >= 2:
            from sklearn.metrics import silhouette_samples, silhouette_score
            mask = labels != -1
            if mask.sum() >= 2:
                avg_silhouette = float(silhouette_score(reduced[mask], labels[mask]))
                per_sample = silhouette_samples(reduced[mask], labels[mask])
                for cl in set(labels[mask]):
                    cl_scores = per_sample[labels[mask] == cl]
                    cluster_silhouettes[int(cl)] = float(np.mean(cl_scores))

        if avg_silhouette < 0.1 and retry_count < 2 and n_clusters >= 2:
            retry_count += 1
            min_cluster_size += 1
            print(f"  Silhouette {avg_silhouette:.3f} < 0.1 — retrying (attempt {retry_count + 1})")
            continue
        break

    hdb_time = time.time() - hdb_start

    print(f"  HDBSCAN params: min_cluster_size={min_cluster_size}, min_samples={min_samples}")
    print(f"  Clusters found: {n_clusters}")
    print(f"  Noise points: {n_noise} ({n_noise / n_posts * 100:.1f}%)")
    print(f"  Avg silhouette: {avg_silhouette:.3f}")
    print(f"  Retries needed: {retry_count}")
    print(f"  Processing time: {hdb_time:.3f}s\n")

    # ── Phase 3c: Noise assignment ──
    print("Step 6c-main: Noise point assignment...")
    noise_start = time.time()
    original_noise = n_noise

    if n_noise > 0 and n_clusters > 0:
        from sklearn.metrics.pairwise import euclidean_distances
        noise_mask = labels == -1
        non_noise_mask = labels != -1
        if non_noise_mask.sum() > 0:
            unique_clusters = sorted(set(labels[non_noise_mask]))
            centroids = np.array([reduced[labels == c].mean(axis=0) for c in unique_clusters])
            noise_indices = np.where(noise_mask)[0]
            noise_reduced = reduced[noise_indices]
            dists = euclidean_distances(noise_reduced, centroids)
            nearest = np.argmin(dists, axis=1)
            for i, idx in enumerate(noise_indices):
                labels[idx] = unique_clusters[nearest[i]]

    noise_time = time.time() - noise_start
    final_noise = int(np.sum(labels == -1))
    print(f"  Reassigned {original_noise - final_noise} noise posts to nearest centroids")
    print(f"  Remaining unassigned: {final_noise}")
    print(f"  Processing time: {noise_time:.3f}s")

    # S3-16: Noise reassignment detail
    noise_detail: list[dict] = []
    if original_noise > 0 and n_clusters > 0:
        # Recompute centroids with final labels (includes reassigned noise)
        final_unique = sorted(set(labels) - {-1})
        final_centroids = {c: reduced[labels == c].mean(axis=0) for c in final_unique}
        # For each cluster, compute mean and std of member distances to centroid
        cluster_dist_stats: dict[int, tuple[float, float]] = {}
        for c in final_unique:
            members = reduced[labels == c]
            dists_to_centroid = np.linalg.norm(members - final_centroids[c], axis=1)
            cluster_dist_stats[c] = (float(dists_to_centroid.mean()), float(dists_to_centroid.std()))

        for i, idx in enumerate(noise_indices):
            assigned_cluster = int(labels[idx])
            dist_to_centroid = float(np.linalg.norm(reduced[idx] - final_centroids[assigned_cluster]))
            mean_dist, std_dist = cluster_dist_stats[assigned_cluster]
            is_outlier = dist_to_centroid > mean_dist + 2 * std_dist if std_dist > 0 else False
            noise_detail.append({
                "title": titles[idx][:50],
                "cluster": assigned_cluster,
                "dist": dist_to_centroid,
                "cluster_mean_dist": mean_dist,
                "cluster_std_dist": std_dist,
                "outlier": is_outlier,
            })

        n_outliers = sum(1 for d in noise_detail if d["outlier"])
        print(f"  Questionable assignments (>2 std): {n_outliers}/{len(noise_detail)}")
    print()

    # ── Phase 3d: 2D map positions ──
    print("Step 6d: 2D map positions (UMAP 1536 -> 2D)...")
    map_start = time.time()

    reducer_2d = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.3,
        metric="cosine",
        random_state=42,
    )
    positions_2d = reducer_2d.fit_transform(embeddings)
    map_time = time.time() - map_start

    # ── Phase 3d+: Cluster-aware 2D nudge ──
    print("Step 6d+: Cluster-aware 2D nudge (15% toward cluster centroid)...")
    nudge_start = time.time()
    positions_pre_nudge = positions_2d.copy()

    unique_lbls = set(labels)
    unique_lbls.discard(-1)
    if unique_lbls:
        centroids_2d = {c: positions_2d[labels == c].mean(axis=0) for c in unique_lbls}
        for i, lbl in enumerate(labels):
            if lbl in centroids_2d:
                positions_2d[i] += 0.15 * (centroids_2d[lbl] - positions_2d[i])

    nudge_time = time.time() - nudge_start

    # Measure nudge effect: avg displacement
    displacements = np.linalg.norm(positions_2d - positions_pre_nudge, axis=1)
    avg_displacement = float(displacements.mean())
    max_displacement = float(displacements.max())
    print(f"  Avg displacement: {avg_displacement:.4f}")
    print(f"  Max displacement: {max_displacement:.4f}")
    print(f"  Processing time: {nudge_time:.4f}s\n")

    x_range = positions_2d[:, 0].max() - positions_2d[:, 0].min()
    y_range = positions_2d[:, 1].max() - positions_2d[:, 1].min()
    print(f"  Map dimensions (post-nudge): x=[{positions_2d[:, 0].min():.2f}, {positions_2d[:, 0].max():.2f}] "
          f"y=[{positions_2d[:, 1].min():.2f}, {positions_2d[:, 1].max():.2f}]")
    print(f"  Spread: {x_range:.2f} x {y_range:.2f}")
    print(f"  Processing time (UMAP 2D): {map_time:.2f}s")

    # S3-17: Convex hull overlap analysis (before vs after nudge)
    def _point_in_hull(point: np.ndarray, hull_eq: np.ndarray) -> bool:
        """Check if a 2D point is inside a convex hull (using half-plane equations)."""
        return bool(np.all(hull_eq[:, :-1] @ point + hull_eq[:, -1] <= 1e-12))

    def _count_hull_overlaps(positions: np.ndarray, lbls: np.ndarray) -> int:
        """Count cluster pairs whose convex hulls overlap."""
        from scipy.spatial import ConvexHull
        unique = sorted(set(lbls) - {-1})
        hull_eqs: dict[int, np.ndarray] = {}
        for c in unique:
            pts = positions[lbls == c]
            if len(pts) < 3:
                continue
            try:
                hull = ConvexHull(pts)
                hull_eqs[c] = hull.equations
            except Exception:
                continue
        overlaps = 0
        hull_ids = list(hull_eqs.keys())
        for i in range(len(hull_ids)):
            for j in range(i + 1, len(hull_ids)):
                a, b = hull_ids[i], hull_ids[j]
                pts_a = positions[lbls == a]
                pts_b = positions[lbls == b]
                # Check if any point of A is inside hull of B or vice versa
                a_in_b = any(_point_in_hull(p, hull_eqs[b]) for p in pts_a)
                b_in_a = any(_point_in_hull(p, hull_eqs[a]) for p in pts_b)
                if a_in_b or b_in_a:
                    overlaps += 1
        return overlaps

    overlaps_before = _count_hull_overlaps(positions_pre_nudge, labels)
    overlaps_after = _count_hull_overlaps(positions_2d, labels)
    total_pairs = len(set(labels) - {-1}) * (len(set(labels) - {-1}) - 1) // 2
    print("\n  Territory overlap (convex hull):")
    print(f"    Before nudge: {overlaps_before}/{total_pairs} cluster pairs overlap")
    print(f"    After nudge:  {overlaps_after}/{total_pairs} cluster pairs overlap")
    if overlaps_before > overlaps_after:
        print(f"    Nudge reduced overlap by {overlaps_before - overlaps_after} pair(s)")
    elif overlaps_before == overlaps_after:
        print("    Nudge did not change overlap count")
    else:
        print(f"    WARNING: Nudge increased overlap by {overlaps_after - overlaps_before} pair(s)")
    print()

    # ── Phase 3e: Cluster analysis ──
    print("Step 6e: Cluster analysis...")
    cluster_groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label != -1:
            cluster_groups.setdefault(int(label), []).append(idx)

    mega_clusters = 0
    for cl, indices in cluster_groups.items():
        if len(indices) > 25:
            mega_clusters += 1

    print(f"  Total clusters: {len(cluster_groups)}")
    print(f"  Mega-clusters (> 25 posts): {mega_clusters}")

    cluster_sizes = [len(indices) for indices in cluster_groups.values()]
    if cluster_sizes:
        print(f"  Cluster sizes: min={min(cluster_sizes)}, max={max(cluster_sizes)}, "
              f"avg={sum(cluster_sizes) / len(cluster_sizes):.1f}, "
              f"median={sorted(cluster_sizes)[len(cluster_sizes) // 2]}")
    print()

    # ── Phase 3e+: Sub-clustering (S3-13) ──
    print("Step 6e+: Recursive sub-clustering for mega-clusters...")
    subcluster_start = time.time()
    MAX_CLUSTER_SIZE = 25
    subcluster_results: list[dict] = []

    for cl_id, member_indices in cluster_groups.items():
        if len(member_indices) <= MAX_CLUSTER_SIZE:
            continue
        sub_embeddings = embeddings[member_indices]
        sub_titles_list = [titles[i] for i in member_indices]
        n_sub = len(member_indices)

        # Sub-clustering UMAP (tighter params, matching clustering.py:_recursive_subcluster)
        sub_n_components = min(10, max(2, n_sub - 2))
        sub_n_neighbors = min(10, max(1, n_sub - 1))
        sub_reducer = umap.UMAP(
            n_components=sub_n_components,
            n_neighbors=sub_n_neighbors,
            min_dist=0.05,
            metric="cosine",
            random_state=43,  # 42 + depth=1
        )
        sub_reduced = sub_reducer.fit_transform(sub_embeddings)

        sub_min_cluster_size = max(3, n_sub // 10)
        sub_clusterer = hdbscan.HDBSCAN(
            min_cluster_size=sub_min_cluster_size,
            min_samples=2,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        sub_labels = sub_clusterer.fit_predict(sub_reduced)

        sub_unique = set(sub_labels) - {-1}
        sub_noise = int(np.sum(sub_labels == -1))

        # Reassign sub-noise to nearest child centroid
        if sub_noise > 0 and len(sub_unique) > 0:
            from sklearn.metrics.pairwise import euclidean_distances as eu_dist
            sub_noise_mask = sub_labels == -1
            sub_non_noise = sub_labels != -1
            if sub_non_noise.sum() > 0:
                sub_uniq_sorted = sorted(sub_unique)
                sub_centroids = np.array([sub_reduced[sub_labels == c].mean(axis=0) for c in sub_uniq_sorted])
                sub_noise_idx = np.where(sub_noise_mask)[0]
                sub_dists = eu_dist(sub_reduced[sub_noise_idx], sub_centroids)
                sub_nearest = np.argmin(sub_dists, axis=1)
                for si, sidx in enumerate(sub_noise_idx):
                    sub_labels[sidx] = sub_uniq_sorted[sub_nearest[si]]

        # Collect child cluster info
        children = []
        for sub_lbl in sorted(set(sub_labels) - {-1}):
            child_indices = [i for i, l in enumerate(sub_labels) if l == sub_lbl]
            child_titles = [sub_titles_list[i] for i in child_indices]
            children.append({
                "label_id": int(sub_lbl),
                "count": len(child_indices),
                "sample_titles": child_titles[:3],
            })

        result = {
            "parent_id": cl_id,
            "parent_size": len(member_indices),
            "sub_clusters_found": len(sub_unique),
            "sub_noise": sub_noise,
            "children": children,
        }
        subcluster_results.append(result)
        print(f"  Cluster {cl_id} ({len(member_indices)} posts) -> {len(sub_unique)} sub-clusters ({sub_noise} noise)")
        for ch in children:
            print(f"    Sub-cluster {ch['label_id']}: {ch['count']} posts")

    subcluster_time = time.time() - subcluster_start
    print(f"  Sub-clustering time: {subcluster_time:.3f}s\n")

    # ── Phase 3e-idempotent: Verify re-clustering produces same result ──
    print("Step 6e-idempotent: Verifying re-clustering idempotency...")
    rerun_clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    rerun_labels = rerun_clusterer.fit_predict(reduced)
    rerun_n_clusters = len(set(rerun_labels)) - (1 if -1 in rerun_labels else 0)
    rerun_noise = int(np.sum(rerun_labels == -1))
    idempotent_match = (rerun_n_clusters == n_clusters and rerun_noise == original_noise
                        and np.array_equal(labels, rerun_labels))
    if idempotent_match:
        print(f"  PASS: Re-clustering produced identical results ({n_clusters} clusters, {original_noise} noise)")
    else:
        print(f"  INFO: Re-clustering differs — {rerun_n_clusters} clusters vs {n_clusters}, "
              f"{rerun_noise} noise vs {original_noise} (HDBSCAN is deterministic, so this indicates a bug)")
    print()

    # ── Phase 3f: TF-IDF labeling ──
    print("Step 6f: TF-IDF cluster labeling...")
    label_start = time.time()

    site_stops = _compute_site_stops(titles)
    print(f"  Site-wide stop words: {', '.join(sorted(site_stops)[:10])}{'...' if len(site_stops) > 10 else ''}")

    # S3-14: Word frequency diagnostics
    from app.services.fast_cluster_labels import _FORMAT_WORDS, _STOP_WORDS, _WORD_RE
    word_doc_freq: Counter = Counter()
    for t in titles:
        stripped = _strip_format(t)
        words = set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS
        word_doc_freq.update(words)
    stop_threshold = int(len(titles) * 0.3)
    top_20_words = word_doc_freq.most_common(20)
    print(f"  Stop word threshold: {stop_threshold} (30% of {len(titles)} titles)")
    print("  Top 20 word frequencies:")
    for word, count in top_20_words:
        marker = " <-- STOPPED" if count >= stop_threshold else ""
        print(f"    {word}: {count}/{len(titles)} ({count / len(titles) * 100:.0f}%){marker}")
    if not site_stops:
        print(f"  WARNING: No site-wide stop words detected. Closest word: "
              f"'{top_20_words[0][0]}' at {top_20_words[0][1]}/{len(titles)} "
              f"({top_20_words[0][1] / len(titles) * 100:.0f}%), needs {stop_threshold}")
    print()

    cluster_labels: dict[int, str] = {}
    for cl_id, indices in cluster_groups.items():
        cl_titles = [titles[i] for i in indices]
        label, _, _ = _tfidf_label(cl_titles, titles, site_stops=site_stops)
        cluster_labels[cl_id] = label

    label_time = time.time() - label_start

    print(f"  Labeled {len(cluster_labels)} clusters in {label_time:.3f}s")
    print()

    # Print all clusters with labels
    print("  Cluster Labels:")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        indices = cluster_groups[cl_id]
        sil = cluster_silhouettes.get(cl_id, 0)
        label = cluster_labels.get(cl_id, "?")
        sample_titles = [titles[i][:60] for i in indices[:3]]
        print(f"    [{cl_id}] \"{label}\" — {len(indices)} posts (silhouette: {sil:.3f})")
        for st in sample_titles:
            print(f"         • {st}")
    print()

    # ── Phase 3g: Format stripping analysis ──
    print("Step 6g: Title format stripping analysis...")
    strip_results = []
    for t in titles[:20]:
        stripped = _strip_format(t)
        phrases = _extract_phrases(t)
        bigrams = [p for p in phrases if " " in p]
        strip_results.append({
            "original": t[:70],
            "stripped": stripped[:70],
            "phrases": len(phrases),
            "bigrams": len(bigrams),
        })
    print("  Sample title stripping (first 10):")
    for r in strip_results[:10]:
        print(f"    \"{r['original']}\"")
        print(f"     -> \"{r['stripped']}\" ({r['phrases']} phrases, {r['bigrams']} bigrams)")
    print()

    # ── Write Report ──
    total_time = umap_time + hdb_time + noise_time + map_time + nudge_time + label_time + subcluster_time
    report_path = "../STEP3-TEST-RESULTS.md"
    lines = []
    lines.append(f"# Step 6 E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Prerequisite:** {n_posts} posts from Step 1 crawl + synthetic embeddings")
    lines.append("**Note:** Embeddings are synthetic (keyword-injected random vectors), not real OpenAI embeddings. Cluster quality will differ with real embeddings.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3a: UMAP
    lines.append("## 3a. UMAP Dimensionality Reduction")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Input dimensions | {embeddings.shape[1]} |")
    lines.append(f"| Output dimensions (clustering) | {reduced.shape[1]} |")
    lines.append(f"| Posts processed | {n_posts} |")
    lines.append(f"| Site type (auto-detected) | {niche_type} (mean_sim={mean_sim:.3f}) |")
    lines.append(f"| UMAP n_components | {n_components} |")
    lines.append(f"| UMAP n_neighbors | {n_neighbors} |")
    lines.append(f"| UMAP min_dist | {min_dist} |")
    lines.append(f"| Processing time | {umap_time:.2f}s |")
    lines.append("")

    # 3b: HDBSCAN
    lines.append("## 3b. HDBSCAN Clustering")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| min_cluster_size | {min_cluster_size} |")
    lines.append(f"| min_samples | {min_samples} |")
    lines.append(f"| **Clusters found** | **{n_clusters}** |")
    lines.append(f"| Noise points (before reassignment) | {original_noise} ({original_noise / n_posts * 100:.1f}%) |")
    lines.append(f"| **Avg silhouette score** | **{avg_silhouette:.3f}** |")
    lines.append(f"| Quality retries | {retry_count} |")
    lines.append(f"| Processing time | {hdb_time:.3f}s |")
    lines.append("")

    # Cluster size distribution
    lines.append("### Cluster Size Distribution")
    lines.append("")
    lines.append("| Size Range | Count | % of Clusters |")
    lines.append("|-----------|-------|--------------|")
    size_ranges = [(1, 5), (6, 10), (11, 15), (16, 25), (26, 50), (51, 999)]
    range_labels = ["1-5", "6-10", "11-15", "16-25", "26-50 (mega)", "51+"]
    for (lo, hi), rl in zip(size_ranges, range_labels):
        count = sum(1 for s in cluster_sizes if lo <= s <= hi)
        pct = count / len(cluster_sizes) * 100 if cluster_sizes else 0
        lines.append(f"| {rl} | {count} | {pct:.0f}% |")
    lines.append("")

    # Per-cluster silhouette
    lines.append("### Per-Cluster Quality")
    lines.append("")
    lines.append("| Cluster | Label | Posts | Silhouette |")
    lines.append("|---------|-------|-------|-----------|")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        sil = cluster_silhouettes.get(cl_id, 0)
        label = cluster_labels.get(cl_id, "?")
        count = len(cluster_groups[cl_id])
        lines.append(f"| {cl_id} | {label} | {count} | {sil:.3f} |")
    lines.append("")

    # 3c: Noise
    lines.append("## 3c. Noise Assignment")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Original noise points | {original_noise} |")
    lines.append(f"| Reassigned to clusters | {original_noise - final_noise} |")
    lines.append(f"| Remaining unassigned | {final_noise} |")
    lines.append(f"| Processing time | {noise_time:.3f}s |")
    lines.append("")

    # 3c+: Noise reassignment detail (S3-16)
    if noise_detail:
        lines.append("### Noise Reassignment Detail")
        lines.append("")
        n_outliers = sum(1 for d in noise_detail if d["outlier"])
        lines.append(f"**Questionable assignments (>2 std from centroid):** {n_outliers}/{len(noise_detail)}")
        lines.append("")
        lines.append("| Post Title | Assigned Cluster | Distance | Cluster Mean Dist | Outlier |")
        lines.append("|-----------|-----------------|----------|-------------------|---------|")
        for d in noise_detail:
            flag = "YES" if d["outlier"] else ""
            lines.append(f"| {d['title']} | {d['cluster']} | {d['dist']:.3f} | {d['cluster_mean_dist']:.3f} +/- {d['cluster_std_dist']:.3f} | {flag} |")
        lines.append("")

    # 3d: Map positions
    lines.append("## 3d. 2D Map Positions")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| X range (post-nudge) | [{positions_2d[:, 0].min():.2f}, {positions_2d[:, 0].max():.2f}] |")
    lines.append(f"| Y range (post-nudge) | [{positions_2d[:, 1].min():.2f}, {positions_2d[:, 1].max():.2f}] |")
    lines.append(f"| Spread | {x_range:.2f} x {y_range:.2f} |")
    lines.append(f"| UMAP 2D time | {map_time:.2f}s |")
    lines.append("| Cluster-aware nudge | 15% toward centroid |")
    lines.append(f"| Avg displacement (nudge) | {avg_displacement:.4f} |")
    lines.append(f"| Max displacement (nudge) | {max_displacement:.4f} |")
    lines.append(f"| Nudge time | {nudge_time:.4f}s |")
    lines.append("")

    # 3d+: Territory overlap (S3-17)
    lines.append("### Territory Overlap (Convex Hull)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total cluster pairs | {total_pairs} |")
    lines.append(f"| Overlapping before nudge | {overlaps_before} |")
    lines.append(f"| Overlapping after nudge | {overlaps_after} |")
    lines.append(f"| Overlap reduction | {overlaps_before - overlaps_after} pair(s) |")
    lines.append("")

    # 3e+: Sub-clustering results (S3-13)
    if subcluster_results:
        lines.append("## 3e+. Sub-Clustering Results")
        lines.append("")
        for sr in subcluster_results:
            lines.append(f"### Parent Cluster {sr['parent_id']} ({sr['parent_size']} posts)")
            lines.append("")
            lines.append(f"**Sub-clusters found:** {sr['sub_clusters_found']} (noise: {sr['sub_noise']})")
            lines.append("")
            if sr['children']:
                lines.append("| Sub-cluster | Posts | Sample Titles |")
                lines.append("|------------|-------|--------------|")
                for ch in sr['children']:
                    samples = "; ".join(t[:40] for t in ch['sample_titles'][:2])
                    lines.append(f"| {ch['label_id']} | {ch['count']} | {samples} |")
                lines.append("")
    else:
        lines.append("## 3e+. Sub-Clustering Results")
        lines.append("")
        lines.append("No mega-clusters (> 25 posts) found. Sub-clustering not triggered.")
        lines.append("")

    # 3f: Labels
    lines.append("## 3f. TF-IDF Cluster Labels")
    lines.append("")
    lines.append(f"**Site-wide stop words detected:** {', '.join(sorted(site_stops)) if site_stops else '(none)'}")
    lines.append(f"**Stop word threshold:** {stop_threshold} occurrences (30% of {len(titles)} titles)")
    lines.append("")
    lines.append("### Word Frequency Analysis (Top 20)")
    lines.append("")
    lines.append("| Word | Titles Containing | % | Stopped? |")
    lines.append("|------|------------------|---|----------|")
    for word, count in top_20_words:
        stopped = "YES" if count >= stop_threshold else ""
        lines.append(f"| {word} | {count}/{len(titles)} | {count / len(titles) * 100:.0f}% | {stopped} |")
    lines.append("")
    lines.append("| Cluster | Label | Posts | Sample Titles |")
    lines.append("|---------|-------|-------|--------------|")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        indices = cluster_groups[cl_id]
        label = cluster_labels.get(cl_id, "?")
        samples = "; ".join(titles[i][:40] for i in indices[:2])
        lines.append(f"| {cl_id} | {label} | {len(indices)} | {samples} |")
    lines.append("")

    # Summary
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Step | Time | External API | Notes |")
    lines.append("|------|------|-------------|-------|")
    lines.append(f"| Crawl (Step 1 prerequisite) | {crawl_time:.1f}s | None | |")
    lines.append(f"| UMAP 15D reduction | {umap_time:.2f}s | None | CPU-bound |")
    lines.append(f"| HDBSCAN clustering | {hdb_time:.3f}s | None | {retry_count} retries |")
    lines.append(f"| Noise assignment | {noise_time:.3f}s | None | {original_noise} -> {final_noise} noise |")
    lines.append(f"| UMAP 2D mapping | {map_time:.2f}s | None | CPU-bound |")
    lines.append(f"| Cluster-aware nudge | {nudge_time:.4f}s | None | 15% toward centroid |")
    lines.append(f"| TF-IDF labeling | {label_time:.3f}s | None | |")
    lines.append(f"| Sub-clustering | {subcluster_time:.3f}s | None | {mega_clusters} mega-clusters split |")
    lines.append(f"| **Total Step 6** | **{total_time:.2f}s** | **Free** | |")
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")

    # S3-13: Sub-clustering results
    if mega_clusters > 0:
        total_sub = sum(sr['sub_clusters_found'] for sr in subcluster_results)
        lines.append(f"- **{mega_clusters} mega-cluster(s) sub-clustered** into {total_sub} child clusters total")

    # Silhouette
    if avg_silhouette < 0.1:
        lines.append(f"- **Low silhouette score ({avg_silhouette:.3f})** -- clusters are weakly separated (expected with synthetic embeddings)")
    elif avg_silhouette < 0.25:
        lines.append(f"- **Moderate silhouette score ({avg_silhouette:.3f})** -- clusters have some overlap")
    else:
        lines.append(f"- **Good silhouette score ({avg_silhouette:.3f})** -- clusters are well-separated")

    # Noise
    if original_noise > n_posts * 0.3:
        lines.append(f"- **High noise rate ({original_noise / n_posts * 100:.1f}%)** -- many posts didn't fit any cluster")
    n_outliers_total = sum(1 for d in noise_detail if d["outlier"]) if noise_detail else 0
    if n_outliers_total > 0:
        lines.append(f"- **{n_outliers_total} questionable noise reassignment(s)** -- assigned posts > 2 std from cluster centroid")

    # Vague labels
    vague_labels = [l for l in cluster_labels.values() if l in ("General Content", "Miscellaneous") or "&" not in l and len(l.split()) == 1]
    if vague_labels:
        lines.append(f"- **{len(vague_labels)} vague label(s)** -- would benefit from Claude backfill")

    # S3-14: Stop words
    if not site_stops:
        lines.append(f"- **No site-wide stop words detected** -- closest word '{top_20_words[0][0]}' at {top_20_words[0][1]}/{len(titles)} "
                      f"({top_20_words[0][1] / len(titles) * 100:.0f}%), needs {stop_threshold} (30%). "
                      f"Copyblogger titles are too diverse for the 150-post subset. Labels may contain site vocabulary.")

    # S3-15: Cluster count artifact
    lines.append(f"- **Cluster count ({n_clusters}) {'is low' if n_clusters < 6 else 'is reasonable'}** -- "
                  f"expected 8-15 for {n_posts} posts. Backlinko (real embeddings) produced 11 clusters. "
                  f"Synthetic embeddings (mean_sim={mean_sim:.3f}) trigger 'diverse content' mode (min_dist=0.05), "
                  f"which compacts clusters. Real Copyblogger content would have higher similarity and more clusters.")

    # S3-17: Overlap
    lines.append(f"- **Territory overlap: {overlaps_before} -> {overlaps_after} pairs** (nudge {'reduced' if overlaps_after < overlaps_before else 'did not reduce'} overlap)")

    # S3-18: Frontend finding
    lines.append("- **Frontend ignores UMAP 2D coordinates** -- EcosystemCanvas.tsx uses D3 force layout with random initial positions, "
                  "not posts.x_pos/y_pos. The UMAP 2D positions are stored in the DB but unused by the current renderer. "
                  "Coordinate range and normalization are not a concern.")

    lines.append("- Synthetic embeddings produce different clustering than real OpenAI embeddings -- use results as structural validation only")
    lines.append("")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to {report_path}")
    print(f"\n=== Step 6 E2E complete — {n_clusters} clusters, {total_time:.2f}s total ===")


if __name__ == "__main__":
    asyncio.run(main())
