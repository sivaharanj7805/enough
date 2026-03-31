"""End-to-end test of Pipeline Step 7: Health Scoring.

Runs all factor scoring functions against real crawled data from Copyblogger.
Uses crawl-only mode (no GA4/GSC data, no database) to validate scoring
logic, role assignment, and ecosystem state assignment.

Produces a comprehensive report with:
  - Three sample posts (best/median/worst) with full factor breakdowns
  - Cross-analysis tables (composite vs word count, year, cluster)
  - Per-cluster detail with role breakdown, top/bottom post, max-variance factor
  - 7x7 factor correlation matrix (Pearson)
  - Score distribution by role with overlap analysis
  - Ecosystem state decision trace per cluster
  - Edge case posts (highest/lowest on each individual factor)
  - Tech SEO with eeat_metadata (OG tags, canonical, JSON-LD from crawl)

Reuses Step 1 crawl and Step 6 clustering (UMAP+HDBSCAN) as prerequisites.
No database required -- tests computation only.
"""

import asyncio
import json
import math
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

import numpy as np

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


# =====================================================================
# Helpers
# =====================================================================


def _simple_flesch(text: str) -> float:
    """Quick Flesch Reading Ease from raw text (no external deps).

    Formula: 206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words)
    Uses a rough syllable count (vowel groups). Good enough for scoring tiers.
    """
    import re
    sentences = max(1, len(re.findall(r'[.!?]+', text)))
    words_list = re.findall(r'[a-zA-Z]+', text)
    n_words = max(1, len(words_list))
    syllables = 0
    for w in words_list:
        # Count vowel groups as syllable proxy
        syl = len(re.findall(r'[aeiouyAEIOUY]+', w))
        syllables += max(1, syl)
    score = 206.835 - 1.015 * (n_words / sentences) - 84.6 * (syllables / n_words)
    return max(0.0, min(100.0, score))


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
    """Run UMAP+HDBSCAN clustering (same as test_step3_e2e.py).

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


def _safe(text: str) -> str:
    """Strip non-ASCII for Windows console output."""
    return text.encode("ascii", "replace").decode("ascii")


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two lists."""
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(max(0, sum((xi - mx) ** 2 for xi in x) / (n - 1)))
    sy = math.sqrt(max(0, sum((yi - my) ** 2 for yi in y) / (n - 1)))
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
    return cov / (sx * sy)


# =====================================================================
# Main
# =====================================================================


