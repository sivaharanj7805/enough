"""End-to-end test of Pipeline Step 10: Recommendations.

Runs the template-based recommendation engine against real crawled data
from Copyblogger. Uses crawl-only mode (no database) to validate
template matching, priority assignment, effort estimation, action
generation, cannibalization recommendations, and orphan link suggestions.

Reuses Step 1 crawl, Step 6 clustering, Step 8 cannibalization, and
Step 9 problem detection as prerequisites.
No database required -- tests recommendation logic only.

Code Step mapping:
  Step 1: Crawl → Step 2: Embeddings → Step 3: Readability → Step 4: PageRank
  → Step 5: Intent → Step 6: Clustering → Step 6b: TF-IDF → Step 6c: AI Citability
  → Step 7: Health Scoring → Step 8: Cannibalization → Step 9: Problem Detection
  → **Step 10: Recommendations (this test)**

Recommendation sources tested:
  - Problem-based templates (21 templates for thin/SEO/decay/AI/GEO problems)
  - Cannibalization pair recommendations (redirect/merge/differentiate)
  - Orphan link suggestions (cosine similarity, no pgvector)
  - Deduplication (one rec per post per type)
  - Priority assignment (critical/high/medium/low)
  - Confidence scoring (high/medium/low)
  - Effort estimation (hours per rec type)
"""

import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from itertools import combinations

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
    """Run UMAP+HDBSCAN clustering (same as previous step tests)."""
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
    """Compute Flesch Reading Ease from plain text."""
    sentences = max(1, len(re.split(r'[.!?]+', text.strip())))
    words_list = re.findall(r'[a-zA-Z]+', text)
    n_words = len(words_list)
    if n_words < 30:
        return None

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
    flesch = 206.835 - 1.015 * (n_words / sentences) - 84.6 * (total_syllables / n_words)
    return max(0.0, min(100.0, flesch))


# ═══════════════════════════════════════════════
# Problem detection (reuse from Step 9)
# ═══════════════════════════════════════════════

def detect_thin_content(posts, cluster_groups, post_cluster_map):
    """Detect thin content problems."""
    problems = []
    cluster_avg_wc = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if getattr(posts[i], 'word_count', None)]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if len(wcs) >= 3 else 1000.0

    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
        if wc == 0:
            continue
        url = (getattr(p, 'url', '') or '').lower()
        title = (getattr(p, 'title', '') or '').lower()
        if any(kw in url or kw in title for kw in ["how-to", "guide", "tutorial", "step-by-step"]):
            threshold = 800
        elif any(kw in url or kw in title for kw in ["/glossary", "what-is", "definition"]):
            threshold = 200
        else:
            threshold = 500

        if wc >= threshold:
            continue
        severity = "high" if wc < threshold * 0.5 else "medium"
        content_type = (
            "tutorial" if any(kw in url or kw in title for kw in ["how-to", "guide", "tutorial"]) else
            "glossary" if any(kw in url or kw in title for kw in ["/glossary", "what-is"]) else
            "default"
        )
        problems.append({
            "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
            "url": getattr(p, 'url', ''), "problem_type": "thin_content",
            "severity": severity, "word_count": wc, "threshold": threshold,
            "content_type": content_type,
        })

    # Check 2: Below cluster average
    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
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
                "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''), "problem_type": "thin_below_cluster_avg",
                "severity": "medium", "word_count": wc,
                "cluster_avg": round(avg), "ratio": round(wc / avg, 2),
            })
    return problems


def detect_seo_issues(posts):
    """Detect SEO issues."""
    problems = []
    for i, p in enumerate(posts):
        meta = getattr(p, 'meta_description', '') or ''
        if len(meta.strip()) < 10:
            problems.append({
                "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''), "problem_type": "seo_missing_meta",
                "severity": "medium", "meta_length": len(meta.strip()),
            })

        title = getattr(p, 'title', '') or ''
        title_len = len(title.strip())
        if title_len < 20 or title_len > 70:
            severity = "medium" if title_len < 20 else "low"
            problems.append({
                "post_index": i, "title": title, "url": getattr(p, 'url', ''),
                "problem_type": "seo_title_length", "severity": severity,
                "title_length": title_len,
            })

        headings = getattr(p, 'headings', [])
        if isinstance(headings, str):
            try:
                headings = json.loads(headings)
            except (json.JSONDecodeError, TypeError):
                headings = []
        has_h2_plus = False
        if headings and isinstance(headings, list):
            has_h2_plus = any(
                h.get("level") in ("h2", "h3", "h4")
                for h in headings if isinstance(h, dict)
            )
        if not has_h2_plus:
            problems.append({
                "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''), "problem_type": "seo_no_headings",
                "severity": "medium",
            })

        body_html = getattr(p, 'body_html', '') or ''
        html_lower = body_html.lower()
        is_trafilatura_xml = html_lower.startswith("<doc") or "<doc " in html_lower[:100]
        has_images = is_trafilatura_xml or any(tag in html_lower for tag in [
            '<img', '<picture', '<figure', '<svg', 'data-src=', 'srcset=',
            'background-image:', 'loading="lazy"', "loading='lazy'",
        ])
        if not has_images:
            problems.append({
                "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''), "problem_type": "seo_no_images",
                "severity": "low",
            })
    return problems


def detect_proxy_decay(posts):
    """Detect content decay using proxy signals."""
    now = datetime.now(UTC)
    eighteen_months_ago = now - timedelta(days=548)
    problems = []

    for i, p in enumerate(posts):
        title = getattr(p, 'title', '') or ''
        last_updated = getattr(p, 'modified_date', None) or getattr(p, 'publish_date', None)
        if not last_updated:
            continue
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=UTC)
        if last_updated >= eighteen_months_ago:
            continue

        year_match = re.search(r'((?:19|20)\d{2})', title)
        if year_match:
            ref_year = int(year_match.group(1))
            if 1990 <= ref_year <= now.year and ref_year < now.year - 1:
                problems.append({
                    "post_index": i, "title": title, "url": getattr(p, 'url', ''),
                    "problem_type": "decay_severe", "severity": "high",
                    "signal": "outdated_year_reference", "ref_year": ref_year,
                })
                continue

        if any(kw in title.lower() for kw in ["best ", "top ", "review", "pricing", "compare", "vs "]):
            months_stale = (now - last_updated).days / 30.44
            problems.append({
                "post_index": i, "title": title, "url": getattr(p, 'url', ''),
                "problem_type": "decay_moderate", "severity": "medium",
                "signal": "time_sensitive_stale", "months_stale": round(months_stale, 1),
            })
            continue

        months_stale = (now - last_updated).days / 30.44
        problems.append({
            "post_index": i, "title": title, "url": getattr(p, 'url', ''),
            "problem_type": "decay_mild", "severity": "medium",
            "signal": "general_staleness", "months_stale": round(months_stale, 1),
        })
    return problems


def detect_readability_issues(posts, cluster_labels=None):
    """Detect readability issues."""
    from app.services.industry_benchmarks import detect_industry
    industry = detect_industry(cluster_labels or [], [])
    thresholds = {"saas": 35.0, "agency": 35.0, "ecommerce": 50.0, "media": 55.0, "default": 50.0}
    threshold = thresholds.get(industry, 50.0)
    problems = []

    for i, p in enumerate(posts):
        text = getattr(p, 'body_text', '') or ''
        if len(text.strip()) < 200:
            continue
        flesch = _compute_flesch(text)
        if flesch is None:
            continue
        if flesch < threshold:
            severity = "high" if flesch < 30 else "medium"
            problems.append({
                "post_index": i, "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''), "problem_type": "readability_too_complex",
                "severity": severity, "flesch_score": round(flesch, 1),
                "threshold": threshold,
            })
    return problems, industry, threshold


# ═══════════════════════════════════════════════
# Cannibalization detection (from Step 8)
# ═══════════════════════════════════════════════

_BLENDED_STOP_WORDS = frozenset({
    "the", "a", "an", "to", "of", "for", "in", "on", "and", "or", "is", "it",
    "that", "this", "your", "how", "what", "why", "you", "with", "by", "from",
    "are", "its", "can", "at", "but", "be", "do", "get",
})

_BLENDED_FORMAT_WORDS = frozenset({
    "guide", "complete", "definitive", "ultimate", "simple", "step",
    "review", "tips", "strategies", "examples", "tools", "best", "free",
    "tutorial", "comparison", "alternative", "alternatives", "report",
    "statistics", "stats", "study", "hub",
})

_BLENDED_INTENT_GROUPS = {
    "learning": {"guide", "how", "tutorial", "strategies", "tips", "techniques",
                 "ways", "steps", "explained", "introduction", "basics",
                 "beginners", "learn", "definitive", "complete", "ultimate"},
    "browsing": {"examples", "templates", "inspiration", "ideas", "samples",
                 "list", "collection", "roundup", "showcase"},
    "evaluation": {"review", "comparison", "versus", "alternative", "alternatives",
                   "pricing", "pros", "cons", "worth"},
    "research": {"statistics", "stats", "report", "study", "data", "survey",
                 "analyzed", "analysis", "research", "findings"},
    "shopping": {"tools", "software", "resources", "platforms", "services",
                 "products", "apps", "picks", "recommendations"},
}


