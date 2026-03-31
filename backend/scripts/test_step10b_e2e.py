"""End-to-end test of Pipeline Step 10b: Claude AI Enrichment.

Validates the enrichment pipeline against real crawled data from Copyblogger.
Since this step requires the Anthropic API and a database, the test simulates
the enrichment logic locally:

  - Builds recommendations from Step 7 (template engine)
  - Validates prompt construction for each recommendation type
  - Tests JSON response parsing (valid, markdown-wrapped, malformed)
  - Verifies enriched storage format (ai_enriched flag, original_actions preserved)
  - Validates RAG context formatting
  - Measures prompt token estimates and cost projections
  - Tests priority ordering for auto-enrich selection

No database required. No Claude API calls. Tests logic + structure only.

Code Step mapping:
  Step 1: Crawl → Step 2: Embeddings → Step 3: Readability → Step 4: PageRank
  → Step 5: Intent → Step 6: Clustering → Step 6b: TF-IDF → Step 6c: AI Citability
  → Step 7: Health Scoring → Step 8: Cannibalization → Step 8b: Chunk Confirmation
  → Step 9: Problem Detection → Step 10: Recommendations → **Step 10b: Claude Enrichment**
"""

import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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


# ═══════════════════════════════════════════════
# Problem detection (reuse from previous step tests)
# ═══════════════════════════════════════════════

def detect_problems(posts, cluster_groups, post_cluster_map):
    """Detect problems (simplified, combines thin + SEO + decay)."""
    problems = []

    cluster_avg_wc = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if getattr(posts[i], 'word_count', None)]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if len(wcs) >= 3 else 1000.0

    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
        title = (getattr(p, 'title', '') or '').lower()
        url = (getattr(p, 'url', '') or '').lower()

        # Thin content
        if 0 < wc < 500:
            problems.append({
                "post_index": i, "title": getattr(p, 'title', ''),
                "url": getattr(p, 'url', ''), "problem_type": "thin_content",
                "severity": "high" if wc < 250 else "medium",
                "word_count": wc, "threshold": 500, "content_type": "default",
            })

        # Missing meta
        meta = getattr(p, 'meta_description', '') or ''
        if len(meta.strip()) < 10:
            problems.append({
                "post_index": i, "title": getattr(p, 'title', ''),
                "url": getattr(p, 'url', ''), "problem_type": "seo_missing_meta",
                "severity": "medium",
            })

        # Decay
        last_updated = getattr(p, 'modified_date', None) or getattr(p, 'publish_date', None)
        if last_updated:
            now = datetime.now(UTC)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            months = (now - last_updated).days / 30.44
            year_match = re.search(r'((?:19|20)\d{2})', getattr(p, 'title', '') or '')
            if year_match and int(year_match.group(1)) < now.year - 1:
                problems.append({
                    "post_index": i, "title": getattr(p, 'title', ''),
                    "url": getattr(p, 'url', ''), "problem_type": "decay_severe",
                    "severity": "high",
                })
            elif months > 18:
                problems.append({
                    "post_index": i, "title": getattr(p, 'title', ''),
                    "url": getattr(p, 'url', ''), "problem_type": "decay_moderate",
                    "severity": "medium",
                })

    return problems


def _extract_slug_words(url: str) -> set[str]:
    """Extract meaningful words from URL slug for overlap computation."""
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/").split("/")[-1] if url else ""
    # Split on hyphens/underscores, filter stop words and short tokens
    stops = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "on", "with", "how", "what", "why"}
    words = set(w.lower() for w in re.split(r'[-_]', path) if len(w) > 2 and w.lower() not in stops)
    return words


def _title_word_overlap(title_a: str, title_b: str) -> float:
    """Compute title word overlap (Jaccard) for cannibalization scoring."""
    stops = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "on", "with", "how", "what", "why",
             "your", "you", "that", "this", "are", "was", "be", "have", "has", "it", "not", "do", "can"}
    words_a = set(w.lower() for w in re.split(r'\W+', title_a or '') if len(w) > 2 and w.lower() not in stops)
    words_b = set(w.lower() for w in re.split(r'\W+', title_b or '') if len(w) > 2 and w.lower() not in stops)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _recommend_resolution(cosine_sim: float, severity: str, slug_overlap: float, title_overlap: float) -> str:
    """Recommend resolution for a cannibalization pair (mirrors Step 8 logic)."""
    if cosine_sim >= 0.95:
        return "redirect"
    if slug_overlap > 0.6:
        return "differentiate"
    if title_overlap > 0.8 and cosine_sim < 0.7:
        return "differentiate"
    if severity == "critical" or cosine_sim >= 0.85:
        return "merge"
    if severity == "high" and slug_overlap > 0.3:
        return "merge"
    return "monitor"


