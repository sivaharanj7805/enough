"""Full Pipeline E2E: Steps 1 through 10b with REAL API calls.

Runs the entire Tended intelligence pipeline against a real site:
  - Step 1:    Crawl + Normalize (SitemapCrawler)
  - Steps 2-5: Enrichment (REAL OpenAI embeddings, Readability, PageRank, Intent)
  - Step 6:    Clustering (UMAP + HDBSCAN with real embeddings)
  - Step 6b:   TF-IDF Cluster Labels
  - Step 6c:   AI Citability Scoring
  - Step 7:    Health Scoring (crawl-only mode)
  - Step 8:    Cannibalization Detection (real embedding cosine similarity)
  - Step 8b:   Chunk Confirmation (REAL OpenAI chunk embeddings)
  - Step 9:    Problem Detection
  - Step 10:   Recommendations
  - Step 10b:  Claude Enrichment (REAL Anthropic API)

Uses the existing e2e test scripts' logic verbatim, replacing synthetic
embeddings with real OpenAI text-embedding-3-small vectors.

Output: ../pipelineresults.md (every single data point captured)
"""

import asyncio
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import combinations

import numpy as np

# Load .env from backend directory
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

TARGET_DOMAIN = "zapier.com"
TARGET_SITEMAP = "https://zapier.com/blog/sitemap.xml"
MAX_PAGES = 150

# OpenAI embedding config (from services/embeddings.py)
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMS = 1536
TRUNCATE_CHARS = 20000
BATCH_SIZE = 100


# ═══════════════════════════════════════════════════════════════════════
# HELPERS (from e2e scripts)
# ═══════════════════════════════════════════════════════════════════════

def _avg(lst):
    return sum(lst) / len(lst) if lst else 0


def _pearson(x: list[float], y: list[float]) -> float:
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


def _extract_slug_words(url: str) -> set[str]:
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/").split("/")[-1] if url else ""
    stops = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "on", "with", "how", "what", "why"}
    return set(w.lower() for w in re.split(r'[-_]', path) if len(w) > 2 and w.lower() not in stops)


def _title_word_overlap(title_a: str, title_b: str) -> float:
    stops = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "on", "with", "how", "what", "why",
             "your", "you", "that", "this", "are", "was", "be", "have", "has", "it", "not", "do", "can"}
    words_a = set(w.lower() for w in re.split(r'\W+', title_a or '') if len(w) > 2 and w.lower() not in stops)
    words_b = set(w.lower() for w in re.split(r'\W+', title_b or '') if len(w) > 2 and w.lower() not in stops)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _recommend_resolution(cosine_sim, severity, slug_overlap, title_overlap):
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


def _smart_excerpt(text: str, max_chars: int = 800) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + "\n[...]\n" + text[-half:].lstrip()


# ═══════════════════════════════════════════════════════════════════════
# REAL OPENAI EMBEDDING (replaces _generate_synthetic_embeddings)
# ═══════════════════════════════════════════════════════════════════════

async def _generate_real_embeddings(posts, openai_client) -> tuple[np.ndarray, dict]:
    """Generate REAL OpenAI text-embedding-3-small embeddings for all posts.

    Returns (embedding_matrix, stats_dict).
    Uses the same batching logic as services/embeddings.py.
    """
    embeddable = [(i, p) for i, p in enumerate(posts) if p.body_text and len(p.body_text.strip()) > 50]

    # Prepare texts, split into short (batchable) and long (chunked)
    short_items = []  # (index, text)
    long_items = []   # (index, chunks)
    for idx, p in embeddable:
        text = f"{p.title}\n\n{p.body_text}" if p.title else p.body_text
        if len(text) <= TRUNCATE_CHARS:
            short_items.append((idx, text.strip()))
        else:
            # Chunk with overlap (same logic as services/embeddings.py)
            overlap = 500
            title_prefix = f"{p.title}\n\n" if p.title else ""
            chunk_size = TRUNCATE_CHARS - len(title_prefix)
            chunks = [text[:TRUNCATE_CHARS].strip()]
            start = TRUNCATE_CHARS - overlap
            while start < len(text):
                chunk_body = text[start:start + chunk_size]
                if len(chunk_body.strip()) < 200:
                    break
                chunks.append(f"{title_prefix}{chunk_body}".strip())
                start += chunk_size - overlap
            long_items.append((idx, chunks))

    n_posts = len(posts)
    embeddings = np.zeros((n_posts, EMBED_DIMS), dtype=np.float32)
    embedded_indices = set()
    total_api_calls = 0
    total_tokens_used = 0

    # Batch embed short posts
    for batch_start in range(0, len(short_items), BATCH_SIZE):
        batch = short_items[batch_start:batch_start + BATCH_SIZE]
        texts = [t for _, t in batch]
        try:
            response = await openai_client.embeddings.create(
                model=EMBED_MODEL, input=texts, dimensions=EMBED_DIMS,
            )
            total_api_calls += 1
            total_tokens_used += response.usage.total_tokens
            for j, emb_data in enumerate(response.data):
                idx = batch[j][0]
                embeddings[idx] = emb_data.embedding
                embedded_indices.add(idx)
        except Exception as e:
            print(f"  ERROR in batch {batch_start}: {e}")
            # Fallback: embed individually
            for idx, text in batch:
                try:
                    resp = await openai_client.embeddings.create(
                        model=EMBED_MODEL, input=[text], dimensions=EMBED_DIMS,
                    )
                    total_api_calls += 1
                    total_tokens_used += resp.usage.total_tokens
                    embeddings[idx] = resp.data[0].embedding
                    embedded_indices.add(idx)
                except Exception as e2:
                    print(f"  ERROR embedding post {idx}: {e2}")
        pct = len(embedded_indices) / len(embeddable) * 100
        print(f"  Embedded {len(embedded_indices)}/{len(embeddable)} posts ({pct:.0f}%)")

    # Embed long posts with chunked mean-pooling
    for idx, chunks in long_items:
        chunk_vectors = []
        for chunk in chunks:
            try:
                resp = await openai_client.embeddings.create(
                    model=EMBED_MODEL, input=[chunk[:TRUNCATE_CHARS]], dimensions=EMBED_DIMS,
                )
                total_api_calls += 1
                total_tokens_used += resp.usage.total_tokens
                chunk_vectors.append(resp.data[0].embedding)
            except Exception as e:
                print(f"  ERROR embedding chunk for post {idx}: {e}")
        if chunk_vectors:
            mean_vec = np.mean(chunk_vectors, axis=0)
            embeddings[idx] = mean_vec
            embedded_indices.add(idx)
        pct = len(embedded_indices) / len(embeddable) * 100
        print(f"  Embedded {len(embedded_indices)}/{len(embeddable)} posts ({pct:.0f}%) [long post, {len(chunks)} chunks]")

    stats = {
        "total_embeddable": len(embeddable),
        "short_posts": len(short_items),
        "long_posts": len(long_items),
        "total_chunks": sum(len(c) for _, c in long_items) + len(short_items),
        "api_calls": total_api_calls,
        "total_tokens": total_tokens_used,
        "cost_usd": total_tokens_used / 1_000_000 * 0.02,
        "embedded_count": len(embedded_indices),
    }
    return embeddings, embedded_indices, stats


# ═══════════════════════════════════════════════════════════════════════
# CLUSTERING (from test_step6_e2e.py)
# ═══════════════════════════════════════════════════════════════════════

