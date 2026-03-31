"""End-to-end test of Pipeline Step 9: Problem Detection.

Runs all crawl-based problem detection checks against real crawled data
from Copyblogger. Uses crawl-only mode (no GA4/GSC/AI citability data,
no database) to validate detection logic, thresholds, and coverage.

Reuses Step 1 crawl and Step 3 clustering as prerequisites.
No database required -- tests detection logic only.

Problem types tested:
  - thin_content (absolute word count)
  - thin_below_cluster_avg (cluster-relative)
  - seo_missing_meta, seo_title_length, seo_no_headings,
    seo_no_internal_links, seo_no_images
  - orphan (no inbound links)
  - proxy decay (stale dates, outdated year refs)
  - readability_too_complex (Flesch score, computed locally)
  - velocity_decline (publishing rate from dates)

Code Step mapping:
  Step 1: Crawl → Step 2: Embeddings → Step 3: Readability → Step 4: PageRank
  → Step 5: Intent → Step 6: Clustering → Step 6b: TF-IDF → Step 6c: AI Citability
  → Step 7: Health Scoring → Step 8: Cannibalization → **Step 9: Problem Detection**
  → Step 10: Recommendations
"""

import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

import numpy as np

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


def _generate_synthetic_embeddings(titles: list[str], n_dims: int = 1536) -> np.ndarray:
    """Generate synthetic embeddings with injected topic structure."""
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
    """Run UMAP+HDBSCAN clustering (same as test_step3_e2e.py)."""
    import hdbscan
    import umap
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
    else:
        min_cluster_size = 12
        min_samples = 3

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


def _compute_flesch(text: str) -> float | None:
    """Compute Flesch Reading Ease from plain text. Returns None if text too short."""
    import re as _re
    # Rough sentence/word/syllable counts
    sentences = max(1, len(_re.split(r'[.!?]+', text.strip())))
    words_list = _re.findall(r'[a-zA-Z]+', text)
    n_words = len(words_list)
    if n_words < 30:
        return None  # Too short to be meaningful

    def _syllables(word: str) -> int:
        word = word.lower()
        count = 0
        vowels = "aeiouy"
        if word[0] in vowels:
            count += 1
        for i in range(1, len(word)):
            if word[i] in vowels and word[i - 1] not in vowels:
                count += 1
        if word.endswith("e"):
            count -= 1
        return max(1, count)

    total_syllables = sum(_syllables(w) for w in words_list)

    # Flesch formula
    flesch = 206.835 - 1.015 * (n_words / sentences) - 84.6 * (total_syllables / n_words)
    return max(0.0, min(100.0, flesch))


# ═══════════════════════════════════════════════
# Problem detection functions (extracted from services/problem_detection.py)
# ═══════════════════════════════════════════════

def detect_thin_content(posts: list, cluster_groups: dict[int, list[int]], post_cluster_map: dict[int, int]) -> list[dict]:
    """Detect thin content problems (checks 1 + 2, no GA4 for check 3)."""
    problems = []

    # Pre-compute cluster avg word counts
    cluster_avg_wc: dict[int, float] = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if posts[i].word_count]
        if len(wcs) >= 3:
            cluster_avg_wc[cl_id] = sum(wcs) / len(wcs)
        else:
            cluster_avg_wc[cl_id] = 1000.0

    # Check 1: Absolute thin content
    for i, p in enumerate(posts):
        wc = p.word_count or 0
        if wc == 0:
            continue

        url = (p.url or "").lower()
        title = (p.title or "").lower()

        # Content-type-aware threshold
        if any(kw in url or kw in title for kw in ["/compare", "/vs-", " vs ", "comparison"]):
            threshold = 500
        elif any(kw in url or kw in title for kw in ["how-to", "guide", "tutorial", "step-by-step"]):
            threshold = 800
        elif any(kw in url or kw in title for kw in ["/glossary", "what-is", "definition"]):
            threshold = 200
        else:
            threshold = 500

        if wc >= threshold:
            continue

        # Multi-signal gate
        headings_list = p.headings if isinstance(p.headings, list) else []
        h2_count = sum(1 for h in headings_list if isinstance(h, dict) and h.get("level") in ("h2", "h3"))
        has_images = "<img" in (p.body_html or "").lower()
        # Count inbound links
        inbound = sum(1 for j, other in enumerate(posts) if j != i and any(
            (getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))) == p.url
            for link in other.internal_links
        ))

        if h2_count >= 2 and has_images and inbound >= 5:
            continue

        severity = "high" if wc < threshold * 0.5 else "medium"
        problems.append({
            "post_index": i,
            "title": p.title or "(no title)",
            "url": p.url,
            "problem_type": "thin_content",
            "severity": severity,
            "word_count": wc,
            "threshold": threshold,
            "content_type": (
                "comparison" if any(kw in url or kw in title for kw in ["/compare", "/vs-"]) else
                "tutorial" if any(kw in url or kw in title for kw in ["how-to", "guide", "tutorial"]) else
                "glossary" if any(kw in url or kw in title for kw in ["/glossary", "what-is"]) else
                "default"
            ),
        })

    # Check 2: Below cluster average
    for i, p in enumerate(posts):
        wc = p.word_count or 0
        if wc == 0 or wc >= 800:
            continue
        cl_id = post_cluster_map.get(i)
        if cl_id is None:
            continue
        avg = cluster_avg_wc.get(cl_id, 0)
        if avg <= 1500:
            continue
        if wc < avg * 0.5:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "thin_below_cluster_avg",
                "severity": "medium",
                "word_count": wc,
                "cluster_avg": round(avg),
                "ratio": round(wc / avg, 2),
            })

    return problems


def detect_seo_issues(posts: list) -> list[dict]:
    """Detect per-post SEO issues (5 checks)."""
    problems = []

    # Pre-compute inbound link counts
    url_to_idx = {p.url: i for i, p in enumerate(posts)}
    link_counts: dict[int, int] = {i: 0 for i in range(len(posts))}
    for i, p in enumerate(posts):
        for link in p.internal_links:
            target_url = getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None:
                link_counts[target_idx] += 1
            # Also count outbound
            if target_idx is not None and target_idx != i:
                link_counts[i] = link_counts.get(i, 0)  # ensure exists

    # Compute total links (inbound + outbound) per post
    total_links: dict[int, int] = {i: 0 for i in range(len(posts))}
    for i, p in enumerate(posts):
        outbound = 0
        inbound = 0
        for j, other in enumerate(posts):
            if j == i:
                continue
            for link in other.internal_links:
                target_url = getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))
                if target_url == p.url:
                    inbound += 1
            for link in p.internal_links:
                target_url = getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))
                if url_to_idx.get(target_url) is not None:
                    outbound += 1
        total_links[i] = inbound + outbound

    for i, p in enumerate(posts):
        # 1. Missing meta description
        meta = p.meta_description or ""
        if len(meta.strip()) < 10:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "seo_missing_meta",
                "severity": "medium",
                "meta_length": len(meta.strip()),
            })

        # 2. Title length
        title = p.title or ""
        title_len = len(title.strip())
        if title_len < 20 or title_len > 70:
            severity = "medium" if title_len < 20 else "low"
            problems.append({
                "post_index": i,
                "title": title,
                "url": p.url,
                "problem_type": "seo_title_length",
                "severity": severity,
                "title_length": title_len,
            })

        # 3. No H2+ headings
        headings = p.headings
        if isinstance(headings, str):
            try:
                headings = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                headings = []
        has_h2_plus = False
        if headings and isinstance(headings, list):
            has_h2_plus = any(
                h.get("level") in ("h2", "h3", "h4")
                for h in headings
                if isinstance(h, dict)
            )
        if not has_h2_plus:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "seo_no_headings",
                "severity": "medium",
            })

        # 4. No internal links
        if total_links[i] == 0:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "seo_no_internal_links",
                "severity": "high",
            })

        # 5. No images
        body_html = p.body_html or ""
        html_lower = body_html.lower()
        is_trafilatura_xml = html_lower.startswith("<doc") or "<doc " in html_lower[:100]
        has_images = is_trafilatura_xml or any(tag in html_lower for tag in [
            '<img', '<picture', '<figure', '<svg',
            'data-src=', 'srcset=', 'background-image:',
            'loading="lazy"', "loading='lazy'",
        ])
        if not has_images:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "seo_no_images",
                "severity": "low",
            })

    return problems