def detect_cannibalization(posts, embeddings, cluster_groups):
    """Detect cannibalization pairs using blended scoring (mirrors fixed Step 8).

    Uses cosine similarity + URL slug overlap + title word overlap to compute
    a blended score. Assigns resolution (redirect/merge/differentiate/monitor)
    and filters out 'monitor' pairs as non-actionable.
    """
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim

    pairs = []
    for cl_id, indices in cluster_groups.items():
        if len(indices) < 2:
            continue
        cl_embeddings = embeddings[indices]
        sim_matrix = cos_sim(cl_embeddings)

        for a_local, b_local in combinations(range(len(indices)), 2):
            cos_val = float(sim_matrix[a_local, b_local])
            if cos_val < 0.45:
                continue
            a_idx = indices[a_local]
            b_idx = indices[b_local]

            title_a = getattr(posts[a_idx], 'title', '') or ''
            title_b = getattr(posts[b_idx], 'title', '') or ''
            url_a = getattr(posts[a_idx], 'url', '') or ''
            url_b = getattr(posts[b_idx], 'url', '') or ''

            # Blended scoring (mirrors compute_blended_cannibalization_score)
            slug_a = _extract_slug_words(url_a)
            slug_b = _extract_slug_words(url_b)
            slug_overlap = len(slug_a & slug_b) / len(slug_a | slug_b) if (slug_a | slug_b) else 0.0
            title_overlap = _title_word_overlap(title_a, title_b)

            # Weights: 25% cosine, 25% slug, 30% title, 20% H2 (H2 unavailable in E2E → 0)
            blended = 0.25 * cos_val + 0.25 * slug_overlap + 0.30 * title_overlap + 0.20 * 0.0

            # Severity tiers (from blended score)
            if blended > 0.80:
                severity = "critical"
            elif blended > 0.55:
                severity = "high"
            elif blended > 0.35:
                severity = "medium"
            else:
                continue  # Below threshold — skip (was "low")

            resolution = _recommend_resolution(cos_val, severity, slug_overlap, title_overlap)

            # Filter out "monitor" — not actionable
            if resolution == "monitor":
                continue

            # Determine stronger post by word count (health scores unavailable in E2E)
            wc_a = getattr(posts[a_idx], 'word_count', 0) or 0
            wc_b = getattr(posts[b_idx], 'word_count', 0) or 0
            stronger_idx = a_idx if wc_a >= wc_b else b_idx

            pairs.append({
                "post_a_idx": a_idx, "post_b_idx": b_idx,
                "title_a": title_a, "title_b": title_b,
                "url_a": url_a, "url_b": url_b,
                "wc_a": wc_a, "wc_b": wc_b,
                "cosine_similarity": round(cos_val, 3),
                "blended_score": round(blended, 3),
                "severity": severity,
                "resolution": resolution,
                "slug_overlap": round(slug_overlap, 3),
                "title_overlap": round(title_overlap, 3),
                "stronger_idx": stronger_idx,
                "cluster_id": cl_id,
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
# Recommendation generation (simplified from Step 7)
# ═══════════════════════════════════════════════

@dataclass
class SimulatedRec:
    """Simulated recommendation matching the DB schema."""
    id: str
    post_index: int
    post_title: str
    url: str
    word_count: int
    body_excerpt: str
    recommendation_type: str
    title: str
    summary: str
    specific_actions: list[str]
    priority: str
    estimated_effort_hours: float
    confidence: str = "medium"
    source: str = "problem"
    # For cann recs
    overlapping_title: str = ""
    overlapping_url: str = ""
    overlapping_wc: int = 0
    overlapping_excerpt: str = ""


def generate_recommendations(posts, problems, cann_pairs) -> list[SimulatedRec]:
    """Generate template recommendations (mirrors fast_recommendations.py)."""
    recs: list[SimulatedRec] = []
    rec_counter = 0
    seen_post_type = {}  # Maps dedup keys → rec/True

    # Problem-based recs
    for prob in problems:
        i = prob["post_index"]
        ptype = prob["problem_type"]
        key = (i, ptype)
        if key in seen_post_type:
            continue
        seen_post_type[key] = True

        p = posts[i]
        wc = getattr(p, 'word_count', 0) or 0
        body = (getattr(p, 'body_text', '') or '')[:1500]

        if ptype == "thin_content":
            rec_type, title_tpl, priority = "expand", "Expand thin content: {title}", "high" if wc < 300 else "medium"
            summary = f"This post has {wc} words, below the 500-word threshold."
            actions = ["Add 500+ words of substantive content", "Research competitor coverage", "Add examples and data"]
        elif ptype == "seo_missing_meta":
            rec_type, title_tpl, priority = "optimize", "Add meta description: {title}", "medium"
            summary = "No meta description. Google will auto-generate one."
            actions = ["Write 150-160 char meta description", "Include primary keyword", "Add compelling CTA"]
        elif ptype in ("decay_severe", "decay_moderate"):
            rec_type, title_tpl, priority = "update", "Update outdated content: {title}", "high" if ptype == "decay_severe" else "medium"
            summary = "Content is outdated and may be losing rankings."
            actions = ["Update statistics and references", "Refresh examples", "Check broken links"]
        else:
            rec_type, title_tpl, priority = "optimize", f"Optimize ({ptype}): {{title}}", "medium"
            summary = f"Issue detected: {ptype}"
            actions = ["Review and fix the detected issue"]

        final_title = title_tpl.format(title=(getattr(p, 'title', '') or '(no title)')[:60])

        effort = 2.0 if rec_type == "expand" else 0.5

        # Title-level dedup: merge actions for identical titles on same post
        title_key = (i, final_title)
        if title_key in seen_post_type:
            existing = seen_post_type[title_key]
            existing.specific_actions = existing.specific_actions + [
                a for a in actions if a not in existing.specific_actions
            ]
            existing.estimated_effort_hours = max(existing.estimated_effort_hours, effort)
            continue

        rec_counter += 1
        rec = SimulatedRec(
            id=f"rec-{rec_counter:04d}",
            post_index=i,
            post_title=getattr(p, 'title', '') or "(no title)",
            url=getattr(p, 'url', ''),
            word_count=wc,
            body_excerpt=body,
            recommendation_type=rec_type,
            title=final_title,
            summary=summary,
            specific_actions=actions,
            priority=priority,
            estimated_effort_hours=2.0 if rec_type == "expand" else 0.5,
            source="problem",
        )
        seen_post_type[title_key] = rec
        recs.append(rec)

    # Cann-based recs — use Step 8's resolution field (not raw cosine thresholds)
    for pair in cann_pairs[:50]:  # cap for test
        a_idx = pair["post_a_idx"]
        b_idx = pair["post_b_idx"]
        p_a = posts[a_idx]
        p_b = posts[b_idx]

        resolution = pair.get("resolution", "monitor")
        if resolution == "monitor":
            continue  # Not actionable

        key = (a_idx, resolution)
        if key in seen_post_type:
            continue
        seen_post_type[key] = True

        cos = pair["cosine_similarity"]
        blended = pair.get("blended_score", cos)
        severity = pair.get("severity", "medium")

        # Map resolution → rec type and priority (mirrors fast_recommendations.py)
        if resolution == "redirect":
            rec_type = "merge"
            priority = "high" if severity in ("critical", "high") else "medium"
        elif resolution == "merge":
            rec_type = "merge"
            priority = "high" if severity in ("critical", "high") else "medium"
        elif resolution == "differentiate":
            rec_type = "differentiate"
            priority = "medium"
        else:
            rec_type = "merge"
            priority = "medium"

        # Determine stronger/weaker post
        stronger_idx = pair.get("stronger_idx", a_idx)
        keep_idx = stronger_idx
        weak_idx = b_idx if keep_idx == a_idx else a_idx
        p_keep = posts[keep_idx]
        p_weak = posts[weak_idx]

        rec_counter += 1
        recs.append(SimulatedRec(
            id=f"rec-{rec_counter:04d}",
            post_index=a_idx,
            post_title=getattr(p_a, 'title', '') or "(no title)",
            url=getattr(p_a, 'url', ''),
            word_count=getattr(p_a, 'word_count', 0) or 0,
            body_excerpt=(getattr(p_a, 'body_text', '') or '')[:800],
            recommendation_type=rec_type,
            title=f"{rec_type.title()}: {(getattr(p_a, 'title', '') or '')[:50]}",
            summary=f"Overlaps with '{(getattr(p_b, 'title', '') or '')[:50]}' (blended: {blended}, resolution: {resolution})",
            specific_actions=[
                f"{rec_type.title()} these overlapping posts",
                "Review shared keyword coverage",
                "Consolidate or differentiate content angles",
            ],
            priority=priority,
            estimated_effort_hours=3.0 if rec_type == "merge" else 1.5,
            source="cannibalization",
            overlapping_title=getattr(p_b, 'title', '') or "",
            overlapping_url=getattr(p_b, 'url', '') or "",
            overlapping_wc=getattr(p_b, 'word_count', 0) or 0,
            overlapping_excerpt=(getattr(p_b, 'body_text', '') or '')[:800],
        ))

    # Orphan interlink recs (top 20)
    url_to_idx = {getattr(p, 'url', ''): i for i, p in enumerate(posts)}
    inbound_counts = {i: 0 for i in range(len(posts))}
    for i, p in enumerate(posts):
        for link in getattr(p, 'internal_links', []):
            target_url = getattr(link, 'target_url', None) or (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1

    orphan_count = 0
    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
        if wc < 200 or inbound_counts[i] > 0:
            continue
        key = (i, "interlink")
        if key in seen_post_type:
            continue
        seen_post_type[key] = True
        orphan_count += 1
        if orphan_count > 20:
            break

        rec_counter += 1
        recs.append(SimulatedRec(
            id=f"rec-{rec_counter:04d}",
            post_index=i,
            post_title=getattr(p, 'title', '') or "(no title)",
            url=getattr(p, 'url', ''),
            word_count=wc,
            body_excerpt=(getattr(p, 'body_text', '') or '')[:1500],
            recommendation_type="interlink",
            title=f"Fix orphan page: {(getattr(p, 'title', '') or '')[:50]}",
            summary="No internal links point to this post. Orphan pages get minimal crawl budget.",
            specific_actions=[
                "Add links from at least 3 related posts",
                "Link from highest-traffic posts in same cluster",
                "Use descriptive anchor text",
            ],
            priority="high",
            estimated_effort_hours=0.5,
            source="orphan",
        ))

    return recs


# ═══════════════════════════════════════════════
# Enrichment logic (mirrors on_demand_enrichment.py)
# ═══════════════════════════════════════════════

def _build_prompt(rec_type: str, context: str) -> str:
    """Build enrichment prompt based on recommendation type (exact copy from service)."""
    if rec_type in ("merge", "redirect"):
        return f"""You are a content strategist. Based on these two overlapping blog posts, provide a specific merge plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"merge_plan": "Which post to keep as primary and why (1 sentence)",
"keep_url": "URL of the post to keep",
"redirect_url": "URL to 301 redirect",
"sections_to_merge": ["Specific sections from secondary post to incorporate"],
"estimated_word_count": "Target word count for merged post",
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "differentiate":
        return f"""You are a content strategist. These posts overlap. Provide a specific differentiation plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"differentiation_plan": "How to make these posts distinct (1-2 sentences)",
"post_a_angle": "Specific angle/focus for post A",
"post_b_angle": "Specific angle/focus for post B",
"keywords_post_a": ["3-5 specific target keywords for post A"],
"keywords_post_b": ["3-5 specific target keywords for post B"],
"sections_to_rewrite": ["Specific overlapping sections that need rewriting"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "expand":
        return f"""You are a content strategist. This thin blog post needs expansion. Provide specific guidance.

{context}

Respond with ONLY a JSON object (no markdown):
{{"expansion_plan": "What this post needs (1-2 sentences)",
"sections_to_add": ["3-5 specific new sections with suggested H2 headings"],
"target_word_count": "Recommended final word count",
"content_gaps": ["Specific topics/questions the current post doesn't address"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "optimize":
        return f"""You are an SEO content strategist. This blog post needs optimization.

{context}

Respond with ONLY a JSON object (no markdown):
{{"optimization_plan": "What needs to change (1-2 sentences)",
"title_suggestion": "Improved title or 'Current title is good'",
"meta_description": "Suggested meta description (150-160 chars)",
"content_improvements": ["2-3 specific improvements with details"],
"estimated_impact": "Expected SEO impact"}}"""

    elif rec_type == "interlink":
        return f"""You are a content strategist. This blog post is an orphan with no inbound internal links.

{context}

Respond with ONLY a JSON object (no markdown):
{{"interlink_plan": "Why this post deserves more internal links (1 sentence)",
"suggested_anchor_texts": ["3-5 natural anchor text phrases"],
"likely_linking_posts": ["3-5 post types that should link here"],
"placement_tips": "Where in linking posts the link should be placed",
"estimated_impact": "Expected impact on crawl depth and rankings"}}"""

    else:
        return f"""You are a content strategist. Provide specific, actionable guidance for this recommendation.

{context}

Respond with ONLY a JSON object (no markdown):
{{"action_plan": "Specific steps to implement",
"priority_rationale": "Why this matters",
"estimated_impact": "Expected SEO impact",
"time_estimate": "Estimated implementation time"}}"""


def _smart_excerpt(text: str, max_chars: int = 800) -> str:
    """Extract first half + last half of text (mirrors on_demand_enrichment._smart_excerpt)."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + "\n[...]\n" + text[-half:].lstrip()


def _build_context(rec: SimulatedRec) -> str:
    """Build context string for a recommendation (mirrors enrich_recommendation)."""
    context = (
        f"Post: {rec.post_title}\n"
        f"URL: {rec.url}\n"
        f"Word count: {rec.word_count}\n"
        f"Recommendation: {rec.title}\n"
        f"{rec.summary}"
    )

    # Add simulated RAG context
    rag_text = (
        f"SIMILAR POSTS ON THIS BLOG (by embedding similarity):\n"
        f"  - \"Related Post A\" (https://example.com/a) — 2100 words, health: 75/100, role: support\n"
        f"  - \"Related Post B\" (https://example.com/b) — 1800 words, health: 68/100, role: support\n\n"
        f"CLUSTER BENCHMARKS:\n"
        f"  - Average word count: 1950\n"
        f"  - Average health score: 65.2\n"
        f"  - Post count: 35\n"
        f"  - Cluster label: Content Marketing & Strategy\n"
        f"  - Ecosystem state: forest"
    )
    context += f"\n\nBLOG CONTEXT (from this site's own data):\n{rag_text}"

    # Cann recs get overlapping post context with smart excerpts
    if rec.recommendation_type in ("merge", "differentiate", "redirect") and rec.overlapping_title:
        excerpt_a = _smart_excerpt(rec.body_excerpt, 800)
        excerpt_b = _smart_excerpt(rec.overlapping_excerpt, 800)
        context += (
            f"\n\nOverlapping post: {rec.overlapping_title}\nURL: {rec.overlapping_url}\n"
            f"Word count: {rec.overlapping_wc}\n\n"
            f"Post A excerpt:\n{excerpt_a}\n\n"
            f"Post B excerpt:\n{excerpt_b}"
        )
    else:
        context += f"\n\nContent excerpt:\n{rec.body_excerpt[:1500]}"

    return context


def _parse_claude_response(response_text: str) -> dict:
    """Parse Claude response, stripping markdown fences if present."""
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": text}


def _build_enriched_actions(enrichment: dict, original_actions: list[str]) -> dict:
    """Build the enriched actions storage format."""
    return {
        "ai_enriched": True,
        "ai_guidance": enrichment,
        "original_actions": original_actions if isinstance(original_actions, list) else [],
    }


# Expected JSON fields per recommendation type
EXPECTED_FIELDS = {
    "merge": ["merge_plan", "keep_url", "redirect_url", "sections_to_merge", "estimated_word_count", "estimated_impact"],
    "redirect": ["merge_plan", "keep_url", "redirect_url", "sections_to_merge", "estimated_word_count", "estimated_impact"],
    "differentiate": ["differentiation_plan", "post_a_angle", "post_b_angle", "keywords_post_a", "keywords_post_b", "sections_to_rewrite", "estimated_impact"],
    "expand": ["expansion_plan", "sections_to_add", "target_word_count", "content_gaps", "estimated_impact"],
    "optimize": ["optimization_plan", "title_suggestion", "meta_description", "content_improvements", "estimated_impact"],
    "interlink": ["interlink_plan", "suggested_anchor_texts", "likely_linking_posts", "placement_tips", "estimated_impact"],
    "update": ["action_plan", "priority_rationale", "estimated_impact", "time_estimate"],
}

# Simulated Claude responses for each rec type (valid JSON)
SIMULATED_RESPONSES = {
    "merge": json.dumps({
        "merge_plan": "Keep the longer, more comprehensive post as primary and 301 redirect the shorter one.",
        "keep_url": "https://copyblogger.com/content-marketing-guide",
        "redirect_url": "https://copyblogger.com/content-marketing-tips",
        "sections_to_merge": ["Email list building section", "ROI measurement framework", "Case study from 2024"],
        "estimated_word_count": "3500",
        "estimated_impact": "High — consolidating link equity from two competing pages should boost rankings for 'content marketing' queries",
    }),
    "redirect": json.dumps({
        "merge_plan": "Redirect the thin, outdated post to the comprehensive guide.",
        "keep_url": "https://copyblogger.com/seo-link-building-guide",
        "redirect_url": "https://copyblogger.com/link-building-strategies",
        "sections_to_merge": ["Unique outreach templates", "Success metrics section"],
        "estimated_word_count": "4000",
        "estimated_impact": "High — link equity consolidation for competitive 'link building' terms",
    }),
    "differentiate": json.dumps({
        "differentiation_plan": "Post A should focus on tactical how-to steps, while Post B should cover strategic planning.",
        "post_a_angle": "Step-by-step link building tactics for beginners",
        "post_b_angle": "Strategic link building campaign planning for agencies",
        "keywords_post_a": ["link building for beginners", "how to get backlinks", "easy link building"],
        "keywords_post_b": ["link building strategy", "link building campaign", "agency link building"],
        "sections_to_rewrite": ["Introduction (both cover same ground)", "Tools section (identical lists)"],
        "estimated_impact": "Medium — reducing keyword cannibalization should improve rankings for both posts",
    }),
    "expand": json.dumps({
        "expansion_plan": "This post covers only the basics. It needs depth on advanced tactics and real examples.",
        "sections_to_add": [
            "Advanced Copywriting Formulas (AIDA, PAS, BAB)",
            "Real-World Examples: Before and After Rewrites",
            "Copywriting Tools and Templates",
            "Measuring Copywriting Impact: Metrics That Matter",
            "FAQ: Common Copywriting Questions"
        ],
        "target_word_count": "2500",
        "content_gaps": [
            "No mention of A/B testing headlines",
            "Missing section on mobile copywriting",
            "No data or statistics to support claims"
        ],
        "estimated_impact": "High — thin posts in this competitive cluster rank poorly; expanding to cluster average should recover lost traffic",
    }),
    "optimize": json.dumps({
        "optimization_plan": "Add a compelling meta description and improve the title for CTR.",
        "title_suggestion": "The Complete Guide to Copywriting: 15 Techniques That Convert",
        "meta_description": "Master copywriting with 15 proven techniques. Learn formulas, frameworks, and real examples that drive conversions. Updated for 2026.",
        "content_improvements": [
            "Add a table of contents with jump links for the 15 techniques",
            "Include before/after examples for each technique",
            "Add an infographic summarizing the key frameworks"
        ],
        "estimated_impact": "Medium — meta description alone can improve CTR by 5-10%",
    }),
    "interlink": json.dumps({
        "interlink_plan": "This high-quality post deserves more internal links to surface it in search and improve crawl depth.",
        "suggested_anchor_texts": [
            "copywriting techniques",
            "how to write compelling copy",
            "copywriting for beginners",
            "learn copywriting",
            "persuasive writing tips"
        ],
        "likely_linking_posts": [
            "Content marketing strategy guides",
            "SEO writing tutorials",
            "Landing page optimization posts",
            "Email marketing conversion posts",
            "Blogging tips roundups"
        ],
        "placement_tips": "Add links in the body text where the topic naturally comes up — avoid footer or sidebar links which pass less PageRank.",
        "estimated_impact": "Medium — fixing orphan status should improve crawl frequency and pass PageRank from linked posts",
    }),
    "update": json.dumps({
        "action_plan": "Update all statistics, replace outdated examples, refresh screenshots and links.",
        "priority_rationale": "This post references 2019 data and tools that have been deprecated. Searchers bouncing from outdated content signals low quality to Google.",
        "estimated_impact": "High — freshness is a ranking signal; updated content often recovers 20-40% of lost traffic within 2-3 months",
        "time_estimate": "2-3 hours for research and rewriting",
    }),
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English text)."""
    return len(text) // 4


async def main():
    from app.services.normalizer import (
        _strip_html_from_meta,
        _strip_site_name_from_title,
        filter_nav_links,
        filter_sitewide_headings,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 10b E2E Test: {TARGET_DOMAIN} ===\n")

    # ── Phase 1: Crawl (reuse Step 1) ──
    crawler = SitemapCrawler(
        sitemap_url=TARGET_SITEMAP,
        domain=TARGET_DOMAIN,
        max_pages=MAX_PAGES,
    )
    print(f"Crawling {TARGET_DOMAIN} (max {MAX_PAGES} pages)...")
    t0 = time.time()
    posts = await crawler.crawl()
    crawl_time = time.time() - t0
    print(f"  Crawled {len(posts)} posts in {crawl_time:.1f}s\n")

    if len(posts) < 10:
        print("ERROR: Too few posts crawled. Aborting.")
        sys.exit(1)

    # Normalize + deduplicate
    seen = set()
    deduped = []
    for p in posts:
        if p.url:
            norm = normalize_url(p.url)
            if norm in seen:
                continue
            seen.add(norm)
            p.url = norm
        if p.title:
            p.title = _strip_site_name_from_title(p.title)
        if p.meta_description:
            p.meta_description = _strip_html_from_meta(p.meta_description)
        deduped.append(p)
    posts = deduped

    links_map = {p.url: p.internal_links for p in posts}
    headings_map = {p.url: p.headings for p in posts}
    filtered_links = filter_nav_links(links_map)
    filtered_headings = filter_sitewide_headings(headings_map)
    for p in posts:
        p.internal_links = filtered_links.get(p.url, p.internal_links)
        p.headings = filtered_headings.get(p.url, p.headings)

    posts = [p for p in posts if p.body_text and len(p.body_text.strip()) > 50]

    # ── Phase 2: Synthetic embeddings + clustering ──
    print("Generating synthetic embeddings...")
    titles = [getattr(p, 'title', '') or '' for p in posts]
    embeddings = _generate_synthetic_embeddings(titles)
    print(f"  Shape: {embeddings.shape}")

    print("Running UMAP + HDBSCAN clustering...")
    t1 = time.time()
    labels, cluster_groups = _run_clustering(embeddings, len(posts))
    cluster_time = time.time() - t1
    n_clusters = len(cluster_groups)
    print(f"  {n_clusters} clusters in {cluster_time:.1f}s\n")

    post_cluster_map = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    # ── Phase 3: Problem detection + cannibalization ──
    print("Running problem detection...")
    problems = detect_problems(posts, cluster_groups, post_cluster_map)
    print(f"  {len(problems)} problems detected")

    print("Running cannibalization detection...")
    cann_pairs = detect_cannibalization(posts, embeddings, cluster_groups)
    print(f"  {len(cann_pairs)} pairs detected")

    # ── Phase 4: Generate recommendations (Step 10) ──
    print("Generating template recommendations (Step 10)...")
    recs = generate_recommendations(posts, problems, cann_pairs)
    print(f"  {len(recs)} recommendations generated\n")

    # ═══════════════════════════════════════════════
    # Phase 5: Step 10b — Claude Enrichment Simulation
    # ═══════════════════════════════════════════════

    print("=" * 60)
    print("STEP 10b: CLAUDE AI ENRICHMENT SIMULATION")
    print("=" * 60 + "\n")

    # 10b-a: Select top 10 by priority with type diversity
    # Mirrors production: prioritize highest-priority recs but ensure at least one
    # rec per type appears in the top 10 for representative enrichment coverage.
    print("--- 10b-a: Select Top 10 Unenriched Recs by Priority (with type diversity) ---\n")

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_recs = sorted(recs, key=lambda r: (priority_order.get(r.priority, 9),))

    # Ensure type diversity: pick best rec of each type first, then fill remaining
    top_10: list = []
    seen_types: set = set()
    # Pass 1: one of each recommendation type (best priority)
    for r in sorted_recs:
        if r.recommendation_type not in seen_types and len(top_10) < 10:
            top_10.append(r)
            seen_types.add(r.recommendation_type)
    # Pass 2: fill remaining slots with highest-priority recs
    for r in sorted_recs:
        if r not in top_10 and len(top_10) < 10:
            top_10.append(r)
    top_10.sort(key=lambda r: (priority_order.get(r.priority, 9),))

    print("| # | Priority | Type | Title (truncated) |")
    print("|---|----------|------|-------------------|")
    for i, r in enumerate(top_10):
        print(f"| {i+1} | {r.priority} | {r.recommendation_type} | {r.title[:55]}{'...' if len(r.title) > 55 else ''} |")

    type_counts = Counter(r.recommendation_type for r in top_10)
    priority_counts = Counter(r.priority for r in top_10)
    source_counts = Counter(r.source for r in top_10)

    print(f"\nTop 10 by type: {dict(type_counts)}")
    print(f"Top 10 by priority: {dict(priority_counts)}")
    print(f"Top 10 by source: {dict(source_counts)}")

    # 10b-b/c: Build contexts and prompts
    print("\n--- 10b-b/c/d: Build Contexts + Prompts ---\n")

    enrichment_results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for i, rec in enumerate(top_10):
        t_start = time.time()

        # Build context
        context = _build_context(rec)
        context_tokens = _estimate_tokens(context)

        # Build prompt
        prompt = _build_prompt(rec.recommendation_type, context)
        prompt_tokens = _estimate_tokens(prompt)

        # Get simulated response
        sim_response = SIMULATED_RESPONSES.get(rec.recommendation_type, SIMULATED_RESPONSES["update"])
        output_tokens = _estimate_tokens(sim_response)

        # Parse response
        parsed = _parse_claude_response(sim_response)

        # Validate expected fields
        expected = EXPECTED_FIELDS.get(rec.recommendation_type, EXPECTED_FIELDS["update"])
        missing_fields = [f for f in expected if f not in parsed]
        extra_fields = [f for f in parsed if f not in expected]

        # Build enriched actions
        enriched = _build_enriched_actions(parsed, rec.specific_actions)

        # Validate enriched format
        format_valid = (
            enriched.get("ai_enriched") is True
            and isinstance(enriched.get("ai_guidance"), dict)
            and isinstance(enriched.get("original_actions"), list)
        )

        elapsed = time.time() - t_start
        total_input_tokens += prompt_tokens
        total_output_tokens += output_tokens

        # Validate prompt contains required markers (S10b-07)
        has_rag_marker = "BLOG CONTEXT" in prompt
        has_json_instruction = "Respond with ONLY a JSON" in prompt
        has_post_data = rec.post_title in prompt and rec.url in prompt

        enrichment_results.append({
            "rec_id": rec.id,
            "rec_type": rec.recommendation_type,
            "priority": rec.priority,
            "title": rec.title[:60],
            "context_tokens": context_tokens,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "has_cann_context": rec.recommendation_type in ("merge", "differentiate", "redirect") and bool(rec.overlapping_title),
            "has_rag_context": has_rag_marker,
            "has_json_instruction": has_json_instruction,
            "has_post_data": has_post_data,
            "missing_fields": missing_fields,
            "extra_fields": extra_fields,
            "fields_valid": len(missing_fields) == 0,
            "format_valid": format_valid,
            "original_actions_preserved": len(enriched.get("original_actions", [])) > 0,
            "elapsed_ms": round(elapsed * 1000, 1),
            "parsed_response": parsed,
            "enriched_actions": enriched,
        })

    # Print per-rec results
    print("| # | Type | Priority | Prompt Tokens | Output Tokens | Fields Valid | Format Valid | Actions Preserved |")
    print("|---|------|----------|--------------|--------------|-------------|-------------|------------------|")
    for i, r in enumerate(enrichment_results):
        print(
            f"| {i+1} | {r['rec_type']:13s} | {r['priority']:8s} "
            f"| {r['prompt_tokens']:13d} | {r['output_tokens']:13d} "
            f"| {'YES' if r['fields_valid'] else 'NO — ' + ','.join(r['missing_fields']):11s} "
            f"| {'YES' if r['format_valid'] else 'NO':11s} "
            f"| {'YES' if r['original_actions_preserved'] else 'NO':17s} |"
        )

    # 10b-e: JSON Parsing Tests (expanded edge cases)
    print("\n--- 10b-e: JSON Response Parsing Tests ---\n")

    parse_tests = [
        ("Valid JSON", '{"merge_plan": "Keep post A", "estimated_impact": "High"}', True, 2),
        ("Markdown-wrapped JSON", '```json\n{"merge_plan": "Keep post A"}\n```', True, 1),
        ("Markdown no lang", '```\n{"merge_plan": "Keep post A"}\n```', True, 1),
        ("Markdown trailing space", '```json\n{"merge_plan": "Keep post A"}\n``` \n', True, 1),
        ("Invalid JSON", 'Here is my analysis: the post should...', False, 1),
        ("Partial JSON", '{"merge_plan": "Keep post A", "keep_url":', False, 1),
        ("Empty response", '', False, 1),
        ("Array response", '[{"plan": "A"}, {"plan": "B"}]', True, 2),
        # New edge cases (S10b-07)
        ("Nested JSON", '{"plan": {"step1": "Do X", "step2": "Do Y"}, "impact": "High"}', True, 2),
        ("Unicode in values", '{"plan": "Üpdate the héading with émojis 🎯"}', True, 1),
        ("Large JSON (many keys)", json.dumps({f"field_{i}": f"value_{i}" for i in range(20)}), True, 20),
        ("Markdown python tag", '```python\n{"plan": "value"}\n```', True, 1),
        ("Leading whitespace", '  \n  {"plan": "value"}', True, 1),
        ("Trailing newlines", '{"plan": "value"}\n\n\n', True, 1),
        ("Boolean values", '{"ai_enriched": true, "count": 5}', True, 2),
    ]

    print("| Test Case | Input | Parsed OK? | Result Keys |")
    print("|-----------|-------|-----------|------------|")
    for name, input_text, expect_clean, expect_keys in parse_tests:
        result = _parse_claude_response(input_text)
        is_clean = "raw_response" not in result
        ok = is_clean == expect_clean
        n_keys = len(result)
        status = "PASS" if ok else "FAIL"
        print(f"| {name:25s} | {input_text[:40]:40s}{'...' if len(input_text) > 40 else '':3s} | {status} ({is_clean}) | {n_keys} keys |")

    all_parse_pass = all(
        ("raw_response" not in _parse_claude_response(t[1])) == t[2]
        for t in parse_tests
    )
    print(f"\nAll {len(parse_tests)} parse tests passed: {'YES' if all_parse_pass else 'NO'}")

    # 10b-f: Storage format validation
    print("\n--- 10b-f: Storage Format Validation ---\n")

    for r in enrichment_results:
        enriched = r["enriched_actions"]
        # Verify it's valid JSON
        json_str = json.dumps(enriched)
        re_parsed = json.loads(json_str)
        assert re_parsed["ai_enriched"] is True
        assert isinstance(re_parsed["ai_guidance"], dict)
        assert isinstance(re_parsed["original_actions"], list)

    print("All 10 enriched actions: valid JSON round-trip OK")
    print(f"All have ai_enriched=true: OK")
    print(f"All have ai_guidance dict: OK")
    print(f"All preserve original_actions: OK")

    # Verify already-enriched check
    for r in enrichment_results:
        enriched = r["enriched_actions"]
        # Simulate the already-enriched check from enrich_recommendation()
        existing = enriched
        if isinstance(existing, dict) and existing.get("ai_enriched"):
            already = True
        else:
            already = False
        assert already, f"Already-enriched check failed for {r['rec_id']}"
    print("Already-enriched guard detects all enriched recs: OK")

    # ═══════════════════════════════════════════════
    # 10b-g: All 7 Rec Types Validation (S10b-04)
    # Tests every rec type regardless of what appears in top 10
    # ═══════════════════════════════════════════════

    print("\n--- 10b-g: All 7 Rec Types Prompt + Response Validation ---\n")

    # Build a synthetic rec for each type so we validate all 7
    all_type_recs = {
        "merge": SimulatedRec(
            id="synth-merge", post_index=0, post_title="Guide to Link Building", url="https://example.com/link-building",
            word_count=2500, body_excerpt="Link building is a core SEO strategy..." * 50,
            recommendation_type="merge", title="Merge: Guide to Link Building",
            summary="Overlaps with 'SEO Backlink Guide' (blended: 0.72)", specific_actions=["Merge overlapping posts"],
            priority="high", estimated_effort_hours=3.0, source="cannibalization",
            overlapping_title="SEO Backlink Guide", overlapping_url="https://example.com/seo-backlinks",
            overlapping_wc=1800, overlapping_excerpt="Backlinks are essential for SEO..." * 50,
        ),
        "redirect": SimulatedRec(
            id="synth-redirect", post_index=1, post_title="Old Copywriting Tips", url="https://example.com/old-tips",
            word_count=300, body_excerpt="Here are some copywriting tips..." * 20,
            recommendation_type="redirect", title="Redirect: Old Copywriting Tips",
            summary="Near-duplicate of 'Complete Copywriting Guide'", specific_actions=["301 redirect to main post"],
            priority="high", estimated_effort_hours=0.5, source="cannibalization",
            overlapping_title="Complete Copywriting Guide", overlapping_url="https://example.com/copywriting-guide",
            overlapping_wc=4000, overlapping_excerpt="Copywriting is the art of persuasive writing..." * 50,
        ),
        "differentiate": SimulatedRec(
            id="synth-diff", post_index=2, post_title="Content Strategy 101", url="https://example.com/content-strategy",
            word_count=2000, body_excerpt="Content strategy involves planning..." * 50,
            recommendation_type="differentiate", title="Differentiate: Content Strategy 101",
            summary="Overlaps with 'Content Marketing Plan' (slug overlap)", specific_actions=["Differentiate angles"],
            priority="medium", estimated_effort_hours=2.0, source="cannibalization",
            overlapping_title="Content Marketing Plan", overlapping_url="https://example.com/content-marketing-plan",
            overlapping_wc=1900, overlapping_excerpt="A content marketing plan outlines..." * 50,
        ),
        "expand": SimulatedRec(
            id="synth-expand", post_index=3, post_title="SEO Basics", url="https://example.com/seo-basics",
            word_count=280, body_excerpt="SEO stands for Search Engine Optimization..." * 15,
            recommendation_type="expand", title="Expand thin content: SEO Basics",
            summary="Only 280 words — below 500-word threshold.", specific_actions=["Add 500+ words"],
            priority="high", estimated_effort_hours=2.0, source="problem",
        ),
        "optimize": SimulatedRec(
            id="synth-optimize", post_index=4, post_title="Email Marketing Tips", url="https://example.com/email-tips",
            word_count=1500, body_excerpt="Email marketing remains one of the most effective..." * 50,
            recommendation_type="optimize", title="Add meta description: Email Marketing Tips",
            summary="No meta description found.", specific_actions=["Write 150-char meta description"],
            priority="medium", estimated_effort_hours=0.5, source="problem",
        ),
        "interlink": SimulatedRec(
            id="synth-interlink", post_index=5, post_title="Guest Blogging Guide", url="https://example.com/guest-blogging",
            word_count=2200, body_excerpt="Guest blogging is a powerful strategy..." * 50,
            recommendation_type="interlink", title="Fix orphan page: Guest Blogging Guide",
            summary="No internal links point to this post.", specific_actions=["Add links from 3+ related posts"],
            priority="high", estimated_effort_hours=0.5, source="orphan",
        ),
        "update": SimulatedRec(
            id="synth-update", post_index=6, post_title="Social Media Trends 2022", url="https://example.com/social-2022",
            word_count=1800, body_excerpt="Social media trends for 2022 include..." * 50,
            recommendation_type="update", title="Update outdated content: Social Media Trends 2022",
            summary="References 2022 data — severely outdated.", specific_actions=["Update statistics and references"],
            priority="high", estimated_effort_hours=1.5, source="problem",
        ),
    }

    all_types_pass = True
    print("| Type | Context Has RAG | Prompt Has Schema | Response Fields Valid | Format Valid |")
    print("|------|----------------|-------------------|----------------------|-------------|")

    for rtype, synth_rec in all_type_recs.items():
        ctx = _build_context(synth_rec)
        prompt = _build_prompt(rtype, ctx)
        sim_resp = SIMULATED_RESPONSES.get(rtype, SIMULATED_RESPONSES["update"])
        parsed = _parse_claude_response(sim_resp)
        enriched = _build_enriched_actions(parsed, synth_rec.specific_actions)

        # Validate context contains RAG markers
        has_rag = "BLOG CONTEXT" in ctx and "CLUSTER BENCHMARKS" in ctx
        # Validate prompt contains the JSON schema hint
        has_schema = "Respond with ONLY a JSON" in prompt
        # Validate expected fields present
        expected = EXPECTED_FIELDS.get(rtype, EXPECTED_FIELDS["update"])
        fields_ok = all(f in parsed for f in expected)
        # Validate storage format
        fmt_ok = (
            enriched.get("ai_enriched") is True
            and isinstance(enriched.get("ai_guidance"), dict)
            and isinstance(enriched.get("original_actions"), list)
            and len(enriched["original_actions"]) > 0
        )

        if not (has_rag and has_schema and fields_ok and fmt_ok):
            all_types_pass = False

        print(
            f"| {rtype:13s} | {'YES' if has_rag else 'NO':14s} | {'YES' if has_schema else 'NO':17s} "
            f"| {'YES' if fields_ok else 'MISSING: ' + ','.join(f for f in expected if f not in parsed):20s} "
            f"| {'YES' if fmt_ok else 'NO':11s} |"
        )

    print(f"\nAll 7 rec types validated: {'YES' if all_types_pass else 'NO'}")

    # ═══════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════

    print("\n" + "=" * 60)
    print("STEP 10b SUMMARY")
    print("=" * 60 + "\n")

    # Cost projection
    cost_per_input_token = 3.0 / 1_000_000  # Sonnet input ~$3/MTok
    cost_per_output_token = 15.0 / 1_000_000  # Sonnet output ~$15/MTok
    est_cost_input = total_input_tokens * cost_per_input_token
    est_cost_output = total_output_tokens * cost_per_output_token
    est_cost_total = est_cost_input + est_cost_output

    print(f"Total recs generated (Step 10): {len(recs)}")
    print(f"Top 10 selected for enrichment: {len(top_10)}")
    print(f"Rec types in top 10: {dict(type_counts)}")
    print(f"Priority breakdown: {dict(priority_counts)}")
    print()
    print(f"Total input tokens (est.):  {total_input_tokens:,}")
    print(f"Total output tokens (est.): {total_output_tokens:,}")
    print(f"Est. cost (input):   ${est_cost_input:.4f}")
    print(f"Est. cost (output):  ${est_cost_output:.4f}")
    print(f"Est. total cost:     ${est_cost_total:.4f}")
    print()
    avg_prompt = statistics.mean(r["prompt_tokens"] for r in enrichment_results)
    avg_output = statistics.mean(r["output_tokens"] for r in enrichment_results)
    print(f"Avg prompt tokens/rec: {avg_prompt:.0f}")
    print(f"Avg output tokens/rec: {avg_output:.0f}")
    print()

    all_fields_valid = all(r["fields_valid"] for r in enrichment_results)
    all_format_valid = all(r["format_valid"] for r in enrichment_results)
    all_actions_preserved = all(r["original_actions_preserved"] for r in enrichment_results)

    print(f"All expected JSON fields present: {'YES' if all_fields_valid else 'NO'}")
    print(f"All enriched formats valid:       {'YES' if all_format_valid else 'NO'}")
    print(f"All original actions preserved:   {'YES' if all_actions_preserved else 'NO'}")
    print(f"JSON parse tests all pass:        {'YES' if all_parse_pass else 'NO'} ({len(parse_tests)} tests)")
    print(f"All 7 rec types validated:        {'YES' if all_types_pass else 'NO'}")
    print()

    # Blended scoring stats (S10b-01 fix)
    resolution_counts = Counter(p.get("resolution", "?") for p in cann_pairs)
    print(f"--- Blended Scoring Stats ---")
    print(f"Cann pairs (after blended filter): {len(cann_pairs)}")
    print(f"Resolution distribution: {dict(resolution_counts)}")
    if cann_pairs:
        blended_scores = [p["blended_score"] for p in cann_pairs]
        print(f"Blended score range: {min(blended_scores):.3f} - {max(blended_scores):.3f}")
        print(f"Blended score avg:   {statistics.mean(blended_scores):.3f}")
    print()

    # Per-type prompt analysis
    print("--- Prompt Size by Rec Type ---\n")
    type_tokens: dict[str, list[int]] = {}
    for r in enrichment_results:
        type_tokens.setdefault(r["rec_type"], []).append(r["prompt_tokens"])

    print("| Rec Type | Count | Avg Tokens | Min | Max |")
    print("|----------|-------|-----------|-----|-----|")
    for rtype, tokens in sorted(type_tokens.items()):
        print(f"| {rtype:13s} | {len(tokens):5d} | {statistics.mean(tokens):9.0f} | {min(tokens):3d} | {max(tokens):3d} |")

    # Coverage analysis
    all_types_covered = set(EXPECTED_FIELDS.keys())
    covered_types = set(r["rec_type"] for r in enrichment_results)
    uncovered = all_types_covered - covered_types

    print(f"\nRec types with prompt template: {len(all_types_covered)} ({', '.join(sorted(all_types_covered))})")
    print(f"Rec types tested in top 10:     {len(covered_types)} ({', '.join(sorted(covered_types))})")
    if uncovered:
        print(f"Untested types:                 {', '.join(sorted(uncovered))}")
    else:
        print("All rec types covered: YES")

    # Sample enrichment output
    print("\n--- Sample Enriched Output (first expand rec) ---\n")
    for r in enrichment_results:
        if r["rec_type"] == "expand":
            print(json.dumps(r["enriched_actions"], indent=2)[:1500])
            break
    else:
        print("(no expand rec in top 10)")

    # Write results for STEP10B-TEST-RESULTS.md consumption
    print("\n\n--- RAW DATA FOR RESULTS DOC ---\n")
    print(f"CRAWL_COUNT={len(posts)}")
    print(f"CLUSTER_COUNT={n_clusters}")
    print(f"PROBLEM_COUNT={len(problems)}")
    print(f"CANN_PAIR_COUNT={len(cann_pairs)}")
    print(f"CANN_RESOLUTIONS={json.dumps(dict(resolution_counts))}")
    print(f"TOTAL_RECS={len(recs)}")
    print(f"TOP_10_TYPES={json.dumps(dict(type_counts))}")
    print(f"TOP_10_PRIORITIES={json.dumps(dict(priority_counts))}")
    print(f"TOTAL_INPUT_TOKENS={total_input_tokens}")
    print(f"TOTAL_OUTPUT_TOKENS={total_output_tokens}")
    print(f"EST_COST={est_cost_total:.4f}")
    print(f"ALL_FIELDS_VALID={all_fields_valid}")
    print(f"ALL_FORMAT_VALID={all_format_valid}")
    print(f"ALL_PARSE_PASS={all_parse_pass}")
    print(f"ALL_TYPES_VALIDATED={all_types_pass}")
    print(f"PARSE_TEST_COUNT={len(parse_tests)}")


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    asyncio.run(main())