def _extract_slug_core_e2e(url: str) -> set[str]:
    """Extract core topic keywords from URL slug."""
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1] if "/" in path else path
    words = set(re.findall(r"[a-z]{3,}", slug.lower()))
    return words - _BLENDED_STOP_WORDS - _BLENDED_FORMAT_WORDS


def _extract_title_entity_e2e(title: str) -> str | None:
    """Extract topic entity from title by stripping format markers."""
    t = title.lower().strip()
    # "X Review" / "X vs Y"
    m = re.match(r"^(.+?)\s+(review|vs\.?|versus|comparison)", t)
    if m:
        entity = re.sub(r"^(the|a|an)\s+", "", m.group(1).strip().rstrip(":"))
        return entity if len(entity) >= 2 else None
    # "Topic: The Definitive Guide" etc.
    m = re.search(r":\s*(?:the|a)?\s*(?:definitive|complete|comprehensive|ultimate)\s+guide", t)
    if m:
        entity = re.sub(r"^(the|a|an)\s+", "", t[:m.start()].strip().rstrip(":"))
        return entity if len(entity) >= 2 else None
    # "How to X" / "N Ways to X"
    m = re.match(r"^(?:how\s+to\s+|\d+\s+(?:ways?|tips?|steps?)\s+(?:to|of|for)\s+)", t)
    if m:
        remainder = re.sub(r"\s*[-–|:].+$", "", t[m.end():].strip())
        if len(remainder) >= 3:
            return " ".join(remainder.split()[:4])
    return None


def _classify_intent_e2e(title: str, url: str) -> str | None:
    """Classify search intent group from title + URL."""
    combined = f"{title} {url}".lower()
    words = set(re.findall(r"[a-z]{3,}", combined))
    best_group, best_overlap = None, 0
    for group, keywords in _BLENDED_INTENT_GROUPS.items():
        overlap = len(words & keywords)
        if overlap > best_overlap:
            best_overlap = overlap
            best_group = group
    return best_group if best_overlap >= 1 else None


def _h2_jaccard_e2e(headings_a: list, headings_b: list) -> float:
    """Compute Jaccard similarity on H2 heading keywords."""
    def _kw_set(headings):
        words = set()
        for h in headings:
            text = (h.get("text", "") if isinstance(h, dict) else str(h)).lower().strip()
            if text:
                words.update(w for w in re.findall(r"[a-z]{3,}", text) if w not in _BLENDED_STOP_WORDS)
        return words
    kw_a, kw_b = _kw_set(headings_a), _kw_set(headings_b)
    if not kw_a or not kw_b:
        return 0.0
    return len(kw_a & kw_b) / len(kw_a | kw_b)


def _title_topic_overlap_e2e(title_a: str, title_b: str) -> float:
    """Compute topic-word Jaccard between titles, ignoring format words."""
    def _topic_words(title):
        t = re.sub(r"\s*[-–|:].{0,30}$", "", title.lower())
        t = re.sub(r"^\d+\s+", "", t)
        words = set(re.findall(r"[a-z]{3,}", t))
        return words - _BLENDED_STOP_WORDS - _BLENDED_FORMAT_WORDS
    a, b = _topic_words(title_a), _topic_words(title_b)
    if not a or not b:
        return 0.3
    return len(a & b) / len(a | b)


def _compute_blended_score_e2e(
    title_a: str, title_b: str,
    url_a: str, url_b: str,
    headings_a: list, headings_b: list,
    cosine_sim: float,
) -> tuple[float, str]:
    """Compute blended cannibalization score mirroring production.

    Weights: cosine 15%, slug 20%, entity+intent 25%, title topic 20%, H2 Jaccard 20%.
    Returns (blended_score, severity_tier).
    """
    # Signal 1: Cosine (15%)
    cosine_component = min(cosine_sim, 1.0)

    # Signal 2: Slug overlap (20%)
    slug_a = _extract_slug_core_e2e(url_a)
    slug_b = _extract_slug_core_e2e(url_b)
    slug_overlap = len(slug_a & slug_b) / len(slug_a | slug_b) if (slug_a and slug_b and (slug_a | slug_b)) else 0.0

    # Signal 3: Entity + intent match (25%)
    entity_a = _extract_title_entity_e2e(title_a)
    entity_b = _extract_title_entity_e2e(title_b)
    entities_different = False
    if entity_a and entity_b:
        if entity_a == entity_b:
            entity_match = 1.0
        else:
            words_a = set(entity_a.split())
            words_b = set(entity_b.split())
            if len(words_a) >= 2 or len(words_b) >= 2:
                word_ov = len(words_a & words_b) / len(words_a | words_b) if (words_a | words_b) else 0.0
                entity_match = word_ov if word_ov >= 0.2 else 0.0
                entities_different = word_ov < 0.2
            else:
                entity_match = 0.0
                entities_different = True
    elif entity_a or entity_b:
        entity_match = 0.2
    else:
        entity_match = 0.0

    intent_a = _classify_intent_e2e(title_a, url_a)
    intent_b = _classify_intent_e2e(title_b, url_b)
    if entities_different:
        intent_match = 0.0
    elif intent_a and intent_b:
        intent_match = 1.0 if intent_a == intent_b else 0.3
    else:
        intent_match = 0.5
    entity_intent_score = entity_match * 0.6 + intent_match * 0.4

    # Signal 4: Title topic overlap (20%)
    title_topic = _title_topic_overlap_e2e(title_a, title_b)

    # Signal 5: H2 Jaccard (20%)
    h2_jaccard = _h2_jaccard_e2e(headings_a, headings_b)

    blended = (
        0.15 * cosine_component
        + 0.20 * slug_overlap
        + 0.25 * entity_intent_score
        + 0.20 * title_topic
        + 0.20 * h2_jaccard
    )

    if blended > 0.80:
        tier = "critical"
    elif blended > 0.55:
        tier = "high"
    elif blended > 0.35:
        tier = "medium"
    else:
        tier = "low"
    return blended, tier


def _recommend_resolution_e2e(
    cosine_sim_val: float,
    severity: str,
    title_a: str,
    title_b: str,
    headings_a: list,
    headings_b: list,
    url_a: str,
    url_b: str,
) -> str:
    """Signal-aware resolution logic mirroring Step 8's _recommend_resolution."""
    if cosine_sim_val >= 0.95:
        return "redirect"

    # H2 subtopic overlap
    h2_jaccard = _h2_jaccard_e2e(headings_a, headings_b)
    if h2_jaccard > 0.7:
        return "merge"

    # Slug overlap
    slug_a = _extract_slug_core_e2e(url_a)
    slug_b = _extract_slug_core_e2e(url_b)
    slug_ov = len(slug_a & slug_b) / len(slug_a | slug_b) if (slug_a and slug_b and (slug_a | slug_b)) else 0.0
    if slug_ov > 0.6:
        return "differentiate"

    # Intent mismatch
    intent_a = _classify_intent_e2e(title_a, url_a)
    intent_b = _classify_intent_e2e(title_b, url_b)
    if intent_a and intent_b and intent_a != intent_b:
        return "differentiate"

    # Title topic overlap
    title_topic = _title_topic_overlap_e2e(title_a, title_b)
    if title_topic > 0.8 and cosine_sim_val < 0.7:
        return "differentiate"

    if severity == "critical" or cosine_sim_val >= 0.85:
        return "merge"
    return "monitor"


