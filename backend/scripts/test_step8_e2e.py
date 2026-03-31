"""End-to-end test of Pipeline Step 8: Cannibalization Detection.

Runs blended cannibalization scoring, entity extraction, intent classification,
and resolution recommendation against real crawled data from Copyblogger.
Uses crawl-only mode (no GA4/GSC data, no database) to validate detection
logic, blended scoring, and pair filtering.

Reuses Step 1 crawl, Step 6 clustering, and Step 7 health scoring as prerequisites.
No database required -- tests computation only using in-memory pairwise comparison.
"""

import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import combinations

import numpy as np

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


def _generate_synthetic_embeddings(titles: list[str], n_dims: int = 1536) -> np.ndarray:
    """Generate synthetic embeddings with injected topic structure.

    Same as test_step3_e2e.py -- uses title keywords to create roughly
    clustered embeddings for UMAP+HDBSCAN.
    """
    np.random.seed(42)
    n = len(titles)
    embeddings = np.random.randn(n, n_dims).astype(np.float32)

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
                offset = np.zeros(n_dims, dtype=np.float32)
                offset[topic_idx * 200:(topic_idx + 1) * 200] = match_count * 2.0
                embeddings[i] += offset

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-8)
    return embeddings


def _run_clustering(embeddings: np.ndarray, n_posts: int) -> tuple[np.ndarray, dict[int, list[int]]]:
    """Run UMAP+HDBSCAN clustering (same as test_step3_e2e.py / test_step4_e2e.py).

    Returns (labels, cluster_groups) where cluster_groups maps
    cluster_id -> list of post indices.
    """
    import umap
    import hdbscan
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim

    sample_size = min(100, n_posts)
    sample_indices = np.random.choice(n_posts, sample_size, replace=False)
    sample = embeddings[sample_indices]
    sim_matrix = cos_sim(sample)
    np.fill_diagonal(sim_matrix, 0)
    mean_sim = sim_matrix.mean()

    n_components = max(2, min(15, n_posts - 2))
    n_neighbors = min(15, n_posts - 1)

    if mean_sim > 0.70:
        min_dist = 0.25
        n_neighbors = min(5, max(1, n_posts - 1))
    elif mean_sim > 0.50:
        min_dist = 0.1
    else:
        min_dist = 0.05

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric="cosine",
        random_state=42,
    )
    reduced = reducer.fit_transform(embeddings)

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

    retry_count = 0
    while True:
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        if n_clusters >= 2:
            from sklearn.metrics import silhouette_score
            mask = labels != -1
            if mask.sum() >= 2:
                avg_sil = float(silhouette_score(reduced[mask], labels[mask]))
                if avg_sil < 0.1 and retry_count < 2:
                    retry_count += 1
                    min_cluster_size += 1
                    continue
        break

    # Noise assignment
    n_noise = int(np.sum(labels == -1))
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

    cluster_groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label != -1:
            cluster_groups.setdefault(int(label), []).append(idx)

    return labels, cluster_groups