def detect_orphans(posts: list) -> list[dict]:
    """Detect orphan content -- posts with zero inbound internal links."""
    url_to_idx = {p.url: i for i, p in enumerate(posts)}
    inbound_counts: dict[int, int] = {i: 0 for i in range(len(posts))}

    for i, p in enumerate(posts):
        for link in p.internal_links:
            target_url = getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1

    problems = []
    for i, p in enumerate(posts):
        wc = p.word_count or 0
        if wc < 200:
            continue
        if inbound_counts[i] == 0:
            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "orphan",
                "severity": "high",
                "word_count": wc,
            })

    return problems


def detect_proxy_decay(posts: list) -> list[dict]:
    """Detect content decay using proxy signals (no GSC needed).

    Mirrors production logic in services/problem_detection.py:_detect_proxy_decay.
    Three signals:
      1. Outdated year references (regex: (19|20)\\d{2}, 2+ years old) -> decay_severe
      2. Time-sensitive keywords + 18+ months stale -> decay_moderate
      3. General staleness (18+ months, no update) -> decay_mild
    """
    now = datetime.now(UTC)
    eighteen_months_ago = now - timedelta(days=548)  # ~18 months
    problems = []

    for i, p in enumerate(posts):
        title = p.title or ""
        last_updated = p.modified_date or p.publish_date
        if not last_updated:
            continue

        # Make timezone-aware if naive
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=UTC)

        if last_updated >= eighteen_months_ago:
            continue

        # Signal 1: Outdated year references (any year 1990-current that's 2+ years old)
        year_match = re.search(r'((?:19|20)\d{2})', title)
        if year_match:
            ref_year = int(year_match.group(1))
            if 1990 <= ref_year <= now.year and ref_year < now.year - 1:
                problems.append({
                    "post_index": i,
                    "title": title,
                    "url": p.url,
                    "problem_type": "decay_severe",
                    "severity": "high",
                    "signal": "outdated_year_reference",
                    "ref_year": ref_year,
                    "proxy": True,
                })
                continue

        # Signal 2: Time-sensitive content not updated in 18+ months
        if any(kw in title.lower() for kw in ["best ", "top ", "review", "pricing", "compare", "vs "]):
            months_stale = (now - last_updated).days / 30.44
            problems.append({
                "post_index": i,
                "title": title,
                "url": p.url,
                "problem_type": "decay_moderate",
                "severity": "medium",
                "signal": "time_sensitive_stale",
                "months_stale": round(months_stale, 1),
                "proxy": True,
            })
            continue

        # Signal 3: General staleness — any post not updated in 18+ months
        months_stale = (now - last_updated).days / 30.44
        problems.append({
            "post_index": i,
            "title": title,
            "url": p.url,
            "problem_type": "decay_mild",
            "severity": "medium",
            "signal": "general_staleness",
            "months_stale": round(months_stale, 1),
            "proxy": True,
        })

    return problems


def detect_readability_issues(posts: list, cluster_labels: list[str] | None = None) -> tuple[list[dict], str, float]:
    """Detect posts with poor readability using Flesch Reading Ease.

    Returns (problems, detected_industry, threshold).
    Uses industry detection from cluster labels to set adaptive threshold.
    """
    from app.services.industry_benchmarks import detect_industry

    industry = detect_industry(cluster_labels or [], [])
    thresholds = {
        "saas": 35.0,
        "agency": 35.0,
        "ecommerce": 50.0,
        "media": 55.0,
        "default": 50.0,
    }
    threshold = thresholds.get(industry, 50.0)
    problems = []

    for i, p in enumerate(posts):
        text = p.body_text or ""
        if len(text.strip()) < 200:
            continue

        flesch = _compute_flesch(text)
        if flesch is None:
            continue

        if flesch < threshold:
            severity = "high" if flesch < 30 else "medium"
            # Approximate grade level from Flesch-Kincaid
            words_list = re.findall(r'[a-zA-Z]+', text)
            n_words = len(words_list)
            sentences = max(1, len(re.split(r'[.!?]+', text.strip())))
            syllables = sum(max(1, sum(1 for j in range(1, len(w.lower())) if w.lower()[j] in "aeiouy" and w.lower()[j-1] not in "aeiouy") + (1 if w.lower()[0] in "aeiouy" else 0) - (1 if w.lower().endswith("e") else 0)) for w in words_list)
            grade_level = 0.39 * (n_words / sentences) + 11.8 * (syllables / n_words) - 15.59
            grade_level = max(0, min(20, grade_level))

            problems.append({
                "post_index": i,
                "title": p.title or "(no title)",
                "url": p.url,
                "problem_type": "readability_too_complex",
                "severity": severity,
                "flesch_score": round(flesch, 1),
                "grade_level": round(grade_level, 1),
                "threshold": threshold,
            })

    return problems, industry, threshold


def detect_velocity_decline(posts: list) -> dict:
    """Analyze publishing velocity from post dates."""
    dates = []
    for p in posts:
        d = p.publish_date
        if d:
            if d.tzinfo is None:
                d = d.replace(tzinfo=UTC)
            dates.append(d)

    if len(dates) < 5:
        return {"status": "insufficient_data", "posts_with_dates": len(dates)}

    dates.sort()
    now = datetime.now(UTC)

    # Recent 90 days vs previous 90 days
    ninety_days_ago = now - timedelta(days=90)
    one_eighty_days_ago = now - timedelta(days=180)

    recent_count = sum(1 for d in dates if d >= ninety_days_ago)
    previous_count = sum(1 for d in dates if one_eighty_days_ago <= d < ninety_days_ago)

    # Weekly velocity
    recent_weekly = recent_count / 13 if recent_count > 0 else 0
    previous_weekly = previous_count / 13 if previous_count > 0 else 0

    # Overall stats
    date_range_days = (dates[-1] - dates[0]).days
    overall_weekly = len(dates) / max(1, date_range_days / 7)

    # Determine trend
    if previous_count > 0 and recent_count < previous_count * 0.5:
        trend = "declining"
    elif recent_count > previous_count * 1.5:
        trend = "accelerating"
    else:
        trend = "stable"

    # Peak velocity period (best publishing year)
    year_counts: dict[int, int] = {}
    for d in dates:
        yr = d.year
        year_counts[yr] = year_counts.get(yr, 0) + 1
    peak_year = max(year_counts, key=year_counts.get) if year_counts else None
    peak_count = year_counts.get(peak_year, 0) if peak_year else 0
    peak_weekly = round(peak_count / 52, 2) if peak_count else 0

    return {
        "status": "analyzed",
        "total_posts_with_dates": len(dates),
        "date_range": f"{dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}",
        "date_range_days": date_range_days,
        "recent_90d_posts": recent_count,
        "previous_90d_posts": previous_count,
        "recent_weekly_velocity": round(recent_weekly, 2),
        "previous_weekly_velocity": round(previous_weekly, 2),
        "overall_weekly_velocity": round(overall_weekly, 2),
        "peak_year": peak_year,
        "peak_year_posts": peak_count,
        "peak_weekly_velocity": peak_weekly,
        "trend": trend,
        "is_declining": trend == "declining",
    }