def detect_cannibalization(posts, embeddings, cluster_groups, post_cluster_map):
    """Detect cannibalization pairs using blended scoring (mirrors Step 8).

    Uses the same 5-signal blended scoring as production:
    cosine (15%), slug overlap (20%), entity+intent (25%),
    title topic (20%), H2 Jaccard (20%).

    Filters out "low" tier pairs (blended <= 0.35) to match production behavior.
    """
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim

    COSINE_THRESHOLD = 0.45  # Initial cosine gate (same as production)
    pairs = []

    for cl_id, indices in cluster_groups.items():
        if len(indices) < 2:
            continue

        cl_embeddings = embeddings[indices]
        sim_matrix = cos_sim(cl_embeddings)

        for a_local, b_local in combinations(range(len(indices)), 2):
            cos_val = float(sim_matrix[a_local, b_local])
            if cos_val < COSINE_THRESHOLD:
                continue

            a_idx = indices[a_local]
            b_idx = indices[b_local]
            post_a = posts[a_idx]
            post_b = posts[b_idx]

            title_a = getattr(post_a, 'title', '') or ''
            title_b = getattr(post_b, 'title', '') or ''
            url_a = getattr(post_a, 'url', '') or ''
            url_b = getattr(post_b, 'url', '') or ''
            headings_a = getattr(post_a, 'headings', []) or []
            headings_b = getattr(post_b, 'headings', []) or []
            wc_a = getattr(post_a, 'word_count', 0) or 0
            wc_b = getattr(post_b, 'word_count', 0) or 0

            # Compute blended score (mirrors production compute_blended_cannibalization_score)
            blended_score, blended_tier = _compute_blended_score_e2e(
                title_a, title_b, url_a, url_b,
                headings_a, headings_b, cos_val,
            )

            # Filter out "low" tier — content series, not cannibalization
            if blended_tier == "low":
                continue

            severity = blended_tier

            # Compute resolution using blended signals (like production Step 8)
            resolution = _recommend_resolution_e2e(
                cos_val, severity,
                title_a, title_b,
                headings_a, headings_b,
                url_a, url_b,
            )

            # Determine stronger post
            stronger_idx = a_idx if wc_a >= wc_b else b_idx

            pairs.append({
                "post_a_idx": a_idx,
                "post_b_idx": b_idx,
                "title_a": title_a,
                "title_b": title_b,
                "url_a": url_a,
                "url_b": url_b,
                "wc_a": wc_a,
                "wc_b": wc_b,
                "cosine_similarity": round(cos_val, 3),
                "blended_score": round(blended_score, 3),
                "severity": severity,
                "cluster_id": cl_id,
                "resolution": resolution,
                "stronger_idx": stronger_idx,
            })

    pairs.sort(key=lambda x: -x["blended_score"])
    seen = set()
    deduped = []
    for p in pairs:
        key = (min(p["post_a_idx"], p["post_b_idx"]), max(p["post_a_idx"], p["post_b_idx"]))
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped


# ═══════════════════════════════════════════════
# Orphan detection
# ═══════════════════════════════════════════════