def _run_clustering(embeddings, n_posts):
    """Run UMAP+HDBSCAN clustering (from test_step6_e2e.py)."""
    import hdbscan
    import umap
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim
    from sklearn.metrics import silhouette_score, silhouette_samples

    # Pin all random seeds for deterministic clustering across runs.
    # Critical for cold outreach: PDF and dashboard must show identical clusters.
    rng = np.random.RandomState(42)
    sample_size = min(100, n_posts)
    sample_indices = rng.choice(n_posts, sample_size, replace=False)
    sample = embeddings[sample_indices]
    sim_matrix = cos_sim(sample)
    np.fill_diagonal(sim_matrix, 0)
    mean_sim = float(sim_matrix.mean())
    max_sim = float(sim_matrix.max())

    n_components = max(2, min(15, n_posts - 2))
    n_neighbors = min(15, n_posts - 1)

    if mean_sim > 0.70:
        min_dist = 0.25
        n_neighbors = min(5, max(1, n_posts - 1))
        niche_type = "tight niche"
    elif mean_sim > 0.55:
        min_dist = 0.15
        n_neighbors = min(10, n_posts - 1)
        niche_type = "moderate focus"
    elif mean_sim > 0.40:
        min_dist = 0.1
        niche_type = "mixed content"
    else:
        min_dist = 0.05
        niche_type = "diverse content"

    reducer = umap.UMAP(
        n_components=n_components, n_neighbors=n_neighbors,
        min_dist=min_dist, metric="cosine", random_state=42,
    )
    reduced = reducer.fit_transform(embeddings)

    if n_posts < 20:
        min_cluster_size, min_samples = max(2, n_posts // 5), 1
    elif n_posts < 100:
        min_cluster_size, min_samples = max(3, n_posts // 10), 2
    elif n_posts < 500:
        min_cluster_size, min_samples = max(5, n_posts // 20), 3
    elif n_posts < 1000:
        min_cluster_size, min_samples = 12, 3
    else:
        min_cluster_size, min_samples = 20, 5

    retry_count = 0
    avg_silhouette = 0.0
    cluster_silhouettes = {}
    original_noise = 0
    while True:
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size, min_samples=min_samples,
            metric="euclidean", cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        original_noise = int(np.sum(labels == -1))

        if n_clusters >= 2:
            mask = labels != -1
            if mask.sum() >= 2:
                avg_silhouette = float(silhouette_score(reduced[mask], labels[mask]))
                per_sample = silhouette_samples(reduced[mask], labels[mask])
                for cl in set(labels[mask]):
                    cl_scores = per_sample[labels[mask] == cl]
                    cluster_silhouettes[int(cl)] = float(np.mean(cl_scores))
                if avg_silhouette < 0.1 and retry_count < 2:
                    retry_count += 1
                    min_cluster_size += 1
                    continue
        break

    # Noise assignment (from test_step6_e2e.py)
    if original_noise > 0 and n_clusters > 0:
        from sklearn.metrics.pairwise import euclidean_distances
        noise_mask = labels == -1
        non_noise_mask = labels != -1
        if non_noise_mask.sum() > 0:
            unique_clusters = sorted(set(labels[non_noise_mask]))
            centroids = np.array([reduced[labels == c].mean(axis=0) for c in unique_clusters])
            noise_indices = np.where(noise_mask)[0]
            dists = euclidean_distances(reduced[noise_indices], centroids)
            nearest = np.argmin(dists, axis=1)
            for i, idx in enumerate(noise_indices):
                labels[idx] = unique_clusters[nearest[i]]

    # Dissolve negative-silhouette clusters (from production clustering.py)
    n_clusters_post_noise = len(set(labels)) - (1 if -1 in labels else 0)
    if cluster_silhouettes and n_clusters_post_noise >= 3:
        from sklearn.metrics.pairwise import euclidean_distances as euc_dist
        neg_clusters = [c for c, s in cluster_silhouettes.items() if s < 0.0]
        pos_clusters = [c for c, s in cluster_silhouettes.items() if s >= 0.0]
        if neg_clusters and pos_clusters:
            pos_centroids = np.array([reduced[labels == c].mean(axis=0) for c in pos_clusters])
            for neg_c in neg_clusters:
                neg_indices = np.where(labels == neg_c)[0]
                if len(neg_indices) == 0:
                    continue
                neg_reduced = reduced[neg_indices]
                dists = euc_dist(neg_reduced, pos_centroids)
                nearest_idx = np.argmin(dists, axis=1)
                for ii, idx in enumerate(neg_indices):
                    labels[idx] = pos_clusters[nearest_idx[ii]]
            # Recompute silhouettes
            mask = labels != -1
            if mask.sum() >= 2 and len(set(labels[mask])) >= 2:
                avg_silhouette = float(silhouette_score(reduced[mask], labels[mask]))
                per_sample = silhouette_samples(reduced[mask], labels[mask])
                cluster_silhouettes = {}
                for cl in set(labels[mask]):
                    cl_scores = per_sample[labels[mask] == cl]
                    cluster_silhouettes[int(cl)] = float(np.mean(cl_scores))
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    cluster_groups = {}
    for idx, label in enumerate(labels):
        if label != -1:
            cluster_groups.setdefault(int(label), []).append(idx)

    # 2D map positions (from test_step6_e2e.py)
    reducer_2d = umap.UMAP(
        n_components=2, n_neighbors=n_neighbors,
        min_dist=0.3, metric="cosine", random_state=42,
    )
    positions_2d = reducer_2d.fit_transform(embeddings)

    # Cluster-aware nudge (15%)
    unique_lbls = set(labels) - {-1}
    if unique_lbls:
        centroids_2d = {c: positions_2d[labels == c].mean(axis=0) for c in unique_lbls}
        for i, lbl in enumerate(labels):
            if lbl in centroids_2d:
                positions_2d[i] += 0.15 * (centroids_2d[lbl] - positions_2d[i])

    return {
        "labels": labels, "cluster_groups": cluster_groups,
        "reduced": reduced, "positions_2d": positions_2d,
        "n_clusters": n_clusters, "original_noise": original_noise,
        "avg_silhouette": avg_silhouette, "cluster_silhouettes": cluster_silhouettes,
        "mean_sim": mean_sim, "max_sim": max_sim,
        "niche_type": niche_type, "n_components": n_components,
        "n_neighbors": n_neighbors, "min_dist": min_dist,
        "min_cluster_size": min_cluster_size, "min_samples": min_samples,
        "retry_count": retry_count,
    }


# ═══════════════════════════════════════════════════════════════════════
# CANNIBALIZATION (from test_step10b_e2e.py)
# ═══════════════════════════════════════════════════════════════════════

def detect_cannibalization(posts, embeddings, cluster_groups):
    """Detect cannibalization pairs using blended scoring (from test_step10b_e2e.py)."""
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
            a_idx, b_idx = indices[a_local], indices[b_local]
            title_a = getattr(posts[a_idx], 'title', '') or ''
            title_b = getattr(posts[b_idx], 'title', '') or ''
            url_a = getattr(posts[a_idx], 'url', '') or ''
            url_b = getattr(posts[b_idx], 'url', '') or ''

            slug_a, slug_b = _extract_slug_words(url_a), _extract_slug_words(url_b)
            slug_overlap = len(slug_a & slug_b) / len(slug_a | slug_b) if (slug_a | slug_b) else 0.0
            title_overlap = _title_word_overlap(title_a, title_b)
            blended = 0.25 * cos_val + 0.25 * slug_overlap + 0.30 * title_overlap + 0.20 * 0.0

            if blended > 0.80:
                severity = "critical"
            elif blended > 0.55:
                severity = "high"
            elif blended > 0.35:
                severity = "medium"
            else:
                continue

            resolution = _recommend_resolution(cos_val, severity, slug_overlap, title_overlap)
            if resolution == "monitor":
                continue

            wc_a = getattr(posts[a_idx], 'word_count', 0) or 0
            wc_b = getattr(posts[b_idx], 'word_count', 0) or 0
            stronger_idx = a_idx if wc_a >= wc_b else b_idx

            pairs.append({
                "post_a_idx": a_idx, "post_b_idx": b_idx,
                "title_a": title_a, "title_b": title_b,
                "url_a": url_a, "url_b": url_b,
                "wc_a": wc_a, "wc_b": wc_b,
                "cosine_similarity": round(cos_val, 4),
                "blended_score": round(blended, 4),
                "severity": severity, "resolution": resolution,
                "slug_overlap": round(slug_overlap, 3),
                "title_overlap": round(title_overlap, 3),
                "stronger_idx": stronger_idx, "cluster_id": cl_id,
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


# ═══════════════════════════════════════════════════════════════════════
# CHUNK CONFIRMATION - Step 8b (REAL OpenAI)
# ═══════════════════════════════════════════════════════════════════════

async def run_chunk_confirmation(posts, cann_pairs, openai_client, max_pairs=20):
    """Real OpenAI chunk-level confirmation (from services/chunk_cannibalization.py)."""
    from app.services.chunk_cannibalization import split_into_chunks

    CHUNK_THRESHOLD = 0.88
    results = []
    total_api_calls = 0
    total_tokens = 0

    for pair in cann_pairs[:max_pairs]:
        a_idx, b_idx = pair["post_a_idx"], pair["post_b_idx"]
        p_a, p_b = posts[a_idx], posts[b_idx]

        chunks_a = split_into_chunks(p_a.body_html or "", p_a.title or "")
        chunks_b = split_into_chunks(p_b.body_html or "", p_b.title or "")

        if not chunks_a or not chunks_b:
            results.append({**pair, "confirmed": None, "max_chunk_sim": 0, "chunks_a": 0, "chunks_b": 0})
            continue

        # Embed chunks via OpenAI
        all_chunks = chunks_a + chunks_b
        try:
            resp = await openai_client.embeddings.create(
                model=EMBED_MODEL,
                input=[c[:1000] for c in all_chunks],
            )
            total_api_calls += 1
            total_tokens += resp.usage.total_tokens
            vecs = [item.embedding for item in resp.data]
        except Exception as e:
            print(f"  ERROR in chunk embedding: {e}")
            results.append({**pair, "confirmed": None, "max_chunk_sim": 0, "chunks_a": len(chunks_a), "chunks_b": len(chunks_b), "error": str(e)})
            continue

        vecs_a = np.array(vecs[:len(chunks_a)])
        vecs_b = np.array(vecs[len(chunks_a):])

        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        chunk_sim = cos_sim(vecs_a, vecs_b)
        max_chunk_sim = float(chunk_sim.max())
        max_pos = np.unravel_index(chunk_sim.argmax(), chunk_sim.shape)

        confirmed = max_chunk_sim >= CHUNK_THRESHOLD
        results.append({
            **pair,
            "confirmed": confirmed,
            "max_chunk_sim": round(max_chunk_sim, 4),
            "chunks_a": len(chunks_a),
            "chunks_b": len(chunks_b),
            "most_similar_chunk_a": chunks_a[max_pos[0]][:100] if max_pos[0] < len(chunks_a) else "",
            "most_similar_chunk_b": chunks_b[max_pos[1]][:100] if max_pos[1] < len(chunks_b) else "",
        })
        status = "CONFIRMED" if confirmed else "denied"
        print(f"  Pair: {pair['title_a'][:35]}... vs {pair['title_b'][:35]}... -> {status} (max={max_chunk_sim:.3f})")

    return results, {"api_calls": total_api_calls, "total_tokens": total_tokens}


# ═══════════════════════════════════════════════════════════════════════
# PROBLEM DETECTION (from test_step10b_e2e.py)
# ═══════════════════════════════════════════════════════════════════════

def detect_problems(posts, cluster_groups, post_cluster_map, ai_results_lookup=None, readability_lookup=None):
    """Detect content problems — mirrors production problem_detection.py."""
    problems = []
    cluster_avg_wc = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if getattr(posts[i], 'word_count', None)]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if len(wcs) >= 3 else 1000.0

    url_to_idx = {getattr(p, 'url', ''): i for i, p in enumerate(posts)}
    inbound_counts = {i: 0 for i in range(len(posts))}
    total_links = 0
    resolved_links = 0
    for i, p in enumerate(posts):
        for link in getattr(p, 'internal_links', []):
            target_url = link.target_url if hasattr(link, 'target_url') else (link.get("target_url") if isinstance(link, dict) else str(link))
            total_links += 1
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                inbound_counts[target_idx] += 1
                resolved_links += 1

    # Orphan quality gate: skip orphan + seo_no_internal_links if link
    # resolution < 20% (capped crawl — most targets outside dataset)
    resolution_rate = resolved_links / max(total_links, 1)
    link_resolution_reliable = total_links == 0 or resolution_rate >= 0.20

    for i, p in enumerate(posts):
        wc = getattr(p, 'word_count', 0) or 0
        title = (getattr(p, 'title', '') or '')
        url = (getattr(p, 'url', '') or '')
        page_type = getattr(p, 'page_type', 'blog') or 'blog'

        # Skip landing/index pages for content problems
        if page_type in ('landing', 'index'):
            # Still check AI citability (schema) for landing pages
            if ai_results_lookup and url in ai_results_lookup:
                ai = ai_results_lookup[url]
                if ai.get("schema", 100) == 0:
                    problems.append({"post_index": i, "title": title, "url": url, "problem_type": "missing_schema", "severity": "low"})
            continue

        # Thin content
        if 0 < wc < 500:
            problems.append({"post_index": i, "title": title, "url": url, "problem_type": "thin_content",
                             "severity": "high" if wc < 250 else "medium", "word_count": wc})

        # Thin below cluster avg
        cl_id = post_cluster_map.get(i)
        if cl_id is not None and cluster_avg_wc.get(cl_id, 0) > 1500:
            avg = cluster_avg_wc[cl_id]
            if wc < avg * 0.5 and wc < 800:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "thin_below_cluster_avg",
                                 "severity": "medium", "word_count": wc, "cluster_avg": int(avg)})

        # Missing meta
        meta = getattr(p, 'meta_description', '') or ''
        if len(meta.strip()) < 10:
            problems.append({"post_index": i, "title": title, "url": url, "problem_type": "seo_missing_meta", "severity": "medium"})

        # Title length (production uses <20 or >70)
        title_len = len(title)
        if title_len < 20 or title_len > 70:
            severity = "medium" if title_len < 20 else "low"
            problems.append({"post_index": i, "title": title, "url": url, "problem_type": "seo_title_length",
                             "severity": severity, "title_length": title_len})

        # No headings
        headings = getattr(p, 'headings', []) or []
        if not headings:
            problems.append({"post_index": i, "title": title, "url": url, "problem_type": "seo_no_headings", "severity": "medium"})

        # No images
        body_html = getattr(p, 'body_html', '') or ''
        html_lower = body_html.lower()
        is_trafilatura = html_lower.startswith("<doc") or "<doc " in html_lower[:100]
        if not is_trafilatura:
            has_images = any(tag in html_lower for tag in [
                '<img', '<picture', '<figure', '<svg', 'data-src=', 'srcset=',
                'background-image:', 'loading="lazy"', "loading='lazy'",
            ])
            if not has_images and len(body_html) > 200:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "seo_no_images", "severity": "low"})

        # Orphan — only if link resolution is reliable (production quality gate)
        if link_resolution_reliable:
            if inbound_counts.get(i, 0) == 0 and wc >= 200:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "orphan", "severity": "high"})

        # Decay (production 3-signal proxy decay with word-boundary keywords)
        last_updated = getattr(p, 'modified_date', None) or getattr(p, 'publish_date', None)
        if last_updated:
            now = datetime.now(UTC)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            months = (now - last_updated).days / 30.44
            if months > 18:
                # 3-signal decay: pick the most severe that applies, then
                # fall through (no continue) so AI citability checks still run
                decay_type = None
                # Signal 1: Outdated year in title
                year_match = re.search(r'((?:19|20)\d{2})', title)
                if year_match:
                    ref_year = int(year_match.group(1))
                    if 1990 <= ref_year <= now.year and ref_year < now.year - 1:
                        decay_type = "decay_severe"
                # Signal 2: Time-sensitive keywords (word boundaries)
                if not decay_type and re.search(r'\bbest\b|\btop\s+\d|\breview\b|\bpricing\b|\bcompare\b|\bvs\b', title.lower()):
                    decay_type = "decay_moderate"
                # Signal 3: General staleness (fallthrough)
                if not decay_type:
                    decay_type = "decay_mild"
                severity = "high" if decay_type == "decay_severe" else "medium"
                problems.append({"post_index": i, "title": title, "url": url,
                                 "problem_type": decay_type, "severity": severity,
                                 "months_stale": round(months, 1)})

        # Readability too complex (industry-adaptive: use 50 as default)
        if readability_lookup and url in readability_lookup:
            fre = readability_lookup[url]
            if fre < 50:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "readability_too_complex",
                                 "severity": "high" if fre < 30 else "medium", "flesch_score": round(fre, 1)})

        # AI citability problems
        if ai_results_lookup and url in ai_results_lookup:
            ai = ai_results_lookup[url]
            if ai.get("cite", 100) < 30:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "low_ai_citability",
                                 "severity": "medium", "citability_score": ai["cite"]})
            if ai.get("eeat", 100) < 20:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "weak_eeat",
                                 "severity": "medium", "eeat_score": ai["eeat"]})
            if ai.get("schema", 100) == 0:
                problems.append({"post_index": i, "title": title, "url": url, "problem_type": "missing_schema", "severity": "low"})

    return problems