async def main():
    from app.services.normalizer import (
        _strip_html_from_meta,
        _strip_site_name_from_title,
        filter_nav_links,
        filter_sitewide_headings,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 9 E2E Test: Problem Detection ({TARGET_DOMAIN}) ===\n")

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
    # PHASE 2: Clustering (reuse Step 3)
    # ===================================================================
    print("Phase 2: Clustering (Step 3 prerequisite)...")
    titles = [p.title or "" for p in posts]
    cluster_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    labels, cluster_groups = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - cluster_start
    n_clusters = len(cluster_groups)
    print(f"  Generated {n_clusters} clusters in {cluster_time:.1f}s")

    # Build post->cluster map
    post_cluster_map: dict[int, int] = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    # Generate cluster labels from titles (for industry detection)
    from app.services.fast_cluster_labels import _compute_site_stops, _tfidf_label
    cluster_titles_map = {}
    for cl_id, indices in cluster_groups.items():
        cluster_titles_map[cl_id] = [posts[i].title or "" for i in indices]
    all_titles_flat = [posts[i].title or "" for i in range(n_posts)]
    site_stops = _compute_site_stops(all_titles_flat)
    cluster_labels = []
    for cl_id in sorted(cluster_groups.keys()):
        label_tuple = _tfidf_label(cluster_titles_map[cl_id], all_titles_flat, site_stops)
        cluster_labels.append(label_tuple[0])  # First element is the label string
    print(f"  Cluster labels: {cluster_labels}")

    # Compute link resolution rate (quality gate for orphan/link checks)
    url_to_idx_qg = {p.url: i for i, p in enumerate(posts)}
    total_outbound_links = 0
    resolved_outbound_links = 0
    for p in posts:
        for link in p.internal_links:
            target_url = getattr(link, "target_url", None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            total_outbound_links += 1
            if url_to_idx_qg.get(target_url) is not None:
                resolved_outbound_links += 1
    link_resolution_rate = resolved_outbound_links / max(total_outbound_links, 1)
    link_resolution_reliable = total_outbound_links == 0 or link_resolution_rate >= 0.20
    print(f"  Link resolution: {resolved_outbound_links}/{total_outbound_links} ({link_resolution_rate:.1%})")
    print(f"  Quality gate: {'PASS (>= 20%)' if link_resolution_reliable else 'FAIL (< 20%) — orphan/link checks will be SKIPPED'}")
    print()

    # ===================================================================
    # PHASE 3: Data Availability Detection (9.0)
    # ===================================================================
    print("Phase 3: Data availability detection (Step 9.0)...")
    print("  GA4 data: NO (crawl-only)")
    print("  GSC data: NO (crawl-only)")
    print("  AI citability scores: NO (crawl-only)")
    print(f"  Mode: Crawl-only — {'8' if link_resolution_reliable else '6'} of 11 detectors will run")
    if not link_resolution_reliable:
        print("  NOTE: Orphan + seo_no_internal_links skipped (link resolution < 20%)")
    print()

    all_problems: list[dict] = []
    detector_timings: dict[str, float] = {}
    detector_counts: dict[str, int] = {}

    # ===================================================================
    # PHASE 4: Thin Content Detection (9.1)
    # ===================================================================
    print("Phase 4: Thin content detection (Step 9.1)...")
    t0 = time.time()
    thin_problems = detect_thin_content(posts, cluster_groups, post_cluster_map)
    detector_timings["thin_content"] = time.time() - t0

    thin_absolute = [p for p in thin_problems if p["problem_type"] == "thin_content"]
    thin_cluster = [p for p in thin_problems if p["problem_type"] == "thin_below_cluster_avg"]
    detector_counts["thin_content"] = len(thin_absolute)
    detector_counts["thin_below_cluster_avg"] = len(thin_cluster)
    all_problems.extend(thin_problems)

    print(f"  Absolute thin content: {len(thin_absolute)} posts")
    print(f"  Below cluster average: {len(thin_cluster)} posts")
    if thin_absolute:
        wcs = [p["word_count"] for p in thin_absolute]
        print(f"  Thin word counts: min={min(wcs)}, max={max(wcs)}, mean={statistics.mean(wcs):.0f}")
    print(f"  Time: {detector_timings['thin_content'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 5: SEO Issue Detection (9.2)
    # ===================================================================
    print("Phase 5: SEO issue detection — 5 checks (Step 9.2)...")
    t0 = time.time()
    seo_problems_raw = detect_seo_issues(posts)
    detector_timings["seo_issues"] = time.time() - t0

    # Quality gate: skip seo_no_internal_links if link resolution < 20%
    if not link_resolution_reliable:
        seo_problems = [p for p in seo_problems_raw if p["problem_type"] != "seo_no_internal_links"]
        skipped_links = len(seo_problems_raw) - len(seo_problems)
        print(f"  QUALITY GATE: skipped {skipped_links} seo_no_internal_links (resolution {link_resolution_rate:.1%} < 20%)")
    else:
        seo_problems = seo_problems_raw

    seo_by_type = Counter(p["problem_type"] for p in seo_problems)
    for seo_type, count in seo_by_type.most_common():
        detector_counts[seo_type] = count
        print(f"  {seo_type}: {count} posts")
    all_problems.extend(seo_problems)
    print(f"  Time: {detector_timings['seo_issues'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 6: Orphan Detection (9.3)
    # ===================================================================
    print("Phase 6: Orphan detection (Step 9.3)...")
    if link_resolution_reliable:
        t0 = time.time()
        orphan_problems = detect_orphans(posts)
        detector_timings["orphan"] = time.time() - t0
        detector_counts["orphan"] = len(orphan_problems)
        all_problems.extend(orphan_problems)
        print(f"  Orphan posts: {len(orphan_problems)}")
        if orphan_problems:
            orphan_wcs = [p["word_count"] for p in orphan_problems]
            print(f"  Orphan word counts: min={min(orphan_wcs)}, max={max(orphan_wcs)}, mean={statistics.mean(orphan_wcs):.0f}")
    else:
        orphan_problems = []
        detector_timings["orphan"] = 0
        detector_counts["orphan"] = 0
        print(f"  QUALITY GATE: SKIPPED (link resolution {link_resolution_rate:.1%} < 20%)")
    print(f"  Time: {detector_timings['orphan'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 7: Proxy Decay Detection (9.4)
    # ===================================================================
    print("Phase 7: Proxy decay detection — crawl-based (Step 9.4)...")
    t0 = time.time()
    decay_problems = detect_proxy_decay(posts)
    detector_timings["proxy_decay"] = time.time() - t0

    decay_by_type = Counter(p["problem_type"] for p in decay_problems)
    for dtype, count in decay_by_type.most_common():
        detector_counts[dtype] = count
        print(f"  {dtype}: {count} posts")
    decay_by_signal = Counter(p.get("signal", "unknown") for p in decay_problems)
    for signal, count in decay_by_signal.most_common():
        print(f"    Signal: {signal} = {count}")
    all_problems.extend(decay_problems)
    print(f"  Time: {detector_timings['proxy_decay'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 8: Readability Detection (9.5)
    # ===================================================================
    print("Phase 8: Readability issue detection (Step 9.5)...")
    t0 = time.time()
    readability_problems, detected_industry, readability_threshold = detect_readability_issues(posts, cluster_labels)
    detector_timings["readability"] = time.time() - t0
    detector_counts["readability_too_complex"] = len(readability_problems)
    all_problems.extend(readability_problems)

    print(f"  Industry detected: {detected_industry} (threshold: Flesch < {readability_threshold})")
    print(f"  Posts with poor readability: {len(readability_problems)}")
    if readability_problems:
        flesch_scores = [p["flesch_score"] for p in readability_problems]
        grade_levels = [p["grade_level"] for p in readability_problems]
        print(f"  Flesch scores: min={min(flesch_scores):.1f}, max={max(flesch_scores):.1f}, mean={statistics.mean(flesch_scores):.1f}")
        print(f"  Grade levels: min={min(grade_levels):.1f}, max={max(grade_levels):.1f}, mean={statistics.mean(grade_levels):.1f}")
    # Also compute overall readability stats for all posts
    all_flesch = []
    for p in posts:
        f = _compute_flesch(p.body_text or "")
        if f is not None:
            all_flesch.append(f)
    if all_flesch:
        print(f"  Site-wide Flesch: min={min(all_flesch):.1f}, max={max(all_flesch):.1f}, mean={statistics.mean(all_flesch):.1f}, median={statistics.median(all_flesch):.1f}")
    print(f"  Time: {detector_timings['readability'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 9: Velocity Analysis (9.6)
    # ===================================================================
    print("Phase 9: Publishing velocity analysis (Step 9.6)...")
    t0 = time.time()
    velocity = detect_velocity_decline(posts)
    detector_timings["velocity"] = time.time() - t0

    if velocity["status"] == "analyzed":
        print(f"  Posts with dates: {velocity['total_posts_with_dates']}")
        print(f"  Date range: {velocity['date_range']}")
        print(f"  Recent 90d posts: {velocity['recent_90d_posts']}")
        print(f"  Previous 90d posts: {velocity['previous_90d_posts']}")
        print(f"  Recent weekly velocity: {velocity['recent_weekly_velocity']}")
        print(f"  Previous weekly velocity: {velocity['previous_weekly_velocity']}")
        print(f"  Overall weekly velocity: {velocity['overall_weekly_velocity']}")
        if velocity.get("peak_year"):
            print(f"  Peak: {velocity['peak_weekly_velocity']} posts/week in {velocity['peak_year']} ({velocity['peak_year_posts']} posts)")
        print(f"  Trend: {velocity['trend']}")
        if velocity["is_declining"]:
            detector_counts["velocity_decline"] = 1
            # Add to all_problems so it appears in severity table and total count
            # Uses the most recent post as the anchor (mirrors production)
            latest_idx = max(range(len(posts)),
                             key=lambda i: getattr(posts[i], 'publish_date', None) or datetime.min)
            all_problems.append({
                "post_index": latest_idx,
                "title": getattr(posts[latest_idx], 'title', '') or "(most recent post)",
                "url": getattr(posts[latest_idx], 'url', ''),
                "problem_type": "velocity_decline",
                "severity": "medium",
                "current_velocity": velocity["recent_weekly_velocity"],
            })
    else:
        print(f"  Status: {velocity['status']}")
    print(f"  Time: {detector_timings['velocity'] * 1000:.1f}ms")
    print()

    # ===================================================================
    # PHASE 10: Skipped Detectors
    # ===================================================================
    print("Phase 10: Skipped detectors (no data)...")
    print("  content_decay (needs GSC): SKIPPED")
    print("  thin_high_bounce (needs GA4): SKIPPED")
    print("  ai_readiness (needs AI citability scores): SKIPPED")
    print()

    # ===================================================================
    # PHASE 11: Related Problem Grouping (9.7)
    # ===================================================================
    print("Phase 11: Related problem grouping & dedup (Step 9.7)...")
    # Mirrors production logic: SUPPRESS seo_no_internal_links when orphan co-exists,
    # MARK thin_below_cluster_avg as related to thin_content.
    from itertools import groupby as _groupby

    # SUPPRESS groups: delete secondary entirely (same customer action)
    suppress_groups = [
        {"types": {"seo_no_internal_links", "orphan"}, "root": "orphan"},
    ]
    # MARK groups: annotate secondary with related_to
    mark_groups = [
        {"types": {"thin_content", "thin_below_cluster_avg"}, "root": "thin_content"},
    ]

    all_problems_sorted = sorted(all_problems, key=lambda p: p["post_index"])
    suppressed_count = 0
    mark_count = 0
    indices_to_remove: set[int] = set()

    for _post_idx, post_probs in _groupby(all_problems_sorted, key=lambda x: x["post_index"]):
        post_probs_list = list(post_probs)
        prob_types = {p["problem_type"] for p in post_probs_list}

        for group in suppress_groups:
            overlap = prob_types & group["types"]
            if len(overlap) > 1:
                for p in post_probs_list:
                    if p["problem_type"] in overlap and p["problem_type"] != group["root"]:
                        idx = all_problems.index(p)
                        indices_to_remove.add(idx)
                        suppressed_count += 1

        for group in mark_groups:
            overlap = prob_types & group["types"]
            if len(overlap) > 1:
                mark_count += 1
                for p in post_probs_list:
                    if p["problem_type"] in overlap and p["problem_type"] != group["root"]:
                        p["related_to"] = group["root"]

    # Remove suppressed problems
    if indices_to_remove:
        all_problems = [p for i, p in enumerate(all_problems) if i not in indices_to_remove]
        # Update seo counts
        seo_by_type = Counter(p["problem_type"] for p in all_problems if p["problem_type"].startswith("seo_"))

    print(f"  Suppressed (deleted): {suppressed_count} seo_no_internal_links (orphan subsumes)")
    print(f"  Marked as related: {mark_count} thin_below_cluster_avg -> thin_content")
    print()

    # ===================================================================
    # PHASE 12: Summary & Analysis
    # ===================================================================
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_problems = len(all_problems)
    print(f"\nTotal problems detected: {total_problems}")
    print(f"Posts analyzed: {n_posts}")
    print(f"Average problems per post: {total_problems / n_posts:.1f}")

    # Problems per post distribution
    problems_per_post: dict[int, int] = Counter(p["post_index"] for p in all_problems)
    max_problems_per_post = max(problems_per_post.values()) if problems_per_post else 0
    clean_posts = n_posts - len(problems_per_post)

    print(f"Clean posts (zero problems): {clean_posts} ({clean_posts / n_posts * 100:.1f}%)")
    print(f"Most problems on single post: {max_problems_per_post}")
    print()

    # By type
    print("By problem type:")
    type_counter = Counter(p["problem_type"] for p in all_problems)
    for ptype, count in type_counter.most_common():
        pct = count / n_posts * 100
        bar = "#" * max(1, int(pct / 2))
        print(f"  {ptype:30s} {count:4d} ({pct:5.1f}%)  {bar}")
    print()

    # By severity
    print("By severity:")
    sev_counter = Counter(p["severity"] for p in all_problems)
    for sev in ["high", "medium", "low"]:
        count = sev_counter.get(sev, 0)
        pct = count / total_problems * 100 if total_problems else 0
        print(f"  {sev:8s} {count:4d} ({pct:5.1f}%)")
    print()

    # Timing
    print("Detector timing:")
    total_time = sum(detector_timings.values())
    for detector, elapsed in sorted(detector_timings.items(), key=lambda x: -x[1]):
        print(f"  {detector:20s} {elapsed * 1000:8.1f}ms")
    print(f"  {'TOTAL':20s} {total_time * 1000:8.1f}ms")
    print()

    # Per-cluster problem density
    print("Per-cluster problem density:")
    cluster_problem_counts: dict[int, int] = {}
    for prob in all_problems:
        cl_id = post_cluster_map.get(prob["post_index"])
        if cl_id is not None:
            cluster_problem_counts[cl_id] = cluster_problem_counts.get(cl_id, 0) + 1

    for cl_id in sorted(cluster_groups.keys()):
        n_cl_posts = len(cluster_groups[cl_id])
        n_cl_probs = cluster_problem_counts.get(cl_id, 0)
        density = n_cl_probs / n_cl_posts if n_cl_posts else 0
        print(f"  Cluster {cl_id:3d}: {n_cl_posts:3d} posts, {n_cl_probs:3d} problems, density={density:.1f}/post")
    print()

    # Top 10 most problematic posts
    print("Top 10 most problematic posts:")
    for post_idx, count in problems_per_post.most_common(10):
        p = posts[post_idx]
        types = [prob["problem_type"] for prob in all_problems if prob["post_index"] == post_idx]
        print(f"  [{count} problems] {(p.title or '(no title)')[:60]}")
        print(f"    Types: {', '.join(types)}")
    print()

    # ===================================================================
    # WRITE REPORT
    # ===================================================================
    print("Writing report...")
    report_path = "../STEP9-TEST-RESULTS.md"
    lines: list[str] = []

    lines.append(f"# Step 9 E2E Test Results — Problem Detection: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Posts analyzed:** {n_posts}")
    lines.append(f"**Clusters:** {n_clusters}")
    lines.append("**Detection mode:** Crawl-only (no GA4, no GSC, no AI citability)")
    lines.append(f"**Prerequisite:** Step 1 crawl ({TARGET_DOMAIN}, {MAX_PAGES} max) + Step 3 clustering (synthetic embeddings)")
    lines.append("**Note:** Proxy decay detection uses crawl dates and title patterns. Real decay detection requires GSC data.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Data availability
    lines.append("## 9.0 Data Availability")
    lines.append("")
    lines.append("| Data Source | Available | Impact |")
    lines.append("|------------|-----------|--------|")
    lines.append("| Crawl data | YES | All crawl-based detectors run |")
    lines.append("| GA4 metrics | NO | thin_high_bounce skipped |")
    lines.append("| GSC metrics | NO | content_decay (3 signals) skipped |")
    lines.append("| AI citability | NO | ai_readiness skipped |")
    lines.append("| Cluster data | YES (synthetic) | thin_below_cluster_avg runs |")
    lines.append("| **Active detectors** | **8 / 10** | |")
    lines.append("")

    # Thin content results
    lines.append("## 9.1 Thin Content Detection")
    lines.append("")
    lines.append("### Absolute Thin Content")
    lines.append("")
    lines.append(f"**Found: {len(thin_absolute)} posts**")
    lines.append("")
    if thin_absolute:
        lines.append("| Post Title | URL | Word Count | Threshold | Type | Severity |")
        lines.append("|-----------|-----|-----------|-----------|------|----------|")
        for p in sorted(thin_absolute, key=lambda x: x["word_count"]):
            title_short = p["title"][:50] + ("..." if len(p["title"]) > 50 else "")
            url_short = p["url"].replace(f"https://{TARGET_DOMAIN}", "")[:40]
            lines.append(f"| {title_short} | {url_short} | {p['word_count']} | {p['threshold']} | {p['content_type']} | {p['severity']} |")
        lines.append("")
        wcs = [p["word_count"] for p in thin_absolute]
        lines.append(f"**Stats:** min={min(wcs)}, max={max(wcs)}, mean={statistics.mean(wcs):.0f}")
    else:
        lines.append("No absolute thin content detected.")
    lines.append("")

    lines.append("### Below Cluster Average")
    lines.append("")
    lines.append(f"**Found: {len(thin_cluster)} posts**")
    lines.append("")
    if thin_cluster:
        lines.append("| Post Title | Word Count | Cluster Avg | Ratio | Severity |")
        lines.append("|-----------|-----------|-------------|-------|----------|")
        for p in sorted(thin_cluster, key=lambda x: x["ratio"]):
            title_short = p["title"][:50] + ("..." if len(p["title"]) > 50 else "")
            lines.append(f"| {title_short} | {p['word_count']} | {p['cluster_avg']} | {p['ratio']:.2f} | {p['severity']} |")
    else:
        lines.append("No posts below cluster average threshold (requires cluster_avg > 1500 AND word_count < 800).")
    lines.append("")

    # SEO issues
    lines.append("## 9.2 SEO Issue Detection")
    lines.append("")
    lines.append("| Check | Problem Type | Count | % of Posts | Severity |")
    lines.append("|-------|-------------|-------|-----------|----------|")
    seo_types_order = ["seo_missing_meta", "seo_title_length", "seo_no_headings", "seo_no_internal_links", "seo_no_images"]
    seo_check_names = {
        "seo_missing_meta": "Missing meta description",
        "seo_title_length": "Title length issue",
        "seo_no_headings": "No H2+ headings",
        "seo_no_internal_links": "No internal links",
        "seo_no_images": "No images detected",
    }
    seo_severities = {
        "seo_missing_meta": "medium",
        "seo_title_length": "low-medium",
        "seo_no_headings": "medium",
        "seo_no_internal_links": "high",
        "seo_no_images": "low",
    }
    for stype in seo_types_order:
        count = seo_by_type.get(stype, 0)
        pct = count / n_posts * 100
        lines.append(f"| {seo_check_names.get(stype, stype)} | `{stype}` | {count} | {pct:.1f}% | {seo_severities.get(stype, 'medium')} |")
    seo_total = sum(seo_by_type.values())
    lines.append(f"| **Total SEO issues** | | **{seo_total}** | | |")
    lines.append("")

    # Sample SEO issues (up to 5 per type)
    for stype in seo_types_order:
        type_problems = [p for p in seo_problems if p["problem_type"] == stype]
        if type_problems:
            lines.append(f"### {seo_check_names.get(stype, stype)} (sample)")
            lines.append("")
            for p in type_problems[:5]:
                title_short = p["title"][:60]
                extra = ""
                if stype == "seo_title_length":
                    extra = f" (length: {p['title_length']})"
                elif stype == "seo_missing_meta":
                    extra = f" (meta length: {p['meta_length']})"
                lines.append(f"- {title_short}{extra}")
            if len(type_problems) > 5:
                lines.append(f"- ... and {len(type_problems) - 5} more")
            lines.append("")

    # Orphan detection
    lines.append("## 9.3 Orphan Detection")
    lines.append("")
    lines.append(f"**Found: {len(orphan_problems)} orphan posts** (no inbound internal links, >= 200 words)")
    lines.append("")
    if orphan_problems:
        lines.append("| Post Title | URL | Word Count |")
        lines.append("|-----------|-----|-----------|")
        for p in sorted(orphan_problems, key=lambda x: -x["word_count"])[:15]:
            title_short = p["title"][:50] + ("..." if len(p["title"]) > 50 else "")
            url_short = p["url"].replace(f"https://{TARGET_DOMAIN}", "")[:40]
            lines.append(f"| {title_short} | {url_short} | {p['word_count']} |")
        if len(orphan_problems) > 15:
            lines.append(f"| ... | | ({len(orphan_problems) - 15} more) |")
    lines.append("")

    # Proxy decay
    lines.append("## 9.4 Proxy Decay Detection")
    lines.append("")
    lines.append(f"**Found: {len(decay_problems)} decay problems** (proxy signals, no GSC)")
    lines.append("")
    if decay_problems:
        lines.append("| Severity | Signal | Count |")
        lines.append("|----------|--------|-------|")
        for dtype in ["decay_severe", "decay_moderate", "decay_mild"]:
            for signal in ["outdated_year_reference", "time_sensitive_stale"]:
                count = sum(1 for p in decay_problems if p["problem_type"] == dtype and p.get("signal") == signal)
                if count > 0:
                    lines.append(f"| {dtype} | {signal} | {count} |")
        lines.append("")

        lines.append("### Sample Proxy Decay")
        lines.append("")
        # Sort by severity tier so decay_severe examples appear first
        _decay_severity_order = {"decay_severe": 0, "decay_moderate": 1, "decay_mild": 2}
        sorted_decay = sorted(decay_problems, key=lambda p: _decay_severity_order.get(p["problem_type"], 9))
        for p in sorted_decay[:10]:
            title_short = p["title"][:60]
            extra = ""
            if p.get("ref_year"):
                extra = f" (year ref: {p['ref_year']})"
            elif p.get("months_stale"):
                extra = f" ({p['months_stale']} months stale)"
            lines.append(f"- [{p['problem_type']}] {title_short}{extra}")
        if len(decay_problems) > 10:
            lines.append(f"- ... and {len(decay_problems) - 10} more")
    lines.append("")

    # Readability
    lines.append("## 9.5 Readability Issues")
    lines.append("")
    lines.append(f"**Industry detected:** {detected_industry} (threshold: Flesch < {readability_threshold})")
    lines.append("")
    lines.append(f"**Found: {len(readability_problems)} posts with poor readability** (Flesch < {readability_threshold})")
    lines.append("")
    if readability_problems:
        lines.append("| Post Title | Flesch Score | Grade Level | Severity |")
        lines.append("|-----------|-------------|-------------|----------|")
        for p in sorted(readability_problems, key=lambda x: x["flesch_score"])[:15]:
            title_short = p["title"][:50] + ("..." if len(p["title"]) > 50 else "")
            lines.append(f"| {title_short} | {p['flesch_score']} | {p['grade_level']} | {p['severity']} |")
        if len(readability_problems) > 15:
            lines.append(f"| ... | | | ({len(readability_problems) - 15} more) |")
        lines.append("")

    if all_flesch:
        lines.append("### Site-Wide Readability Distribution")
        lines.append("")
        lines.append("| Score Range | Count | % | Histogram |")
        lines.append("|------------|-------|---|-----------|")
        flesch_buckets = [(0, 30, "0-30 (very hard)"), (30, 50, "30-50 (hard)"),
                         (50, 60, "50-60 (fairly hard)"), (60, 70, "60-70 (standard)"),
                         (70, 80, "70-80 (fairly easy)"), (80, 100, "80-100 (easy)")]
        for lo, hi, label in flesch_buckets:
            count = sum(1 for f in all_flesch if lo <= f < hi)
            pct = count / len(all_flesch) * 100
            bar = "#" * max(1, int(pct / 2))
            lines.append(f"| {label} | {count} | {pct:.1f}% | {bar} |")
        lines.append("")

    # Velocity
    lines.append("## 9.6 Publishing Velocity")
    lines.append("")
    if velocity["status"] == "analyzed":
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Posts with dates | {velocity['total_posts_with_dates']} |")
        lines.append(f"| Date range | {velocity['date_range']} |")
        lines.append(f"| Date range (days) | {velocity['date_range_days']} |")
        lines.append(f"| Recent 90d posts | {velocity['recent_90d_posts']} |")
        lines.append(f"| Previous 90d posts | {velocity['previous_90d_posts']} |")
        lines.append(f"| Recent weekly velocity | {velocity['recent_weekly_velocity']} |")
        lines.append(f"| Previous weekly velocity | {velocity['previous_weekly_velocity']} |")
        lines.append(f"| Overall weekly velocity | {velocity['overall_weekly_velocity']} |")
        if velocity.get("peak_year"):
            lines.append(f"| **Peak velocity** | **{velocity['peak_weekly_velocity']} posts/week in {velocity['peak_year']} ({velocity['peak_year_posts']} posts)** |")
        lines.append(f"| **Trend** | **{velocity['trend']}** |")
        if velocity["is_declining"]:
            lines.append("| **Would flag** | **velocity_decline (medium)** |")
    else:
        lines.append(f"Insufficient data: {velocity.get('posts_with_dates', 0)} posts with dates")
    lines.append("")

    # Skipped detectors
    lines.append("## Skipped Detectors")
    lines.append("")
    lines.append("| Detector | Reason | Would Need |")
    lines.append("|----------|--------|-----------|")
    lines.append("| Content decay (3 signals) | No GSC data | `gsc_metrics` table with click/position data |")
    lines.append("| Thin: high bounce | No GA4 data | `ga4_metrics` table with bounce_rate, engagement_time |")
    lines.append("| AI readiness (5+ checks) | No AI citability scores | Step 6c (AI Citability) must run first |")
    lines.append("")

    # Related problem grouping
    lines.append("## 9.7 Related Problem Grouping & Dedup")
    lines.append("")
    lines.append(f"**Suppressed (orphan subsumes seo_no_internal_links):** {suppressed_count}")
    lines.append(f"**Marked as related (thin cluster):** {mark_count}")
    lines.append("")
    lines.append("| Group | Strategy | Problem Types | Affected Posts |")
    lines.append("|-------|----------|-------------|---------------|")
    lines.append(f"| Orphan cluster | SUPPRESS (delete secondary) | orphan, seo_no_internal_links | {suppressed_count} |")
    lines.append(f"| Thin cluster | MARK (annotate) | thin_content, thin_below_cluster_avg | {mark_count} |")
    lines.append("")

    # Summary
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Detector | Problems | Time | External API | Notes |")
    lines.append("|----------|---------|------|-------------|-------|")
    detector_order = [
        ("thin_content", "Thin content (absolute)", "thin_content"),
        ("thin_below_cluster_avg", "Thin content (cluster avg)", "thin_content"),
        ("seo_missing_meta", "SEO: missing meta", "seo_issues"),
        ("seo_title_length", "SEO: title length", "seo_issues"),
        ("seo_no_headings", "SEO: no headings", "seo_issues"),
        ("seo_no_internal_links", "SEO: no internal links", "seo_issues"),
        ("seo_no_images", "SEO: no images", "seo_issues"),
        ("orphan", "Orphan detection", "orphan"),
        ("decay_severe", "Proxy decay (severe)", "proxy_decay"),
        ("decay_moderate", "Proxy decay (moderate)", "proxy_decay"),
        ("readability_too_complex", "Readability issues", "readability"),
    ]
    for ptype, label, timing_key in detector_order:
        count = detector_counts.get(ptype, 0)
        t = detector_timings.get(timing_key, 0)
        lines.append(f"| {label} | {count} | {t * 1000:.1f}ms | None | Crawl-based |")
    if velocity.get("is_declining"):
        lines.append(f"| Velocity decline | 1 | {detector_timings.get('velocity', 0) * 1000:.1f}ms | None | |")

    total_det_time = sum(detector_timings.values())
    lines.append(f"| **Total Step 9** | **{total_problems}** | **{total_det_time * 1000:.1f}ms** | **Free** | |")
    lines.append("")

    # Problem density
    lines.append("## Per-Cluster Problem Density")
    lines.append("")
    lines.append("| Cluster | Posts | Problems | Density (per post) | Top Problem Types |")
    lines.append("|---------|-------|---------|-------------------|------------------|")
    for cl_id in sorted(cluster_groups.keys()):
        n_cl_posts = len(cluster_groups[cl_id])
        n_cl_probs = cluster_problem_counts.get(cl_id, 0)
        density = n_cl_probs / n_cl_posts if n_cl_posts else 0
        # Top problem types for this cluster
        cl_types = Counter(
            prob["problem_type"] for prob in all_problems
            if post_cluster_map.get(prob["post_index"]) == cl_id
        )
        top_types = ", ".join(f"{t}={c}" for t, c in cl_types.most_common(3))
        lines.append(f"| {cl_id} | {n_cl_posts} | {n_cl_probs} | {density:.1f} | {top_types} |")
    lines.append("")

    # Top 10 most problematic
    lines.append("## Top 10 Most Problematic Posts")
    lines.append("")
    lines.append("| # | Post Title | Problems | Types |")
    lines.append("|---|-----------|---------|-------|")
    for rank, (post_idx, count) in enumerate(problems_per_post.most_common(10), 1):
        p = posts[post_idx]
        types = sorted(set(prob["problem_type"] for prob in all_problems if prob["post_index"] == post_idx))
        title_short = (p.title or "(no title)")[:50]
        lines.append(f"| {rank} | {title_short} | {count} | {', '.join(types)} |")
    lines.append("")

    # Severity distribution
    lines.append("## Severity Distribution")
    lines.append("")
    lines.append("| Severity | Count | % of Total | Histogram |")
    lines.append("|----------|-------|-----------|-----------|")
    for sev in ["high", "medium", "low"]:
        count = sev_counter.get(sev, 0)
        pct = count / total_problems * 100 if total_problems else 0
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {sev} | {count} | {pct:.1f}% | {bar} |")
    lines.append("")

    # S6-20: Severity scores from weight table
    lines.append("## Severity Scores (Weight Table Verification)")
    lines.append("")
    lines.append("Each problem type has a weight that produces a `severity_score` (0-100) stored in details JSON.")
    lines.append("")
    lines.append("| Problem Type | Weight | Severity Score | Count in Test |")
    lines.append("|-------------|--------|---------------|--------------|")
    # Import the weight table
    from app.services.problem_detection import ProblemDetector
    weight_table = ProblemDetector._PROBLEM_WEIGHTS
    for ptype in sorted(weight_table.keys(), key=lambda k: -weight_table[k]):
        w = weight_table[ptype]
        score = round(w * 100)
        count = type_counter.get(ptype, 0)
        lines.append(f"| `{ptype}` | {w} | {score} | {count} |")
    # Show types not in weight table (would default to 0.5)
    for ptype, count in type_counter.most_common():
        if ptype not in weight_table:
            lines.append(f"| `{ptype}` | 0.5 (default) | 50 | {count} |")
    lines.append("")

    # S6-15: Top 10 ranked by severity weight sum (not count)
    lines.append("## Top 10 Most Problematic Posts (by Severity Weight Sum)")
    lines.append("")
    lines.append("Ranked by sum of problem weights, not raw problem count.")
    lines.append("")
    # Compute weight sum per post
    post_weight_sums: dict[int, float] = {}
    for prob in all_problems:
        idx = prob["post_index"]
        w = weight_table.get(prob["problem_type"], 0.5)
        post_weight_sums[idx] = post_weight_sums.get(idx, 0.0) + w
    top_by_weight = sorted(post_weight_sums.items(), key=lambda x: -x[1])[:10]
    lines.append("| # | Post Title | Weight Sum | Problem Count | Types (with weights) |")
    lines.append("|---|-----------|-----------|--------------|---------------------|")
    for rank, (post_idx, wsum) in enumerate(top_by_weight, 1):
        p = posts[post_idx]
        count = problems_per_post.get(post_idx, 0)
        types_with_weights = []
        for prob in all_problems:
            if prob["post_index"] == post_idx:
                w = weight_table.get(prob["problem_type"], 0.5)
                types_with_weights.append(f"{prob['problem_type']}({w})")
        title_short = (p.title or "(no title)")[:45]
        lines.append(f"| {rank} | {title_short} | {wsum:.1f} | {count} | {', '.join(sorted(set(types_with_weights)))} |")
    lines.append("")

    # S6-17: PDF report problem selection preview
    lines.append("## PDF Report Preview (Simulated)")
    lines.append("")
    lines.append("Problems that would appear in the cold outreach PDF, prioritized by severity weight:")
    lines.append("")
    # Group problems by type and count, sorted by weight
    type_weights = {}
    for ptype, count in type_counter.items():
        w = weight_table.get(ptype, 0.5)
        type_weights[ptype] = {"count": count, "weight": w, "score": round(w * 100), "pct": count / n_posts * 100}
    sorted_types = sorted(type_weights.items(), key=lambda x: (-x[1]["weight"], -x[1]["count"]))
    lines.append("| Priority | Problem Type | Weight | Affected Posts | % | PDF Section |")
    lines.append("|----------|-------------|--------|---------------|---|------------|")
    pdf_sections = {
        "orphan": "Quick Wins",
        "seo_no_internal_links": "Quick Wins",
        "seo_missing_meta": "Quick Wins",
        "seo_no_headings": "Quick Wins",
        "seo_title_length": "Quick Wins",
        "seo_no_images": "Quick Wins",
        "thin_content": "Key Findings",
        "thin_below_cluster_avg": "Key Findings",
        "decay_severe": "Key Findings",
        "decay_moderate": "30-Day Plan",
        "decay_mild": "30-Day Plan",
        "readability_too_complex": "30-Day Plan",
        "velocity_decline": "Key Findings",
    }
    for rank, (ptype, info) in enumerate(sorted_types, 1):
        section = pdf_sections.get(ptype, "30-Day Plan")
        lines.append(f"| {rank} | `{ptype}` | {info['weight']} | {info['count']} | {info['pct']:.1f}% | {section} |")
    lines.append("")

    # S6-26: Generated problem text preview for top 3 problems
    pdf_text_templates = {
        "seo_missing_meta": lambda c: (
            f"Add meta descriptions to {c} posts — prioritize your top 10 by traffic. "
            "A compelling 150-character description improves CTR by 5.8% on average."
        ),
        "seo_no_headings": lambda c: (
            f"{c} posts lack H2/H3 heading structure. Add 3-5 descriptive H2s per post "
            "to improve scannability and help search engines understand content hierarchy."
        ),
        "decay_severe": lambda c: (
            f"{c} posts reference outdated years in their titles. Update the year, refresh "
            "the data, and republish — Google rewards updated content with a ranking boost."
        ),
        "decay_moderate": lambda c: (
            f"{c} time-sensitive posts haven't been updated in 18+ months. Refresh pricing, "
            "statistics, and recommendations to maintain accuracy and rankings."
        ),
        "decay_mild": lambda c: (
            f"{c} posts haven't been updated in 18+ months. Audit for outdated information, "
            "add recent examples, and update the publish date to signal freshness."
        ),
        "thin_content": lambda c: (
            f"{c} posts fall below the minimum word count for their content type. "
            "Expand with examples, data, and actionable advice to provide real value."
        ),
        "thin_below_cluster_avg": lambda c: (
            f"{c} posts are significantly shorter than their topic cluster average. "
            "These underperform peers — expand to match cluster depth or merge with related content."
        ),
        "orphan": lambda c: (
            f"{c} posts have zero inbound internal links — invisible to users browsing your site. "
            "Add contextual links from related pillar content to surface these pages."
        ),
        "readability_too_complex": lambda c: (
            f"{c} posts score below the readability threshold. Shorten sentences, "
            "replace jargon with plain language, and break up long paragraphs."
        ),
        "velocity_decline": lambda _: (
            "Publishing velocity has declined significantly. Resume consistent publishing "
            "(3+ posts/week) to maintain organic traffic momentum."
        ),
    }
    lines.append("### Generated Problem Text (Top 3)")
    lines.append("")
    for rank, (ptype, info) in enumerate(sorted_types[:3], 1):
        template = pdf_text_templates.get(ptype)
        if template:
            text = template(info["count"])
            section = pdf_sections.get(ptype, "30-Day Plan")
            lines.append(f"**{rank}. {ptype}** ({section}):")
            lines.append(f"> {text}")
            lines.append("")
    lines.append("")

    # S6-12: Cross-reference problems with health scores (simulated)
    # Compute simplified composite score for each post (crawl-only proxy)
    # Factors: freshness (40%), content depth (30%), structure (30%)
    now_dt = datetime.now(UTC)
    post_composites: dict[int, float] = {}
    for i, p in enumerate(posts):
        # Freshness: 0-100 based on age
        last_update = p.modified_date or p.publish_date
        if last_update:
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=UTC)
            age_days = (now_dt - last_update).days
            freshness = max(0, 100 - age_days / 30)
        else:
            freshness = 20
        # Content depth: 0-100 based on word count
        wc = p.word_count or 0
        depth = min(100, wc / 30)
        # Structure: 0-100 based on headings + meta
        has_h = 1 if p.headings and len(p.headings) > 0 else 0
        has_meta = 1 if p.meta_description and len(p.meta_description) > 10 else 0
        structure = has_h * 50 + has_meta * 50
        composite = freshness * 0.4 + depth * 0.3 + structure * 0.3
        post_composites[i] = max(10, min(95, composite))

    lines.append("## Problem Density vs Content Metrics")
    lines.append("")
    lines.append("| Problem Count | Posts | Avg Word Count | Avg Has Headings | Avg Composite Score |")
    lines.append("|-------------|-------|---------------|-----------------|-------------------|")
    # Group posts by problem count bucket
    for bucket_lo, bucket_hi, label in [(0, 0, "0 (clean)"), (1, 2, "1-2"), (3, 4, "3-4"), (5, 10, "5+")]:
        bucket_posts = []
        for i, _p in enumerate(posts):
            pc = problems_per_post.get(i, 0)
            if bucket_lo <= pc <= bucket_hi:
                bucket_posts.append(i)
        if not bucket_posts:
            continue
        avg_wc = statistics.mean([posts[i].word_count or 0 for i in bucket_posts])
        has_headings_pct = sum(1 for i in bucket_posts if posts[i].headings and len(posts[i].headings) > 0) / len(bucket_posts) * 100
        avg_composite = statistics.mean([post_composites.get(i, 50) for i in bucket_posts])
        lines.append(f"| {label} | {len(bucket_posts)} | {avg_wc:.0f} | {has_headings_pct:.0f}% | {avg_composite:.1f} |")
    lines.append("")
    lines.append("*Composite is a simplified crawl-only proxy (40% freshness + 30% depth + 30% structure). Production uses 10 weighted factors.*")
    lines.append("")

    # S6-11: first_detected_at preservation note
    lines.append("## first_detected_at Preservation")
    lines.append("")
    lines.append("**Note:** This crawl-only test cannot verify `first_detected_at` preservation because it does not")
    lines.append("use a database. In production, `detect_all()` preserves timestamps by:")
    lines.append("")
    lines.append("1. Reading existing `(post_id, problem_type) -> first_detected_at` from `content_problems`")
    lines.append("2. Storing the map in `self._first_detected_map`")
    lines.append("3. Passing `COALESCE($6, NOW())` in every INSERT with the preserved timestamp")
    lines.append("4. Using `COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)` in ON CONFLICT")
    lines.append("")
    lines.append("**Verification requires:** Two sequential pipeline runs against the same site with a real database.")
    lines.append("The second run should show `first_detected_at` timestamps from the first run for continuing problems.")
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")
    observations = []
    observations.append(f"- **{total_problems} total problems** across {n_posts} posts ({total_problems / n_posts:.1f} avg per post)")
    observations.append(f"- **{clean_posts} clean posts ({clean_posts / n_posts * 100:.1f}%)** have zero detected problems")

    # Most common problem type
    if type_counter:
        most_common_type, most_common_count = type_counter.most_common(1)[0]
        observations.append(f"- **Most common problem:** `{most_common_type}` ({most_common_count} posts, {most_common_count / n_posts * 100:.1f}%)")

    # Orphan rate
    orphan_rate = len(orphan_problems) / n_posts * 100
    if orphan_rate > 30:
        observations.append(f"- **High orphan rate ({orphan_rate:.0f}%)** -- many posts have no inbound internal links. Internal linking strategy needed.")
    elif orphan_rate > 10:
        observations.append(f"- **Moderate orphan rate ({orphan_rate:.0f}%)** -- some posts lack inbound internal links")

    # SEO insights
    if seo_by_type.get("seo_no_headings", 0) > n_posts * 0.2:
        observations.append(f"- **{seo_by_type.get('seo_no_headings', 0)} posts lack H2+ headings** -- older content may predate modern heading best practices")
    if seo_by_type.get("seo_no_images", 0) > n_posts * 0.3:
        observations.append(f"- **{seo_by_type.get('seo_no_images', 0)} posts have no detected images** -- may be trafilatura artifact or genuinely imageless old posts")

    # Readability insight
    if len(readability_problems) > n_posts * 0.3:
        observations.append(f"- **{len(readability_problems)} posts ({len(readability_problems) / n_posts * 100:.0f}%) have poor readability** -- site writes at a high grade level")
    if all_flesch:
        observations.append(f"- **Site-wide readability:** mean Flesch {statistics.mean(all_flesch):.0f}, median {statistics.median(all_flesch):.0f}")

    # Velocity insight
    if velocity.get("status") == "analyzed":
        observations.append(f"- **Publishing velocity:** {velocity['overall_weekly_velocity']} posts/week overall, trend is {velocity['trend']}")

    observations.append(f"- **Detection completed in {total_det_time * 1000:.0f}ms** -- all crawl-based, zero API calls, zero cost")
    observations.append("- Crawl-only mode provides ~70% problem coverage. Adding GA4/GSC would unlock content decay and bounce-rate detection.")

    for obs in observations:
        lines.append(obs)
    lines.append("")

    # Write file
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to {report_path}")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