def detect_orphans(posts):
    """Detect orphan posts with no inbound internal links."""
    url_to_idx = {getattr(p, 'url', ''): i for i, p in enumerate(posts)}
    inbound_counts = {i: 0 for i in range(len(posts))}

    for i, p in enumerate(posts):
        for link in getattr(p, 'internal_links', []):
            target_url = getattr(link, 'target_url', None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1

    orphans = []
    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
        if wc < 200:
            continue
        if inbound_counts[i] == 0:
            orphans.append({
                "post_index": i,
                "title": getattr(p, 'title', '') or "(no title)",
                "url": getattr(p, 'url', ''),
                "word_count": wc,
            })
    return orphans


# ═══════════════════════════════════════════════
# Recommendation generation (mirrors fast_recommendations.py)
# ═══════════════════════════════════════════════


def _format_staleness(months: float | int, fallback: str = "a long time") -> str:
    """Format months_stale into human-readable staleness text."""
    m = int(months) if months else 0
    if m <= 0:
        return fallback
    if m >= 24:
        years = m / 12
        return f"{years:.1f} years" if years != int(years) else f"{int(years)} years"
    return f"{m} months"


_TEMPLATES = {
    "thin_content": {
        "recommendation_type": "expand",
        "title_tpl": "Expand thin content: {title}",
        "summary_tpl": "This post has {word_count} words, which is below the {threshold}-word threshold for {content_type} content. Expand to at least {target_words} words to match cluster average.",
        "actions_tpl": [
            "Add {words_needed}+ words of substantive content",
            "Research what top-ranking competitors cover that this post doesn't",
            "Add practical examples, case studies, or data points",
            "Consider adding an FAQ section addressing related questions",
        ],
        "effort_hours": 2.0,
        "priority_fn": lambda d: "high" if d.get("word_count", 0) < 300 else "medium",
    },
    "thin_below_cluster_avg": {
        "recommendation_type": "expand",
        "title_tpl": "Expand to match cluster depth: {title}",
        "summary_tpl": "At {word_count} words, this post is significantly below the cluster average of {cluster_avg} words. Posts below cluster average tend to underperform in rankings.",
        "actions_tpl": [
            "Expand by {words_needed}+ words to reach cluster average ({cluster_avg} words)",
            "Study the top 3 posts in this cluster for section ideas",
            "Add depth on subtopics your competitors cover",
        ],
        "effort_hours": 1.5,
        "priority_fn": lambda d: "medium" if d.get("word_count", 0) > 500 else "high",
    },
    "seo_title_length": {
        "recommendation_type": "optimize",
        "title_tpl": "Fix title length: {title}",
        "summary_fn": lambda d: (
            f"Title is only {d['title_length']} characters (recommended: 30-60). "
            "Short titles miss keyword opportunities and look sparse in search results."
            if d.get("title_length", 50) < 30
            else f"Title is {d['title_length']} characters (recommended: 30-60). "
            "Titles over 60 characters get truncated in Google search results."
        ),
        "actions_fn": lambda d: (
            [
                f"Expand title from {d['title_length']} to 30-60 characters",
                "Add the primary keyword and a descriptive modifier",
                "Include the content type (Recipe, Guide, How-To) if not already present",
            ]
            if d.get("title_length", 50) < 30
            else [
                f"Shorten title from {d['title_length']} to under 60 characters",
                "Front-load the primary keyword in the first 40 characters",
                "Remove filler words unless they add value",
            ]
        ),
        "effort_hours": 0.25,
        "priority_fn": lambda d: "low",
    },
    "seo_missing_meta": {
        "recommendation_type": "optimize",
        "title_tpl": "Add meta description: {title}",
        "summary_tpl": "This post has no meta description. Google will auto-generate one, which is often suboptimal for CTR.",
        "actions_tpl": [
            "Write a 150-160 character meta description",
            "Include the primary keyword naturally",
            "Add a compelling reason to click (number, benefit, or question)",
            "Match search intent",
        ],
        "effort_hours": 0.25,
        "priority_fn": lambda d: "medium",
    },
    "seo_no_images": {
        "recommendation_type": "optimize",
        "title_tpl": "Add visual content: {title}",
        "summary_tpl": "No images detected. Posts with relevant images get 94% more views than text-only content.",
        "actions_tpl": [
            "Add at least 1 relevant image per 300 words",
            "Include descriptive alt text with target keywords",
            "Consider diagrams, screenshots, or hero images",
            "Use WebP format for faster loading",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "low",
    },
    "readability_too_complex": {
        "recommendation_type": "optimize",
        "title_tpl": "Improve readability: {title}",
        "summary_tpl": "Flesch readability score of {readability_score:.0f} is below the industry threshold of {threshold}. Complex writing reduces engagement.",
        "actions_tpl": [
            "Break long sentences (>25 words) into shorter ones",
            "Replace jargon with simpler alternatives",
            "Add subheadings every 2-3 paragraphs",
            "Use bullet points for lists of 3+ items",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "medium",
    },
    "orphan": {
        "recommendation_type": "interlink",
        "title_tpl": "Fix orphan page: {title}",
        "summary_tpl": "This post has no internal links pointing to it. Orphan pages get minimal crawl budget.",
        "actions_tpl": [
            "Add links from at least 3 related posts",
            "Link from highest-traffic posts in the same cluster",
            "Use descriptive anchor text (not 'click here')",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "high",
    },
    "decay_severe": {
        "recommendation_type": "update",
        "title_tpl": "Urgent: update decaying content: {title}",
        "summary_fn": lambda d: (
            f"This post hasn't been updated in {_format_staleness(d.get('months_stale', 0), 'over 12 months')} "
            "and is losing rankings. Stale content faces a double penalty: lower rankings AND AI systems stop citing it."
        ),
        "actions_tpl": [
            "Update all statistics and examples to current year",
            "Add a visible 'Last updated' timestamp",
            "Refresh the introduction with a TL;DR answer",
            "Add an FAQ section with 3-5 current questions",
            "Update dateModified in Article JSON-LD schema",
            "Fix any broken or outdated external links",
        ],
        "effort_hours": 2.0,
        "priority_fn": lambda d: "high",
    },
    "decay_moderate": {
        "recommendation_type": "update",
        "title_tpl": "Refresh stale content: {title}",
        "summary_fn": lambda d: (
            f"This post hasn't been updated in {_format_staleness(d.get('months_stale', 0), 'over 6 months')}. "
            "AI citation risk: AI systems actively replace older sources with fresher competitors."
        ),
        "actions_tpl": [
            "Update the 'Last updated' date after substantive edits",
            "Refresh statistics older than 6 months",
            "Add 1-2 new insights or data points",
            "Check the opening still answers the primary query",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "medium",
    },
    "decay_mild": {
        "recommendation_type": "refresh",
        "title_tpl": "Consider refreshing older content: {title}",
        "summary_fn": lambda d: (
            f"This post hasn't been updated in {_format_staleness(d.get('months_stale', 0), 'over 18 months')}. "
            "Periodic content refreshes maintain relevance and prevent gradual ranking decay."
        ),
        "actions_tpl": [
            "Update the published/modified date after making substantive edits",
            "Check for outdated references, broken links, or stale examples",
            "Add a recent example, statistic, or data point",
            "Verify all external links still work",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "low",
    },
    "seo_no_headings": {
        "recommendation_type": "optimize",
        "title_tpl": "Add heading structure: {title}",
        "summary_tpl": "This post lacks H2+ heading structure. Headings improve scannability, SEO, and AI extraction.",
        "actions_tpl": [
            "Add 3-5 descriptive H2 headings summarizing each section",
            "Use H3s for subsections within longer H2 blocks",
            "Include target keywords in at least one H2",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "medium",
    },
}

_HIGH_CONF_TYPES = {"thin_content", "seo_missing_meta", "orphan", "missing_schema",
                     "seo_no_images", "seo_title_length", "seo_no_headings"}
_MED_CONF_TYPES = {"readability_too_complex", "thin_below_cluster_avg",
                    "improve_ai_citability", "poor_ai_structure"}


def generate_recommendations(problems, posts, cluster_groups, post_cluster_map):
    """Generate template-based recommendations from problems.

    For problem types affecting >30% of posts, generates one site-level
    summary rec + per-post recs for only the top 10 most impactful posts.
    """
    cluster_avg_wc = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [getattr(posts[i], 'word_count', 0) or 0 for i in indices if getattr(posts[i], 'word_count', None)]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if wcs else 1500

    total_posts = len(posts)
    _AGGREGATION_THRESHOLD = 0.30
    _AGGREGATION_PER_POST_LIMIT = 10

    # Count unique posts per problem type
    ptype_post_counts = Counter()
    _seen_pp = set()
    for prob in problems:
        _k = (prob["problem_type"], prob["post_index"])
        if _k not in _seen_pp:
            _seen_pp.add(_k)
            ptype_post_counts[prob["problem_type"]] += 1

    aggregated_types = set()
    aggregated_counts = {}
    aggregated_per_post_count = {}
    for ptype, count in ptype_post_counts.items():
        if count / total_posts > _AGGREGATION_THRESHOLD:
            aggregated_types.add(ptype)
            aggregated_counts[ptype] = count
            aggregated_per_post_count[ptype] = 0

    recs = []
    seen_post_types = set()

    for prob in problems:
        ptype = prob["problem_type"]
        post_idx = prob["post_index"]

        key = (post_idx, ptype)
        if key in seen_post_types:
            continue
        seen_post_types.add(key)

        template = _TEMPLATES.get(ptype)
        if not template:
            continue

        # For aggregated types, only emit per-post recs for top N posts
        if ptype in aggregated_types:
            aggregated_per_post_count[ptype] += 1
            if aggregated_per_post_count[ptype] > _AGGREGATION_PER_POST_LIMIT:
                continue

        cl_id = post_cluster_map.get(post_idx)
        cluster_avg = int(cluster_avg_wc.get(cl_id, 1500)) if cl_id is not None else 1500
        word_count = prob.get("word_count", getattr(posts[post_idx], 'word_count', 0) or 0)
        title = prob.get("title", "(no title)")

        ctx = {
            "title": title[:80],
            "word_count": word_count,
            "url": prob.get("url", ""),
            "threshold": prob.get("threshold", 500),
            "content_type": prob.get("content_type", "general"),
            "target_words": max(cluster_avg, prob.get("threshold", 500)),
            "words_needed": max(0, cluster_avg - word_count),
            "cluster_avg": cluster_avg,
            "title_length": len(title),
            "readability_score": prob.get("flesch_score", 0),
            "months_stale": prob.get("months_stale", 0),
        }

        try:
            rec_title = template["title_tpl"].format(**ctx)
            if "summary_fn" in template:
                summary = template["summary_fn"](ctx)
            else:
                summary = template["summary_tpl"].format(**ctx)
            if "actions_fn" in template:
                actions = template["actions_fn"](ctx)
            else:
                actions = [a.format(**ctx) for a in template["actions_tpl"]]
            priority = template["priority_fn"](ctx)
        except (KeyError, ValueError, TypeError) as e:
            print(f"  WARNING: Template error for {ptype} on post {post_idx}: {e}")
            continue

        confidence = (
            "high" if ptype in _HIGH_CONF_TYPES else
            "medium" if ptype in _MED_CONF_TYPES else
            "low"
        )

        recs.append({
            "post_index": post_idx,
            "post_title": title,
            "post_url": prob.get("url", ""),
            "problem_type": ptype,
            "recommendation_type": template["recommendation_type"],
            "priority": priority,
            "effort_hours": template["effort_hours"],
            "estimated_impact": "medium",
            "title": rec_title,
            "summary": summary,
            "actions": actions,
            "confidence": confidence,
            "source": "problem",
        })

    # Site-level summary recs for aggregated problem types
    _type_labels = {
        "seo_no_headings": "lack H2/H3 heading structure",
        "seo_missing_meta": "are missing a meta description",
        "decay_mild": "haven't been updated recently",
        "seo_no_images": "have no images",
        "seo_title_length": "have title length issues",
    }
    for ptype in aggregated_types:
        template = _TEMPLATES.get(ptype)
        if not template:
            continue
        count = aggregated_counts[ptype]
        first_prob = next((p for p in problems if p["problem_type"] == ptype), None)
        if not first_prob:
            continue
        label = _type_labels.get(ptype, f"have the '{ptype}' issue")
        shown = min(_AGGREGATION_PER_POST_LIMIT, count)
        recs.append({
            "post_index": first_prob["post_index"],
            "post_title": first_prob.get("title", ""),
            "post_url": first_prob.get("url", ""),
            "problem_type": ptype,
            "recommendation_type": template["recommendation_type"],
            "priority": "medium",
            "effort_hours": template["effort_hours"] * 2,
            "estimated_impact": "high",
            "title": f"Site-wide: {count} of {total_posts} posts {label}",
            "summary": (
                f"{count} posts ({count * 100 // total_posts}% of your site) {label}. "
                f"The top {shown} most impactful posts have individual recommendations below. "
                f"For the remaining {count - shown}, apply the same fix pattern in bulk."
            ),
            "actions": [
                f"Start with the {shown} individual recommendations for this issue",
                "Use a batch workflow or CMS plugin to fix the remaining posts efficiently",
                "Prioritize your highest-traffic pages first",
                f"Total affected: {count} posts",
            ],
            "confidence": "high",
            "source": "problem",
            "is_aggregated": True,
        })

    return recs


def generate_cannibalization_recs(cann_pairs, posts):
    """Generate recommendations from cannibalization pairs using Step 8's resolution."""
    recs = []
    for pair in cann_pairs:
        cos = pair["cosine_similarity"]
        resolution = pair.get("resolution", "monitor")
        severity = pair.get("severity", "medium")
        stronger_idx = pair.get("stronger_idx")

        # Skip 'monitor' pairs — low severity, not actionable
        if resolution == "monitor":
            continue

        # Determine stronger/weaker using Step 8's computation
        if stronger_idx == pair["post_b_idx"]:
            keep_title, keep_url = pair["title_b"], pair["url_b"]
            weak_title, weak_url = pair["title_a"], pair["url_a"]
        else:
            keep_title, keep_url = pair["title_a"], pair["url_a"]
            weak_title, weak_url = pair["title_b"], pair["url_b"]

        if resolution == "redirect":
            rec_type = "merge"
            title = f"Redirect duplicate: {weak_title[:50]}"
            summary = f"Near-identical posts (cosine={cos:.3f}, severity={severity}). 301 redirect the weaker post."
            actions = [
                f"301 redirect {weak_url} -> {keep_url}",
                "Merge any unique content from the redirected post",
                "Update internal links pointing to the old URL",
            ]
            priority = "critical"
            effort = 0.5
        elif resolution == "merge":
            rec_type = "merge"
            title = f"Merge overlapping content: {keep_title[:50]}"
            summary = f"Same subtopics covered (cosine={cos:.3f}, severity={severity}). Combine into stronger post."
            actions = [
                "Compare both posts section by section",
                f"Move unique content from '{weak_title[:40]}' into '{keep_title[:40]}'",
                "301 redirect the merged post",
                "Update internal links",
            ]
            priority = "high"
            effort = 2.0
        else:  # differentiate
            rec_type = "differentiate"
            title = f"Differentiate competing content: {pair['title_a'][:50]}"
            summary = f"Similar keywords (cosine={cos:.3f}, severity={severity}). Refocus each on a distinct angle."
            actions = [
                "Identify the unique angle for each post",
                "Adjust titles and H1s to target different keyword variants",
                "Cross-link between the two posts",
                "Consider making one 'beginner' and the other 'advanced'",
            ]
            priority = severity  # Use Step 8's severity as priority
            effort = 1.5

        confidence = "high" if resolution in ("redirect", "merge") else "medium"

        recs.append({
            "post_index": pair["post_a_idx"],
            "post_title": pair["title_a"],
            "post_url": pair["url_a"],
            "problem_type": "cannibalization",
            "recommendation_type": rec_type,
            "priority": priority,
            "effort_hours": effort,
            "estimated_impact": "high" if resolution in ("redirect", "merge") else "medium",
            "title": title,
            "summary": summary,
            "actions": actions,
            "confidence": confidence,
            "source": "cannibalization",
            "cosine_similarity": cos,
            "resolution": resolution,
            "pair_title_b": pair["title_b"],
            "pair_url_b": pair["url_b"],
        })
    return recs


def generate_orphan_link_recs(orphan_posts, posts, embeddings):
    """Generate link suggestion recommendations for orphan posts.

    Applies minimum similarity threshold (0.20) to prevent nonsensical
    suggestions (negative/near-zero cosine). If <20% of orphans produce
    quality matches, generates a single site-level rec instead.
    """
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim

    _MIN_ORPHAN_SIMILARITY = 0.20

    url_to_idx = {getattr(p, 'url', ''): i for i, p in enumerate(posts)}
    inbound_counts = {i: 0 for i in range(len(posts))}
    for i, p in enumerate(posts):
        for link in getattr(p, 'internal_links', []):
            target_url = getattr(link, 'target_url', None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1

    linked_indices = [i for i, c in inbound_counts.items() if c > 0]
    if not linked_indices:
        return []

    recs = []
    quality_count = 0
    for orphan in orphan_posts[:20]:
        orphan_idx = orphan["post_index"]
        if orphan_idx >= len(embeddings):
            continue
        orphan_emb = embeddings[orphan_idx].reshape(1, -1)
        linked_embs = embeddings[linked_indices]

        similarities = cos_sim(orphan_emb, linked_embs)[0]
        top_k = min(5, len(linked_indices))
        top_idxs = np.argsort(similarities)[-top_k:][::-1]

        link_sources = []
        for idx in top_idxs:
            src_idx = linked_indices[idx]
            sim_val = float(similarities[idx])
            if sim_val >= _MIN_ORPHAN_SIMILARITY:
                link_sources.append({
                    "post_index": src_idx,
                    "title": getattr(posts[src_idx], 'title', '') or '',
                    "url": getattr(posts[src_idx], 'url', ''),
                    "similarity": round(sim_val, 3),
                })

        if not link_sources:
            continue

        quality_count += 1

        source_list = [
            f"Link from \"{s['title'][:55]}\" (similarity: {s['similarity']:.2f})"
            for s in link_sources[:3]
        ]
        actions = [
            "This post has 0 inbound internal links.",
            "Add a contextual link from these relevant posts:",
            *source_list,
            "Use descriptive anchor text, not generic 'click here'.",
        ]

        recs.append({
            "post_index": orphan_idx,
            "post_title": orphan["title"],
            "post_url": orphan["url"],
            "problem_type": "orphan_link",
            "recommendation_type": "interlink",
            "priority": "high",
            "effort_hours": 0.5,
            "estimated_impact": "medium",
            "title": f"Fix orphan: {orphan['title'][:60]}",
            "summary": f"No inbound links. Link from {len(link_sources)} related posts.",
            "actions": actions,
            "confidence": "high",
            "source": "orphan_link",
            "link_sources": link_sources,
        })

    # Quality gate: if <20% of orphans had quality matches, link graph is too sparse
    orphan_count = min(20, len(orphan_posts))
    if orphan_count > 0 and quality_count < orphan_count * 0.20:
        recs.clear()
        recs.append({
            "post_index": orphan_posts[0]["post_index"],
            "post_title": orphan_posts[0]["title"],
            "post_url": orphan_posts[0]["url"],
            "problem_type": "orphan_link",
            "recommendation_type": "interlink",
            "priority": "high",
            "effort_hours": 2.0,
            "estimated_impact": "high",
            "title": f"Internal linking needs attention ({orphan_count} orphan pages)",
            "summary": (
                f"{orphan_count} posts have no inbound internal links, but your link graph "
                f"is too sparse to suggest specific link sources (only {quality_count} had "
                f"semantically similar linked posts). Run a full-depth crawl for per-post suggestions."
            ),
            "actions": [
                f"Run a full site crawl (current: capped at {orphan_count} orphans)",
                "After full crawl, re-run the pipeline for per-post link suggestions",
                "Add links from your pillar/cornerstone content to orphan pages",
                "Use navigation, category pages, and related-posts widgets",
            ],
            "confidence": "high",
            "source": "orphan_link",
        })

    return recs


# ═══════════════════════════════════════════════
# Synthetic cannibalization pair injection
# ═══════════════════════════════════════════════

@dataclass
class FakePost:
    title: str = ""
    url: str = ""
    body_text: str = "Placeholder body text for synthetic test post with enough words to pass filters."
    body_html: str = "<p>Placeholder body text for synthetic test post with enough words to pass filters.</p>"
    meta_description: str = ""
    word_count: int = 1200
    headings: list = field(default_factory=list)
    internal_links: list = field(default_factory=list)
    publish_date: object = None
    modified_date: object = None
    readability_score: float = 65.0
    content_intent: str = "informational"
    language: str = "en"


async def main():
    from app.services.normalizer import (
        _strip_html_from_meta,
        _strip_site_name_from_title,
        filter_nav_links,
        filter_sitewide_headings,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Code Step 10 E2E Test: Recommendations ({TARGET_DOMAIN}) ===\n")

    # ===================================================================
    # PHASE 1: Crawl (Code Step 1 prerequisite)
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

    print("Phase 1: Crawling (Code Step 1 prerequisite)...")
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
    # PHASE 2: Clustering (Code Step 6 prerequisite)
    # ===================================================================
    print("Phase 2: Clustering (Code Step 6 prerequisite)...")
    titles = [p.title or "" for p in posts]
    cluster_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    labels, cluster_groups = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - cluster_start
    n_clusters = len(cluster_groups)
    print(f"  Generated {n_clusters} clusters in {cluster_time:.1f}s")

    post_cluster_map = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    # Generate cluster labels
    from app.services.fast_cluster_labels import _compute_site_stops, _tfidf_label
    cluster_titles_map = {}
    for cl_id, indices in cluster_groups.items():
        cluster_titles_map[cl_id] = [getattr(posts[i], 'title', '') or '' for i in indices]
    all_titles_flat = [getattr(posts[i], 'title', '') or '' for i in range(n_posts)]
    site_stops = _compute_site_stops(all_titles_flat)
    cluster_labels = []
    for cl_id in sorted(cluster_groups.keys()):
        label_tuple = _tfidf_label(cluster_titles_map[cl_id], all_titles_flat, site_stops)
        cluster_labels.append(label_tuple[0])
    print(f"  Cluster labels: {cluster_labels}\n")

    # ===================================================================
    # PHASE 2b: Inject synthetic cannibalization pairs
    # ===================================================================
    print("Phase 2b: Injecting synthetic cannibalization test cases...")
    fake_a = FakePost(
        title="SEO Link Building Guide: The Definitive Resource",
        url="https://copyblogger.com/seo-link-building-guide/",
        headings=[{"text": "What is Link Building", "level": "h2"},
                  {"text": "Best Link Building Strategies", "level": "h2"}],
    )
    fake_b = FakePost(
        title="Link Building Strategies for SEO: A Complete Guide",
        url="https://copyblogger.com/link-building-strategies-seo/",
        headings=[{"text": "Top Link Building Techniques", "level": "h2"},
                  {"text": "Best Link Building Strategies", "level": "h2"}],
    )
    fake_c = FakePost(
        title="17 Content Marketing Tips That Actually Work",
        url="https://copyblogger.com/content-marketing-tips/",
        headings=[{"text": "Create a Content Calendar", "level": "h2"}],
    )
    fake_d = FakePost(
        title="Content Marketing Strategies for B2B Growth",
        url="https://copyblogger.com/content-marketing-strategies/",
        headings=[{"text": "Build a Content Calendar", "level": "h2"}],
    )

    injected_start_idx = len(posts)
    posts.extend([fake_a, fake_b, fake_c, fake_d])
    n_posts = len(posts)

    first_cluster_id = list(cluster_groups.keys())[0]
    base_embedding = embeddings[cluster_groups[first_cluster_id][0]].copy()

    new_embeddings = np.zeros((4, embeddings.shape[1]), dtype=np.float32)
    np.random.seed(999)
    noise1 = np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.05
    new_embeddings[0] = base_embedding + noise1
    new_embeddings[1] = base_embedding + noise1 * 0.3
    noise2 = np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.15
    new_embeddings[2] = base_embedding + noise2
    new_embeddings[3] = base_embedding + noise2 * 0.5 + np.random.randn(embeddings.shape[1]).astype(np.float32) * 0.08
    for i in range(4):
        norm = np.linalg.norm(new_embeddings[i])
        if norm > 0:
            new_embeddings[i] /= norm

    embeddings = np.vstack([embeddings, new_embeddings])
    for offset in range(4):
        idx = injected_start_idx + offset
        labels = np.append(labels, first_cluster_id)
        cluster_groups[first_cluster_id].append(idx)
        post_cluster_map[idx] = first_cluster_id

    cosine_pair1 = float(np.dot(embeddings[injected_start_idx], embeddings[injected_start_idx + 1]))
    cosine_pair2 = float(np.dot(embeddings[injected_start_idx + 2], embeddings[injected_start_idx + 3]))
    print(f"  Injected 4 synthetic posts at indices {injected_start_idx}-{injected_start_idx+3}")
    print(f"  Pair 1 cosine: {cosine_pair1:.3f} (SEO Link Building)")
    print(f"  Pair 2 cosine: {cosine_pair2:.3f} (Content Marketing)")
    print(f"  Total posts: {n_posts}\n")

    # ===================================================================
    # PHASE 3: Problem Detection (Code Step 9 prerequisite)
    # ===================================================================
    print("Phase 3: Problem detection (Code Step 9 prerequisite)...")
    all_problems = []
    det_timings = {}

    t0 = time.time()
    thin_problems = detect_thin_content(posts, cluster_groups, post_cluster_map)
    det_timings["thin_content"] = time.time() - t0
    all_problems.extend(thin_problems)
    print(f"  Thin content: {len(thin_problems)} problems")

    t0 = time.time()
    seo_problems = detect_seo_issues(posts)
    det_timings["seo_issues"] = time.time() - t0
    all_problems.extend(seo_problems)
    print(f"  SEO issues: {len(seo_problems)} problems")

    t0 = time.time()
    decay_problems = detect_proxy_decay(posts)
    det_timings["proxy_decay"] = time.time() - t0
    all_problems.extend(decay_problems)
    print(f"  Proxy decay: {len(decay_problems)} problems")

    t0 = time.time()
    readability_problems, detected_industry, readability_threshold = detect_readability_issues(posts, cluster_labels)
    det_timings["readability"] = time.time() - t0
    all_problems.extend(readability_problems)
    print(f"  Readability: {len(readability_problems)} problems")

    total_problems = len(all_problems)
    print(f"  Total: {total_problems} problems\n")

    # ===================================================================
    # PHASE 4: Cannibalization Detection (Code Step 8 prerequisite)
    # ===================================================================
    print("Phase 4: Cannibalization detection (Code Step 8 prerequisite)...")
    t0 = time.time()
    cann_pairs = detect_cannibalization(posts, embeddings, cluster_groups, post_cluster_map)
    det_timings["cannibalization"] = time.time() - t0
    print(f"  Pairs found: {len(cann_pairs)}")
    for pair in cann_pairs[:5]:
        print(f"    [{pair['severity']}] blended={pair['blended_score']:.3f} cos={pair['cosine_similarity']:.3f}: {pair['title_a'][:35]} vs {pair['title_b'][:35]}")
    print()

    # ===================================================================
    # PHASE 5: Orphan Detection
    # ===================================================================
    print("Phase 5: Orphan detection...")
    t0 = time.time()
    orphan_posts_list = detect_orphans(posts)
    det_timings["orphan_detection"] = time.time() - t0
    print(f"  Orphan posts: {len(orphan_posts_list)}\n")

    # ===================================================================
    # PHASE 6: RECOMMENDATION GENERATION (Code Step 10)
    # ===================================================================
    print("=" * 60)
    print("PHASE 6: RECOMMENDATION GENERATION (Code Step 10)")
    print("=" * 60)
    print()

    # 10a. Problem-based recommendations
    print("10a. Problem-based template recommendations...")
    t0 = time.time()
    problem_recs = generate_recommendations(all_problems, posts, cluster_groups, post_cluster_map)
    rec_timings = {"problem_recs": time.time() - t0}
    print(f"  Generated: {len(problem_recs)} recs from {total_problems} problems")

    rec_by_type = Counter(r["recommendation_type"] for r in problem_recs)
    rec_by_priority = Counter(r["priority"] for r in problem_recs)
    rec_by_confidence = Counter(r["confidence"] for r in problem_recs)
    rec_by_problem = Counter(r["problem_type"] for r in problem_recs)
    print(f"  By type: {dict(rec_by_type)}")
    print(f"  By priority: {dict(rec_by_priority)}")
    print()

    # 10b. Cannibalization recommendations
    print("10b. Cannibalization recommendations...")
    t0 = time.time()
    cann_recs = generate_cannibalization_recs(cann_pairs, posts)
    rec_timings["cann_recs"] = time.time() - t0
    print(f"  Generated: {len(cann_recs)} recs")
    for r in cann_recs[:3]:
        print(f"    [{r['priority']}] {r['recommendation_type']}: {r['title'][:60]}")
    print()

    # 10c. Orphan link suggestions
    print("10c. Orphan link suggestions...")
    t0 = time.time()
    orphan_recs = generate_orphan_link_recs(orphan_posts_list, posts, embeddings)
    rec_timings["orphan_recs"] = time.time() - t0
    print(f"  Generated: {len(orphan_recs)} recs\n")

    all_recs = problem_recs + cann_recs + orphan_recs
    total_recs = len(all_recs)

    # ===================================================================
    # ANALYSIS & REPORT
    # ===================================================================
    print("=" * 60)
    print(f"TOTAL: {total_recs} recommendations")
    print("=" * 60)
    print()

    all_rec_types = Counter(r["recommendation_type"] for r in all_recs)
    all_priorities = Counter(r["priority"] for r in all_recs)
    all_confidences = Counter(r["confidence"] for r in all_recs)
    all_sources = Counter(r["source"] for r in all_recs)

    print("By type:", dict(all_rec_types))
    print("By priority:", dict(all_priorities))
    print("By confidence:", dict(all_confidences))
    print("By source:", dict(all_sources))

    total_effort = sum(r["effort_hours"] for r in all_recs)
    effort_by_priority = {}
    for r in all_recs:
        effort_by_priority[r["priority"]] = effort_by_priority.get(r["priority"], 0) + r["effort_hours"]
    print(f"Total effort: {total_effort:.1f}h")
    print()

    # Template coverage
    problem_types_with_templates = set(_TEMPLATES.keys())
    detected_problem_types = set(p["problem_type"] for p in all_problems)
    untemplated = detected_problem_types - problem_types_with_templates
    if untemplated:
        print(f"Untemplated problem types: {untemplated}")

    # Dedup stats
    dedup_ratio = (1 - len(problem_recs) / total_problems) * 100 if total_problems else 0
    print(f"Dedup: {total_problems} problems -> {len(problem_recs)} recs ({dedup_ratio:.1f}% deduped)")
    print()

    # Cluster density
    cluster_rec_counts = {}
    for r in all_recs:
        cl_id = post_cluster_map.get(r["post_index"])
        if cl_id is not None:
            cluster_rec_counts[cl_id] = cluster_rec_counts.get(cl_id, 0) + 1

    # Recs per post
    recs_per_post = Counter(r["post_index"] for r in all_recs)

    total_rec_time = sum(rec_timings.values())
    print(f"Step 10 time: {total_rec_time*1000:.1f}ms")
    print()

    # Sample recs
    print("Sample recommendations:")
    seen_types = set()
    for r in all_recs:
        rtype = r["recommendation_type"]
        if rtype in seen_types:
            continue
        seen_types.add(rtype)
        print(f"  [{rtype}] {r['title'][:65]} (priority={r['priority']}, effort={r['effort_hours']}h)")
    print()

    # ===================================================================
    # WRITE REPORT
    # ===================================================================
    print("Writing report...")
    report_path = "../STEP10-TEST-RESULTS.md"
    lines = []

    lines.append(f"# Code Step 10 E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Pipeline Step:** Code Step 10 (Spec Step 7) — Recommendations")
    lines.append(f"**Posts analyzed:** {n_posts} (including 4 synthetic cannibalization test posts)")
    lines.append(f"**Clusters:** {n_clusters}")
    lines.append(f"**Problems detected (Step 9):** {total_problems}")
    lines.append(f"**Cannibalization pairs (Step 8):** {len(cann_pairs)}")
    lines.append(f"**Orphan posts:** {len(orphan_posts_list)}")
    lines.append("**Mode:** Crawl-only (no database, no Claude enrichment)")
    lines.append(f"**Prerequisite:** Step 1 crawl ({TARGET_DOMAIN}, {MAX_PAGES} max) + Step 6 clustering (synthetic embeddings) + Step 8 cannibalization + Step 9 problem detection")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 10a. Input Summary
    lines.append("## 10a. Input Summary")
    lines.append("")
    lines.append("### Problems by Type (Input to Recommendation Engine)")
    lines.append("")
    lines.append("| Problem Type | Count | Has Template? |")
    lines.append("|-------------|-------|--------------|")
    all_problem_types = Counter(p["problem_type"] for p in all_problems)
    for ptype, count in all_problem_types.most_common():
        has_tpl = "YES" if ptype in _TEMPLATES else "NO"
        lines.append(f"| `{ptype}` | {count} | {has_tpl} |")
    lines.append(f"| **Total** | **{total_problems}** | **{len(problem_types_with_templates & detected_problem_types)}/{len(detected_problem_types)} covered** |")
    lines.append("")

    lines.append("### Cannibalization Pairs (Input from Step 8)")
    lines.append("")
    if cann_pairs:
        lines.append("| # | Post A | Post B | Blended | Cosine | Severity | Resolution |")
        lines.append("|---|--------|--------|---------|--------|----------|-----------|")
        for i, pair in enumerate(cann_pairs[:10], 1):
            res = pair.get("resolution", "—")
            blended = pair.get("blended_score", 0.0)
            lines.append(f"| {i} | {pair['title_a'][:35]} | {pair['title_b'][:35]} | {blended:.3f} | {pair['cosine_similarity']:.3f} | {pair['severity']} | {res} |")
        if len(cann_pairs) > 10:
            lines.append(f"| ... | | | | | | ({len(cann_pairs) - 10} more) |")
    else:
        lines.append("No cannibalization pairs detected.")
    lines.append("")

    lines.append(f"### Orphan Posts: {len(orphan_posts_list)}")
    lines.append("")

    # 10b. Recommendation Output
    lines.append("## 10b. Recommendation Output")
    lines.append("")
    lines.append("### By Recommendation Type")
    lines.append("")
    lines.append("| Recommendation Type | Count | % of Total | Source |")
    lines.append("|-------------------|-------|-----------|--------|")
    for rtype, count in all_rec_types.most_common():
        pct = count / total_recs * 100
        src_counts = Counter(r["source"] for r in all_recs if r["recommendation_type"] == rtype)
        src = ", ".join(f"{s}" for s, _ in src_counts.most_common())
        lines.append(f"| `{rtype}` | {count} | {pct:.1f}% | {src} |")
    lines.append(f"| **Total** | **{total_recs}** | **100%** | |")
    lines.append("")

    # Priority distribution
    lines.append("### By Priority")
    lines.append("")
    lines.append("| Priority | Count | % of Total | Effort (hrs) | Histogram |")
    lines.append("|----------|-------|-----------|-------------|-----------|")
    for prio in ["critical", "high", "medium", "low"]:
        count = all_priorities.get(prio, 0)
        pct = count / total_recs * 100 if total_recs else 0
        hrs = effort_by_priority.get(prio, 0)
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {prio} | {count} | {pct:.1f}% | {hrs:.1f} | {bar} |")
    lines.append("")

    # Confidence distribution
    lines.append("### By Confidence")
    lines.append("")
    lines.append("| Confidence | Count | % of Total |")
    lines.append("|-----------|-------|-----------|")
    for conf in ["high", "medium", "low"]:
        count = all_confidences.get(conf, 0)
        pct = count / total_recs * 100 if total_recs else 0
        lines.append(f"| {conf} | {count} | {pct:.1f}% |")
    lines.append("")

    # Source breakdown
    lines.append("### By Source")
    lines.append("")
    lines.append("| Source | Count | % of Total |")
    lines.append("|--------|-------|-----------|")
    for src, count in all_sources.most_common():
        pct = count / total_recs * 100
        lines.append(f"| {src} | {count} | {pct:.1f}% |")
    lines.append("")

    # 10c. Effort Estimation
    lines.append("## 10c. Effort Estimation")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total estimated effort | {total_effort:.1f} hours |")
    if total_recs:
        lines.append(f"| Average effort per rec | {total_effort/total_recs:.2f} hours |")
    lines.append(f"| High-priority effort | {effort_by_priority.get('critical', 0) + effort_by_priority.get('high', 0):.1f} hours |")
    lines.append(f"| Medium-priority effort | {effort_by_priority.get('medium', 0):.1f} hours |")
    lines.append(f"| Low-priority effort | {effort_by_priority.get('low', 0):.1f} hours |")
    lines.append("")

    lines.append("### Effort by Recommendation Type")
    lines.append("")
    lines.append("| Rec Type | Count | Effort/Rec | Total Effort |")
    lines.append("|----------|-------|-----------|-------------|")
    effort_by_rectype = {}
    for r in all_recs:
        rt = r["recommendation_type"]
        effort_by_rectype[rt] = effort_by_rectype.get(rt, {"count": 0, "total": 0})
        effort_by_rectype[rt]["count"] += 1
        effort_by_rectype[rt]["total"] += r["effort_hours"]
    for rt, info in sorted(effort_by_rectype.items(), key=lambda x: -x[1]["total"]):
        per_rec = info["total"] / info["count"] if info["count"] else 0
        lines.append(f"| `{rt}` | {info['count']} | {per_rec:.2f}h | {info['total']:.1f}h |")
    lines.append("")

    # 10d. Template Coverage
    lines.append("## 10d. Template Coverage")
    lines.append("")
    lines.append("| Problem Type | Template? | Problems | Recs Generated | Coverage |")
    lines.append("|-------------|----------|---------|---------------|----------|")
    for ptype, count in all_problem_types.most_common():
        has_tpl = "YES" if ptype in _TEMPLATES else "NO"
        recs_gen = rec_by_problem.get(ptype, 0)
        coverage = f"{recs_gen/count*100:.0f}%" if count > 0 else "N/A"
        lines.append(f"| `{ptype}` | {has_tpl} | {count} | {recs_gen} | {coverage} |")
    lines.append("")
    lines.append(f"**Deduplication:** {total_problems} problem instances -> {len(problem_recs)} unique recommendations ({dedup_ratio:.1f}% deduped)")
    lines.append("**Dedup rule:** One recommendation per (post_id, problem_type) pair")
    lines.append("")

    # 10e. Cannibalization Recommendations Detail
    lines.append("## 10e. Cannibalization Recommendations")
    lines.append("")
    if cann_recs:
        cann_by_action = Counter(r["recommendation_type"] for r in cann_recs)
        cann_by_priority = Counter(r["priority"] for r in cann_recs)
        lines.append("### Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total cannibalization recs | {len(cann_recs)} |")
        for action, cnt in cann_by_action.most_common():
            lines.append(f"| Action: {action} | {cnt} |")
        for prio, cnt in cann_by_priority.most_common():
            lines.append(f"| Priority: {prio} | {cnt} |")
        lines.append("")

        lines.append("### Top 30 Cannibalization Recommendations")
        lines.append("")
        lines.append("| # | Action | Priority | Cosine | Post A | Post B | Effort |")
        lines.append("|---|--------|----------|--------|--------|--------|--------|")
        for i, r in enumerate(cann_recs[:30], 1):
            cos = r.get("cosine_similarity", 0)
            lines.append(f"| {i} | {r['recommendation_type']} | {r['priority']} | {cos:.3f} | {r['post_title'][:30]} | {r.get('pair_title_b', '')[:30]} | {r['effort_hours']}h |")
        if len(cann_recs) > 30:
            lines.append(f"| ... | | | | | | ({len(cann_recs) - 30} more) |")
        lines.append("")

        lines.append("### Resolution Logic (Step 8 Blended Scoring)")
        lines.append("")
        lines.append("| Resolution | Action | Priority | Effort | Source |")
        lines.append("|-----------|--------|----------|--------|--------|")
        lines.append("| redirect | 301 redirect weaker -> stronger | critical | 0.5h | cosine >= 0.95 |")
        lines.append("| merge | Merge content, then redirect | high | 2.0h | H2 Jaccard > 0.7 or critical severity |")
        lines.append("| differentiate | Refocus on distinct angles | severity-based | 1.5h | slug/title overlap |")
        lines.append("| monitor | Skip (not actionable) | — | — | low overlap, different intents |")
        cann_resolutions = Counter(r.get("resolution", "unknown") for r in cann_recs)
        if cann_resolutions:
            lines.append("")
            lines.append(f"**Resolution distribution:** {', '.join(f'{k}={v}' for k, v in cann_resolutions.most_common())}")
        total_pairs = len(cann_pairs)
        monitor_count = sum(1 for p in cann_pairs if p.get("resolution") == "monitor")
        if monitor_count:
            lines.append(f"**Filtered out:** {monitor_count} of {total_pairs} pairs had resolution=monitor (skipped)")
    else:
        lines.append("No cannibalization recommendations generated.")
    lines.append("")

    # 10f. Orphan Link Recommendations
    lines.append("## 10f. Orphan Link Recommendations")
    lines.append("")
    if orphan_recs:
        # Check if this is a site-level quality gate rec vs per-post recs
        per_post_orphans = [r for r in orphan_recs if r.get("link_sources")]
        site_level_orphans = [r for r in orphan_recs if not r.get("link_sources")]

        lines.append(f"**Generated:** {len(orphan_recs)} orphan link recommendations")
        lines.append(f"**Per-post recs:** {len(per_post_orphans)} | **Site-level recs:** {len(site_level_orphans)}")
        lines.append(f"**Similarity threshold:** 0.20 minimum (negative/near-zero filtered out)")
        lines.append(f"**Quality gate:** <20% with quality matches triggers site-level fallback")
        lines.append("")

        if site_level_orphans:
            lines.append("### Site-Level Orphan Recommendation")
            lines.append("")
            for r in site_level_orphans:
                lines.append(f"**Title:** {r['title']}")
                lines.append(f"**Summary:** {r['summary'][:200]}")
                lines.append("")
                lines.append("**Actions:**")
                for a in r["actions"]:
                    lines.append(f"- {a}")
                lines.append("")

        if per_post_orphans:
            lines.append("### Per-Post Orphan Recommendations")
            lines.append("")
            lines.append("| # | Orphan Post | Word Count | Link Sources | Top Source Similarity |")
            lines.append("|---|-----------|-----------|-------------|---------------------|")
            for i, r in enumerate(per_post_orphans[:15], 1):
                sources = r.get("link_sources", [])
                top_sim = sources[0]["similarity"] if sources else 0
                wc = next((o["word_count"] for o in orphan_posts_list if o["post_index"] == r["post_index"]), 0)
                lines.append(f"| {i} | {r['post_title'][:45]} | {wc} | {len(sources)} | {top_sim:.3f} |")
            if len(per_post_orphans) > 15:
                lines.append(f"| ... | | | | ({len(per_post_orphans) - 15} more) |")
            lines.append("")

            lines.append("### Sample Link Suggestions (Top 3 Orphans)")
            lines.append("")
            for r in per_post_orphans[:3]:
                lines.append(f"**Orphan:** {r['post_title'][:60]}")
                lines.append("")
                sources = r.get("link_sources", [])
                if sources:
                    lines.append("| Suggested Source | Similarity |")
                    lines.append("|-----------------|-----------|")
                    for s in sources[:5]:
                        lines.append(f"| {s['title'][:50]} | {s['similarity']:.3f} |")
                lines.append("")
    else:
        lines.append("No orphan link recommendations generated (all below similarity threshold).")
    lines.append("")

    # 10g. Per-Cluster Recommendation Density
    lines.append("## 10g. Per-Cluster Recommendation Density")
    lines.append("")
    lines.append("| Cluster | Label | Posts | Recs | Density | Top Rec Types |")
    lines.append("|---------|-------|-------|------|---------|-------------|")
    for cl_id in sorted(cluster_groups.keys()):
        n_cl_posts = len(cluster_groups[cl_id])
        n_cl_recs = cluster_rec_counts.get(cl_id, 0)
        density = n_cl_recs / n_cl_posts if n_cl_posts else 0
        cl_idx = sorted(cluster_groups.keys()).index(cl_id)
        label = cluster_labels[cl_idx] if cl_idx < len(cluster_labels) else "Unknown"
        cl_types = Counter(r["recommendation_type"] for r in all_recs if post_cluster_map.get(r["post_index"]) == cl_id)
        top_types = ", ".join(f"{t}={c}" for t, c in cl_types.most_common(3))
        lines.append(f"| {cl_id} | {label[:25]} | {n_cl_posts} | {n_cl_recs} | {density:.1f} | {top_types} |")
    lines.append("")

    # 10h. Top 10 Most Recommended Posts
    lines.append("## 10h. Top 10 Most Recommended Posts")
    lines.append("")
    lines.append("| # | Post Title | Recs | Priority Mix | Rec Types |")
    lines.append("|---|-----------|------|-------------|----------|")
    for rank, (post_idx, count) in enumerate(recs_per_post.most_common(10), 1):
        title = (getattr(posts[post_idx], 'title', '') or '(no title)')[:45]
        types = sorted(set(r["recommendation_type"] for r in all_recs if r["post_index"] == post_idx))
        priorities = Counter(r["priority"] for r in all_recs if r["post_index"] == post_idx)
        prio_mix = ", ".join(f"{p}={c}" for p, c in priorities.most_common())
        lines.append(f"| {rank} | {title} | {count} | {prio_mix} | {', '.join(types)} |")
    lines.append("")

    # 10i. Sample Recommendations (One Per Type)
    lines.append("## 10i. Sample Recommendations (One Per Type)")
    lines.append("")
    seen_types_report = set()
    for r in all_recs:
        rtype = r["recommendation_type"]
        if rtype in seen_types_report:
            continue
        seen_types_report.add(rtype)
        lines.append(f"### {rtype}")
        lines.append("")
        lines.append(f"**Title:** {r['title'][:80]}")
        lines.append(f"**Priority:** {r['priority']} | **Effort:** {r['effort_hours']}h | **Confidence:** {r['confidence']}")
        lines.append(f"**Summary:** {r['summary'][:200]}")
        lines.append("")
        lines.append("**Actions:**")
        for a in r['actions']:
            lines.append(f"- {a[:100]}")
        lines.append("")

    # Processing Summary
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Sub-step | Recs | Time | External API | Notes |")
    lines.append("|----------|------|------|-------------|-------|")
    lines.append(f"| 10a. Problem-based templates | {len(problem_recs)} | {rec_timings['problem_recs']*1000:.1f}ms | None | {len(_TEMPLATES)} templates |")
    lines.append(f"| 10b. Cannibalization recs | {len(cann_recs)} | {rec_timings['cann_recs']*1000:.1f}ms | None | redirect/merge/differentiate |")
    lines.append(f"| 10c. Orphan link suggestions | {len(orphan_recs)} | {rec_timings['orphan_recs']*1000:.1f}ms | None | cosine similarity |")
    lines.append(f"| 10d. Claude enrichment (Tier 2) | SKIPPED | - | Anthropic API | Crawl-only mode |")
    lines.append(f"| **Total Step 10** | **{total_recs}** | **{total_rec_time*1000:.1f}ms** | **Free** | |")
    lines.append("")

    lines.append("### Prerequisite Timings")
    lines.append("")
    lines.append("| Step | Time | Notes |")
    lines.append("|------|------|-------|")
    lines.append(f"| Crawl (Code Step 1) | {crawl_time:.1f}s | |")
    lines.append(f"| Clustering (Code Step 6) | {cluster_time:.1f}s | |")
    for det, elapsed in sorted(det_timings.items(), key=lambda x: -x[1]):
        lines.append(f"| {det} | {elapsed*1000:.1f}ms | |")
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")
    lines.append(f"- **{total_recs} total recommendations** generated from {total_problems} problems, {len(cann_pairs)} cannibalization pairs, and {len(orphan_posts_list)} orphan posts")
    lines.append(f"- **Template coverage: {len(problem_types_with_templates & detected_problem_types)}/{len(detected_problem_types)} problem types** have matching templates")
    if untemplated:
        lines.append(f"- **Untemplated problem types:** {', '.join(sorted(untemplated))} — these problems are detected but produce no recommendations")
    lines.append(f"- **Deduplication removed {dedup_ratio:.0f}%** of problem->rec mappings (one rec per post per type)")
    lines.append(f"- **Total estimated effort: {total_effort:.0f} hours** ({total_effort/40:.1f} work weeks)")
    high_prio_count = all_priorities.get("critical", 0) + all_priorities.get("high", 0)
    high_prio_effort = effort_by_priority.get("critical", 0) + effort_by_priority.get("high", 0)
    lines.append(f"- **High-priority recs: {high_prio_count}** ({high_prio_effort:.0f} hours) — action first")
    most_common_rec = all_rec_types.most_common(1)[0] if all_rec_types else ("none", 0)
    lines.append(f"- **Most common recommendation type:** `{most_common_rec[0]}` ({most_common_rec[1]} recs)")
    lines.append(f"- **Recommendation generation completed in {total_rec_time*1000:.0f}ms** — zero API calls, zero cost (Tier 1 only)")
    lines.append(f"- **Claude enrichment (Tier 2) skipped** — would add AI-generated strategic advice to top 10 recs for ~$0.02")
    lines.append(f"- Synthetic embeddings produce different cannibalization pairs than real OpenAI embeddings — use results as structural validation only")

    # Data quality notes
    lines.append("")
    lines.append("## Data Quality Notes")
    lines.append("")
    lines.append("| Factor | Impact | Notes |")
    lines.append("|--------|--------|-------|")
    lines.append("| Synthetic embeddings | High | Cannibalization pairs and orphan link suggestions differ from real OpenAI embeddings |")
    lines.append("| No GA4/GSC data | Medium | Cannot detect traffic-based decay or performance-based cannibalization severity |")
    lines.append("| No AI citability scores | Medium | GEO-related templates (low_ai_citability, weak_eeat, etc.) not triggered |")
    lines.append("| No database | Low | Template logic, priority assignment, and effort estimation are identical to production |")
    lines.append("| Crawl-only mode | Low | Problem detection uses same thresholds as production |")
    lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nReport written to {report_path}")
    print(f"Total: {total_recs} recs | Time: {total_rec_time*1000:.1f}ms | Cost: $0")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