# ═══════════════════════════════════════════════════════════════════════
# RECOMMENDATIONS (from test_step10b_e2e.py)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SimulatedRec:
    id: str
    post_index: int
    post_title: str
    url: str
    word_count: int
    body_excerpt: str
    recommendation_type: str
    title: str
    summary: str
    specific_actions: list
    priority: str
    estimated_effort_hours: float
    confidence: str = "medium"
    source: str = "problem"
    overlapping_title: str = ""
    overlapping_url: str = ""
    overlapping_wc: int = 0
    overlapping_excerpt: str = ""


def _format_staleness(months):
    """Format months_stale into human-readable text."""
    m = int(months) if months else 0
    if m <= 0:
        return "a long time"
    if m >= 24:
        years = m / 12
        return f"{years:.1f} years" if years != int(years) else f"{int(years)} years"
    return f"{m} months"


def generate_recommendations(posts, problems, cann_pairs):
    """Generate template recommendations — mirrors production fast_recommendations.py."""
    recs = []
    rec_counter = 0
    seen_post_type = {}  # Maps (post_index, ptype) or (post_index, title) → rec/True

    # ── Site-level aggregation (production fix) ──
    # Count unique posts per problem type
    total_posts = len(posts)
    ptype_post_counts = Counter()
    for prob in problems:
        ptype_post_counts[(prob["problem_type"], prob["post_index"])] = 1
    ptype_counts = Counter()
    for (ptype, _pi) in ptype_post_counts:
        ptype_counts[ptype] += 1
    aggregated_types = {pt for pt, cnt in ptype_counts.items() if cnt / max(total_posts, 1) > 0.30}
    aggregated_per_post = {pt: 0 for pt in aggregated_types}
    AGG_LIMIT = 10

    for prob in problems:
        i = prob["post_index"]
        ptype = prob["problem_type"]
        key = (i, ptype)
        if key in seen_post_type:
            continue
        seen_post_type[key] = True

        # For aggregated types, limit per-post recs
        if ptype in aggregated_types:
            aggregated_per_post[ptype] += 1
            if aggregated_per_post[ptype] > AGG_LIMIT:
                continue

        p = posts[i]
        wc = getattr(p, 'word_count', 0) or 0
        body = (getattr(p, 'body_text', '') or '')[:1500]
        months = prob.get("months_stale", 0)

        if ptype == "thin_content":
            rec_type, title_tpl, priority = "expand", "Expand thin content: {title}", "high" if wc < 300 else "medium"
            summary = f"This post has {wc} words, below the 500-word threshold."
            actions = ["Add 500+ words of substantive content", "Research competitor coverage", "Add examples and data"]
            effort = 2.0
        elif ptype == "seo_missing_meta":
            rec_type, title_tpl, priority = "optimize", "Add meta description: {title}", "medium"
            summary = "No meta description. Google will auto-generate one."
            actions = ["Write 150-160 char meta description", "Include primary keyword", "Add compelling CTA"]
            effort = 0.25
        elif ptype == "decay_severe":
            rec_type, title_tpl, priority = "update", "Urgent: update decaying content: {title}", "high"
            summary = f"This post hasn't been updated in {_format_staleness(months)}. Stale content loses both Google rankings and AI citations."
            actions = ["Update all statistics and data points", "Add visible 'Last updated' date", "Refresh intro with TL;DR answer", "Add FAQ section"]
            effort = 2.0
        elif ptype == "decay_moderate":
            rec_type, title_tpl, priority = "update", "Refresh stale content: {title}", "medium"
            summary = f"This post hasn't been updated in {_format_staleness(months)}. AI systems replace older sources with fresher competitors."
            actions = ["Update 'Last updated' date", "Refresh statistics older than 6 months", "Add 1-2 new insights or data points"]
            effort = 1.0
        elif ptype == "decay_mild":
            rec_type, title_tpl, priority = "refresh", "Consider refreshing older content: {title}", "low"
            summary = f"This post hasn't been updated in {_format_staleness(months)}. Periodic refreshes maintain relevance."
            actions = ["Update published/modified date", "Check for outdated references", "Add a recent example or data point"]
            effort = 0.5
        elif ptype == "orphan":
            rec_type, title_tpl, priority = "interlink", "Fix orphan page: {title}", "high"
            summary = "No internal links point to this post. Orphan pages get minimal crawl budget."
            actions = ["Add links from at least 3 related posts", "Link from highest-traffic posts in same cluster", "Use descriptive anchor text"]
            effort = 0.5
        elif ptype == "readability_too_complex":
            rec_type, title_tpl, priority = "optimize", "Simplify readability: {title}", "medium"
            summary = f"Flesch Reading Ease is {prob.get('flesch_score', 'N/A')}, below threshold."
            actions = ["Shorten sentences to under 20 words", "Replace jargon with plain language", "Break long paragraphs"]
            effort = 1.0
        elif ptype == "low_ai_citability":
            rec_type, title_tpl, priority = "optimize", "Improve AI citability: {title}", "medium"
            summary = f"AI citability score is {prob.get('citability_score', 'N/A')}/100."
            actions = ["Add data tables", "Include first-person experience language", "Add original statistics"]
            effort = 2.0
        elif ptype == "missing_schema":
            rec_type, title_tpl, priority = "add_schema", "Add JSON-LD schema: {title}", "high"
            summary = "No structured data detected. Schema markup increases AI Overview and rich result eligibility."
            actions = ["Add Article JSON-LD", "Add FAQPage schema if applicable", "Validate at schema.org/validator"]
            effort = 0.5
        elif ptype == "seo_no_headings":
            rec_type, title_tpl, priority = "optimize", "Add heading structure: {title}", "medium"
            summary = "No H2+ headings found. Headings improve scannability, SEO, and AI extraction."
            actions = ["Add 3-5 descriptive H2 headings", "Use H3s for subsections", "Include keywords in at least one H2"]
            effort = 0.5
        elif ptype == "seo_title_length":
            rec_type, title_tpl, priority = "optimize", "Fix title length: {title}", "low"
            summary = f"Title is {prob.get('title_length', '?')} chars (ideal: 30-70)."
            actions = ["Adjust title to 30-70 characters", "Front-load primary keyword"]
            effort = 0.25
        elif ptype == "weak_eeat":
            rec_type, title_tpl, priority = "strengthen_eeat", "Strengthen E-E-A-T signals: {title}", "medium"
            summary = f"Weak E-E-A-T signals (score: {prob.get('eeat_score', '?')}/100)."
            actions = ["Add author byline and bio", "Display visible publish/update date", "Add external source links"]
            effort = 1.0
        elif ptype == "poor_ai_structure":
            rec_type, title_tpl, priority = "improve_ai_structure", "Restructure for AI extraction: {title}", "medium"
            summary = f"AI extraction score: {prob.get('extraction_score', '?')}/100."
            actions = ["Front-load answer in first 200 words", "Start H2 sections with direct answers", "Add TL;DR section"]
            effort = 1.5
        elif ptype == "thin_below_cluster_avg":
            rec_type, title_tpl, priority = "expand", "Expand to match cluster depth: {title}", "medium"
            summary = f"At {wc} words, below cluster average."
            actions = ["Expand content to reach cluster average", "Study top posts in cluster for ideas"]
            effort = 1.5
        elif ptype == "geo_no_faq_section":
            rec_type, title_tpl, priority = "add_faq_section", "Add FAQ section for AI citation: {title}", "medium"
            summary = "No FAQ section. FAQ sections boost AI citation likelihood."
            actions = ["Add H2 FAQ section with 3-5 Q&A pairs", "Add FAQPage JSON-LD schema"]
            effort = 1.0
        elif ptype == "geo_no_question_headers":
            rec_type, title_tpl, priority = "reformat_headers_geo", "Reformat headers as questions: {title}", "medium"
            summary = "Low question-format header ratio. AI matches prompts to question headers."
            actions = ["Reformat 25-35% of headers as questions", "Follow each question header with a direct answer"]
            effort = 0.5
        elif ptype == "geo_low_data_density":
            rec_type, title_tpl, priority = "increase_data_density", "Add data points for AI citation: {title}", "medium"
            summary = "Low data density. AI systems cite data-rich content more often."
            actions = ["Add specific statistics with numbers", "Include 1 data point per 200 words"]
            effort = 1.5
        elif ptype == "geo_no_answer_first":
            rec_type, title_tpl, priority = "add_answer_first", "Add TL;DR for AI extraction: {title}", "medium"
            summary = "First 200 words don't directly answer the query."
            actions = ["Add TL;DR in first 200 words", "Use declarative answer language"]
            effort = 0.5
        elif ptype == "geo_missing_faq_schema":
            rec_type, title_tpl, priority = "add_faq_schema", "Add FAQPage schema markup: {title}", "high"
            summary = "Has FAQ content but no FAQPage JSON-LD schema."
            actions = ["Add FAQPage JSON-LD schema", "Validate at schema.org/validator"]
            effort = 0.5
        elif ptype == "geo_no_updated_date":
            rec_type, title_tpl, priority = "add_freshness_signal", "Add visible update date: {title}", "low"
            summary = "No visible 'Last updated' timestamp."
            actions = ["Add visible 'Last updated' element", "Update dateModified in Article schema"]
            effort = 0.25
        elif ptype == "seo_no_internal_links":
            rec_type, title_tpl, priority = "interlink", "Add internal links: {title}", "medium"
            summary = "No internal links point to this post."
            actions = ["Add links from 3 related posts", "Use descriptive anchor text"]
            effort = 0.5
        elif ptype == "seo_no_images":
            rec_type, title_tpl, priority = "optimize", "Add visual content: {title}", "low"
            summary = "No images detected in this post."
            actions = ["Add 1 relevant image per 300 words", "Include descriptive alt text"]
            effort = 0.5
        else:
            rec_type, title_tpl, priority = "optimize", f"Optimize ({ptype}): {{title}}", "medium"
            summary = f"Issue detected: {ptype}"
            actions = ["Review and fix the detected issue"]
            effort = 0.5

        final_title = title_tpl.format(title=(getattr(p, 'title', '') or '(no title)')[:60])

        # Title-level dedup: if two recs for the same post have identical titles,
        # merge their actions into one rec (combined actions, max effort).
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
            id=f"rec-{rec_counter:04d}", post_index=i,
            post_title=getattr(p, 'title', '') or "(no title)",
            url=getattr(p, 'url', ''), word_count=wc, body_excerpt=body,
            recommendation_type=rec_type,
            title=final_title,
            summary=summary, specific_actions=actions, priority=priority,
            estimated_effort_hours=effort, source="problem",
        )
        seen_post_type[title_key] = rec
        recs.append(rec)

    # ── Site-level summary recs for aggregated types ──
    _type_labels = {
        "seo_no_headings": "lack H2/H3 heading structure",
        "seo_missing_meta": "are missing a meta description",
        "decay_mild": "haven't been updated recently",
        "seo_no_images": "have no images",
        "seo_title_length": "have title length issues",
        "missing_schema": "are missing JSON-LD schema markup",
        "orphan": "are orphan pages with no inbound links",
    }
    for ptype in aggregated_types:
        count = ptype_counts[ptype]
        shown = min(AGG_LIMIT, count)
        label = _type_labels.get(ptype, f"have the '{ptype}' issue")
        rec_counter += 1
        recs.append(SimulatedRec(
            id=f"rec-{rec_counter:04d}", post_index=0,
            post_title="(site-level)", url="", word_count=0, body_excerpt="",
            recommendation_type="site_level",
            title=f"Site-wide: {count} of {total_posts} posts {label}",
            summary=f"{count} posts ({count * 100 // max(total_posts, 1)}% of site) {label}. Top {shown} have individual recs.",
            specific_actions=[
                f"Start with the {shown} individual recommendations",
                "Use batch workflow to fix remaining posts",
                "Prioritize highest-traffic pages first",
            ],
            priority="medium", estimated_effort_hours=2.0, source="aggregation",
        ))

    # ── Cannibalization recommendations ──
    for pair in cann_pairs[:50]:
        a_idx, b_idx = pair["post_a_idx"], pair["post_b_idx"]
        resolution = pair.get("resolution", "monitor")
        if resolution == "monitor":
            continue
        key = (a_idx, resolution)
        if key in seen_post_type:
            continue
        seen_post_type[key] = True
        p_a, p_b = posts[a_idx], posts[b_idx]
        if resolution in ("redirect", "merge"):
            rec_type, priority = "merge", "high" if pair["severity"] in ("critical", "high") else "medium"
        else:
            rec_type, priority = "differentiate", "medium"

        rec_counter += 1
        recs.append(SimulatedRec(
            id=f"rec-{rec_counter:04d}", post_index=a_idx,
            post_title=getattr(p_a, 'title', '') or "", url=getattr(p_a, 'url', ''),
            word_count=getattr(p_a, 'word_count', 0) or 0,
            body_excerpt=(getattr(p_a, 'body_text', '') or '')[:800],
            recommendation_type=rec_type,
            title=f"{rec_type.title()}: {(getattr(p_a, 'title', '') or '')[:50]}",
            summary=f"Overlaps with '{(getattr(p_b, 'title', '') or '')[:50]}' (blended: {pair['blended_score']}, resolution: {resolution})",
            specific_actions=[f"{rec_type.title()} these overlapping posts", "Review shared keyword coverage", "Consolidate or differentiate content angles"],
            priority=priority, estimated_effort_hours=3.0 if rec_type == "merge" else 1.5,
            source="cannibalization",
            overlapping_title=getattr(p_b, 'title', '') or "",
            overlapping_url=getattr(p_b, 'url', '') or "",
            overlapping_wc=getattr(p_b, 'word_count', 0) or 0,
            overlapping_excerpt=(getattr(p_b, 'body_text', '') or '')[:800],
        ))
    return recs