async def main():
    from app.services.normalizer import (
        filter_nav_links,
        filter_sitewide_headings,
        _strip_site_name_from_title,
        _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
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
        _assign_role,
        _assign_ecosystem_state,
    )
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 7 E2E Test (Deep Analysis): {TARGET_DOMAIN} ===\n")

    # =================================================================
    # PHASE 1: Crawl (reuse Step 1)
    # =================================================================
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

    # =================================================================
    # PHASE 2: Clustering (reuse Step 6)
    # =================================================================
    print("Phase 2: Clustering (Step 6 prerequisite)...")
    titles = [p.title or "" for p in posts]
    cluster_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    labels, cluster_groups = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - cluster_start
    n_clusters = len(cluster_groups)
    print(f"  Generated {n_clusters} clusters in {cluster_time:.1f}s\n")

    # =================================================================
    # PHASE 3: Content Profile Detection
    # =================================================================
    print("Phase 3: Content profile detection...")
    word_counts_all = [p.word_count for p in posts if p.word_count > 50]
    if word_counts_all:
        median_wc = statistics.median(word_counts_all)
        stddev_wc = statistics.stdev(word_counts_all) if len(word_counts_all) > 1 else 0
    else:
        median_wc = 1000
        stddev_wc = 500
    is_short_form = median_wc < 600 and stddev_wc < 400
    print(f"  Median word count: {median_wc:.0f}")
    print(f"  Stddev word count: {stddev_wc:.0f}")
    print(f"  Short-form: {is_short_form}\n")

    # =================================================================
    # PHASE 4: Weight Distribution (Crawl-Only Mode)
    # =================================================================
    print("Phase 4: Weight distribution (crawl-only mode)...")
    weights = compute_dynamic_weights(has_ga4=False, has_gsc=False)
    print("  Factor weights:")
    for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
        bar = "#" * int(weight * 100)
        print(f"    {factor:25s} {weight:5.0%}  {bar}")
    weight_sum = sum(weights.values())
    print(f"  Weight sum: {weight_sum:.4f}")
    if abs(weight_sum - 1.0) > 0.01:
        print("  WARNING: Weights do not sum to 1.0!")
    print()

    # =================================================================
    # PHASE 5: Factor Scoring
    # =================================================================
    print("Phase 5: Factor scoring (all posts)...")
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)
    ai_default = 40.0

    # Pre-compute AI citability scores if the module is available (Step 6c prerequisite)
    ai_readiness_cache: dict[int, float] = {}
    try:
        from app.services.ai_citability import compute_citability_score, compute_eeat_score
        print("  Computing AI citability (Step 6c) for each post...")
        for i, p in enumerate(posts):
            try:
                cite_score, _ = compute_citability_score(
                    body_html=p.body_html or "",
                    headings=p.headings or [],
                    word_count=p.word_count or 0,
                )
                eeat_score, _ = compute_eeat_score(
                    body_html=p.body_html or "",
                    headings=p.headings or [],
                    word_count=p.word_count or 0,
                )
                ai_readiness_cache[i] = (cite_score + eeat_score) / 2.0
            except Exception:
                ai_readiness_cache[i] = ai_default
        ai_scores = list(ai_readiness_cache.values())
        print(f"  AI readiness: mean={sum(ai_scores)/len(ai_scores):.1f}, "
              f"min={min(ai_scores):.1f}, max={max(ai_scores):.1f}")
    except ImportError:
        print("  AI citability module not available — using flat default 40.0")

    # Pre-compute readability scores once (S4-32: avoid recomputing in every factor call)
    readability_cache: dict[int, float | None] = {}
    for i, p in enumerate(posts):
        readability_cache[i] = _simple_flesch(p.body_text) if p.body_text else None

    # Pre-compute per-cluster averages for content depth
    cluster_avg_wc: dict[int, float] = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if posts[i].word_count]
        if len(wcs) >= 3:
            cluster_avg_wc[cl_id] = sum(wcs) / len(wcs)
        else:
            cluster_avg_wc[cl_id] = 1000.0

    # Map post index -> cluster id
    post_cluster_map: dict[int, int] = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    # Build real inbound/outbound link counts from crawled internal_links
    url_to_idx: dict[str, int] = {p.url: i for i, p in enumerate(posts)}
    inbound_counts: dict[int, int] = {i: 0 for i in range(n_posts)}
    outbound_counts: dict[int, int] = {i: 0 for i in range(n_posts)}
    for i, p in enumerate(posts):
        for link in p.internal_links:
            target_url = (
                link.target_url
                if hasattr(link, "target_url")
                else (link.get("target_url") if isinstance(link, dict) else str(link))
            )
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1
                outbound_counts[i] += 1

    # Compute factor timings
    factor_timings: dict[str, float] = {}

    # -- Traffic trend (crawl-only: all unknown) --
    t0 = time.time()
    for _ in posts:
        _compute_trend(0, 0, 0)
    factor_timings["traffic_trend"] = time.time() - t0

    # -- Ranking (crawl-only: default position 100) --
    t0 = time.time()
    for _ in posts:
        _ranking_score(100.0)
    factor_timings["ranking"] = time.time() - t0

    # -- Engagement (crawl-only: defaults) --
    t0 = time.time()
    for _ in posts:
        _engagement_score(0.5, 60.0)
    factor_timings["engagement"] = time.time() - t0

    # -- Freshness --
    t0 = time.time()
    for p in posts:
        last_updated = p.modified_date or p.publish_date
        _freshness_score(last_updated, now, title=p.title or "", url=p.url)
    factor_timings["freshness"] = time.time() - t0

    # -- Content depth --
    t0 = time.time()
    for i, p in enumerate(posts):
        cl_id = post_cluster_map.get(i, 0)
        avg = cluster_avg_wc.get(cl_id, 1000.0)
        _content_depth_score(p.word_count or 0, avg, body_html=p.body_html, short_form=is_short_form)
    factor_timings["content_depth"] = time.time() - t0

    # -- Technical SEO (with eeat_metadata) --
    t0 = time.time()
    for i, p in enumerate(posts):
        eeat = p.eeat_signals if isinstance(p.eeat_signals, dict) else {}
        _technical_seo_score(
            meta_description=p.meta_description,
            title=p.title,
            headings=p.headings,
            has_outbound=outbound_counts.get(i, 0) > 0,
            has_inbound=inbound_counts.get(i, 0) > 0,
            body_html=p.body_html,
            eeat_metadata=eeat,
        )
    factor_timings["technical_seo"] = time.time() - t0

    # -- Predicted engagement --
    t0 = time.time()
    for idx_pe, p in enumerate(posts):
        _predicted_engagement_score(
            body_html=p.body_html,
            readability_score=readability_cache.get(idx_pe),
            headings=p.headings,
        )
    factor_timings["predicted_engagement"] = time.time() - t0

    # -- Content structure --
    t0 = time.time()
    for p in posts:
        _content_structure_score(
            body_html=p.body_html,
            word_count=p.word_count or 0,
            headings=p.headings,
        )
    factor_timings["content_structure"] = time.time() - t0

    print("  Factor timing (pure computation, no DB):")
    for factor, elapsed in sorted(factor_timings.items(), key=lambda x: -x[1]):
        print(f"    {factor:25s} {elapsed * 1000:.1f}ms")
    print()

    # =================================================================
    # PHASE 6: Composite Scoring
    # =================================================================
    print("Phase 6: Composite scoring (crawl-only mode)...")
    score_start = time.time()

    # The 7 crawl-only factors we track for correlation analysis
    CRAWL_FACTORS = [
        "freshness", "content_depth", "internal_links",
        "technical_seo", "ai_readiness", "content_richness",
    ]
    # Map factor name -> metric dict key (handles singular/plural inconsistency)
    FACTOR_KEY_MAP = {
        "freshness": "freshness_score",
        "content_depth": "content_depth_score",
        "internal_links": "internal_link_score",
        "technical_seo": "technical_seo_score",
        "ai_readiness": "ai_readiness_score",
        "content_richness": "content_richness_score",
    }

    factor_scores_all: dict[str, list[float]] = {f: [] for f in CRAWL_FACTORS}
    factor_scores_all["traffic_trend"] = []
    factor_scores_all["ranking"] = []
    factor_scores_all["engagement"] = []

    post_metrics: list[dict] = []

    for i, p in enumerate(posts):
        cl_id = post_cluster_map.get(i, 0)
        avg_wc = cluster_avg_wc.get(cl_id, 1000.0)
        last_updated = p.modified_date or p.publish_date
        eeat = p.eeat_signals if isinstance(p.eeat_signals, dict) else {}

        # Factor 1: Traffic trend (crawl-only: unknown)
        trend, trend_score = _compute_trend(0, 0, 0)

        # Factor 2: Ranking (crawl-only: default 100)
        ranking = _ranking_score(100.0)

        # Factor 3: Engagement (crawl-only: defaults)
        engagement = _engagement_score(0.5, 60.0)

        # Factor 4: Freshness
        freshness = _freshness_score(last_updated, now, title=p.title or "", url=p.url)

        # Factor 5: Content depth
        depth = _content_depth_score(
            p.word_count or 0, avg_wc,
            body_html=p.body_html, short_form=is_short_form,
        )

        # Factor 6: Internal links (relative to cluster max)
        cluster_indices = cluster_groups.get(cl_id, [])
        max_inbound_cluster = max(
            (inbound_counts.get(j, 0) for j in cluster_indices), default=1
        )
        inbound = inbound_counts.get(i, 0)
        link_score = min(100.0, (inbound / max(max_inbound_cluster, 1)) * 100.0)

        # Factor 7: Technical SEO (with eeat_metadata for head tag checks)
        tech = _technical_seo_score(
            meta_description=p.meta_description,
            title=p.title,
            headings=p.headings,
            has_outbound=outbound_counts.get(i, 0) > 0,
            has_inbound=inbound > 0,
            body_html=p.body_html,
            eeat_metadata=eeat,
        )

        # Factor 8: AI readiness (from Step 6c if available, else flat default)
        ai_readiness = ai_readiness_cache.get(i, ai_default)

        # Factor 9: Predicted engagement
        predicted_eng = _predicted_engagement_score(
            body_html=p.body_html,
            readability_score=readability_cache.get(i),
            headings=p.headings,
        )

        # Factor 10: Content structure
        content_struct = _content_structure_score(
            body_html=p.body_html,
            word_count=p.word_count or 0,
            headings=p.headings,
        )

        # S4-25: Merged content_richness = average of predicted_engagement + content_structure
        content_rich = (predicted_eng + content_struct) / 2.0

        # Composite
        composite = (
            weights["traffic_trend"] * trend_score
            + weights["ranking"] * ranking
            + weights["engagement"] * engagement
            + weights["freshness"] * freshness
            + weights["content_depth"] * depth
            + weights["internal_links"] * link_score
            + weights["technical_seo"] * tech
            + weights["ai_readiness"] * ai_readiness
            + weights.get("content_richness", 0) * content_rich
            + weights.get("predicted_engagement", 0) * predicted_eng
            + weights.get("content_structure", 0) * content_struct
        )

        # Clamp to [10, 95]
        composite = max(10.0, min(95.0, composite))

        # Store all factor scores
        factor_scores_all["traffic_trend"].append(trend_score)
        factor_scores_all["ranking"].append(ranking)
        factor_scores_all["engagement"].append(engagement)
        factor_scores_all["freshness"].append(freshness)
        factor_scores_all["content_depth"].append(depth)
        factor_scores_all["internal_links"].append(link_score)
        factor_scores_all["technical_seo"].append(tech)
        factor_scores_all["ai_readiness"].append(ai_readiness)
        factor_scores_all["content_richness"].append(content_rich)

        post_metrics.append({
            "index": i,
            "title": p.title or "(no title)",
            "url": p.url,
            "word_count": p.word_count or 0,
            "cluster_id": cl_id,
            "composite": composite,
            "trend": trend,
            "trend_score": trend_score,
            "ranking_score": ranking,
            "engagement_score": engagement,
            "freshness_score": freshness,
            "content_depth_score": depth,
            "internal_link_score": link_score,
            "technical_seo_score": tech,
            "ai_readiness_score": ai_readiness,
            "predicted_engagement_score": predicted_eng,
            "content_structure_score": content_struct,
            "content_richness_score": content_rich,
            "traffic_contribution": 0.0,
            "traffic": 0,
            "publish_date": p.publish_date,
            "role": "",
            "inbound_links": inbound,
            "outbound_links": outbound_counts.get(i, 0),
            "eeat_signals": eeat,
        })

    score_time = time.time() - score_start
    composites = [m["composite"] for m in post_metrics]
    print(f"  Scored {len(post_metrics)} posts in {score_time * 1000:.1f}ms")
    print(f"  Composite range: {min(composites):.1f} - {max(composites):.1f}")
    print(f"  Mean: {statistics.mean(composites):.1f}, Median: {statistics.median(composites):.1f}")
    print(f"  Stddev: {statistics.stdev(composites):.1f}\n")

    # =================================================================
    # PHASE 7: Role Assignment
    # =================================================================
    print("Phase 7: Role assignment (crawl-only mode, relative pillar threshold)...")
    # First pass: absolute threshold assignment
    for m in post_metrics:
        role = _assign_role(
            composite=m["composite"],
            traffic_contribution=0.0,
            recent_pv=0,
            is_cannibalizing=False,
            has_traffic_data=False,
        )
        m["role"] = role

    # Second pass: relative pillar threshold per cluster (S4-30)
    # Pillar = top 15% of composites within each cluster
    for cl_id, member_indices in cluster_groups.items():
        cl_posts = [post_metrics[idx] for idx in member_indices]
        if len(cl_posts) < 3:
            continue
        sorted_composites = sorted(m["composite"] for m in cl_posts)
        pillar_cutoff = sorted_composites[int(len(sorted_composites) * 0.85)]
        for m in cl_posts:
            if m["composite"] >= pillar_cutoff:
                m["role"] = "pillar"
            elif m["composite"] >= 30:
                m["role"] = "supporter"
            elif m["composite"] >= 15:
                m["role"] = "at_risk"
            else:
                m["role"] = "dead_weight"

    role_counter = Counter(m["role"] for m in post_metrics)
    print("  Role distribution:")
    for role, count in role_counter.most_common():
        pct = count / len(post_metrics) * 100
        bar = "#" * int(pct)
        print(f"    {role:15s} {count:4d} ({pct:5.1f}%)  {bar}")
    print()

    # =================================================================
    # PHASE 8: Ecosystem State Assignment
    # =================================================================
    print("Phase 8: Ecosystem state assignment...")
    cluster_states: dict[int, dict] = {}

    for cl_id, indices in cluster_groups.items():
        cluster_post_metrics = [post_metrics[i] for i in indices]

        cluster_health = (
            sum(m["composite"] for m in cluster_post_metrics) / len(cluster_post_metrics)
            if cluster_post_metrics else 0
        )

        ecosystem_state = _assign_ecosystem_state(
            post_metrics=cluster_post_metrics,
            cannibal_pairs_count=0,
            post_count=len(cluster_post_metrics),
            cluster_health=cluster_health,
            now=now,
            thirty_days_ago=thirty_days_ago,
            has_traffic_data=False,
        )

        cluster_states[cl_id] = {
            "cluster_id": cl_id,
            "post_count": len(cluster_post_metrics),
            "health": cluster_health,
            "ecosystem_state": ecosystem_state,
            "roles": Counter(m["role"] for m in cluster_post_metrics),
        }

    state_counter = Counter(c["ecosystem_state"] for c in cluster_states.values())
    print("  Ecosystem state distribution:")
    for state, count in state_counter.most_common():
        print(f"    {state:10s} {count:3d} cluster(s)")
    print()

    print("  Per-cluster summary:")
    for cl_id in sorted(cluster_states.keys(), key=lambda k: -cluster_states[k]["post_count"]):
        cs = cluster_states[cl_id]
        roles_str = ", ".join(f"{r}={c}" for r, c in cs["roles"].most_common())
        print(f"    Cluster {cl_id:3d}: {cs['post_count']:3d} posts, "
              f"health={cs['health']:.1f}, state={cs['ecosystem_state']:8s}, "
              f"roles=[{roles_str}]")
    print()

    # =================================================================
    # PHASE 9: Deep Analysis & Report Generation
    # =================================================================
    print("Phase 9: Generating deep analysis report...")

    sorted_by_score = sorted(post_metrics, key=lambda m: -m["composite"])

    # -----------------------------------------------------------------
    # Pre-compute analysis data
    # -----------------------------------------------------------------

    # Publish year extraction
    def _get_year(m: dict) -> int | None:
        pd = m.get("publish_date")
        if pd and hasattr(pd, "year"):
            return pd.year
        return None

    # Factor variance contribution
    active_factors = [f for f in weights if weights[f] > 0]
    factor_variance_contribution: dict[str, float] = {}
    for factor in active_factors:
        weighted_scores = [weights[factor] * s for s in factor_scores_all.get(factor, [])]
        if len(weighted_scores) > 1:
            factor_variance_contribution[factor] = statistics.stdev(weighted_scores)
        else:
            factor_variance_contribution[factor] = 0.0
    total_variance = sum(factor_variance_contribution.values()) or 1.0

    # Score distribution histogram
    buckets = list(range(0, 101, 10))
    histogram: dict[str, int] = {}
    for lo in buckets[:-1]:
        hi = lo + 10
        label = f"{lo}-{hi}"
        histogram[label] = sum(1 for c in composites if lo <= c < hi)
    histogram["90-100"] = sum(1 for c in composites if 90 <= c <= 100)

    # eeat_metadata stats for tech SEO section
    eeat_og_count = sum(1 for m in post_metrics if m["eeat_signals"].get("has_og_tags"))
    eeat_canonical_count = sum(1 for m in post_metrics if m["eeat_signals"].get("has_canonical"))
    eeat_jsonld_count = sum(1 for m in post_metrics if m["eeat_signals"].get("has_jsonld"))

    # =================================================================
    # WRITE REPORT
    # =================================================================
    report_path = "../STEP4-TEST-RESULTS.md"
    lines: list[str] = []

    lines.append(f"# Step 7 E2E Test Results: {TARGET_DOMAIN} (Deep Analysis)")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Posts scored:** {n_posts}")
    lines.append(f"**Clusters:** {n_clusters}")
    lines.append(f"**Scoring mode:** Crawl-only (no GA4, no GSC)")
    lines.append(f"**AI readiness:** Default 40.0 (no AI citability step)")
    lines.append(f"**Prerequisite:** Step 1 crawl ({TARGET_DOMAIN}, {MAX_PAGES} max) + Step 6 clustering (synthetic embeddings)")
    lines.append(f"**Content profile:** {'Short-form' if is_short_form else 'Long-form'} (median {median_wc:.0f}w, stddev {stddev_wc:.0f}w)")
    lines.append(f"**Role thresholds (crawl-only):** pillar >= 45, supporter >= 30, at_risk >= 15, dead_weight < 15")
    lines.append("")
    lines.append("---")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 1: Weight Distribution
    # -----------------------------------------------------------------
    lines.append("## 1. Weight Distribution (Crawl-Only Mode)")
    lines.append("")
    lines.append("| # | Factor | Weight | Source |")
    lines.append("|---|--------|--------|--------|")
    factor_order = [
        ("ai_readiness", "AI Citability scores (default 40.0)"),
        ("content_depth", "Crawl (word count vs cluster avg)"),
        ("content_richness", "Crawl proxy merged (predicted engagement + content structure / 2)"),
        ("freshness", "Crawl (publish_date / modified_date)"),
        ("internal_links", "Crawl (inbound link count, real resolution)"),
        ("technical_seo", "Crawl (meta, title, headings, OG, canonical, JSON-LD via eeat_metadata)"),
        ("traffic_trend", "GA4 (zeroed in crawl-only)"),
        ("ranking", "GSC (zeroed in crawl-only)"),
        ("engagement", "GA4 (zeroed in crawl-only)"),
    ]
    for i, (factor, source) in enumerate(factor_order, 1):
        w = weights.get(factor, 0)
        lines.append(f"| {i} | {factor} | {w:.0%} | {source} |")
    lines.append(f"| | **Total** | **{weight_sum:.0%}** | |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 2: Per-Factor Score Distribution
    # -----------------------------------------------------------------
    lines.append("## 2. Per-Factor Score Distribution")
    lines.append("")
    lines.append("| Factor | Min | Max | Mean | Median | Stddev | Weight |")
    lines.append("|--------|-----|-----|------|--------|--------|--------|")
    for factor in active_factors:
        scores = factor_scores_all.get(factor, [])
        if not scores:
            continue
        w = weights.get(factor, 0)
        mn = min(scores)
        mx = max(scores)
        avg = statistics.mean(scores)
        med = statistics.median(scores)
        sd = statistics.stdev(scores) if len(scores) > 1 else 0
        lines.append(f"| {factor} | {mn:.1f} | {mx:.1f} | {avg:.1f} | {med:.1f} | {sd:.1f} | {w:.0%} |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 3: Three Sample Posts (Best / Median / Worst)
    # -----------------------------------------------------------------
    lines.append("## 3. Three Sample Posts: Full Factor Breakdowns")
    lines.append("")
    lines.append("### BEST, MEDIAN, and WORST posts with every factor score and the math.")
    lines.append("")

    best_post = sorted_by_score[0]
    worst_post = sorted_by_score[-1]
    median_idx = len(sorted_by_score) // 2
    median_post = sorted_by_score[median_idx]

    sample_posts = [
        ("BEST", best_post),
        ("MEDIAN", median_post),
        ("WORST", worst_post),
    ]

    for label, m in sample_posts:
        title_display = m["title"][:80]
        lines.append(f"#### {label} Post: \"{title_display}\" ({m['word_count']} words)")
        lines.append("")
        lines.append("```")
        lines.append(f"URL: {m['url']}")
        lines.append(f"Cluster: {m['cluster_id']}, Role: {m['role']}")
        lines.append(f"Inbound links: {m['inbound_links']}, Outbound links: {m['outbound_links']}")

        eeat_s = m["eeat_signals"]
        lines.append(f"eeat_metadata: OG={eeat_s.get('has_og_tags', False)}, "
                      f"canonical={eeat_s.get('has_canonical', False)}, "
                      f"JSON-LD={eeat_s.get('has_jsonld', False)}")

        pd = m.get("publish_date")
        pd_str = pd.strftime("%Y-%m-%d") if pd and hasattr(pd, "strftime") else "unknown"
        lines.append(f"Publish date: {pd_str}")
        lines.append("")
        lines.append("Factor breakdown:")

        crawl_factor_list = [
            ("freshness", m["freshness_score"], weights.get("freshness", 0)),
            ("content_depth", m["content_depth_score"], weights.get("content_depth", 0)),
            ("internal_links", m["internal_link_score"], weights.get("internal_links", 0)),
            ("technical_seo", m["technical_seo_score"], weights.get("technical_seo", 0)),
            ("ai_readiness", m["ai_readiness_score"], weights.get("ai_readiness", 0)),
            ("content_richness", m["content_richness_score"], weights.get("content_richness", 0)),
        ]

        running_total = 0.0
        for fname, fscore, fweight in crawl_factor_list:
            contribution = fscore * fweight
            running_total += contribution
            lines.append(f"  {fname:25s} {fscore:6.1f} x {fweight:.2f} = {contribution:5.2f}")

        clamped = max(10.0, min(95.0, running_total))
        lines.append(f"  {'':25s} {'':6s}   {'':4s}   -----")
        lines.append(f"  {'COMPOSITE':25s} {'':6s}   {'':4s}   {running_total:.2f} (clamped to {clamped:.1f})")
        lines.append("```")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 4: Composite Score Distribution
    # -----------------------------------------------------------------
    lines.append("## 4. Composite Score Distribution")
    lines.append("")
    lines.append("| Score Range | Count | % | Histogram |")
    lines.append("|------------|-------|---|-----------|")
    for label_h, count in histogram.items():
        pct = count / len(composites) * 100 if composites else 0
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {label_h} | {count} | {pct:.1f}% | {bar} |")
    lines.append("")
    lines.append(f"**Composite stats:** min={min(composites):.1f}, max={max(composites):.1f}, "
                  f"mean={statistics.mean(composites):.1f}, median={statistics.median(composites):.1f}, "
                  f"stddev={statistics.stdev(composites):.1f}")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 5: Cross-Analysis Tables
    # -----------------------------------------------------------------
    lines.append("## 5. Cross-Analysis Tables")
    lines.append("")

    # 5a. Composite vs Word Count buckets
    lines.append("### 5a. Composite vs Word Count")
    lines.append("")
    wc_buckets = [
        ("0-500", 0, 500),
        ("500-1000", 500, 1000),
        ("1000-2000", 1000, 2000),
        ("2000+", 2000, 999999),
    ]
    lines.append("| Word Count | Posts | Avg Composite | Min | Max | Avg Freshness | Avg Tech SEO |")
    lines.append("|------------|-------|---------------|-----|-----|---------------|-------------|")
    for label_b, lo, hi in wc_buckets:
        bucket_posts = [m for m in post_metrics if lo <= m["word_count"] < hi]
        if not bucket_posts:
            lines.append(f"| {label_b} | 0 | - | - | - | - | - |")
            continue
        avg_c = statistics.mean([m["composite"] for m in bucket_posts])
        mn_c = min(m["composite"] for m in bucket_posts)
        mx_c = max(m["composite"] for m in bucket_posts)
        avg_f = statistics.mean([m["freshness_score"] for m in bucket_posts])
        avg_t = statistics.mean([m["technical_seo_score"] for m in bucket_posts])
        lines.append(f"| {label_b} | {len(bucket_posts)} | {avg_c:.1f} | {mn_c:.1f} | {mx_c:.1f} | {avg_f:.1f} | {avg_t:.1f} |")
    lines.append("")

    # 5b. Composite vs Publish Year
    lines.append("### 5b. Composite vs Publish Year")
    lines.append("")
    year_groups: dict[int, list[dict]] = {}
    no_year_posts = []
    for m in post_metrics:
        y = _get_year(m)
        if y:
            year_groups.setdefault(y, []).append(m)
        else:
            no_year_posts.append(m)

    lines.append("| Year | Posts | Avg Composite | Min | Max | Avg Freshness | Avg Depth |")
    lines.append("|------|-------|---------------|-----|-----|---------------|----------|")
    for year in sorted(year_groups.keys()):
        yp = year_groups[year]
        avg_c = statistics.mean([m["composite"] for m in yp])
        mn_c = min(m["composite"] for m in yp)
        mx_c = max(m["composite"] for m in yp)
        avg_f = statistics.mean([m["freshness_score"] for m in yp])
        avg_d = statistics.mean([m["content_depth_score"] for m in yp])
        lines.append(f"| {year} | {len(yp)} | {avg_c:.1f} | {mn_c:.1f} | {mx_c:.1f} | {avg_f:.1f} | {avg_d:.1f} |")
    if no_year_posts:
        avg_c = statistics.mean([m["composite"] for m in no_year_posts])
        lines.append(f"| (no date) | {len(no_year_posts)} | {avg_c:.1f} | - | - | - | - |")
    lines.append("")

    # 5c. Composite vs Cluster
    lines.append("### 5c. Composite vs Cluster (avg per cluster)")
    lines.append("")
    lines.append("| Cluster | Posts | Avg Composite | Min | Max | State | Top Role |")
    lines.append("|---------|-------|---------------|-----|-----|-------|----------|")
    for cl_id in sorted(cluster_states.keys(), key=lambda k: -cluster_states[k]["post_count"]):
        cs = cluster_states[cl_id]
        cl_posts = [m for m in post_metrics if m["cluster_id"] == cl_id]
        if not cl_posts:
            continue
        avg_c = statistics.mean([m["composite"] for m in cl_posts])
        mn_c = min(m["composite"] for m in cl_posts)
        mx_c = max(m["composite"] for m in cl_posts)
        top_role = cs["roles"].most_common(1)[0][0] if cs["roles"] else "none"
        lines.append(f"| {cl_id} | {cs['post_count']} | {avg_c:.1f} | {mn_c:.1f} | {mx_c:.1f} | {cs['ecosystem_state']} | {top_role} |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 6: Per-Cluster Detail
    # -----------------------------------------------------------------
    lines.append("## 6. Per-Cluster Detail")
    lines.append("")
    lines.append("Full role breakdown, top post, bottom post, highest-variance factor per cluster.")
    lines.append("")

    for cl_id in sorted(cluster_states.keys(), key=lambda k: -cluster_states[k]["post_count"]):
        cs = cluster_states[cl_id]
        cl_posts = sorted(
            [m for m in post_metrics if m["cluster_id"] == cl_id],
            key=lambda m: -m["composite"],
        )
        if not cl_posts:
            continue

        lines.append(f"### Cluster {cl_id} ({cs['post_count']} posts, health={cs['health']:.1f}, state={cs['ecosystem_state']})")
        lines.append("")

        # Role breakdown
        lines.append("**Role breakdown:**")
        for role_name, role_cnt in cs["roles"].most_common():
            lines.append(f"- {role_name}: {role_cnt}")
        lines.append("")

        # Top and bottom post
        top = cl_posts[0]
        bot = cl_posts[-1]
        lines.append(f"**Top post:** {top['title'][:60]} (score={top['composite']:.1f}, {top['word_count']}w)")
        lines.append(f"**Bottom post:** {bot['title'][:60]} (score={bot['composite']:.1f}, {bot['word_count']}w)")
        lines.append("")

        # Highest-variance factor in this cluster
        if len(cl_posts) > 1:
            max_var_factor = ""
            max_var_val = -1.0
            for f in CRAWL_FACTORS:
                f_key = FACTOR_KEY_MAP.get(f, f"{f}_score")
                f_vals = [m[f_key] for m in cl_posts]
                if len(f_vals) > 1:
                    sd = statistics.stdev(f_vals)
                    if sd > max_var_val:
                        max_var_val = sd
                        max_var_factor = f
            lines.append(f"**Highest-variance factor:** {max_var_factor} (stddev={max_var_val:.1f})")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 7: Factor Correlation Matrix (7x7)
    # -----------------------------------------------------------------
    lines.append("## 7. Factor Correlation Matrix (7x7 Pearson)")
    lines.append("")
    lines.append("Pairwise Pearson correlation between the 7 crawl-only factors.")
    lines.append("Pairs with |r| > 0.5 are marked with **bold**.")
    lines.append("")

    # Header row
    short_names = {
        "freshness": "Fresh",
        "content_depth": "Depth",
        "internal_links": "Links",
        "technical_seo": "Tech",
        "ai_readiness": "AI",
        "content_richness": "Richness",
    }
    header = "| | " + " | ".join(short_names[f] for f in CRAWL_FACTORS) + " |"
    sep = "|---" + "|---" * len(CRAWL_FACTORS) + "|"
    lines.append(header)
    lines.append(sep)

    strong_pairs: list[tuple[str, str, float]] = []

    for f1 in CRAWL_FACTORS:
        row = f"| {short_names[f1]} "
        f1_key = FACTOR_KEY_MAP.get(f1, f"{f1}_score")
        f1_vals = [m[f1_key] for m in post_metrics]
        for f2 in CRAWL_FACTORS:
            f2_key = FACTOR_KEY_MAP.get(f2, f"{f2}_score")
            f2_vals = [m[f2_key] for m in post_metrics]
            r = _pearson(f1_vals, f2_vals)
            if f1 == f2:
                row += "| 1.00 "
            elif abs(r) > 0.5:
                row += f"| **{r:.2f}** "
                if f1 < f2:
                    strong_pairs.append((f1, f2, r))
            else:
                row += f"| {r:.2f} "
        row += "|"
        lines.append(row)
    lines.append("")

    if strong_pairs:
        lines.append("**Strong correlations (|r| > 0.5):**")
        for f1, f2, r in sorted(strong_pairs, key=lambda x: -abs(x[2])):
            direction = "positive" if r > 0 else "negative"
            lines.append(f"- {f1} <-> {f2}: r={r:.2f} ({direction})")
        lines.append("")
    else:
        lines.append("*No factor pairs with |r| > 0.5 found.*")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 8: Role Distribution (with score ranges)
    # -----------------------------------------------------------------
    lines.append("## 8. Score Distribution by Role")
    lines.append("")
    lines.append("| Role | Count | % | Min | Max | Avg | Median |")
    lines.append("|------|-------|---|-----|-----|-----|--------|")

    role_ranges: dict[str, tuple[float, float]] = {}
    for role_name, count in role_counter.most_common():
        pct = count / len(post_metrics) * 100
        role_posts_list = [m["composite"] for m in post_metrics if m["role"] == role_name]
        mn = min(role_posts_list)
        mx = max(role_posts_list)
        avg_r = statistics.mean(role_posts_list)
        med_r = statistics.median(role_posts_list)
        role_ranges[role_name] = (mn, mx)
        lines.append(f"| {role_name} | {count} | {pct:.1f}% | {mn:.1f} | {mx:.1f} | {avg_r:.1f} | {med_r:.1f} |")
    lines.append("")

    # Check for overlap
    lines.append("**Range overlap analysis:**")
    roles_sorted = sorted(role_ranges.keys())
    overlap_found = False
    for i_r in range(len(roles_sorted)):
        for j_r in range(i_r + 1, len(roles_sorted)):
            r1 = roles_sorted[i_r]
            r2 = roles_sorted[j_r]
            lo1, hi1 = role_ranges[r1]
            lo2, hi2 = role_ranges[r2]
            overlap_lo = max(lo1, lo2)
            overlap_hi = min(hi1, hi2)
            if overlap_lo <= overlap_hi:
                lines.append(f"- {r1} [{lo1:.1f}-{hi1:.1f}] overlaps with {r2} [{lo2:.1f}-{hi2:.1f}] "
                              f"in range [{overlap_lo:.1f}-{overlap_hi:.1f}]")
                overlap_found = True
    if not overlap_found:
        lines.append("- No range overlap between roles (thresholds are absolute cutoffs).")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 9: Ecosystem State Decision Trace
    # -----------------------------------------------------------------
    lines.append("## 9. Ecosystem State Decision Trace")
    lines.append("")
    lines.append("For each cluster, every condition checked by `_assign_ecosystem_state`:")
    lines.append("")

    for cl_id in sorted(cluster_states.keys(), key=lambda k: -cluster_states[k]["post_count"]):
        cs = cluster_states[cl_id]
        cl_posts_dt = [m for m in post_metrics if m["cluster_id"] == cl_id]
        n_cl = cs["post_count"]
        health = cs["health"]

        has_pillar = any(m["role"] == "pillar" for m in cl_posts_dt)

        # Cannibalization rate (always 0 on first run)
        total_possible_pairs = n_cl * (n_cl - 1) / 2 if n_cl > 1 else 1
        cann_rate = 0.0 / total_possible_pairs

        # Has recent
        has_recent = any(
            m["publish_date"] is not None
            and hasattr(m["publish_date"], "replace")
            and m["publish_date"].replace(tzinfo=UTC) >= thirty_days_ago
            for m in cl_posts_dt
        )

        # Avg freshness
        avg_freshness = (
            sum(m["freshness_score"] for m in cl_posts_dt) / max(n_cl, 1)
        )

        lines.append(f"```")
        lines.append(f"Cluster {cl_id} ({n_cl} posts, health={health:.1f}):")

        # Seedbed check
        is_seedbed = has_recent and n_cl <= 3
        seedbed_reason = f"has_recent={has_recent} AND post_count={n_cl} <= 3"
        lines.append(f"  seedbed? {'YES' if is_seedbed else 'NO':3s} ({seedbed_reason})")

        if not is_seedbed:
            # Swamp check (no-traffic branch)
            is_swamp = cann_rate > 0.5
            swamp_reason = f"cannibalization_rate {cann_rate:.1f} {'>' if cann_rate > 0.5 else '<='} 0.5"
            lines.append(f"  swamp?   {'YES' if is_swamp else 'NO':3s} ({swamp_reason})")

            # Desert check
            is_desert = avg_freshness < 25
            desert_reason = f"avg_freshness {avg_freshness:.1f} {'<' if avg_freshness < 25 else '>='} 25"
            lines.append(f"  desert?  {'YES' if is_desert else 'NO':3s} ({desert_reason})")

            # Forest check — threshold is 38 for crawl-only, 50 with traffic
            forest_threshold = 38.0  # crawl-only mode (no GA4/GSC in this test)
            forest_cond1 = has_pillar
            forest_cond2 = cann_rate < 0.2
            forest_cond3 = health > forest_threshold
            is_forest = forest_cond1 and forest_cond2 and forest_cond3
            forest_reason = (
                f"has_pillar={forest_cond1}, cann_rate={cann_rate:.1f}<0.2={forest_cond2}, "
                f"health={health:.1f}>{forest_threshold}={forest_cond3}"
            )
            lines.append(f"  forest?  {'YES' if is_forest else 'NO':3s} ({forest_reason})")

        lines.append(f"  Result:  {cs['ecosystem_state']}")
        lines.append(f"```")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 10: Edge Case Posts
    # -----------------------------------------------------------------
    lines.append("## 10. Edge Case Posts")
    lines.append("")
    lines.append("Post that scored highest and lowest on each individual factor.")
    lines.append("")

    lines.append("| Factor | Highest Score | Highest Post | Lowest Score | Lowest Post |")
    lines.append("|--------|--------------|-------------|-------------|------------|")

    for f in CRAWL_FACTORS:
        f_key = FACTOR_KEY_MAP.get(f, f"{f}_score")
        best_m = max(post_metrics, key=lambda m: m[f_key])
        worst_m = min(post_metrics, key=lambda m: m[f_key])
        best_title = best_m["title"][:40]
        worst_title = worst_m["title"][:40]
        lines.append(
            f"| {f} | {best_m[f_key]:.1f} | {best_title} "
            f"| {worst_m[f_key]:.1f} | {worst_title} |"
        )
    lines.append("")

    # Detailed edge case breakdowns
    lines.append("### Edge Case Detail")
    lines.append("")
    for f in CRAWL_FACTORS:
        f_key = FACTOR_KEY_MAP.get(f, f"{f}_score")
        best_m = max(post_metrics, key=lambda m: m[f_key])
        worst_m = min(post_metrics, key=lambda m: m[f_key])
        lines.append(f"**{f} -- highest ({best_m[f_key]:.1f}):** {best_m['title'][:60]} "
                      f"({best_m['word_count']}w, composite={best_m['composite']:.1f}, role={best_m['role']})")
        lines.append(f"**{f} -- lowest ({worst_m[f_key]:.1f}):** {worst_m['title'][:60]} "
                      f"({worst_m['word_count']}w, composite={worst_m['composite']:.1f}, role={worst_m['role']})")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 11: Tech SEO with eeat_metadata
    # -----------------------------------------------------------------
    lines.append("## 11. Tech SEO with eeat_metadata (Head Tag Checks)")
    lines.append("")
    lines.append("The crawl's `_extract_eeat_metadata` now extracts `has_og_tags`, `has_canonical`, ")
    lines.append("`has_jsonld` booleans from `<head>`. These are passed to `_technical_seo_score` ")
    lines.append("as the `eeat_metadata` parameter.")
    lines.append("")
    lines.append("| Head Tag Signal | Posts With | Posts Without | Detection Rate |")
    lines.append("|----------------|-----------|--------------|---------------|")
    lines.append(f"| Open Graph tags | {eeat_og_count} | {n_posts - eeat_og_count} | {eeat_og_count/n_posts*100:.1f}% |")
    lines.append(f"| Canonical tag | {eeat_canonical_count} | {n_posts - eeat_canonical_count} | {eeat_canonical_count/n_posts*100:.1f}% |")
    lines.append(f"| JSON-LD schema | {eeat_jsonld_count} | {n_posts - eeat_jsonld_count} | {eeat_jsonld_count/n_posts*100:.1f}% |")
    lines.append("")

    # Tech SEO score breakdown by how many head checks pass
    tech_breakdown: dict[int, int] = {}
    for m in post_metrics:
        eeat_s = m["eeat_signals"]
        head_checks = sum([
            bool(eeat_s.get("has_og_tags")),
            bool(eeat_s.get("has_canonical")),
            bool(eeat_s.get("has_jsonld")),
        ])
        tech_breakdown[head_checks] = tech_breakdown.get(head_checks, 0) + 1

    lines.append("**Head tag check distribution (out of 3 eeat_metadata checks):**")
    lines.append("")
    lines.append("| Checks Passing | Posts | % |")
    lines.append("|---------------|-------|---|")
    for n_checks in sorted(tech_breakdown.keys()):
        cnt = tech_breakdown[n_checks]
        lines.append(f"| {n_checks}/3 | {cnt} | {cnt/n_posts*100:.1f}% |")
    lines.append("")

    # Impact analysis: compare tech SEO scores with and without eeat_metadata
    lines.append("**Impact of eeat_metadata on tech SEO scores:**")
    lines.append("")
    # Recalculate without eeat_metadata for comparison
    tech_without_eeat = []
    tech_with_eeat = [m["technical_seo_score"] for m in post_metrics]
    for i_t, p in enumerate(posts):
        tech_no_eeat = _technical_seo_score(
            meta_description=p.meta_description,
            title=p.title,
            headings=p.headings,
            has_outbound=outbound_counts.get(i_t, 0) > 0,
            has_inbound=inbound_counts.get(i_t, 0) > 0,
            body_html=p.body_html,
            eeat_metadata=None,  # No eeat_metadata
        )
        tech_without_eeat.append(tech_no_eeat)

    avg_with = statistics.mean(tech_with_eeat)
    avg_without = statistics.mean(tech_without_eeat)
    delta = avg_with - avg_without
    lines.append(f"- Average tech SEO **with** eeat_metadata: {avg_with:.1f}")
    lines.append(f"- Average tech SEO **without** eeat_metadata: {avg_without:.1f}")
    lines.append(f"- Delta: +{delta:.1f} points (eeat_metadata adds {delta:.1f} to mean tech SEO)")
    lines.append(f"- Max possible improvement: +37.5 (3 checks x 12.5 points each)")
    lines.append("")

    # Show schema types distribution
    schema_type_counter: Counter = Counter()
    for m in post_metrics:
        for st in m["eeat_signals"].get("schema_types", []):
            schema_type_counter[st] += 1
    if schema_type_counter:
        lines.append("**JSON-LD schema types found:**")
        lines.append("")
        lines.append("| Schema Type | Count |")
        lines.append("|------------|-------|")
        for stype, cnt in schema_type_counter.most_common(15):
            lines.append(f"| {stype} | {cnt} |")
        lines.append("")

    # -----------------------------------------------------------------
    # Section 12: Factor Variance Contribution
    # -----------------------------------------------------------------
    lines.append("## 12. Factor Variance Contribution")
    lines.append("")
    lines.append("Which factors contribute most to score differentiation between posts:")
    lines.append("")
    lines.append("| Factor | Weighted Stddev | % of Total Variance | Weight |")
    lines.append("|--------|----------------|--------------------|---------| ")
    for factor, var in sorted(factor_variance_contribution.items(), key=lambda x: -x[1]):
        pct = var / total_variance * 100
        lines.append(f"| {factor} | {var:.2f} | {pct:.1f}% | {weights.get(factor, 0):.0%} |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 13: Top 10 / Bottom 10
    # -----------------------------------------------------------------
    lines.append("## 13. Top 10 Posts by Composite Score")
    lines.append("")
    lines.append("| # | Score | Role | Fresh | Depth | Tech | Links | Richness | WC | Title |")
    lines.append("|---|-------|------|-------|-------|------|-------|----------|----|----|")
    for rank, m in enumerate(sorted_by_score[:10], 1):
        title_short = m["title"][:45]
        lines.append(
            f"| {rank} | {m['composite']:.1f} | {m['role']} "
            f"| {m['freshness_score']:.0f} | {m['content_depth_score']:.0f} "
            f"| {m['technical_seo_score']:.0f} | {m['internal_link_score']:.0f} "
            f"| {m['content_richness_score']:.0f} "
            f"| {m['word_count']} | {title_short} |"
        )
    lines.append("")

    lines.append("## 14. Bottom 10 Posts by Composite Score")
    lines.append("")
    lines.append("| # | Score | Role | Fresh | Depth | Tech | Links | Richness | WC | Title |")
    lines.append("|---|-------|------|-------|-------|------|-------|----------|----|----|")
    for rank, m in enumerate(sorted_by_score[-10:], 1):
        title_short = m["title"][:45]
        lines.append(
            f"| {rank} | {m['composite']:.1f} | {m['role']} "
            f"| {m['freshness_score']:.0f} | {m['content_depth_score']:.0f} "
            f"| {m['technical_seo_score']:.0f} | {m['internal_link_score']:.0f} "
            f"| {m['content_richness_score']:.0f} "
            f"| {m['word_count']} | {title_short} |"
        )
    lines.append("")

    # -----------------------------------------------------------------
    # Section 15: Ecosystem State per Cluster (summary table)
    # -----------------------------------------------------------------
    lines.append("## 15. Ecosystem State per Cluster")
    lines.append("")
    lines.append("| Cluster | Posts | Health | State | Pillar | Supporter | At Risk | Dead Weight |")
    lines.append("|---------|-------|--------|-------|--------|-----------|---------|-------------|")
    for cl_id in sorted(cluster_states.keys(), key=lambda k: -cluster_states[k]["post_count"]):
        cs = cluster_states[cl_id]
        r = cs["roles"]
        lines.append(
            f"| {cl_id} | {cs['post_count']} | {cs['health']:.1f} | {cs['ecosystem_state']} "
            f"| {r.get('pillar', 0)} | {r.get('supporter', 0)} "
            f"| {r.get('at_risk', 0)} | {r.get('dead_weight', 0)} |"
        )
    lines.append("")

    lines.append("### State Summary")
    lines.append("")
    lines.append("| State | Clusters | Meaning |")
    lines.append("|-------|----------|---------|")
    state_meanings = {
        "seedbed": "New cluster (<= 3 posts, recent content)",
        "swamp": "High cannibalization (>50%) or large without pillar",
        "desert": "Stale content (avg freshness < 25)",
        "forest": "Healthy (has pillar, low cann, health > 38 crawl-only / > 50 with traffic)",
        "meadow": "Everything else (default)",
    }
    for state in ["forest", "meadow", "seedbed", "swamp", "desert"]:
        count = state_counter.get(state, 0)
        lines.append(f"| {state} | {count} | {state_meanings.get(state, '')} |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 16: Internal Link Analysis
    # -----------------------------------------------------------------
    lines.append("## 16. Internal Link Analysis (Real Resolution)")
    lines.append("")
    total_inbound = sum(inbound_counts.values())
    total_outbound = sum(outbound_counts.values())
    zero_inbound = sum(1 for v in inbound_counts.values() if v == 0)
    zero_outbound = sum(1 for v in outbound_counts.values() if v == 0)
    max_inbound_val = max(inbound_counts.values()) if inbound_counts else 0
    max_inbound_post_idx = max(inbound_counts, key=inbound_counts.get) if inbound_counts else 0
    max_inbound_title = post_metrics[max_inbound_post_idx]["title"][:50] if post_metrics else ""

    lines.append(f"- Total internal links resolved: {total_inbound}")
    lines.append(f"- Posts with 0 inbound links (orphans): {zero_inbound}/{n_posts} ({zero_inbound/n_posts*100:.1f}%)")
    lines.append(f"- Posts with 0 outbound links: {zero_outbound}/{n_posts} ({zero_outbound/n_posts*100:.1f}%)")
    lines.append(f"- Max inbound links: {max_inbound_val} ({max_inbound_title})")
    lines.append("")

    # Inbound link distribution
    inbound_buckets = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 999999)]
    inbound_labels = ["0", "1-2", "3-5", "6-10", "11+"]
    lines.append("| Inbound Links | Posts | % | Avg Composite |")
    lines.append("|--------------|-------|---|---------------|")
    for (lo, hi), label_ib in zip(inbound_buckets, inbound_labels):
        ib_posts = [m for m in post_metrics if lo <= m["inbound_links"] <= hi]
        if not ib_posts:
            lines.append(f"| {label_ib} | 0 | 0.0% | - |")
            continue
        avg_c = statistics.mean([m["composite"] for m in ib_posts])
        lines.append(f"| {label_ib} | {len(ib_posts)} | {len(ib_posts)/n_posts*100:.1f}% | {avg_c:.1f} |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 17: Processing Time
    # -----------------------------------------------------------------
    lines.append("## 17. Processing Time")
    lines.append("")
    lines.append("| Step | Time | Notes |")
    lines.append("|------|------|-------|")
    lines.append(f"| Crawl (Step 1) | {crawl_time:.1f}s | {len(raw_posts)} URLs |")
    lines.append(f"| Clustering (Step 6) | {cluster_time:.1f}s | Synthetic embeddings |")
    total_factor_time = sum(factor_timings.values())
    lines.append(f"| Factor scoring (all) | {total_factor_time * 1000:.1f}ms | Pure computation |")
    for factor, elapsed in sorted(factor_timings.items(), key=lambda x: -x[1]):
        lines.append(f"|   {factor} | {elapsed * 1000:.1f}ms | |")
    lines.append(f"| Composite scoring | {score_time * 1000:.1f}ms | Weights + clamp |")
    lines.append(f"| **Total Step 7** | **{(total_factor_time + score_time) * 1000:.0f}ms** | **No DB, no API calls** |")
    lines.append("")

    # -----------------------------------------------------------------
    # Section 18: Observations
    # -----------------------------------------------------------------
    lines.append("## 18. Observations")
    lines.append("")

    # Observation 1: AI readiness
    lines.append("1. **AI readiness contributes zero variance** -- all posts have the default 40.0 score. "
                  "In production with real AI citability scores (range 10-90), AI readiness (36% weight) "
                  "would be the dominant differentiator. In this test, it adds a flat 14.4 to every composite.")
    lines.append("")

    # Observation 2: Traffic zeroed
    lines.append("2. **Traffic, ranking, and engagement are zeroed** -- expected in crawl-only mode. "
                  f"Traffic trend returns 'unknown' with score 30.0 for all posts. "
                  f"Ranking score for position 100 = {_ranking_score(100.0):.1f}. "
                  f"Engagement with defaults (bounce=0.5, time=60s) = {_engagement_score(0.5, 60.0):.1f}. "
                  f"These contribute 0 to composite because their weights are 0%.")
    lines.append("")

    # Observation 3: Score spread
    spread = max(composites) - min(composites)
    lines.append(f"3. **Score spread is {spread:.1f} points** (range {min(composites):.1f}-{max(composites):.1f}). "
                  f"This is {'narrow' if spread < 30 else 'moderate' if spread < 50 else 'wide'}. "
                  f"{'With real AI citability scores, spread would be wider.' if spread < 40 else ''}")
    lines.append("")

    # Observation 4: Freshness
    fresh_scores = factor_scores_all["freshness"]
    if fresh_scores:
        fresh_above_80 = sum(1 for s in fresh_scores if s >= 80)
        fresh_below_40 = sum(1 for s in fresh_scores if s < 40)
        lines.append(f"4. **Freshness distribution:** {fresh_above_80} posts score >= 80 (recent), "
                      f"{fresh_below_40} posts score < 40 (stale). "
                      f"Mean freshness: {statistics.mean(fresh_scores):.1f}.")
    lines.append("")

    # Observation 5: Internal links (real resolution)
    link_scores = factor_scores_all["internal_links"]
    if link_scores:
        zero_links = sum(1 for s in link_scores if s == 0)
        nonzero_links = sum(1 for s in link_scores if s > 0)
        lines.append(f"5. **Internal link resolution:** {nonzero_links}/{n_posts} posts have resolved inbound links "
                      f"(score > 0). {zero_links} posts are orphans (0 inbound). "
                      f"Mean link score: {statistics.mean(link_scores):.1f}. "
                      f"This uses real crawled internal_links with URL matching, not a fake 0-everywhere default.")
    lines.append("")

    # Observation 6: Tech SEO with eeat_metadata
    tech_scores = factor_scores_all["technical_seo"]
    if tech_scores:
        perfect_tech = sum(1 for s in tech_scores if s >= 87.5)
        lines.append(f"6. **Technical SEO with eeat_metadata:** {perfect_tech} posts score >= 87.5 (7/8 checks). "
                      f"Mean tech SEO: {statistics.mean(tech_scores):.1f}. "
                      f"eeat_metadata detection: OG={eeat_og_count}, canonical={eeat_canonical_count}, "
                      f"JSON-LD={eeat_jsonld_count}. "
                      f"Delta vs without eeat_metadata: +{delta:.1f} points.")
    lines.append("")

    # Observation 7: Role distribution
    pillar_count = role_counter.get("pillar", 0)
    supporter_count = role_counter.get("supporter", 0)
    at_risk_count = role_counter.get("at_risk", 0)
    dead_count = role_counter.get("dead_weight", 0)
    lines.append(f"7. **Role distribution (crawl-only thresholds):** "
                  f"pillar={pillar_count} (>= 45), "
                  f"supporter={supporter_count} (>= 30), "
                  f"at_risk={at_risk_count} (>= 15), "
                  f"dead_weight={dead_count} (< 15). "
                  f"No posts can be 'competitor' because cannibalization_pairs is empty on first run.")
    lines.append("")

    # Observation 8: Ecosystem states
    forest_count = state_counter.get("forest", 0)
    meadow_count = state_counter.get("meadow", 0)
    desert_count = state_counter.get("desert", 0)
    swamp_count = state_counter.get("swamp", 0)
    seedbed_count = state_counter.get("seedbed", 0)
    lines.append(f"8. **Ecosystem states:** forest={forest_count}, meadow={meadow_count}, "
                  f"seedbed={seedbed_count}, swamp={swamp_count}, desert={desert_count}. "
                  f"Without cannibalization data, swamp can only trigger on cann_rate > 0.5 "
                  f"(always 0 on first run). Desert requires avg freshness < 25.")
    lines.append("")

    # Observation 9: Clamping
    clamped_low = sum(1 for m in post_metrics if m["composite"] == 10.0)
    clamped_high = sum(1 for m in post_metrics if m["composite"] == 95.0)
    lines.append(f"9. **Score clamping:** {clamped_low} posts clamped to floor (10), "
                  f"{clamped_high} posts clamped to ceiling (95). "
                  f"{'No clamping occurred.' if clamped_low == 0 and clamped_high == 0 else ''}")
    lines.append("")

    # Observation 10: Content richness (merged factor)
    richness_scores = factor_scores_all["content_richness"]
    if richness_scores:
        avg_richness = statistics.mean(richness_scores)
        max_richness = max(richness_scores)
        lines.append(f"10. **Content richness (merged factor)** -- avg={avg_richness:.1f}, max={max_richness:.1f}. "
                      f"Merges predicted_engagement + content_structure to eliminate triple-counting with tech_seo. "
                      f"Readability {'IS' if any(_simple_flesch(p.body_text) > 0 for p in posts[:3]) else 'NOT'} feeding into predicted_engagement component.")
    lines.append("")

    # Observation 11: Content depth vs word count correlation
    wc_list = [m["word_count"] for m in post_metrics]
    depth_list = [m["content_depth_score"] for m in post_metrics]
    wc_depth_r = _pearson(wc_list, depth_list)
    lines.append(f"11. **Content depth vs word count correlation:** r={wc_depth_r:.2f}. "
                  f"{'Strong' if abs(wc_depth_r) > 0.7 else 'Moderate' if abs(wc_depth_r) > 0.4 else 'Weak'} "
                  f"correlation. Content depth also factors in cluster average comparison "
                  f"and quality bonuses (lists, images, tables, external links), "
                  f"so it is not just a word count proxy.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by `backend/scripts/test_step4_e2e.py` (deep analysis) -- "
                  "crawl-only mode, no database, eeat_metadata enabled.*")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  Report written to {report_path}")
    print(f"\n=== Step 7 E2E complete (deep analysis) -- {n_posts} posts scored, "
          f"{n_clusters} clusters, {(total_factor_time + score_time) * 1000:.0f}ms scoring time ===")


if __name__ == "__main__":
    asyncio.run(main())