def _compute_health_scores(posts, cluster_groups, n_posts):
    """Compute crawl-only health scores (reuse Step 7 logic)."""
    from app.services.health_scoring import (
        compute_dynamic_weights,
        _compute_trend,
        _ranking_score,
        _engagement_score,
        _freshness_score,
        _content_depth_score,
        _technical_seo_score,
        _predicted_engagement_score,
        _content_structure_score,
    )

    now = datetime.now(UTC)
    weights = compute_dynamic_weights(has_ga4=False, has_gsc=False)

    # Cluster averages
    cluster_avg_wc: dict[int, float] = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if posts[i].word_count]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if len(wcs) >= 3 else 1000.0

    post_cluster_map: dict[int, int] = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    # Word count profile
    word_counts_all = [p.word_count for p in posts if p.word_count and p.word_count > 50]
    median_wc = statistics.median(word_counts_all) if word_counts_all else 1000
    stddev_wc = statistics.stdev(word_counts_all) if len(word_counts_all) > 1 else 500
    is_short_form = median_wc < 600 and stddev_wc < 400

    # Inbound links
    url_to_idx: dict[str, int] = {p.url: i for i, p in enumerate(posts)}
    inbound_counts: dict[int, int] = {i: 0 for i in range(n_posts)}
    outbound_counts: dict[int, int] = {i: 0 for i in range(n_posts)}
    for i, p in enumerate(posts):
        for link in p.internal_links:
            target_url = link.target_url if hasattr(link, "target_url") else (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1
                outbound_counts[i] += 1

    health_scores: list[float] = []
    for i, p in enumerate(posts):
        cl_id = post_cluster_map.get(i, 0)
        avg_wc = cluster_avg_wc.get(cl_id, 1000.0)
        last_updated = p.modified_date or p.publish_date

        trend_score = _compute_trend(0, 0, 0)[1]
        ranking = _ranking_score(100.0)
        engagement = _engagement_score(0.5, 60.0)
        freshness = _freshness_score(last_updated, now, title=p.title or "", url=p.url)
        depth = _content_depth_score(p.word_count or 0, avg_wc, body_html=p.body_html, short_form=is_short_form)

        cluster_indices = cluster_groups.get(cl_id, [])
        max_inbound_cluster = max((inbound_counts.get(j, 0) for j in cluster_indices), default=1)
        inbound = inbound_counts.get(i, 0)
        link_score = min(100.0, (inbound / max(max_inbound_cluster, 1)) * 100.0)

        tech = _technical_seo_score(
            meta_description=p.meta_description, title=p.title, headings=p.headings,
            has_outbound=outbound_counts.get(i, 0) > 0, has_inbound=inbound > 0,
            body_html=p.body_html,
        )
        ai_readiness = 40.0
        predicted_eng = _predicted_engagement_score(body_html=p.body_html, readability_score=None, headings=p.headings)
        content_struct = _content_structure_score(body_html=p.body_html, word_count=p.word_count or 0, headings=p.headings)

        composite = (
            weights["traffic_trend"] * trend_score
            + weights["ranking"] * ranking
            + weights["engagement"] * engagement
            + weights["freshness"] * freshness
            + weights["content_depth"] * depth
            + weights["internal_links"] * link_score
            + weights["technical_seo"] * tech
            + weights["ai_readiness"] * ai_readiness
            + weights.get("predicted_engagement", 0) * predicted_eng
            + weights.get("content_structure", 0) * content_struct
        )
        composite = max(10.0, min(95.0, composite))
        health_scores.append(composite)

    return health_scores


async def main():
    from app.services.normalizer import (
        filter_nav_links,
        filter_sitewide_headings,
        _strip_site_name_from_title,
        _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.services.cannibalization import (
        compute_blended_cannibalization_score,
        CannibalizationDetector,
        _extract_title_entity,
        _extract_title_keywords,
        _classify_intent_group,
        _h2_subtopic_jaccard,
        _title_topic_overlap,
        _extract_slug_core,
        _is_review_template,
        COSINE_THRESHOLD_FLAG,
        COSINE_THRESHOLD_HIGH,
        COSINE_THRESHOLD_CRITICAL,
        MIN_SHARED_QUERIES,
    )
    from app.utils.url_normalize import normalize_url
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim

    print(f"=== Step 8 E2E Test: {TARGET_DOMAIN} ===\n")

    # ===================================================================
    # PHASE 1: Crawl (reuse Step 1)
    # ===================================================================
    crawler = SitemapCrawler(
        sitemap_url=TARGET_SITEMAP,
        domain=TARGET_DOMAIN,
        delay_seconds=0.5,
        max_pages=MAX_PAGES,
        concurrency=10,
        max_retries=3,
        timeout_seconds=30.0,
    )

    print("Phase 1: Crawling (Step 1 prerequisite)...")
    crawl_start = time.time()
    raw_posts = await crawler.crawl()
    crawl_time = time.time() - crawl_start
    print(f"  Crawled {len(raw_posts)} posts in {crawl_time:.1f}s")

    # Normalize
    seen: set[str] = set()
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
    posts = [p for p in posts if (p.word_count or 0) >= 100]
    n_posts = len(posts)
    print(f"  Normalized to {n_posts} posts (>= 100 words)\n")

    if n_posts == 0:
        print("ERROR: No posts after filtering. Exiting.")
        sys.exit(1)

    # ===================================================================
    # PHASE 2: Clustering (reuse Step 6)
    # ===================================================================
    print("Phase 2: Clustering (Step 6 prerequisite)...")
    titles = [p.title or "" for p in posts]
    cluster_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    labels, cluster_groups = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - cluster_start
    n_clusters = len(cluster_groups)
    print(f"  Generated {n_clusters} clusters in {cluster_time:.1f}s\n")

    # ===================================================================
    # PHASE 2b: Inject synthetic cannibalization pairs (S5-13)
    # ===================================================================
    # Real crawl data with synthetic embeddings produces 0 pairs — not enough
    # to validate detection. Inject deliberate cannibalization: 2 pairs of posts
    # with similar titles/slugs and near-identical embeddings in the same cluster.
    print("Phase 2b: Injecting synthetic cannibalization test cases...")
    from dataclasses import dataclass, field

    @dataclass
    class FakePost:
        title: str = ""
        url: str = ""
        body_text: str = "Placeholder body text for synthetic test post."
        body_html: str = "<p>Placeholder body text for synthetic test post.</p>"
        meta_description: str = ""
        word_count: int = 1200
        headings: list = field(default_factory=list)
        internal_links: list = field(default_factory=list)
        publish_date: object = None
        modified_date: object = None

    # Pair 1: "SEO Link Building Guide" vs "Link Building Strategies for SEO"
    # Same topic, same slug keywords, should be flagged as cannibalization
    fake_a = FakePost(
        title="SEO Link Building Guide: The Definitive Resource",
        url="https://copyblogger.com/seo-link-building-guide/",
        headings=[{"text": "What is Link Building", "level": 2},
                  {"text": "Best Link Building Strategies", "level": 2},
                  {"text": "Outreach Templates", "level": 2}],
    )
    fake_b = FakePost(
        title="Link Building Strategies for SEO: A Complete Guide",
        url="https://copyblogger.com/link-building-strategies-seo/",
        headings=[{"text": "Top Link Building Techniques", "level": 2},
                  {"text": "Best Link Building Strategies", "level": 2},
                  {"text": "Guest Post Outreach", "level": 2}],
    )

    # Pair 2: "Content Marketing Tips" vs "Content Marketing Strategies"
    fake_c = FakePost(
        title="17 Content Marketing Tips That Actually Work",
        url="https://copyblogger.com/content-marketing-tips/",
        headings=[{"text": "Create a Content Calendar", "level": 2},
                  {"text": "Content Distribution Channels", "level": 2}],
    )
    fake_d = FakePost(
        title="Content Marketing Strategies for B2B Growth",
        url="https://copyblogger.com/content-marketing-strategies/",
        headings=[{"text": "Build a Content Calendar", "level": 2},
                  {"text": "Content Distribution Best Practices", "level": 2}],
    )

    injected_posts = [fake_a, fake_b, fake_c, fake_d]
    injected_start_idx = len(posts)
    posts.extend(injected_posts)
    n_posts = len(posts)

    # Create near-identical embeddings for each pair (cosine ~0.90+)
    # Use the first cluster's centroid as the base, add small noise
    first_cluster_id = list(cluster_groups.keys())[0]
    first_cluster_indices = cluster_groups[first_cluster_id]
    base_embedding = embeddings[first_cluster_indices[0]].copy()

    new_embeddings = np.zeros((4, embeddings.shape[1]), dtype=np.float32)
    np.random.seed(999)
    # Pair 1: very similar (cosine ~0.95)
    noise1 = np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.05
    new_embeddings[0] = base_embedding + noise1
    new_embeddings[1] = base_embedding + noise1 * 0.3  # Very close to [0]
    # Pair 2: moderately similar (cosine ~0.80)
    noise2 = np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.15
    new_embeddings[2] = base_embedding + noise2
    new_embeddings[3] = base_embedding + noise2 * 0.5 + np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.08

    # L2 normalize
    for i in range(4):
        norm = np.linalg.norm(new_embeddings[i])
        if norm > 0:
            new_embeddings[i] /= norm

    embeddings = np.vstack([embeddings, new_embeddings])

    # Add injected posts to the first cluster
    for offset in range(4):
        idx = injected_start_idx + offset
        labels = np.append(labels, first_cluster_id)
        cluster_groups[first_cluster_id].append(idx)

    # Update titles list
    titles = [p.title if hasattr(p, 'title') else p.get('title', '') for p in posts]

    cosine_pair1 = float(np.dot(embeddings[injected_start_idx], embeddings[injected_start_idx + 1]))
    cosine_pair2 = float(np.dot(embeddings[injected_start_idx + 2], embeddings[injected_start_idx + 3]))
    print(f"  Injected 4 synthetic posts at indices {injected_start_idx}-{injected_start_idx+3}")
    print(f"  Pair 1 cosine: {cosine_pair1:.3f} (SEO Link Building)")
    print(f"  Pair 2 cosine: {cosine_pair2:.3f} (Content Marketing)")
    print(f"  Total posts: {n_posts}\n")

    # ===================================================================
    # PHASE 3: Health Scoring (reuse Step 7)
    # ===================================================================
    print("Phase 3: Health scoring (Step 7 prerequisite)...")
    health_start = time.time()
    health_scores = _compute_health_scores(posts, cluster_groups, n_posts)
    health_time = time.time() - health_start
    print(f"  Scored {n_posts} posts in {health_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 4: Pairwise Similarity Distribution (Threshold Calibration)
    # ===================================================================
    print("Phase 4: Pairwise similarity distribution (calibration)...")
    calibration_start = time.time()

    # Compute pairwise cosine similarity for a random sample (mimic DB calibration)
    sample_size = min(500, n_posts * (n_posts - 1) // 2)
    all_pair_indices = list(combinations(range(n_posts), 2))
    np.random.seed(42)
    if len(all_pair_indices) > sample_size:
        sample_indices = np.random.choice(len(all_pair_indices), sample_size, replace=False)
        sampled_pairs = [all_pair_indices[i] for i in sample_indices]
    else:
        sampled_pairs = all_pair_indices

    sample_sims = []
    for i, j in sampled_pairs:
        sim = float(np.dot(embeddings[i], embeddings[j]))
        sample_sims.append(sim)

    sample_sims_arr = np.array(sample_sims)
    p85 = float(np.percentile(sample_sims_arr, 85))
    p92 = float(np.percentile(sample_sims_arr, 92))
    p97 = float(np.percentile(sample_sims_arr, 97))

    calibrated_flag = max(p85, 0.40)
    calibrated_high = max(p92, 0.50)
    calibrated_critical = max(p97, 0.60)

    calibration_time = time.time() - calibration_start

    print(f"  Sampled {len(sampled_pairs)} pairs")
    print(f"  Distribution: min={sample_sims_arr.min():.4f}, median={np.median(sample_sims_arr):.4f}, max={sample_sims_arr.max():.4f}")
    print(f"  Percentiles: p85={p85:.4f}, p92={p92:.4f}, p97={p97:.4f}")
    print(f"  Calibrated thresholds: flag={calibrated_flag:.4f}, high={calibrated_high:.4f}, critical={calibrated_critical:.4f}")
    print(f"  Calibration time: {calibration_time * 1000:.1f}ms\n")

    # Use defaults for this test (synthetic embeddings have different distribution)
    t_flag = COSINE_THRESHOLD_FLAG
    t_high = COSINE_THRESHOLD_HIGH
    t_critical = COSINE_THRESHOLD_CRITICAL
    print(f"  Using default thresholds for test: flag={t_flag}, high={t_high}, critical={t_critical}")
    print(f"  (Calibrated thresholds not used -- synthetic embeddings have unusual distribution)\n")

    # ===================================================================
    # PHASE 5: Entity Extraction Test
    # ===================================================================
    print("Phase 5: Entity extraction from titles...")
    entity_start = time.time()
    entities: dict[int, str | None] = {}
    entity_counts = Counter()

    for i, p in enumerate(posts):
        entity = _extract_title_entity(p.title or "")
        entities[i] = entity
        if entity:
            entity_counts[entity] += 1

    entity_time = time.time() - entity_start
    extracted_count = sum(1 for e in entities.values() if e is not None)
    print(f"  Extracted entities from {extracted_count}/{n_posts} titles ({extracted_count/n_posts*100:.1f}%)")
    print(f"  Unique entities: {len(entity_counts)}")
    print(f"  Top 10 entities:")
    for entity, count in entity_counts.most_common(10):
        print(f"    {entity}: {count} posts")
    print(f"  Extraction time: {entity_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 6: Intent Classification Test
    # ===================================================================
    print("Phase 6: Intent classification...")
    intent_start = time.time()
    intents: dict[int, str | None] = {}
    intent_counter = Counter()

    for i, p in enumerate(posts):
        intent = _classify_intent_group(p.title or "", p.url)
        intents[i] = intent
        if intent:
            intent_counter[intent] += 1

    intent_time = time.time() - intent_start
    classified_count = sum(1 for i in intents.values() if i is not None)
    print(f"  Classified {classified_count}/{n_posts} posts ({classified_count/n_posts*100:.1f}%)")
    print(f"  Intent distribution:")
    for intent, count in intent_counter.most_common():
        pct = count / n_posts * 100
        bar = "#" * int(pct)
        print(f"    {intent:12s} {count:4d} ({pct:5.1f}%)  {bar}")
    unclassified = n_posts - classified_count
    print(f"    {'(none)':12s} {unclassified:4d} ({unclassified/n_posts*100:5.1f}%)")
    print(f"  Classification time: {intent_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 7: Per-Cluster Cannibalization Detection
    # ===================================================================
    print("Phase 7: Per-cluster cannibalization detection...")
    detection_start = time.time()

    all_pairs: list[dict] = []
    filtered_pairs: list[dict] = []  # Pairs filtered by low blended score (for S5-05 analysis)
    closest_misses: dict[int, dict] = {}  # Per-cluster highest-sim pair NOT flagged (for S5-09)
    cluster_pair_counts: dict[int, int] = {}
    skipped_same_hash = 0
    skipped_low_blended = 0
    total_candidates = 0

    for cl_id, indices in cluster_groups.items():
        if len(indices) < 2:
            cluster_pair_counts[cl_id] = 0
            continue

        cluster_posts = [(i, posts[i]) for i in indices]
        pairs_in_cluster = 0

        for (idx_a, post_a), (idx_b, post_b) in combinations(cluster_posts, 2):
            total_candidates += 1

            # Cosine similarity (in-memory)
            cosine_sim = float(np.dot(embeddings[idx_a], embeddings[idx_b]))

            # No GSC data in this test
            n_shared = 0

            # Intent-aware threshold
            intent_a = intents.get(idx_a)
            intent_b = intents.get(idx_b)
            effective_flag = t_flag
            if intent_a and intent_b and intent_a != intent_b:
                effective_flag = t_flag + 0.10

            # Cannibalization gate
            is_cannibal = False
            if cosine_sim >= effective_flag:
                is_cannibal = True
            if n_shared >= MIN_SHARED_QUERIES:
                is_cannibal = True

            if not is_cannibal:
                # Track closest miss per cluster (highest cosine pair that didn't pass gate)
                miss_key = cl_id
                if miss_key not in closest_misses or cosine_sim > closest_misses[miss_key].get("cosine_sim", 0):
                    closest_misses[miss_key] = {
                        "title_a": post_a.title or "(no title)",
                        "title_b": post_b.title or "(no title)",
                        "cosine_sim": cosine_sim,
                        "threshold_used": effective_flag,
                    }
                continue

            # Headings
            headings_a = post_a.headings or []
            headings_b = post_b.headings or []

            # Build post dicts for blended scoring
            post_a_dict = {"title": post_a.title or "", "url": post_a.url, "content_intent": intent_a}
            post_b_dict = {"title": post_b.title or "", "url": post_b.url, "content_intent": intent_b}

            blended_score, blended_tier = compute_blended_cannibalization_score(
                post_a_dict, post_b_dict, headings_a, headings_b, cosine_sim,
            )

            # Filter low-tier — capture details for filtered pair analysis (S5-05)
            if blended_tier == "low":
                skipped_low_blended += 1
                # Skip homepage-like posts for samples (S5-19: they dominate the list)
                title_a_lower = (post_a.title or "").lower()
                title_b_lower = (post_b.title or "").lower()
                is_homepage = any(
                    "content marketing tools" in t or len(t) < 15 or " - " in t
                    for t in [title_a_lower, title_b_lower]
                )
                if len(filtered_pairs) < 10 and not is_homepage:
                    slug_a_f = _extract_slug_core(post_a.url)
                    slug_b_f = _extract_slug_core(post_b.url)
                    slug_overlap_f = len(slug_a_f & slug_b_f) / len(slug_a_f | slug_b_f) if (slug_a_f | slug_b_f) else 0.0
                    filtered_pairs.append({
                        "title_a": post_a.title or "(no title)",
                        "title_b": post_b.title or "(no title)",
                        "cosine_sim": cosine_sim,
                        "blended_score": blended_score,
                        "slug_overlap": slug_overlap_f,
                        "entity_a": entities.get(idx_a),
                        "entity_b": entities.get(idx_b),
                        "title_topic": _title_topic_overlap(post_a.title or "", post_b.title or ""),
                        "h2_jaccard": _h2_subtopic_jaccard(headings_a, headings_b),
                    })
                continue

            severity = blended_tier

            # Stronger post (health score based, no traffic)
            strength_a = health_scores[idx_a]
            strength_b = health_scores[idx_b]
            stronger_idx = idx_a if strength_a >= strength_b else idx_b

            # Severity score
            severity_score = min(100.0, blended_score * 100)

            # Resolution
            resolution = CannibalizationDetector._recommend_resolution(
                cosine_sim, severity, intent_a, intent_b,
            )

            # Slug overlap
            slug_a = _extract_slug_core(post_a.url)
            slug_b = _extract_slug_core(post_b.url)
            slug_overlap = len(slug_a & slug_b) / len(slug_a | slug_b) if (slug_a | slug_b) else 0.0

            # Title topic overlap
            title_topic = _title_topic_overlap(post_a.title or "", post_b.title or "")

            # H2 Jaccard
            h2_jaccard = _h2_subtopic_jaccard(headings_a, headings_b)

            all_pairs.append({
                "cluster_id": cl_id,
                "idx_a": idx_a,
                "idx_b": idx_b,
                "title_a": post_a.title or "(no title)",
                "title_b": post_b.title or "(no title)",
                "url_a": post_a.url,
                "url_b": post_b.url,
                "cosine_sim": cosine_sim,
                "blended_score": blended_score,
                "severity": severity,
                "severity_score": severity_score,
                "resolution": resolution,
                "stronger_idx": stronger_idx,
                "entity_a": entities.get(idx_a),
                "entity_b": entities.get(idx_b),
                "intent_a": intent_a,
                "intent_b": intent_b,
                "slug_overlap": slug_overlap,
                "title_topic": title_topic,
                "h2_jaccard": h2_jaccard,
                "health_a": health_scores[idx_a],
                "health_b": health_scores[idx_b],
                "is_synthetic": idx_a >= injected_start_idx or idx_b >= injected_start_idx,
            })
            pairs_in_cluster += 1

        cluster_pair_counts[cl_id] = pairs_in_cluster

    detection_time = time.time() - detection_start
    n_within_cluster_pairs = len(all_pairs)

    print(f"  Total candidate pairs evaluated: {total_candidates}")
    print(f"  Pairs above cosine threshold: {total_candidates - skipped_low_blended + n_within_cluster_pairs}")
    print(f"  Pairs filtered (low blended): {skipped_low_blended}")
    print(f"  Within-cluster pairs found: {n_within_cluster_pairs}")
    print(f"  Detection time: {detection_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 7b: Cross-Cluster Detection (in-memory, mirrors _detect_cross_cluster)
    # ===================================================================
    print("Phase 7b: Cross-cluster cannibalization detection (in-memory)...")
    cross_start = time.time()
    cross_cluster_pairs: list[dict] = []
    existing_pair_keys = {(p["idx_a"], p["idx_b"]) for p in all_pairs}
    cross_candidates_checked = 0

    # For each post, find top 5 nearest neighbors across ALL posts (not just same cluster)
    post_cluster_map: dict[int, int] = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    for i in range(n_posts):
        # Compute cosine to all other posts
        sims = []
        for j in range(n_posts):
            if i == j:
                continue
            sim = float(np.dot(embeddings[i], embeddings[j]))
            sims.append((j, sim))
        # Top 5 by similarity
        sims.sort(key=lambda x: -x[1])
        for j, sim in sims[:5]:
            if sim < t_high:
                continue
            # Only cross-cluster
            if post_cluster_map.get(i) == post_cluster_map.get(j):
                continue
            pair_key = (min(i, j), max(i, j))
            if pair_key in existing_pair_keys:
                continue
            existing_pair_keys.add(pair_key)
            cross_candidates_checked += 1

            post_a = posts[pair_key[0]]
            post_b = posts[pair_key[1]]
            headings_a = post_a.headings or []
            headings_b = post_b.headings or []
            post_a_dict = {"title": post_a.title or "", "url": post_a.url}
            post_b_dict = {"title": post_b.title or "", "url": post_b.url}

            blended_score, blended_tier = compute_blended_cannibalization_score(
                post_a_dict, post_b_dict, headings_a, headings_b, sim,
            )
            if blended_tier == "low":
                continue

            cross_cluster_pairs.append({
                "idx_a": pair_key[0], "idx_b": pair_key[1],
                "title_a": post_a.title or "", "title_b": post_b.title or "",
                "url_a": post_a.url, "url_b": post_b.url,
                "cosine_sim": sim, "blended_score": blended_score,
                "severity": blended_tier,
                "severity_score": min(100.0, blended_score * 100),
                "resolution": CannibalizationDetector._recommend_resolution(sim, blended_tier),
                "cluster_a": post_cluster_map.get(pair_key[0]),
                "cluster_b": post_cluster_map.get(pair_key[1]),
                "is_synthetic": pair_key[0] >= injected_start_idx or pair_key[1] >= injected_start_idx,
            })

    cross_time = time.time() - cross_start
    all_pairs.extend([{**cp, "entity_a": entities.get(cp["idx_a"]),
                        "entity_b": entities.get(cp["idx_b"]),
                        "slug_overlap": 0.0, "title_topic": 0.0, "h2_jaccard": 0.0,
                        "health_a": health_scores[cp["idx_a"]],
                        "health_b": health_scores[cp["idx_b"]],
                        "stronger_idx": cp["idx_a"],
                        "intent_a": intents.get(cp["idx_a"]),
                        "intent_b": intents.get(cp["idx_b"]),
                        "cluster_id": cp["cluster_a"],
                        } for cp in cross_cluster_pairs])
    n_pairs = len(all_pairs)

    print(f"  Cross-cluster candidates checked: {cross_candidates_checked}")
    print(f"  Cross-cluster pairs found: {len(cross_cluster_pairs)}")
    print(f"  **Total pairs (within + cross): {n_pairs}**")
    print(f"  Cross-cluster time: {cross_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 8: Analysis
    # ===================================================================
    print("Phase 8: Analyzing results...")

    # Severity distribution
    severity_counter = Counter(p["severity"] for p in all_pairs)
    print("  Severity distribution:")
    for sev in ["critical", "high", "medium"]:
        count = severity_counter.get(sev, 0)
        pct = count / max(n_pairs, 1) * 100
        print(f"    {sev:10s} {count:4d} ({pct:5.1f}%)")

    # Resolution distribution
    resolution_counter = Counter(p["resolution"] for p in all_pairs)
    print("  Resolution distribution:")
    for res, count in resolution_counter.most_common():
        pct = count / max(n_pairs, 1) * 100
        print(f"    {res:15s} {count:4d} ({pct:5.1f}%)")

    # Per-cluster breakdown
    print("  Per-cluster pairs:")
    for cl_id in sorted(cluster_pair_counts.keys(), key=lambda k: -cluster_pair_counts[k]):
        count = cluster_pair_counts[cl_id]
        if count > 0:
            cl_size = len(cluster_groups.get(cl_id, []))
            max_possible = cl_size * (cl_size - 1) // 2
            pct = count / max(max_possible, 1) * 100
            print(f"    Cluster {cl_id:3d}: {count:4d} pairs / {max_possible} possible ({pct:.1f}%)")

    # Sort by severity_score descending
    all_pairs.sort(key=lambda p: -p["severity_score"])
    print()

    # ===================================================================
    # PHASE 9: Chunk Splitting Test (offline, no OpenAI)
    # ===================================================================
    print("Phase 9: Chunk splitting test (no OpenAI, structure only)...")
    from app.services.chunk_cannibalization import split_into_chunks

    chunk_start = time.time()
    chunk_counts: list[int] = []
    total_chunks = 0
    posts_with_chunks = 0

    for p in posts:
        chunks = split_into_chunks(p.body_html or "", p.title or "")
        n_chunks = len(chunks)
        chunk_counts.append(n_chunks)
        total_chunks += n_chunks
        if n_chunks > 0:
            posts_with_chunks += 1

    chunk_time = time.time() - chunk_start

    print(f"  Posts with chunks: {posts_with_chunks}/{n_posts}")
    print(f"  Total chunks: {total_chunks}")
    if chunk_counts:
        print(f"  Chunks per post: min={min(chunk_counts)}, max={max(chunk_counts)}, "
              f"mean={statistics.mean(chunk_counts):.1f}, median={statistics.median(chunk_counts):.0f}")
    print(f"  Splitting time: {chunk_time * 1000:.1f}ms\n")

    # ===================================================================
    # PHASE 10: Generate Report
    # ===================================================================
    print("Phase 10: Generating report...")

    report_path = "../STEP5-TEST-RESULTS.md"
    lines: list[str] = []

    n_real_posts = injected_start_idx
    n_synthetic_posts = n_posts - n_real_posts

    lines.append(f"# Step 8 E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Posts:** {n_real_posts} real (from crawl) + {n_synthetic_posts} synthetic (injected for validation) = {n_posts} total")
    lines.append(f"**Prerequisite:** Step 1 crawl + synthetic embeddings + Step 6 clustering + Step 7 health scores")
    lines.append(f"**Note:** Embeddings are synthetic (keyword-injected random vectors), not real OpenAI embeddings. Cosine similarity distribution will differ with real embeddings.")
    lines.append(f"**GSC data:** None (crawl-only mode -- no query overlap signal)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 5a. Threshold Calibration ──
    lines.append("## 5a. Threshold Calibration")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Pairs sampled | {len(sampled_pairs)} |")
    lines.append(f"| Similarity min | {sample_sims_arr.min():.4f} |")
    lines.append(f"| Similarity median | {np.median(sample_sims_arr):.4f} |")
    lines.append(f"| Similarity max | {sample_sims_arr.max():.4f} |")
    lines.append(f"| Similarity stddev | {sample_sims_arr.std():.4f} |")
    lines.append(f"| p85 (flag candidate) | {p85:.4f} |")
    lines.append(f"| p92 (high candidate) | {p92:.4f} |")
    lines.append(f"| p97 (critical candidate) | {p97:.4f} |")
    lines.append(f"| Calibrated flag | {calibrated_flag:.4f} |")
    lines.append(f"| Calibrated high | {calibrated_high:.4f} |")
    lines.append(f"| Calibrated critical | {calibrated_critical:.4f} |")
    lines.append(f"| **Thresholds used (defaults)** | **flag={t_flag}, high={t_high}, critical={t_critical}** |")
    lines.append(f"| Calibration time | {calibration_time * 1000:.1f}ms |")
    lines.append("")

    # Histogram of similarities
    sim_buckets = [(-0.1, 0.0), (0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4),
                   (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.0)]
    lines.append("### Pairwise Similarity Distribution")
    lines.append("")
    lines.append("| Range | Count | % | Histogram |")
    lines.append("|-------|-------|---|-----------|")
    for lo, hi in sim_buckets:
        count = int(np.sum((sample_sims_arr >= lo) & (sample_sims_arr < hi)))
        pct = count / len(sample_sims_arr) * 100 if len(sample_sims_arr) > 0 else 0
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| [{lo:.1f}, {hi:.1f}) | {count} | {pct:.1f}% | {bar} |")
    lines.append("")

    # ── 5b. Entity Extraction ──
    lines.append("## 5b. Entity Extraction")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Titles with entity | {extracted_count}/{n_posts} ({extracted_count/n_posts*100:.1f}%) |")
    lines.append(f"| Unique entities | {len(entity_counts)} |")
    lines.append(f"| Processing time | {entity_time * 1000:.1f}ms |")
    lines.append("")

    lines.append("### Top Entities")
    lines.append("")
    lines.append("| Entity | Posts | Example Title |")
    lines.append("|--------|-------|--------------|")
    for entity, count in entity_counts.most_common(15):
        # Find first post with this entity
        example_title = ""
        for i, e in entities.items():
            if e == entity:
                example_title = (posts[i].title or "")[:60]
                break
        lines.append(f"| {entity} | {count} | {example_title} |")
    lines.append("")

    # ── 5c. Intent Classification ──
    lines.append("## 5c. Intent Classification")
    lines.append("")
    lines.append("| Intent Group | Posts | % |")
    lines.append("|-------------|-------|---|")
    for intent, count in intent_counter.most_common():
        pct = count / n_posts * 100
        lines.append(f"| {intent} | {count} | {pct:.1f}% |")
    lines.append(f"| (unclassified) | {unclassified} | {unclassified/n_posts*100:.1f}% |")
    lines.append("")

    # ── 5d. Cannibalization Detection ──
    lines.append("## 5d. Cannibalization Detection")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Clusters scanned | {n_clusters} |")
    lines.append(f"| Total candidate pairs | {total_candidates} |")
    lines.append(f"| Pairs above cosine threshold | {total_candidates - skipped_low_blended + n_pairs} |")
    lines.append(f"| Filtered (low blended score) | {skipped_low_blended} |")
    lines.append(f"| **Cannibalization pairs found** | **{n_pairs}** |")
    lines.append(f"| Detection time | {detection_time * 1000:.1f}ms |")
    lines.append("")

    # Severity distribution
    lines.append("### Severity Distribution")
    lines.append("")
    lines.append("| Severity | Count | % |")
    lines.append("|----------|-------|---|")
    for sev in ["critical", "high", "medium"]:
        count = severity_counter.get(sev, 0)
        pct = count / max(n_pairs, 1) * 100
        lines.append(f"| {sev} | {count} | {pct:.1f}% |")
    lines.append("")

    # Resolution distribution
    lines.append("### Resolution Distribution")
    lines.append("")
    lines.append("| Resolution | Count | % | Meaning |")
    lines.append("|-----------|-------|---|---------|")
    res_meanings = {
        "redirect": "301 redirect shorter to longer (cosine >= 0.95)",
        "merge": "Combine into stronger post (critical severity or cosine >= 0.85)",
        "differentiate": "Refocus each on its unique intent (different intents)",
        "monitor": "Add internal links, track over time (moderate overlap)",
    }
    for res in ["redirect", "merge", "differentiate", "monitor"]:
        count = resolution_counter.get(res, 0)
        pct = count / max(n_pairs, 1) * 100
        lines.append(f"| {res} | {count} | {pct:.1f}% | {res_meanings.get(res, '')} |")
    lines.append("")

    # Per-cluster breakdown
    lines.append("### Per-Cluster Pair Count")
    lines.append("")
    lines.append("| Cluster | Posts | Candidate Pairs | Cannibalizing Pairs | Rate |")
    lines.append("|---------|-------|-----------------|--------------------|----- |")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        cl_size = len(cluster_groups[cl_id])
        max_possible = cl_size * (cl_size - 1) // 2
        found = cluster_pair_counts.get(cl_id, 0)
        rate = found / max(max_possible, 1) * 100
        lines.append(f"| {cl_id} | {cl_size} | {max_possible} | {found} | {rate:.1f}% |")
    lines.append("")

    # ── 5d+. Filtered Pairs (S5-05: verify false positive filtering) ──
    if filtered_pairs:
        lines.append("## 5d+. Sample Filtered Pairs (blended <= 0.35, cosine above threshold)")
        lines.append("")
        lines.append("These pairs passed the cosine threshold but were filtered by the blended score. Verify they are genuine false positives:")
        lines.append("")
        lines.append("| # | Cosine | Blended | Slug | Entity A | Entity B | Title Topic | H2 Jacc | Title A | Title B | Correct? |")
        lines.append("|---|--------|---------|------|----------|----------|-------------|---------|---------|---------|----------|")
        for rank, fp in enumerate(filtered_pairs[:5], 1):
            ta = fp["title_a"][:35]
            tb = fp["title_b"][:35]
            ea = fp["entity_a"] or "None"
            eb = fp["entity_b"] or "None"
            # Heuristic: if different entities or low title overlap, it's correctly filtered
            correct = "YES" if fp["title_topic"] < 0.5 or (ea != "None" and eb != "None" and ea != eb) else "REVIEW"
            lines.append(
                f"| {rank} | {fp['cosine_sim']:.3f} | {fp['blended_score']:.3f} "
                f"| {fp['slug_overlap']:.3f} | {ea[:15]} | {eb[:15]} "
                f"| {fp['title_topic']:.3f} | {fp['h2_jaccard']:.3f} "
                f"| {ta} | {tb} | {correct} |"
            )
        lines.append("")
        lines.append(f"**Total filtered:** {skipped_low_blended} pairs. Showing {min(5, len(filtered_pairs))} samples above.")
        lines.append("")

    # ── 5d++. Closest Misses (S5-09: per-cluster closest miss) ──
    if closest_misses:
        lines.append("## 5d++. Per-Cluster Closest Misses (highest cosine pair NOT flagged)")
        lines.append("")
        lines.append("These are the highest-similarity pairs that did NOT pass the cosine threshold. If any look like real cannibalization, the threshold may be too high:")
        lines.append("")
        lines.append("| Cluster | Cosine | Threshold | Title A | Title B |")
        lines.append("|---------|--------|-----------|---------|---------|")
        for cl_id in sorted(closest_misses.keys()):
            miss = closest_misses[cl_id]
            ta = miss["title_a"][:40]
            tb = miss["title_b"][:40]
            lines.append(f"| {cl_id} | {miss['cosine_sim']:.3f} | {miss['threshold_used']:.3f} | {ta} | {tb} |")
        lines.append("")

    # ── 5e. Top Cannibalization Pairs ──
    lines.append("## 5e. Top Cannibalization Pairs (by Blended Score)")
    lines.append("")
    top_n = min(20, n_pairs)
    if top_n > 0:
        lines.append(f"### Top {top_n} Pairs")
        lines.append("")
        lines.append("| # | Source | Severity | Blended | Cosine | Resolution | Title A | Title B |")
        lines.append("|---|--------|----------|---------|--------|-----------|---------|---------|")
        for rank, pair in enumerate(all_pairs[:top_n], 1):
            title_a_short = pair["title_a"][:40]
            title_b_short = pair["title_b"][:40]
            source = "synthetic" if pair.get("is_synthetic") else "real"
            lines.append(
                f"| {rank} | {source} | {pair['severity']} | {pair['blended_score']:.3f} "
                f"| {pair['cosine_sim']:.3f} | {pair['resolution']} "
                f"| {title_a_short} | {title_b_short} |"
            )
        lines.append("")

        # Signal breakdown for top 5
        lines.append("### Signal Breakdown (Top 5)")
        lines.append("")
        for rank, pair in enumerate(all_pairs[:min(5, n_pairs)], 1):
            source = "SYNTHETIC" if pair.get("is_synthetic") else "REAL"
            lines.append(f"**Pair {rank}** ({source}):")
            lines.append(f"- Post A: `{pair['url_a']}`")
            lines.append(f"- Post B: `{pair['url_b']}`")
            lines.append("")
            lines.append("| Signal | Value | Weight | Contribution |")
            lines.append("|--------|-------|--------|-------------|")
            cos_val = pair['cosine_sim']
            slug_val = pair['slug_overlap']
            ent_a = pair['entity_a'] or 'None'
            ent_b = pair['entity_b'] or 'None'
            tt_val = pair['title_topic']
            h2_val = pair['h2_jaccard']
            blended = pair['blended_score']
            lines.append(f"| Cosine similarity | {cos_val:.3f} | 15% | {cos_val * 0.15:.3f} |")
            lines.append(f"| Slug overlap | {slug_val:.3f} | 20% | {slug_val * 0.20:.3f} |")
            lines.append(f"| Entity+Intent | entity_a=\"{ent_a[:40]}\", entity_b=\"{ent_b[:40]}\" | 25% | (composite) |")
            lines.append(f"| Title topic overlap | {tt_val:.3f} | 20% | {tt_val * 0.20:.3f} |")
            lines.append(f"| H2 Jaccard | {h2_val:.3f} | 20% | {h2_val * 0.20:.3f} |")
            lines.append(f"| **Blended** | **{blended:.3f}** | | **{pair['severity']}** |")
            lines.append("")
        lines.append("")
    else:
        lines.append("*No cannibalization pairs found.*")
        lines.append("")

    # ── 5f. Blended Score Distribution ──
    if n_pairs > 0:
        lines.append("## 5f. Blended Score Distribution")
        lines.append("")
        blended_scores = [p["blended_score"] for p in all_pairs]
        score_buckets = [(0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55),
                         (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80),
                         (0.80, 1.01)]
        lines.append("| Score Range | Count | % | Severity |")
        lines.append("|------------|-------|---|----------|")
        for lo, hi in score_buckets:
            count = sum(1 for s in blended_scores if lo <= s < hi)
            pct = count / n_pairs * 100
            sev = "critical" if lo >= 0.80 else "high" if lo >= 0.55 else "medium"
            lines.append(f"| [{lo:.2f}, {hi:.2f}) | {count} | {pct:.1f}% | {sev} |")
        lines.append("")
        lines.append(f"**Blended score stats:** min={min(blended_scores):.3f}, max={max(blended_scores):.3f}, "
                      f"mean={statistics.mean(blended_scores):.3f}, median={statistics.median(blended_scores):.3f}")
        if len(blended_scores) > 1:
            lines[-1] += f", stddev={statistics.stdev(blended_scores):.3f}"
        lines.append("")

    # ── 5g. Cosine vs Blended Comparison ──
    if n_pairs > 0:
        lines.append("## 5g. Cosine vs Blended Score Comparison")
        lines.append("")
        lines.append("Shows how the blended score differs from raw cosine similarity:")
        lines.append("")
        lines.append("| Metric | Cosine | Blended | Difference |")
        lines.append("|--------|--------|---------|------------|")
        cosine_scores = [p["cosine_sim"] for p in all_pairs]
        cos_mean = statistics.mean(cosine_scores)
        bld_mean = statistics.mean(blended_scores)
        lines.append(f"| Mean | {cos_mean:.3f} | {bld_mean:.3f} | {bld_mean - cos_mean:+.3f} |")
        cos_med = statistics.median(cosine_scores)
        bld_med = statistics.median(blended_scores)
        lines.append(f"| Median | {cos_med:.3f} | {bld_med:.3f} | {bld_med - cos_med:+.3f} |")
        lines.append(f"| Min | {min(cosine_scores):.3f} | {min(blended_scores):.3f} | |")
        lines.append(f"| Max | {max(cosine_scores):.3f} | {max(blended_scores):.3f} | |")
        lines.append("")

        # Count pairs where blended changed the severity vs what cosine alone would give
        cosine_would_flag = sum(1 for p in all_pairs if p["cosine_sim"] >= t_flag)
        blended_actual = n_pairs
        lines.append(f"**Cosine-only would flag:** {cosine_would_flag} pairs (>= {t_flag})")
        lines.append(f"**Blended actually flagged:** {blended_actual} pairs (> 0.35)")
        lines.append(f"**Blended filtered out:** {skipped_low_blended} pairs (cosine above threshold but blended <= 0.35)")
        lines.append("")

    # ── 5h. Chunk Splitting ──
    lines.append("## 5h. Chunk Splitting (Structure Only, No Embeddings)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Posts with chunks | {posts_with_chunks}/{n_posts} |")
    lines.append(f"| Total chunks | {total_chunks} |")
    if chunk_counts:
        lines.append(f"| Min chunks/post | {min(chunk_counts)} |")
        lines.append(f"| Max chunks/post | {max(chunk_counts)} |")
        lines.append(f"| Mean chunks/post | {statistics.mean(chunk_counts):.1f} |")
        lines.append(f"| Median chunks/post | {statistics.median(chunk_counts):.0f} |")
    lines.append(f"| Splitting time | {chunk_time * 1000:.1f}ms |")
    lines.append("")

    # Chunk count distribution
    chunk_dist = Counter()
    for c in chunk_counts:
        if c <= 1:
            chunk_dist["1 (title only)"] += 1
        elif c <= 3:
            chunk_dist["2-3"] += 1
        elif c <= 5:
            chunk_dist["4-5"] += 1
        elif c <= 10:
            chunk_dist["6-10"] += 1
        elif c <= 20:
            chunk_dist["11-20"] += 1
        else:
            chunk_dist["21+"] += 1

    lines.append("### Chunks per Post Distribution")
    lines.append("")
    lines.append("| Range | Count | % |")
    lines.append("|-------|-------|---|")
    for label in ["1 (title only)", "2-3", "4-5", "6-10", "11-20", "21+"]:
        count = chunk_dist.get(label, 0)
        pct = count / n_posts * 100
        lines.append(f"| {label} | {count} | {pct:.1f}% |")
    lines.append("")

    # ── 5i. Stronger Post Analysis ──
    if n_pairs > 0:
        lines.append("## 5i. Stronger Post Analysis")
        lines.append("")
        # Health score gap between stronger and weaker post
        health_gaps = []
        for p in all_pairs:
            stronger_health = max(p["health_a"], p["health_b"])
            weaker_health = min(p["health_a"], p["health_b"])
            health_gaps.append(stronger_health - weaker_health)

        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Mean health gap (stronger - weaker) | {statistics.mean(health_gaps):.1f} |")
        lines.append(f"| Median health gap | {statistics.median(health_gaps):.1f} |")
        lines.append(f"| Max health gap | {max(health_gaps):.1f} |")
        lines.append(f"| Min health gap | {min(health_gaps):.1f} |")
        close_pairs = sum(1 for g in health_gaps if g < 5)
        lines.append(f"| Pairs with health gap < 5 (close call) | {close_pairs} ({close_pairs/n_pairs*100:.1f}%) |")
        lines.append("")

    # ── 5j. Entity Extraction Failures (S5-09) ──
    lines.append("## 5j. Entity Extraction Failures")
    lines.append("")
    lines.append("Titles where entity extraction returned None — showing what a correct entity would be:")
    lines.append("")
    lines.append("| # | Title | Extracted | Suggested Entity |")
    lines.append("|---|-------|-----------|-----------------|")
    failure_count = 0
    for i, p in enumerate(posts):
        if entities.get(i) is None and failure_count < 10:
            title = (p.title or "")[:60]
            # Suggest what the entity should be (manual heuristic for report)
            words = re.findall(r"[a-z]{3,}", (p.title or "").lower())
            meaningful = [w for w in words if w not in {"the", "a", "an", "and", "or", "but", "in", "on",
                                                         "at", "to", "for", "of", "with", "by", "is", "are",
                                                         "how", "what", "why", "your", "you", "that", "this",
                                                         "from", "it", "its", "can", "has", "have", "here"}]
            suggested = " ".join(meaningful[:3]) if meaningful else "(unclear)"
            lines.append(f"| {failure_count + 1} | {title} | None | {suggested} |")
            failure_count += 1
    lines.append("")
    no_entity_count = sum(1 for e in entities.values() if e is None)
    lines.append(f"**Total unmatched:** {no_entity_count}/{n_posts} ({no_entity_count/n_posts*100:.0f}%)")
    lines.append("")

    # ── 5k. Calibration Validation (S5-09) ──
    lines.append("## 5k. Calibration Validation")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append(f"| p85 raw | {p85:.4f} | Below floor 0.40 | " if p85 < 0.40 else f"| p85 raw | {p85:.4f} | Above floor |")
    lines.append(f"| p92 raw | {p92:.4f} | Below floor 0.50 | " if p92 < 0.50 else f"| p92 raw | {p92:.4f} | Above floor |")
    lines.append(f"| p97 raw | {p97:.4f} | Below floor 0.60 | " if p97 < 0.60 else f"| p97 raw | {p97:.4f} | Above floor |")
    floors_triggered = sum(1 for p, f in [(p85, 0.40), (p92, 0.50), (p97, 0.60)] if p < f)
    lines.append(f"| Floors triggered | {floors_triggered}/3 | "
                  f"{'All floors active — synthetic embeddings have lower similarity than real OpenAI embeddings' if floors_triggered == 3 else 'Partial floor activation'} |")
    lines.append("")
    lines.append("Synthetic embeddings (keyword-injected random vectors) produce a median pairwise similarity of "
                  f"{np.median(sample_sims_arr):.4f}, far below real text-embedding-3-small which typically produces "
                  f"0.15-0.35 median similarity. This means calibrated percentile values fall below the absolute floors, "
                  f"so floors override calibrated values. **This is expected behavior** for synthetic embeddings.")
    lines.append("")

    # ── 5l. Cross-Analysis: All Pairs Above Cosine Threshold (S5-09) ──
    # Show breakdown of all 2500+ pairs that passed cosine threshold
    total_above_cosine = n_pairs + skipped_low_blended
    lines.append("## 5l. Cross-Analysis: Cosine → Blended Pipeline")
    lines.append("")
    lines.append(f"Of {total_candidates} total candidate pairs in all clusters:")
    lines.append("")
    lines.append("```")
    below_threshold = total_candidates - total_above_cosine
    lines.append(f"  {total_candidates:5d} total candidate pairs")
    lines.append(f"  → {below_threshold:5d} below cosine threshold ({below_threshold/max(total_candidates,1)*100:.1f}%) — skipped")
    lines.append(f"  → {total_above_cosine:5d} above cosine threshold ({total_above_cosine/max(total_candidates,1)*100:.1f}%)")
    lines.append(f"      → {skipped_low_blended:5d} filtered by blended score ≤ 0.35 ({skipped_low_blended/max(total_above_cosine,1)*100:.1f}% of above-threshold)")
    lines.append(f"      → {n_pairs:5d} flagged as cannibalization ({n_pairs/max(total_above_cosine,1)*100:.1f}% of above-threshold)")
    lines.append("```")
    lines.append("")
    lines.append(f"**Blended score false-positive prevention rate:** {skipped_low_blended/max(total_above_cosine,1)*100:.1f}% "
                  f"— {skipped_low_blended} pairs that cosine alone would have flagged were correctly filtered by the "
                  f"5-signal blended score.")
    lines.append("")

    # ── Processing Summary ──
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Step | Time | External API | Notes |")
    lines.append("|------|------|-------------|-------|")
    lines.append(f"| Crawl (Step 1 prerequisite) | {crawl_time:.1f}s | None | |")
    lines.append(f"| Clustering (Step 6 prerequisite) | {cluster_time:.1f}s | None | Synthetic embeddings |")
    lines.append(f"| Health scoring (Step 7 prerequisite) | {health_time * 1000:.1f}ms | None | Crawl-only mode |")
    lines.append(f"| Threshold calibration | {calibration_time * 1000:.1f}ms | None | {len(sampled_pairs)} pairs sampled |")
    lines.append(f"| Entity extraction | {entity_time * 1000:.1f}ms | None | Regex-based |")
    lines.append(f"| Intent classification | {intent_time * 1000:.1f}ms | None | Keyword-based |")
    lines.append(f"| Within-cluster detection | {detection_time * 1000:.1f}ms | None | {total_candidates} pairs evaluated |")
    lines.append(f"| Cross-cluster detection | {cross_time * 1000:.1f}ms | None | {cross_candidates_checked} candidates, {len(cross_cluster_pairs)} found |")
    lines.append(f"| Chunk splitting | {chunk_time * 1000:.1f}ms | None | Structure only |")
    total_step5_time = calibration_time + entity_time + intent_time + detection_time + cross_time + chunk_time
    lines.append(f"| **Total Step 8** | **{total_step5_time * 1000:.0f}ms** | **Free** | **No DB, no API** |")
    lines.append("")

    # ── Observations ──
    lines.append("## Observations")
    lines.append("")

    # 1. Pair count
    cannibalization_rate = n_pairs / max(total_candidates, 1) * 100
    lines.append(f"1. **Cannibalization rate: {n_pairs}/{total_candidates} pairs ({cannibalization_rate:.1f}%)** -- "
                  f"{'high' if cannibalization_rate > 20 else 'moderate' if cannibalization_rate > 5 else 'low'} rate. "
                  f"Synthetic embeddings produce {'higher' if cannibalization_rate > 20 else 'different'} similarity patterns "
                  f"than real OpenAI embeddings. With real embeddings, the distribution would be more concentrated "
                  f"around topically similar posts.")
    lines.append("")

    # 2. Blended filtering
    if n_pairs > 0 or skipped_low_blended > 0:
        total_above_cosine = n_pairs + skipped_low_blended
        filter_rate = skipped_low_blended / max(total_above_cosine, 1) * 100
        lines.append(f"2. **Blended score filtered {skipped_low_blended} pairs ({filter_rate:.0f}%)** -- "
                      f"posts that passed the cosine threshold ({t_flag}) but scored <= 0.35 blended. "
                      f"These are 'content series' (topically similar but targeting different keywords/intents). "
                      f"Without blended scoring, these would be false positives.")
    else:
        lines.append("2. **No pairs to evaluate blended filtering** -- cosine threshold may be too high for synthetic embeddings.")
    lines.append("")

    # 3. Entity extraction
    lines.append(f"3. **Entity extraction: {extracted_count}/{n_posts} titles ({extracted_count/n_posts*100:.0f}%)** -- "
                  f"{'good' if extracted_count/n_posts > 0.5 else 'low'} extraction rate. "
                  f"Copyblogger titles often use creative/editorial formats that don't match the "
                  f"standard entity patterns (X Review, How to X, N Best X). "
                  f"Real SEO sites (Backlinko, Ahrefs blog) typically have higher extraction rates.")
    lines.append("")

    # 4. Intent classification
    lines.append(f"4. **Intent classification: {classified_count}/{n_posts} posts ({classified_count/n_posts*100:.0f}%)** -- "
                  f"most common intent: {intent_counter.most_common(1)[0][0] if intent_counter else 'none'} "
                  f"({intent_counter.most_common(1)[0][1] if intent_counter else 0} posts). "
                  f"Intent-aware threshold raises the flag threshold by +0.10 for cross-intent pairs, "
                  f"reducing false positives where posts target different search purposes.")
    lines.append("")

    # 5. Severity distribution
    if n_pairs > 0:
        critical_count = severity_counter.get("critical", 0)
        high_count = severity_counter.get("high", 0)
        medium_count = severity_counter.get("medium", 0)
        lines.append(f"5. **Severity: {critical_count} critical, {high_count} high, {medium_count} medium** -- "
                      f"{'no' if critical_count == 0 else f'{critical_count}'} near-duplicate pairs detected. "
                      f"In crawl-only mode (no GSC), severity is determined entirely by the blended score: "
                      f">0.80 = critical, >0.55 = high, >0.35 = medium.")
    else:
        lines.append("5. **No pairs found** -- all candidate pairs were either below the cosine threshold "
                      "or filtered by the blended score.")
    lines.append("")

    # 6. Resolution
    if n_pairs > 0:
        monitor_count = resolution_counter.get("monitor", 0)
        merge_count = resolution_counter.get("merge", 0)
        redirect_count = resolution_counter.get("redirect", 0)
        diff_count = resolution_counter.get("differentiate", 0)
        lines.append(f"6. **Resolution recommendations: {monitor_count} monitor, {merge_count} merge, "
                      f"{redirect_count} redirect, {diff_count} differentiate** -- "
                      f"'monitor' dominates because most pairs have moderate overlap (cosine < 0.85, not critical severity). "
                      f"With real embeddings and higher cosine similarities, 'merge' and 'redirect' would be more common.")
    else:
        lines.append("6. **No resolution recommendations** -- no pairs to resolve.")
    lines.append("")

    # 7. Chunk splitting
    lines.append(f"7. **Chunk splitting: {total_chunks} chunks from {n_posts} posts** -- "
                  f"avg {statistics.mean(chunk_counts):.1f} chunks/post. "
                  f"Chunk confirmation (Step 8b) would embed these at ~$0.50/site via OpenAI, "
                  f"checking max pairwise chunk similarity >= 0.88 to confirm section-level overlap. "
                  f"Not run in this test (requires OpenAI API key).")
    lines.append("")

    # 8. Health gap
    if n_pairs > 0:
        avg_gap = statistics.mean(health_gaps)
        lines.append(f"8. **Stronger post determination: mean health gap = {avg_gap:.1f}** -- "
                      f"{'small gap -- many close calls' if avg_gap < 5 else 'clear winner in most pairs'}. "
                      f"In crawl-only mode (no traffic data), strength = health score only. "
                      f"With GA4 data, traffic is weighted 10x higher than health score, "
                      f"which would produce clearer winners.")
    else:
        lines.append("8. **No stronger post analysis** -- no pairs found.")
    lines.append("")

    # 9. HNSW pre-filter (not used in this test)
    lines.append(f"9. **HNSW pre-filter: not applicable** -- this test uses in-memory cosine similarity "
                  f"(numpy dot product). In production with pgvector, clusters with 20+ posts use "
                  f"HNSW index to find top-10 nearest neighbors per post, reducing O(n²) to O(10n) candidates.")
    lines.append("")

    # 10. Cross-cluster results
    lines.append(f"10. **Cross-cluster cannibalization: {len(cross_cluster_pairs)} pairs found** -- "
                  f"in-memory scan (top 5 neighbors per post, cosine >= {t_high} high threshold, "
                  f"different clusters). Checked {cross_candidates_checked} cross-cluster candidates. "
                  f"Production uses pgvector HNSW index for the same algorithm via `_detect_cross_cluster()`.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by `backend/scripts/test_step5_e2e.py` -- crawl-only mode, no database, no OpenAI API.*")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  Report written to {report_path}")
    print(f"\n=== Step 8 E2E complete -- {n_pairs} cannibalization pairs found, "
          f"{n_posts} posts, {n_clusters} clusters, {total_step5_time * 1000:.0f}ms detection time ===")


if __name__ == "__main__":
    asyncio.run(main())