# ═══════════════════════════════════════════════════════════════════════
# CLAUDE ENRICHMENT - Step 10b (REAL Anthropic API)
# ═══════════════════════════════════════════════════════════════════════

def _build_enrichment_prompt(rec_type: str, context: str) -> str:
    """Build enrichment prompt (from test_step10b_e2e.py / on_demand_enrichment.py)."""
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


async def run_claude_enrichment(recs, posts, anthropic_client, max_recs=10):
    """Real Claude enrichment for top recommendations.

    Uses type-diverse selection: instead of pure priority ordering (which
    produces 10 identical add_schema enrichments), select up to 2 recs per
    recommendation_type from the top candidates. This ensures the enrichment
    budget covers different recommendation types (update, expand, add_schema,
    optimize, differentiate, etc.).
    """
    CLAUDE_MODEL = "claude-sonnet-4-20250514"
    priority_order = {"high": 0, "medium": 1, "low": 2}
    # Fetch more candidates than needed for type-diverse selection
    candidate_pool = sorted(recs, key=lambda r: priority_order.get(r.priority, 3))[:max_recs * 3]

    # Type-diverse selection: max 3 per recommendation_type
    MAX_PER_TYPE = 3
    type_counts: dict[str, int] = {}
    sorted_recs: list = []
    for rec in candidate_pool:
        rt = rec.recommendation_type
        if type_counts.get(rt, 0) < MAX_PER_TYPE:
            sorted_recs.append(rec)
            type_counts[rt] = type_counts.get(rt, 0) + 1
        if len(sorted_recs) >= max_recs:
            break
    # If we still have room, fill from remaining candidates
    if len(sorted_recs) < max_recs:
        selected_ids = {id(r) for r in sorted_recs}
        for rec in candidate_pool:
            if id(rec) not in selected_ids:
                sorted_recs.append(rec)
                if len(sorted_recs) >= max_recs:
                    break

    enriched = []
    total_input_tokens = 0
    total_output_tokens = 0

    for rec in sorted_recs:
        context = (
            f"Post: {rec.post_title}\nURL: {rec.url}\nWord count: {rec.word_count}\n"
            f"Recommendation: {rec.title}\n{rec.summary}"
        )
        if rec.recommendation_type in ("merge", "differentiate") and rec.overlapping_title:
            excerpt_a = _smart_excerpt(rec.body_excerpt, 600)
            excerpt_b = _smart_excerpt(rec.overlapping_excerpt, 600)
            context += (f"\n\nOverlapping post: {rec.overlapping_title}\nURL: {rec.overlapping_url}\n"
                        f"Word count: {rec.overlapping_wc}\n\nPost A excerpt:\n{excerpt_a}\n\nPost B excerpt:\n{excerpt_b}")
        else:
            context += f"\n\nContent excerpt:\n{rec.body_excerpt[:1200]}"

        prompt = _build_enrichment_prompt(rec.recommendation_type, context)

        try:
            response = await anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            response_text = response.content[0].text.strip()
            # Parse JSON (strip markdown fences if present)
            clean = response_text
            if clean.startswith("```"):
                clean = re.sub(r'^```\w*\n?', '', clean)
                clean = re.sub(r'\n?```\s*$', '', clean)
            try:
                ai_guidance = json.loads(clean)
            except json.JSONDecodeError:
                ai_guidance = {"raw_response": clean}

            enriched.append({"rec": rec, "ai_guidance": ai_guidance, "success": True})
            print(f"  Enriched: {rec.title[:60]}...")
        except Exception as e:
            enriched.append({"rec": rec, "ai_guidance": {}, "success": False, "error": str(e)})
            print(f"  ERROR enriching {rec.title[:40]}: {e}")

    stats = {"total_input_tokens": total_input_tokens, "total_output_tokens": total_output_tokens,
             "cost_usd": (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000}
    return enriched, stats


# ═══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════

async def main():
    from openai import AsyncOpenAI
    from anthropic import AsyncAnthropic

    from app.services.normalizer import (
        filter_nav_links, filter_sitewide_headings,
        _strip_site_name_from_title, _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.services.readability import compute_flesch_reading_ease, compute_grade_level
    from app.services.fast_intent import classify_intent
    from app.services.ai_citability import (
        compute_citability_score, compute_eeat_score,
        compute_schema_score, compute_extraction_score,
        generate_ai_problems,
    )
    from app.services.fast_cluster_labels import _compute_site_stops, _tfidf_label, _strip_format
    from app.services.health_scoring import (
        compute_dynamic_weights, _compute_trend, _freshness_score,
        _content_depth_score, _technical_seo_score,
        _predicted_engagement_score, _assign_role, _assign_ecosystem_state,
    )
    from app.utils.url_normalize import normalize_url

    openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    anthropic_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    L = []
    def w(s=""): L.append(s)
    timings = {}  # step -> seconds

    w(f"# Full Pipeline Results: {TARGET_DOMAIN}")
    w(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    w(f"**Target:** `{TARGET_SITEMAP}`")
    w(f"**Max pages cap:** {MAX_PAGES}")
    w(f"**Pipeline:** Steps 1 through 10b (ALL steps, real API calls)")
    w(f"**Embeddings:** OpenAI `{EMBED_MODEL}` (REAL, not synthetic)")
    w(f"**Chunk confirmation:** OpenAI `{EMBED_MODEL}` (REAL)")
    w(f"**Claude enrichment:** `claude-sonnet-4-20250514` (REAL)")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: CRAWL + NORMALIZE (from test_full_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 1: Crawl + Normalize")
    w()

    progress_log = []
    def on_progress(processed, total):
        progress_log.append((processed, total, time.time()))

    crawler = SitemapCrawler(
        sitemap_url=TARGET_SITEMAP, domain=TARGET_DOMAIN,
        delay_seconds=0.5, max_pages=MAX_PAGES, concurrency=10,
        max_retries=3, timeout_seconds=30.0, on_progress=on_progress,
    )

    print("=" * 70)
    print("STEP 1: Crawling...")
    t0 = time.time()
    raw_posts = await crawler.crawl()
    crawl_time = time.time() - t0
    timings["1_crawl"] = crawl_time

    skipped = getattr(crawler, '_skipped', [])
    skip_reasons = Counter(reason for _, reason in skipped)

    # Normalize (from test_full_e2e.py)
    seen = set()
    posts = []
    dupes = 0
    for p in raw_posts:
        norm = normalize_url(p.url)
        if norm not in seen:
            seen.add(norm)
            p.url = norm
            p.title = _strip_site_name_from_title(p.title)
            p.meta_description = _strip_html_from_meta(p.meta_description)
            posts.append(p)
        else:
            dupes += 1

    links_map = {p.url: p.internal_links for p in posts}
    headings_map = {p.url: p.headings for p in posts}
    filtered_links = filter_nav_links(links_map)
    filtered_headings = filter_sitewide_headings(headings_map)

    nav_removed = 0
    headings_removed = 0
    for p in posts:
        old_l = len(p.internal_links)
        p.internal_links = filtered_links.get(p.url, p.internal_links)
        nav_removed += old_l - len(p.internal_links)
        old_h = len(p.headings)
        p.headings = filtered_headings.get(p.url, p.headings)
        headings_removed += old_h - len(p.headings)

    total = len(posts)
    print(f"  {total} posts normalized in {crawl_time:.1f}s")

    # Step 1 Report (from test_full_e2e.py)
    w("## 1.1 Crawl Summary")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Duration | {crawl_time:.1f}s |")
    w(f"| URLs discovered | {crawler._total} |")
    w(f"| Posts extracted | {len(raw_posts)} |")
    w(f"| Posts after dedup | {total} |")
    w(f"| Duplicates removed | {dupes} |")
    w(f"| URLs skipped | {len(skipped)} |")
    w(f"| Extraction rate | {len(raw_posts)/max(crawler._total,1)*100:.1f}% |")
    w(f"| Avg time per URL | {crawl_time/max(crawler._total,1):.2f}s |")
    w()

    if skip_reasons:
        w("### Skipped URLs")
        w()
        w("| Reason | Count |")
        w("|--------|-------|")
        for reason, count in skip_reasons.most_common():
            w(f"| `{reason}` | {count} |")
        w()
        for url, reason in skipped[:10]:
            w(f"- `{url}` -- {reason}")
        w()

    w("## 1.2 Normalization")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Nav links removed | {nav_removed} |")
    w(f"| Sitewide headings removed | {headings_removed} |")
    w(f"| URL duplicates removed | {dupes} |")
    w()

    word_counts = [p.word_count for p in posts]
    w("## 1.3 Content Statistics")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Total posts | {total} |")
    w(f"| Total words | {sum(word_counts):,} |")
    w(f"| Avg word count | {sum(word_counts)//max(total,1):,} |")
    w(f"| Median word count | {sorted(word_counts)[total//2]:,} |")
    w(f"| Min word count | {min(word_counts):,} |")
    w(f"| Max word count | {max(word_counts):,} |")
    w()

    page_types = Counter(p.page_type for p in posts)
    w("### Page Type Distribution")
    w()
    w("| Type | Count | % |")
    w("|------|-------|---|")
    for pt, c in page_types.most_common():
        w(f"| {pt} | {c} | {c/total*100:.1f}% |")
    w()

    langs = Counter(p.language for p in posts)
    w("### Language")
    w()
    w("| Language | Count |")
    w("|----------|-------|")
    for lang, c in langs.most_common():
        w(f"| {lang or 'None'} | {c} |")
    w()

    has_pub = sum(1 for p in posts if p.publish_date)
    has_mod = sum(1 for p in posts if p.modified_date)
    has_meta = sum(1 for p in posts if p.meta_description)
    has_head = sum(1 for p in posts if p.headings)
    has_lang = sum(1 for p in posts if p.language)
    w("## 1.4 Field Coverage")
    w()
    w("| Field | Has Value | Missing | Coverage |")
    w("|-------|-----------|---------|----------|")
    for name, has in [("publish_date", has_pub), ("modified_date", has_mod),
                       ("meta_description", has_meta), ("headings", has_head), ("language", has_lang)]:
        w(f"| {name} | {has} | {total - has} | {has/total*100:.1f}% |")
    w()

    total_links = sum(len(p.internal_links) for p in posts)
    posts_with_links = sum(1 for p in posts if p.internal_links)
    known_urls = {p.url for p in posts}
    resolvable = sum(1 for p in posts for l in p.internal_links if normalize_url(l.target_url) in known_urls)
    unresolvable = total_links - resolvable
    w("## 1.5 Internal Link Graph")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Total internal links | {total_links} |")
    w(f"| Posts with links | {posts_with_links} ({posts_with_links/total*100:.0f}%) |")
    w(f"| Avg links per post | {total_links/total:.1f} |")
    w(f"| Resolvable | {resolvable} ({resolvable/max(total_links,1)*100:.1f}%) |")
    w(f"| Unresolvable | {unresolvable} |")
    w(f"| Nav links filtered | {nav_removed} |")
    w()

    h_counts = Counter()
    for p in posts:
        for h in p.headings:
            h_counts[h.get("level", "?")] += 1
    w("## 1.6 Heading Structure")
    w()
    w("| Level | Count | Avg/Post |")
    w("|-------|-------|----------|")
    for lvl in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        c = h_counts.get(lvl, 0)
        if c > 0:
            w(f"| {lvl.upper()} | {c} | {c/total:.1f} |")
    w()

    # Filter landing/index pages from word count rankings
    content_posts = [p for p in posts if (getattr(p, 'page_type', 'blog') or 'blog') not in ('landing', 'index')]
    by_words = sorted(content_posts, key=lambda p: p.word_count)
    w("## 1.7 Longest Posts")
    w()
    w("| # | Title | Words | Type |")
    w("|---|-------|-------|------|")
    for i, p in enumerate(by_words[-10:][::-1], 1):
        t = p.title[:55] + "..." if len(p.title) > 55 else p.title
        w(f"| {i} | {t} | {p.word_count:,} | {p.page_type} |")
    w()

    w("## 1.8 Shortest Posts")
    w()
    w("| # | Title | Words | Type |")
    w("|---|-------|-------|------|")
    for i, p in enumerate(by_words[:10], 1):
        t = p.title[:55] + "..." if len(p.title) > 55 else p.title
        w(f"| {i} | {t} | {p.word_count:,} | {p.page_type} |")
    w()

    no_dates = [p for p in posts if not p.publish_date and not p.modified_date]
    if no_dates:
        w("## 1.9 Posts Missing Both Dates")
        w()
        w(f"**{len(no_dates)} posts** have no publish_date or modified_date:")
        w()
        for p in no_dates[:15]:
            u = p.url.replace(f"https://{TARGET_DOMAIN}", "")
            w(f"- `{u}` -- {p.word_count} words, type: {p.page_type}")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: REAL OPENAI EMBEDDINGS
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 2: OpenAI Embeddings (REAL)")
    w()

    print("\nSTEP 2: Generating REAL OpenAI embeddings...")
    t1 = time.time()
    embeddings, embedded_indices, embed_stats = await _generate_real_embeddings(posts, openai_client)
    embed_time = time.time() - t1
    timings["2_embeddings"] = embed_time

    w("## 2.1 Embedding Results")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Model | `{EMBED_MODEL}` |")
    w(f"| Dimensions | {EMBED_DIMS} |")
    w(f"| Posts to embed | {embed_stats['total_embeddable']} |")
    w(f"| Short posts (batchable) | {embed_stats['short_posts']} |")
    w(f"| Long posts (chunked) | {embed_stats['long_posts']} |")
    w(f"| Total chunks | {embed_stats['total_chunks']} |")
    w(f"| API calls | {embed_stats['api_calls']} |")
    w(f"| Total tokens | {embed_stats['total_tokens']:,} |")
    w(f"| **Cost** | **${embed_stats['cost_usd']:.4f}** |")
    w(f"| Successfully embedded | {embed_stats['embedded_count']} |")
    w(f"| Duration | {embed_time:.1f}s |")
    w()

    # Filter to only embedded posts for subsequent steps
    posts_filtered = [p for i, p in enumerate(posts) if i in embedded_indices]
    embeddings_filtered = embeddings[list(sorted(embedded_indices))]
    # Re-index
    idx_map = {old: new for new, old in enumerate(sorted(embedded_indices))}
    posts = posts_filtered
    embeddings = embeddings_filtered
    n_posts = len(posts)

    # Pairwise similarity analysis (from test_step6_e2e.py)
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim
    sample_size = min(100, n_posts)
    sample_indices_arr = np.random.choice(n_posts, sample_size, replace=False)
    sample = embeddings[sample_indices_arr]
    sim_matrix = cos_sim(sample)
    np.fill_diagonal(sim_matrix, 0)
    mean_sim = float(sim_matrix.mean())
    max_sim = float(sim_matrix.max())

    w("## 2.2 Embedding Similarity Analysis")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts with embeddings | {n_posts} |")
    w(f"| **Mean pairwise cosine similarity** | **{mean_sim:.4f}** |")
    w(f"| Max pairwise cosine similarity | {max_sim:.4f} |")
    w(f"| Min pairwise cosine similarity | {float(sim_matrix[sim_matrix > 0].min()):.4f} |")
    w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: READABILITY (from test_full_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 3: Readability")
    w()

    print("\nSTEP 3: Readability scoring...")
    t2 = time.time()
    readability = []
    for p in posts:
        if not p.body_text or len(p.body_text) < 100:
            continue
        fre = compute_flesch_reading_ease(p.body_text)
        grade = compute_grade_level(p.body_text)
        readability.append({"url": p.url, "title": p.title, "fre": fre, "grade": grade, "words": p.word_count})
    read_time = time.time() - t2
    timings["3_readability"] = read_time

    fre_scores = [r["fre"] for r in readability]
    grade_scores = [r["grade"] for r in readability]
    readability_lookup = {r["url"]: r["fre"] for r in readability}

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts scored | {len(readability)} |")
    w(f"| Processing time | {read_time:.3f}s |")
    w(f"| **Avg Flesch Reading Ease** | **{_avg(fre_scores):.1f}** |")
    w(f"| **Avg Grade Level** | **{_avg(grade_scores):.1f}** |")
    w(f"| Min FRE | {min(fre_scores):.1f} |")
    w(f"| Max FRE | {max(fre_scores):.1f} |")
    w()

    w("### Distribution")
    w()
    w("| Range | Label | Count | % |")
    w("|-------|-------|-------|---|")
    ranges = [(90,100,"Very easy"),(80,89,"Easy"),(70,79,"Fairly easy"),
              (60,69,"Standard"),(50,59,"Fairly difficult"),(30,49,"Difficult"),(0,29,"Very confusing")]
    for lo, hi, label in ranges:
        c = sum(1 for s in fre_scores if lo <= s <= hi)
        w(f"| {lo}-{hi} | {label} | {c} | {c/len(fre_scores)*100:.0f}% |")
    w()

    by_fre = sorted(readability, key=lambda r: r["fre"])
    w("### Hardest to Read (Bottom 5)")
    w()
    w("| Title | FRE | Grade | Words |")
    w("|-------|-----|-------|-------|")
    for r in by_fre[:5]:
        t = r["title"][:50] + "..." if len(r["title"]) > 50 else r["title"]
        w(f"| {t} | {r['fre']:.1f} | {r['grade']:.1f} | {r['words']:,} |")
    w()

    w("### Easiest to Read (Top 5)")
    w()
    w("| Title | FRE | Grade | Words |")
    w("|-------|-----|-------|-------|")
    for r in by_fre[-5:][::-1]:
        t = r["title"][:50] + "..." if len(r["title"]) > 50 else r["title"]
        w(f"| {t} | {r['fre']:.1f} | {r['grade']:.1f} | {r['words']:,} |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: PAGERANK (in-memory with networkx)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 4: Internal PageRank")
    w()

    print("\nSTEP 4: Computing internal PageRank...")
    t3 = time.time()
    import networkx as nx
    url_to_idx = {p.url: i for i, p in enumerate(posts)}
    G = nx.DiGraph()
    G.add_nodes_from(range(n_posts))
    edge_count = 0
    for i, p in enumerate(posts):
        for link in p.internal_links:
            target_url = link.target_url if hasattr(link, 'target_url') else (link.get("target_url") if isinstance(link, dict) else str(link))
            target_idx = url_to_idx.get(target_url)
            if target_idx is not None and target_idx != i:
                G.add_edge(i, target_idx)
                edge_count += 1

    pr_scores = nx.pagerank(G, alpha=0.85) if edge_count > 0 else {i: 1.0/n_posts for i in range(n_posts)}
    pagerank_time = time.time() - t3
    timings["4_pagerank"] = pagerank_time

    pr_values = list(pr_scores.values())
    top_pr = sorted([(i, s) for i, s in pr_scores.items()], key=lambda x: -x[1])

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Nodes (posts) | {n_posts} |")
    w(f"| Edges (internal links) | {edge_count} |")
    w(f"| Avg PageRank | {_avg(pr_values):.6f} |")
    w(f"| Max PageRank | {max(pr_values):.6f} |")
    w(f"| Min PageRank | {min(pr_values):.6f} |")
    w(f"| Duration | {pagerank_time:.3f}s |")
    w()

    w("### Top 10 by Internal Authority")
    w()
    w("| # | Title | PageRank | Inbound Links |")
    w("|---|-------|----------|---------------|")
    for rank, (idx, score) in enumerate(top_pr[:10], 1):
        t = posts[idx].title[:50] + "..." if len(posts[idx].title) > 50 else posts[idx].title
        inbound = G.in_degree(idx)
        w(f"| {rank} | {t} | {score:.6f} | {inbound} |")
    w()

    w("### Bottom 10 (Lowest Authority)")
    w()
    w("| # | Title | PageRank | Inbound Links |")
    w("|---|-------|----------|---------------|")
    for rank, (idx, score) in enumerate(top_pr[-10:][::-1], 1):
        t = posts[idx].title[:50] + "..." if len(posts[idx].title) > 50 else posts[idx].title
        inbound = G.in_degree(idx)
        w(f"| {rank} | {t} | {score:.6f} | {inbound} |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: INTENT CLASSIFICATION (from test_full_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 5: Intent Classification")
    w()

    print("\nSTEP 5: Intent classification...")
    t4 = time.time()
    intents = []
    for p in posts:
        intent = classify_intent(p.title or "", p.url or "", p.word_count or 0)
        intents.append({"url": p.url, "title": p.title, "intent": intent})
    intent_time = time.time() - t4
    timings["5_intent"] = intent_time
    intent_dist = Counter(r["intent"] for r in intents)

    w("| Intent | Count | % |")
    w("|--------|-------|---|")
    for intent, c in intent_dist.most_common():
        w(f"| {intent} | {c} | {c/len(intents)*100:.1f}% |")
    w()

    non_info = [r for r in intents if r["intent"] != "informational"]
    if non_info:
        w("### Non-Informational Posts")
        w()
        w("| Intent | Title | URL |")
        w("|--------|-------|-----|")
        for r in non_info:
            t = r["title"][:45] + "..." if len(r["title"]) > 45 else r["title"]
            u = r["url"].replace(f"https://{TARGET_DOMAIN}", "")
            w(f"| {r['intent']} | {t} | `{u}` |")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: CLUSTERING (from test_step6_e2e.py — with REAL embeddings)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 6: Clustering (UMAP + HDBSCAN)")
    w()

    print("\nSTEP 6: Clustering with REAL embeddings...")
    t5 = time.time()
    cl_result = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - t5
    timings["6_clustering"] = cluster_time

    labels = cl_result["labels"]
    cluster_groups = cl_result["cluster_groups"]
    n_clusters = cl_result["n_clusters"]

    w("## 6.1 UMAP + HDBSCAN Results")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Site type (auto-detected) | {cl_result['niche_type']} (mean_sim={cl_result['mean_sim']:.4f}) |")
    w(f"| UMAP n_components | {cl_result['n_components']} |")
    w(f"| UMAP n_neighbors | {cl_result['n_neighbors']} |")
    w(f"| UMAP min_dist | {cl_result['min_dist']} |")
    w(f"| HDBSCAN min_cluster_size | {cl_result['min_cluster_size']} |")
    w(f"| HDBSCAN min_samples | {cl_result['min_samples']} |")
    w(f"| **Clusters found** | **{n_clusters}** |")
    w(f"| Noise points (before reassignment) | {cl_result['original_noise']} |")
    w(f"| **Avg silhouette score** | **{cl_result['avg_silhouette']:.4f}** |")
    w(f"| Quality retries | {cl_result['retry_count']} |")
    w(f"| Duration | {cluster_time:.2f}s |")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6b: TF-IDF CLUSTER LABELS (from test_step6_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("## 6b. TF-IDF Cluster Labels")
    w()

    print("\nSTEP 6b: TF-IDF cluster labeling...")
    t5b = time.time()
    titles = [p.title or "" for p in posts]
    site_stops = _compute_site_stops(titles)
    cluster_labels = {}
    for cl_id, indices in cluster_groups.items():
        cl_titles = [titles[i] for i in indices]
        label, _, _ = _tfidf_label(cl_titles, titles, site_stops=site_stops)
        cluster_labels[cl_id] = label
    label_time = time.time() - t5b
    timings["6b_labels"] = label_time

    # ── Claude label upgrade for cold outreach ($0.02) ──
    # TF-IDF labels are clean but vague ("Content", "Copy"). Claude produces
    # "Content Marketing & SEO Strategy", "Copywriting Techniques" — more
    # descriptive and credible for cold outreach PDFs.
    print("  Upgrading labels with Claude...")
    CLAUDE_LABEL_MODEL = "claude-sonnet-4-20250514"
    claude_labels = {}
    for cl_id, indices in cluster_groups.items():
        cl_titles = [titles[i] for i in indices[:15]]
        if not cl_titles:
            continue
        prompt = (
            f"These are {len(cl_titles)} blog post titles from {TARGET_DOMAIN}, "
            "all in the same topic cluster.\n\n"
            "Titles:\n" + "\n".join(f"- {t}" for t in cl_titles) +
            "\n\nWhat topic do these posts share? Respond with ONLY a 2-4 word "
            "topic label.\nExamples: \"Email Marketing\", \"Link Building Guides\", "
            "\"Copywriting Techniques\", \"SEO Strategy\"\n"
            "Do not include the site name. Do not include format words like "
            "\"guide\" or \"post\" unless the topic IS about guides/posts."
        )
        try:
            resp = await anthropic_client.messages.create(
                model=CLAUDE_LABEL_MODEL, max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            label = resp.content[0].text.strip().strip('"').strip("'")
            if label and len(label) >= 3:
                claude_labels[cl_id] = label
        except Exception as e:
            print(f"  Claude label failed for cluster {cl_id}: {e}")
    # Merge: use Claude label if available, fall back to TF-IDF
    for cl_id in cluster_labels:
        if cl_id in claude_labels:
            cluster_labels[cl_id] = claude_labels[cl_id]

    w("| Cluster | Label | Posts | Silhouette | Sample Titles |")
    w("|---------|-------|-------|-----------|---------------|")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        indices = cluster_groups[cl_id]
        sil = cl_result["cluster_silhouettes"].get(cl_id, 0)
        label = cluster_labels.get(cl_id, "?")
        sample = [titles[i][:40] for i in indices[:2]]
        w(f"| {cl_id} | **{label}** | {len(indices)} | {sil:.3f} | {'; '.join(sample)} |")
    w()

    # Cluster size distribution
    cluster_sizes = [len(indices) for indices in cluster_groups.values()]
    w("### Cluster Size Distribution")
    w()
    w("| Size Range | Count |")
    w("|-----------|-------|")
    for lo, hi, rl in [(1,5,"1-5"),(6,10,"6-10"),(11,15,"11-15"),(16,25,"16-25"),(26,50,"26-50"),(51,999,"51+")]:
        count = sum(1 for s in cluster_sizes if lo <= s <= hi)
        if count > 0:
            w(f"| {rl} | {count} |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6c: AI CITABILITY SCORING (from test_full_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 6c: AI Citability Scoring")
    w()

    print("\nSTEP 6c: AI Citability scoring...")
    t5c = time.time()
    all_word_counts = sorted(p.word_count for p in posts if p.body_text)
    site_median_words = all_word_counts[len(all_word_counts) // 2] if all_word_counts else 0

    ai_results = []
    all_ai_problems = []
    for p in posts:
        post_url = (p.url or "")
        if not p.body_text and not p.body_html:
            # No content to analyze, but still add to results with score 0
            # so missing_schema is detected for ALL posts, not just those with body content
            ai_results.append({"url": post_url, "title": p.title, "words": p.word_count or 0,
                               "cite": 0, "eeat": 0, "schema": 0, "extract": 0,
                               "signals": {}, "problems": 0})
            continue
        cite, cite_sig = compute_citability_score(p.body_text or "", p.body_html)
        eeat, eeat_sig = compute_eeat_score(
            p.body_html, crawl_eeat=p.eeat_signals, headings=p.headings,
            word_count=p.word_count, site_median_words=site_median_words,
            publish_date=p.publish_date, modified_date=p.modified_date,
        )
        schema, schema_sig = compute_schema_score(p.body_html)
        extract, extract_sig = compute_extraction_score(p.body_text, p.body_html, p.headings)
        all_sig = {**cite_sig, **{f"eeat_{k}": v for k, v in eeat_sig.items()},
                   **{f"schema_{k}": v for k, v in schema_sig.items()},
                   **{f"extract_{k}": v for k, v in extract_sig.items()}}
        ai_probs = generate_ai_problems(post_url, p.title, cite, eeat, schema, extract, all_sig)
        all_ai_problems.extend(ai_probs)
        ai_results.append({"url": post_url, "title": p.title, "words": p.word_count,
                           "cite": cite, "eeat": eeat, "schema": schema, "extract": extract,
                           "signals": all_sig, "problems": len(ai_probs)})
    ai_time = time.time() - t5c
    timings["6c_citability"] = ai_time

    ai_results_lookup = {r["url"]: r for r in ai_results}
    cite_scores = [r["cite"] for r in ai_results]
    eeat_scores = [r["eeat"] for r in ai_results]
    schema_scores = [r["schema"] for r in ai_results]
    extract_scores = [r["extract"] for r in ai_results]

    w("| Dimension | Avg | Min | Max | Median |")
    w("|-----------|-----|-----|-----|--------|")
    for name, scores in [("Citability", cite_scores), ("E-E-A-T", eeat_scores),
                          ("Schema", schema_scores), ("Extraction", extract_scores)]:
        s = sorted(scores)
        w(f"| {name} | {_avg(s):.1f} | {min(s)} | {max(s)} | {s[len(s)//2]} |")
    w()

    ai_ready = sum(1 for s in cite_scores if s >= 60)
    w(f"**AI-ready posts (citability >= 60):** {ai_ready} ({ai_ready/len(cite_scores)*100:.1f}%)")
    w()

    # Filter out landing/index pages from AI readiness rankings
    _content_ai = [r for r in ai_results
                   if (getattr(next((p for p in posts if (p.url or "") == r["url"]), None), "page_type", "blog") or "blog")
                   not in ("landing", "index")]
    by_cite = sorted(_content_ai, key=lambda r: r["cite"], reverse=True)
    w("### Top 10 Most AI-Ready")
    w()
    w("| # | Title | Cite | EEAT | Schema | Extract | Words |")
    w("|---|-------|------|------|--------|---------|-------|")
    for i, r in enumerate(by_cite[:10], 1):
        t = r["title"][:40] + "..." if len(r["title"]) > 40 else r["title"]
        w(f"| {i} | {t} | {r['cite']} | {r['eeat']} | {r['schema']} | {r['extract']} | {r['words']:,} |")
    w()

    w("### Bottom 10 Least AI-Ready")
    w()
    w("| # | Title | Cite | EEAT | Schema | Extract | Words |")
    w("|---|-------|------|------|--------|---------|-------|")
    for i, r in enumerate(by_cite[-10:][::-1], 1):
        t = r["title"][:40] + "..." if len(r["title"]) > 40 else r["title"]
        w(f"| {i} | {t} | {r['cite']} | {r['eeat']} | {r['schema']} | {r['extract']} | {r['words']:,} |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 7: HEALTH SCORING (from test_step7_e2e.py — crawl-only mode)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 7: Health Scoring (Crawl-Only Mode)")
    w()

    print("\nSTEP 7: Health scoring...")
    t6 = time.time()
    now = datetime.now(UTC)
    weights = compute_dynamic_weights(has_ga4=False, has_gsc=False)

    w("## 7.1 Weight Distribution (Crawl-Only)")
    w()
    w("| Factor | Weight |")
    w("|--------|--------|")
    for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
        if weight > 0:
            w(f"| {factor} | {weight:.0%} |")
    w()

    # Pre-compute cluster averages and link counts
    post_cluster_map = {}
    for cl_id, indices in cluster_groups.items():
        for idx in indices:
            post_cluster_map[idx] = cl_id

    cluster_avg_wc = {}
    for cl_id, indices in cluster_groups.items():
        wcs = [posts[i].word_count for i in indices if posts[i].word_count]
        cluster_avg_wc[cl_id] = sum(wcs) / len(wcs) if len(wcs) >= 3 else 1000.0

    inbound_counts = {i: G.in_degree(i) for i in range(n_posts)}
    outbound_counts = {i: G.out_degree(i) for i in range(n_posts)}
    max_inbound = max(inbound_counts.values()) if inbound_counts else 1

    # Score all posts
    health_scores = []
    for i, p in enumerate(posts):
        cl_id = post_cluster_map.get(i, 0)
        avg_wc = cluster_avg_wc.get(cl_id, 1000.0)
        last_updated = p.modified_date or p.publish_date
        eeat_data = p.eeat_signals if isinstance(p.eeat_signals, dict) else {}

        freshness = _freshness_score(last_updated, now, title=p.title or "", url=p.url)
        depth = _content_depth_score(p.word_count or 0, avg_wc, body_html=p.body_html)
        link_score = min(100.0, (inbound_counts.get(i, 0) / max(max_inbound, 1)) * 100.0)
        tech_seo = _technical_seo_score(p.meta_description, p.title, p.headings,
                                         has_outbound=outbound_counts.get(i, 0) > 0,
                                         has_inbound=inbound_counts.get(i, 0) > 0,
                                         body_html=p.body_html, eeat_metadata=eeat_data)
        ai_readiness = ai_results_lookup.get(p.url, {}).get("cite", 40.0)
        richness = _predicted_engagement_score(body_html=p.body_html, headings=p.headings)

        composite = (
            weights.get("freshness", 0) * freshness +
            weights.get("content_depth", 0) * depth +
            weights.get("internal_links", 0) * link_score +
            weights.get("technical_seo", 0) * tech_seo +
            weights.get("ai_readiness", 0) * ai_readiness +
            weights.get("content_richness", 0) * richness
        )

        health_scores.append({
            "index": i, "title": p.title, "url": p.url, "words": p.word_count,
            "composite": round(composite, 1),
            "freshness": round(freshness, 1), "depth": round(depth, 1),
            "links": round(link_score, 1), "tech_seo": round(tech_seo, 1),
            "ai_readiness": round(ai_readiness, 1), "richness": round(richness, 1),
        })

    health_time = time.time() - t6
    timings["7_health"] = health_time

    composites = [h["composite"] for h in health_scores]

    # Filter out landing/index pages from rankings — these aren't blog content
    # and showing "expand this 186-word homepage" as a Quick Win kills credibility
    _content_page_types = {"blog", "product", "glossary", "article", "resource"}
    by_health_all = sorted(health_scores, key=lambda h: -h["composite"])
    by_health = [h for h in by_health_all
                 if (getattr(posts[h["index"]], "page_type", "blog") or "blog") in _content_page_types]

    w("## 7.2 Score Distribution")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts scored | {len(health_scores)} |")
    w(f"| **Avg composite** | **{_avg(composites):.1f}** |")
    w(f"| Median composite | {sorted(composites)[len(composites)//2]:.1f} |")
    w(f"| Min composite | {min(composites):.1f} |")
    w(f"| Max composite | {max(composites):.1f} |")
    w(f"| Duration | {health_time:.3f}s |")
    w()

    w("### Top 15 Healthiest Posts")
    w()
    w("| # | Title | Composite | Fresh | Depth | Links | TechSEO | AI | Rich |")
    w("|---|-------|-----------|-------|-------|-------|---------|-----|------|")
    for rank, h in enumerate(by_health[:15], 1):
        t = h["title"][:35] + "..." if len(h["title"]) > 35 else h["title"]
        w(f"| {rank} | {t} | **{h['composite']}** | {h['freshness']} | {h['depth']} | {h['links']} | {h['tech_seo']} | {h['ai_readiness']} | {h['richness']} |")
    w()

    w("### Bottom 15 (Weakest Posts)")
    w()
    w("| # | Title | Composite | Fresh | Depth | Links | TechSEO | AI | Rich |")
    w("|---|-------|-----------|-------|-------|-------|---------|-----|------|")
    for rank, h in enumerate(by_health[-15:][::-1], 1):
        t = h["title"][:35] + "..." if len(h["title"]) > 35 else h["title"]
        w(f"| {rank} | {t} | **{h['composite']}** | {h['freshness']} | {h['depth']} | {h['links']} | {h['tech_seo']} | {h['ai_readiness']} | {h['richness']} |")
    w()

    # Per-cluster health
    w("### Per-Cluster Health")
    w()
    w("| Cluster | Label | Posts | Avg Health | Best Post | Worst Post |")
    w("|---------|-------|-------|-----------|-----------|------------|")
    for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
        indices = cluster_groups[cl_id]
        cl_health = [health_scores[i]["composite"] for i in indices]
        avg_h = _avg(cl_health)
        best_idx = indices[cl_health.index(max(cl_health))]
        worst_idx = indices[cl_health.index(min(cl_health))]
        label = cluster_labels.get(cl_id, "?")
        best_t = posts[best_idx].title[:25] + "..." if len(posts[best_idx].title) > 25 else posts[best_idx].title
        worst_t = posts[worst_idx].title[:25] + "..." if len(posts[worst_idx].title) > 25 else posts[worst_idx].title
        w(f"| {cl_id} | {label} | {len(indices)} | {avg_h:.1f} | {best_t} ({max(cl_health):.0f}) | {worst_t} ({min(cl_health):.0f}) |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 8: CANNIBALIZATION DETECTION (with REAL embeddings)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 8: Cannibalization Detection")
    w()

    print("\nSTEP 8: Cannibalization detection with REAL embeddings...")
    t7 = time.time()
    cann_pairs = detect_cannibalization(posts, embeddings, cluster_groups)
    cann_time = time.time() - t7
    timings["8_cannibalization"] = cann_time

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Pairs detected | {len(cann_pairs)} |")
    w(f"| Critical pairs | {sum(1 for p in cann_pairs if p['severity'] == 'critical')} |")
    w(f"| High pairs | {sum(1 for p in cann_pairs if p['severity'] == 'high')} |")
    w(f"| Medium pairs | {sum(1 for p in cann_pairs if p['severity'] == 'medium')} |")
    w(f"| Duration | {cann_time:.3f}s |")
    w()

    if cann_pairs:
        resolution_dist = Counter(p["resolution"] for p in cann_pairs)
        w("### Resolution Distribution")
        w()
        w("| Resolution | Count |")
        w("|-----------|-------|")
        for res, count in resolution_dist.most_common():
            w(f"| {res} | {count} |")
        w()

        w("### All Cannibalization Pairs")
        w()
        w("| # | Post A | Post B | Cosine | Blended | Severity | Resolution |")
        w("|---|--------|--------|--------|---------|----------|------------|")
        for rank, pair in enumerate(cann_pairs[:30], 1):
            ta = pair["title_a"][:30] + "..." if len(pair["title_a"]) > 30 else pair["title_a"]
            tb = pair["title_b"][:30] + "..." if len(pair["title_b"]) > 30 else pair["title_b"]
            w(f"| {rank} | {ta} | {tb} | {pair['cosine_similarity']:.3f} | {pair['blended_score']:.3f} | {pair['severity']} | {pair['resolution']} |")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 8b: CHUNK CONFIRMATION (REAL OpenAI)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 8b: Chunk-Level Confirmation (REAL OpenAI)")
    w()

    print("\nSTEP 8b: Chunk confirmation with REAL OpenAI embeddings...")
    t7b = time.time()
    chunk_results, chunk_stats = await run_chunk_confirmation(posts, cann_pairs, openai_client, max_pairs=min(20, len(cann_pairs)))
    chunk_time = time.time() - t7b
    timings["8b_chunks"] = chunk_time

    confirmed_count = sum(1 for r in chunk_results if r.get("confirmed") is True)
    denied_count = sum(1 for r in chunk_results if r.get("confirmed") is False)

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Pairs analyzed | {len(chunk_results)} |")
    w(f"| **Confirmed** | **{confirmed_count}** |")
    w(f"| Denied | {denied_count} |")
    w(f"| Threshold | 0.88 |")
    w(f"| API calls | {chunk_stats['api_calls']} |")
    w(f"| Tokens used | {chunk_stats['total_tokens']:,} |")
    w(f"| Duration | {chunk_time:.1f}s |")
    w()

    if chunk_results:
        w("### Chunk Confirmation Detail")
        w()
        w("| # | Post A | Post B | Post-Level Cos | Max Chunk Sim | Chunks A | Chunks B | Confirmed |")
        w("|---|--------|--------|---------------|--------------|---------|---------|-----------|")
        for rank, r in enumerate(chunk_results, 1):
            ta = r.get("title_a", "")[:25] + "..." if len(r.get("title_a", "")) > 25 else r.get("title_a", "")
            tb = r.get("title_b", "")[:25] + "..." if len(r.get("title_b", "")) > 25 else r.get("title_b", "")
            confirmed_str = "YES" if r.get("confirmed") else ("NO" if r.get("confirmed") is False else "N/A")
            w(f"| {rank} | {ta} | {tb} | {r.get('cosine_similarity', 0):.3f} | {r.get('max_chunk_sim', 0):.3f} | {r.get('chunks_a', 0)} | {r.get('chunks_b', 0)} | {confirmed_str} |")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 9: PROBLEM DETECTION (from test_step9_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 9: Problem Detection")
    w()

    print("\nSTEP 9: Problem detection...")
    t8 = time.time()
    problems = detect_problems(posts, cluster_groups, post_cluster_map, ai_results_lookup, readability_lookup)
    problem_time = time.time() - t8
    timings["9_problems"] = problem_time

    problem_dist = Counter(p["problem_type"] for p in problems)
    severity_dist = Counter(p["severity"] for p in problems)
    posts_with_problems = len(set(p["post_index"] for p in problems))

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| **Total problems** | **{len(problems)}** |")
    w(f"| Posts with problems | {posts_with_problems} ({posts_with_problems/n_posts*100:.0f}%) |")
    w(f"| Avg problems per post | {len(problems)/n_posts:.1f} |")
    w(f"| Duration | {problem_time:.3f}s |")
    w()

    w("### By Problem Type")
    w()
    w("| Problem Type | Count | % of Posts |")
    w("|-------------|-------|-----------|")
    for ptype, count in problem_dist.most_common():
        w(f"| `{ptype}` | {count} | {count/n_posts*100:.0f}% |")
    w()

    w("### By Severity")
    w()
    w("| Severity | Count |")
    w("|----------|-------|")
    for sev, count in severity_dist.most_common():
        w(f"| {sev} | {count} |")
    w()

    # Most problematic posts
    problem_count_per_post = Counter(p["post_index"] for p in problems)
    w("### Most Problematic Posts")
    w()
    w("| # | Title | Problems | Types |")
    w("|---|-------|----------|-------|")
    for rank, (idx, count) in enumerate(problem_count_per_post.most_common(15), 1):
        t = posts[idx].title[:40] + "..." if len(posts[idx].title) > 40 else posts[idx].title
        types = ", ".join(sorted(set(p["problem_type"] for p in problems if p["post_index"] == idx)))
        w(f"| {rank} | {t} | {count} | {types} |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 10: RECOMMENDATIONS (from test_step10b_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 10: Recommendations")
    w()

    print("\nSTEP 10: Generating recommendations...")
    t9 = time.time()
    recs = generate_recommendations(posts, problems, cann_pairs)
    rec_time = time.time() - t9
    timings["10_recommendations"] = rec_time

    rec_type_dist = Counter(r.recommendation_type for r in recs)
    priority_dist = Counter(r.priority for r in recs)

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| **Total recommendations** | **{len(recs)}** |")
    w(f"| High priority | {priority_dist.get('high', 0)} |")
    w(f"| Medium priority | {priority_dist.get('medium', 0)} |")
    w(f"| Low priority | {priority_dist.get('low', 0)} |")
    w(f"| Total estimated effort | {sum(r.estimated_effort_hours for r in recs):.1f} hours |")
    w()

    w("### By Type")
    w()
    w("| Type | Count |")
    w("|------|-------|")
    for rtype, count in rec_type_dist.most_common():
        w(f"| {rtype} | {count} |")
    w()

    w("### All Recommendations (sorted by priority)")
    w()
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_recs = sorted(recs, key=lambda r: (priority_order.get(r.priority, 3), -r.estimated_effort_hours))
    w("| # | Priority | Type | Title | Effort |")
    w("|---|----------|------|-------|--------|")
    for rank, r in enumerate(sorted_recs[:50], 1):
        t = r.title[:55] + "..." if len(r.title) > 55 else r.title
        w(f"| {rank} | {r.priority} | {r.recommendation_type} | {t} | {r.estimated_effort_hours}h |")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 10b: CLAUDE ENRICHMENT (REAL Anthropic API)
    # ═══════════════════════════════════════════════════════════════════
    w("# STEP 10b: Claude AI Enrichment (REAL)")
    w()

    print("\nSTEP 10b: Claude AI enrichment (REAL API calls)...")
    t10 = time.time()
    enriched, enrich_stats = await run_claude_enrichment(recs, posts, anthropic_client, max_recs=10)
    enrich_time = time.time() - t10
    timings["10b_enrichment"] = enrich_time

    successful = sum(1 for e in enriched if e["success"])
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Recommendations enriched | {len(enriched)} |")
    w(f"| Successful | {successful} |")
    w(f"| Failed | {len(enriched) - successful} |")
    w(f"| Input tokens | {enrich_stats['total_input_tokens']:,} |")
    w(f"| Output tokens | {enrich_stats['total_output_tokens']:,} |")
    w(f"| **Cost** | **${enrich_stats['cost_usd']:.4f}** |")
    w(f"| Duration | {enrich_time:.1f}s |")
    w()

    for rank, e in enumerate(enriched, 1):
        rec = e["rec"]
        w(f"## Enrichment {rank}: {rec.title[:60]}")
        w()
        w(f"**Type:** {rec.recommendation_type} | **Priority:** {rec.priority} | **Source:** {rec.source}")
        w(f"**Post:** {rec.post_title}")
        w(f"**URL:** `{rec.url}`")
        w(f"**Summary:** {rec.summary}")
        w()
        if e["success"]:
            w("### AI Guidance")
            w()
            w("```json")
            w(json.dumps(e["ai_guidance"], indent=2))
            w("```")
        else:
            w(f"**ERROR:** {e.get('error', 'Unknown error')}")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # CROSS-ANALYSIS (from test_full_e2e.py)
    # ═══════════════════════════════════════════════════════════════════
    w("# CROSS-ANALYSIS")
    w()

    w("## Readability vs Citability")
    w()
    easy = [r for r in ai_results if readability_lookup.get(r["url"], 0) >= 70]
    hard = [r for r in ai_results if readability_lookup.get(r["url"], 0) < 50]
    mid = [r for r in ai_results if 50 <= readability_lookup.get(r["url"], 0) < 70]
    w("| Readability | Posts | Avg Citability | Avg E-E-A-T |")
    w("|------------|-------|---------------|------------|")
    if easy: w(f"| Easy (FRE >= 70) | {len(easy)} | {_avg([r['cite'] for r in easy]):.1f} | {_avg([r['eeat'] for r in easy]):.1f} |")
    if mid: w(f"| Medium (FRE 50-69) | {len(mid)} | {_avg([r['cite'] for r in mid]):.1f} | {_avg([r['eeat'] for r in mid]):.1f} |")
    if hard: w(f"| Hard (FRE < 50) | {len(hard)} | {_avg([r['cite'] for r in hard]):.1f} | {_avg([r['eeat'] for r in hard]):.1f} |")
    w()

    w("## Word Count vs Citability")
    w()
    short_posts = [r for r in ai_results if r["words"] < 1000]
    med_posts = [r for r in ai_results if 1000 <= r["words"] < 3000]
    long_p = [r for r in ai_results if r["words"] >= 3000]
    w("| Length | Posts | Avg Citability | Avg Extraction |")
    w("|--------|-------|---------------|---------------|")
    if short_posts: w(f"| Short (<1K) | {len(short_posts)} | {_avg([r['cite'] for r in short_posts]):.1f} | {_avg([r['extract'] for r in short_posts]):.1f} |")
    if med_posts: w(f"| Medium (1-3K) | {len(med_posts)} | {_avg([r['cite'] for r in med_posts]):.1f} | {_avg([r['extract'] for r in med_posts]):.1f} |")
    if long_p: w(f"| Long (3K+) | {len(long_p)} | {_avg([r['cite'] for r in long_p]):.1f} | {_avg([r['extract'] for r in long_p]):.1f} |")
    w()

    w("## Health vs PageRank Correlation")
    w()
    health_by_idx = {h["index"]: h["composite"] for h in health_scores}
    health_list = [health_by_idx.get(i, 0) for i in range(n_posts)]
    pr_list = [pr_scores.get(i, 0) for i in range(n_posts)]
    corr = _pearson(health_list, pr_list)
    w(f"**Pearson correlation (Health vs PageRank):** {corr:.3f}")
    w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # SAMPLE POSTS (from test_full_e2e.py — 3 quality levels)
    # ═══════════════════════════════════════════════════════════════════
    w("# SAMPLE POSTS (Full Detail)")
    w()
    samples = [
        ("Best AI-Ready Post", by_cite[0]),
        ("Median Post", by_cite[len(by_cite)//2]),
        ("Worst AI-Ready Post", by_cite[-1]),
    ]
    for label, r in samples:
        w(f"## {label}")
        w()
        w(f"**Title:** {r['title']}")
        w(f"**URL:** `{r['url']}`")
        w(f"**Words:** {r['words']:,}")
        w()
        w("| Dimension | Score |")
        w("|-----------|-------|")
        w(f"| Citability | {r['cite']}/100 |")
        w(f"| E-E-A-T | {r['eeat']}/100 |")
        w(f"| Schema | {r['schema']}/100 |")
        w(f"| Extraction | {r['extract']}/100 |")
        w()
        sig = r["signals"]
        w("**Key Signals:**")
        w()
        w("| Signal | Value |")
        w("|--------|-------|")
        signal_keys = [
            ("data_tables", "Data tables"), ("numbered_list_items", "Numbered list items"),
            ("first_person_markers", "First-person markers"), ("stats_mentions", "Statistics"),
            ("definition_paragraphs", "Definitions"), ("entity_density_per_1k", "Entity density/1K"),
            ("citation_markers", "Citations"), ("question_headers", "Question headers"),
            ("total_headers", "Total headers"), ("eeat_author_found", "Author found"),
            ("eeat_author_name", "Author name"), ("eeat_has_author_bio", "Author bio"),
            ("eeat_has_visible_date", "Visible date"), ("eeat_date_age_days", "Date age (days)"),
            ("eeat_external_outbound_links", "External links"), ("schema_has_schema", "Has schema"),
            ("schema_schema_types", "Schema types"), ("extract_h2_with_direct_answer", "H2s with direct answer"),
            ("extract_total_h2", "Total H2s"), ("extract_has_faq_section", "FAQ section"),
            ("quotable_paragraphs", "Quotable paragraphs"),
        ]
        for key, label_str in signal_keys:
            val = sig.get(key)
            if val is not None and val != "" and val != [] and val != 0 and val is not False:
                w(f"| {label_str} | {val} |")
        w()

    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # PROCESSING SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    w("# PROCESSING SUMMARY")
    w()

    total_cost = embed_stats["cost_usd"] + enrich_stats["cost_usd"] + (chunk_stats["total_tokens"] / 1_000_000 * 0.02)
    total_time = sum(timings.values())

    w("| Step | Duration | External API | Cost |")
    w("|------|----------|-------------|------|")
    w(f"| 1. Crawl + Normalize | {timings.get('1_crawl', 0):.1f}s | None | $0 |")
    w(f"| 2. Embeddings (REAL OpenAI) | {timings.get('2_embeddings', 0):.1f}s | OpenAI | ${embed_stats['cost_usd']:.4f} |")
    w(f"| 3. Readability | {timings.get('3_readability', 0):.3f}s | None | $0 |")
    w(f"| 4. PageRank | {timings.get('4_pagerank', 0):.3f}s | None | $0 |")
    w(f"| 5. Intent | {timings.get('5_intent', 0):.4f}s | None | $0 |")
    w(f"| 6. Clustering (UMAP+HDBSCAN) | {timings.get('6_clustering', 0):.2f}s | None | $0 |")
    w(f"| 6b. TF-IDF Labels | {timings.get('6b_labels', 0):.3f}s | None | $0 |")
    w(f"| 6c. AI Citability | {timings.get('6c_citability', 0):.3f}s | None | $0 |")
    w(f"| 7. Health Scoring | {timings.get('7_health', 0):.3f}s | None | $0 |")
    w(f"| 8. Cannibalization | {timings.get('8_cannibalization', 0):.3f}s | None | $0 |")
    w(f"| 8b. Chunk Confirmation (REAL) | {timings.get('8b_chunks', 0):.1f}s | OpenAI | ${chunk_stats['total_tokens']/1_000_000*0.02:.4f} |")
    w(f"| 9. Problem Detection | {timings.get('9_problems', 0):.3f}s | None | $0 |")
    w(f"| 10. Recommendations | {timings.get('10_recommendations', 0):.3f}s | None | $0 |")
    w(f"| 10b. Claude Enrichment (REAL) | {timings.get('10b_enrichment', 0):.1f}s | Anthropic | ${enrich_stats['cost_usd']:.4f} |")
    w(f"| **TOTAL** | **{total_time:.0f}s** | | **${total_cost:.4f}** |")
    w()

    w("## Site Summary")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Domain | {TARGET_DOMAIN} |")
    w(f"| Total posts analyzed | {n_posts} |")
    w(f"| Total words | {sum(p.word_count for p in posts):,} |")
    w(f"| Clusters | {n_clusters} |")
    w(f"| Cannibalization pairs | {len(cann_pairs)} |")
    w(f"| Problems detected | {len(problems)} |")
    w(f"| Recommendations generated | {len(recs)} |")
    w(f"| AI-enriched recommendations | {successful} |")
    w(f"| Avg health score | {_avg(composites):.1f}/100 |")
    w(f"| Avg AI citability | {_avg(cite_scores):.1f}/100 |")
    w(f"| Total API cost | ${total_cost:.4f} |")
    w(f"| Total processing time | {total_time:.0f}s |")
    w()

    # Write markdown output
    report_md = "\n".join(L)
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "pipelineresults.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"\nReport written to {out_path} ({len(L)} lines)")

    # ── Generate PDF audit report ──
    print("\nGenerating PDF audit report...")
    try:
        from app.services.pdf_report import generate_audit_pdf

        # Build the report dict expected by generate_audit_pdf
        avg_health = _avg(composites)
        avg_cite = _avg(cite_scores)
        avg_eeat = _avg(eeat_scores)
        avg_schema = _avg(schema_scores)
        avg_extract = _avg(extract_scores)

        # Top clusters for PDF
        pdf_clusters = []
        for cl_id in sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k])):
            indices = cluster_groups[cl_id]
            cl_health_scores = [health_scores[i]["composite"] for i in indices if i < len(health_scores)]
            avg_cl_health = round(_avg(cl_health_scores), 1) if cl_health_scores else 0
            pdf_clusters.append({
                "label": cluster_labels.get(cl_id, "Unknown"),
                "post_count": len(indices),
                "health_score": avg_cl_health,
                "ecosystem_state": (
                    "forest" if avg_cl_health >= 65
                    else "meadow" if avg_cl_health >= 50
                    else "seedbed" if avg_cl_health >= 35
                    else "desert"
                ),
            })

        # Worst posts for PDF (bottom 5 by health)
        pdf_worst = []
        for h in by_health[-5:][::-1]:
            # Collect actual problem types for this post
            post_idx = h["index"]
            post_problems = [p["problem_type"] for p in problems if p["post_index"] == post_idx]
            post_meta = (getattr(posts[post_idx], "meta_description", "") or "").strip()
            # Look up actual citability score for this post
            post_url = (getattr(posts[post_idx], "url", "") or "")
            post_cite = next((r["cite"] for r in ai_results if r["url"] == post_url), 0)
            pdf_worst.append({
                "title": h["title"],
                "url": h["url"],
                "health_score": h["composite"],
                "word_count": h["words"],
                "meta_description": post_meta,
                "citability_score": round(post_cite),
                "issue": ", ".join(post_problems),
            })

        # Top recs for PDF
        pdf_recs = []
        for r in recs[:10]:
            pdf_recs.append({
                "title": r.title,
                "summary": r.summary,
                "rec_type": r.recommendation_type,
                "post_title": r.post_title,
                "priority": r.priority,
            })

        # Key findings
        pdf_findings = []
        meta_missing = sum(1 for p in problems if p["problem_type"] == "seo_missing_meta")
        schema_missing = sum(1 for p in problems if p["problem_type"] == "missing_schema")
        no_headings = sum(1 for p in problems if p["problem_type"] == "seo_no_headings")
        stale = sum(1 for p in problems if p["problem_type"].startswith("decay_"))
        if meta_missing:
            pdf_findings.append(f"{meta_missing} of {n_posts} posts ({meta_missing*100//n_posts}%) are missing meta descriptions")
        if schema_missing:
            pdf_findings.append(f"{schema_missing} of {n_posts} posts have no structured data")
        if stale:
            pdf_findings.append(f"{stale} posts haven't been updated in 18+ months")
        if no_headings:
            pdf_findings.append(f"{no_headings} posts lack H2/H3 heading structure")

        # Cann pairs for PDF
        pdf_cann = []
        for pair in cann_pairs[:5]:
            a_idx, b_idx = pair["post_a_idx"], pair["post_b_idx"]
            pdf_cann.append({
                "post_a_title": posts[a_idx].title,
                "post_b_title": posts[b_idx].title,
                "overlap_score": pair.get("cosine", pair.get("blended_score", 0)),
            })

        # Build problem type counts for categorized issue breakdown
        _ptc: Counter = Counter()
        for p in problems:
            _ptc[p["problem_type"]] += 1

        # Build richer key findings (P2-03: 3-5 bullets, not just 2)
        pdf_findings = []
        if schema_missing:
            pdf_findings.append(f"{schema_missing} of {n_posts} posts have no structured data \u2014 invisible to AI Overviews")
        cann_high = sum(1 for p in cann_pairs if p.get("severity") in ("critical", "high"))
        if len(cann_pairs) > 3:
            pdf_findings.append(f"{len(cann_pairs)} pairs of posts compete against each other, including {cann_high} high-severity pairs")
        readability_below = sum(1 for v in readability_lookup.values() if v < 60)
        avg_read_val = round(_avg(list(readability_lookup.values())), 1) if readability_lookup else 0
        if readability_below / max(n_posts, 1) > 0.3:
            pdf_findings.append(f"{readability_below*100//n_posts}% of posts score below readable threshold (Flesch {avg_read_val} avg vs 60 target)")
        stale_count = sum(1 for p in problems if p["problem_type"].startswith("decay_"))
        if stale_count > 10:
            pdf_findings.append(f"{stale_count} posts haven\u2019t been updated in 18+ months")
        if round(avg_eeat) >= 70:
            pdf_findings.append(f"Your E-E-A-T score of {round(avg_eeat)}/100 is strong \u2014 author attribution is working well")

        cann_post_count = len(set(
            p["post_a_idx"] for p in cann_pairs
        ) | set(p["post_b_idx"] for p in cann_pairs))

        pdf_report_data = {
            "site_domain": TARGET_DOMAIN,
            "overall_health": round(avg_health),
            "total_posts": n_posts,
            "cluster_count": n_clusters,
            "problem_count": len(problems),
            "rec_count": len(recs),
            "cann_pair_count": len(cann_pairs),
            "cann_post_count": cann_post_count,
            "orphan_count": 0,  # Skipped in capped crawl
            "thin_content_count": sum(1 for p in problems if p["problem_type"] == "thin_content"),
            "exact_duplicate_count": 0,
            "ai_citability_score": round(avg_cite, 1),
            "ai_eeat_score": round(avg_eeat, 1),
            "ai_schema_score": round(avg_schema, 1),
            "ai_extraction_score": round(avg_extract, 1),
            "ai_pct_ready": round(sum(1 for r in ai_results if r["cite"] >= 60) / max(n_posts, 1) * 100),
            "ai_pct_schema": round(sum(1 for r in ai_results if r["schema"] > 0) / max(n_posts, 1) * 100),
            "score_confidence": "crawl_only",
            "avg_word_count": round(_avg([p.word_count for p in posts if p.word_count])),
            "avg_readability": avg_read_val,
            "updated_12mo": 0,
            "meta_desc_pct": round(sum(1 for p in posts if (p.meta_description or "").strip()) / max(n_posts, 1) * 100),
            "meta_missing_count": meta_missing,
            "avg_question_header_ratio": round(_avg([
                r.get("signals", {}).get("question_headers", 0) / max(r.get("signals", {}).get("total_headers", 1), 1) * 100
                for r in ai_results if r.get("signals", {}).get("total_headers", 0) > 0
            ]), 1) if ai_results else 0,
            "pct_has_faq": round(sum(1 for r in ai_results if r.get("signals", {}).get("extract_has_faq_section") or r.get("signals", {}).get("has_faq_section")) / max(n_posts, 1) * 100),
            "problem_type_counts": dict(_ptc),
            "top_clusters": pdf_clusters[:6],
            "top_cann_pairs": pdf_cann,
            "top_recs": pdf_recs,
            "worst_posts": pdf_worst,
            "best_posts": [],
            "key_findings": pdf_findings,
        }

        pdf_bytes = generate_audit_pdf(pdf_report_data)
        pdf_out = os.path.join(os.path.dirname(out_path), f"{TARGET_DOMAIN.replace('/', '-')}-audit-report.pdf")
        with open(pdf_out, "wb") as pf:
            pf.write(pdf_bytes)
        print(f"PDF written to {pdf_out} ({len(pdf_bytes):,} bytes)")
    except Exception as e:
        print(f"PDF generation failed: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'=' * 70}")
    print(f"PIPELINE COMPLETE!")
    print(f"Report: {out_path} ({len(L)} lines)")
    print(f"Total time: {total_time:.0f}s | Total cost: ${total_cost:.4f}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
