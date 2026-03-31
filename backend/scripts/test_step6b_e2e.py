"""End-to-end test of Pipeline Step 6b: TF-IDF Cluster Labeling.

Runs the full TF-IDF labeling algorithm against real crawled data from
Copyblogger. Reuses Step 1 crawl and Step 3 clustering (UMAP+HDBSCAN)
as prerequisites, then applies _tfidf_label() to each cluster.

No database required -- tests computation only.
"""

import asyncio
import statistics
import sys
import time
from collections import Counter
from datetime import datetime

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


async def main():
    from app.services.fast_cluster_labels import (
        _FORMAT_MARKERS,
        _FORMAT_WORDS,
        _STOP_WORDS,
        _WORD_RE,
        _build_corpus_stats,
        _compute_site_stops,
        _extract_body_phrases,
        _extract_phrases,
        _generate_description,
        _strip_format,
        _tfidf_label,
        _validate_label_specificity,
    )
    from app.services.normalizer import (
        _strip_html_from_meta,
        _strip_site_name_from_title,
        filter_nav_links,
        filter_sitewide_headings,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 6b E2E Test: {TARGET_DOMAIN} ===\n")

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

    titles = [p.title or "" for p in posts]

    # ===================================================================
    # PHASE 2: Clustering (reuse Step 3)
    # ===================================================================
    print("Phase 2: Clustering (Step 3 prerequisite)...")
    cluster_start = time.time()
    embeddings = _generate_synthetic_embeddings(titles)
    labels, cluster_groups = _run_clustering(embeddings, n_posts)
    cluster_time = time.time() - cluster_start
    n_clusters = len(cluster_groups)
    print(f"  Generated {n_clusters} clusters in {cluster_time:.1f}s")
    for cl_id, indices in sorted(cluster_groups.items(), key=lambda x: -len(x[1])):
        print(f"    Cluster {cl_id}: {len(indices)} posts")
    print()

    # ===================================================================
    # PHASE 3: Site-Wide Stop Word Detection
    # ===================================================================
    print("Phase 3: Site-wide stop word detection...")
    stop_start = time.time()
    site_stops = _compute_site_stops(titles)
    stop_time = time.time() - stop_start

    # Also compute the raw word frequencies for reporting
    doc_freq: Counter = Counter()
    for t in titles:
        stripped = _strip_format(t)
        words = set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS
        doc_freq.update(words)
    # Mirror the adaptive threshold from _compute_site_stops
    if n_posts < 100:
        threshold_pct = 0.15
    elif n_posts < 300:
        threshold_pct = 0.20
    else:
        threshold_pct = 0.30
    threshold = n_posts * threshold_pct

    print(f"  Threshold: {threshold:.0f} occurrences ({threshold_pct:.0%} of {n_posts} titles)")
    print(f"  Site stops detected: {sorted(site_stops) if site_stops else '(none)'}")
    print(f"  Time: {stop_time * 1000:.2f}ms")
    print()

    # Show top 20 words by doc frequency
    print("  Top 20 words by document frequency:")
    for word, count in doc_freq.most_common(20):
        pct = count / n_posts * 100
        stopped = "STOPPED" if word in site_stops else ""
        print(f"    {word:20s} {count:3d}/{n_posts} ({pct:5.1f}%) {stopped}")
    print()

    # ===================================================================
    # PHASE 4: Format Marker Stripping Analysis
    # ===================================================================
    print("Phase 4: Format marker stripping analysis...")
    strip_results: list[tuple[str, str]] = []
    stripped_count = 0
    for t in titles:
        stripped = _strip_format(t)
        if stripped.lower() != t.lower().strip():
            strip_results.append((t, stripped))
            stripped_count += 1

    print(f"  Titles modified by stripping: {stripped_count}/{n_posts} ({stripped_count / n_posts * 100:.1f}%)")
    if strip_results[:10]:
        print("  Examples (first 10):")
        for original, stripped in strip_results[:10]:
            orig_short = original[:60]
            strip_short = stripped[:60]
            print(f"    '{orig_short}' -> '{strip_short}'")
    print()

    # ===================================================================
    # PHASE 5: Phrase Extraction Analysis
    # ===================================================================
    print("Phase 5: Phrase extraction analysis...")
    all_unigrams: list[str] = []
    all_bigrams: list[str] = []
    phrases_per_title: list[int] = []

    for t in titles:
        phrases = _extract_phrases(t)
        uni = [p for p in phrases if " " not in p]
        bi = [p for p in phrases if " " in p]
        all_unigrams.extend(uni)
        all_bigrams.extend(bi)
        phrases_per_title.append(len(phrases))

    print(f"  Total unigrams extracted: {len(all_unigrams)}")
    print(f"  Total bigrams extracted: {len(all_bigrams)}")
    print(f"  Unique unigrams: {len(set(all_unigrams))}")
    print(f"  Unique bigrams: {len(set(all_bigrams))}")
    print(f"  Phrases per title: min={min(phrases_per_title)}, max={max(phrases_per_title)}, "
          f"mean={statistics.mean(phrases_per_title):.1f}, median={statistics.median(phrases_per_title):.1f}")
    print()

    print("  Top 15 unigrams (across all titles):")
    for word, count in Counter(all_unigrams).most_common(15):
        in_stops = " (site-stop)" if word in site_stops else ""
        print(f"    {word:20s} {count:3d}{in_stops}")
    print()

    print("  Top 15 bigrams (across all titles):")
    for phrase, count in Counter(all_bigrams).most_common(15):
        print(f"    {phrase:30s} {count:3d}")
    print()

    # ===================================================================
    # PHASE 6: Multi-Signal TF-IDF Labeling Per Cluster
    # ===================================================================
    print("Phase 6: Multi-signal TF-IDF labeling per cluster...")
    label_start = time.time()

    noise = _FORMAT_WORDS | site_stops
    cluster_label_details: list[dict] = []

    # Pre-compute corpus stats once (matches label_clusters_fast behavior)
    corpus_phrases_pre, corpus_words_pre, n_docs_pre = _build_corpus_stats(titles, site_stops)

    # Collect all cluster title lists for negative validation
    all_cluster_title_lists: list[list[str]] = []
    cluster_id_order: list[int] = sorted(cluster_groups.keys(), key=lambda k: -len(cluster_groups[k]))
    for cl_id in cluster_id_order:
        all_cluster_title_lists.append([titles[i] for i in cluster_groups[cl_id]])

    total_body_phrases = 0
    total_heading_phrases = 0
    total_title_phrases = 0

    for idx, cl_id in enumerate(cluster_id_order):
        indices = cluster_groups[cl_id]
        cluster_titles = [titles[i] for i in indices]

        # S6b-12: Build multi-signal extra phrases from body + headings
        extra_phrases: list[str] = []
        cl_body_count = 0
        cl_heading_count = 0
        for i in indices:
            p = posts[i]
            body_ph, heading_ph = _extract_body_phrases(p.body_html, p.headings)
            extra_phrases.extend(body_ph)          # 1x weight
            extra_phrases.extend(heading_ph * 2)   # 2x weight
            cl_body_count += len(body_ph)
            cl_heading_count += len(heading_ph)

        # Count title-only phrases for diagnostic
        title_only_phrases: list[str] = []
        for t in cluster_titles:
            title_only_phrases.extend(_extract_phrases(t))
        cl_title_count = len(title_only_phrases)

        total_body_phrases += cl_body_count
        total_heading_phrases += cl_heading_count
        total_title_phrases += cl_title_count

        # Run _tfidf_label with multi-signal
        t0 = time.time()
        label, alternatives, desc_words = _tfidf_label(
            cluster_titles, titles, site_stops=site_stops,
            corpus_phrases=corpus_phrases_pre, corpus_words=corpus_words_pre,
            n_docs=n_docs_pre, extra_phrases=extra_phrases,
        )
        label_time_ms = (time.time() - t0) * 1000

        # S6b-14: Negative label validation
        is_specific = _validate_label_specificity(label, idx, all_cluster_title_lists)

        # S6b-13: Generate description
        description = _generate_description(label, desc_words)

        # S6b-26: Signal-source diagnostic — where did the label bigram come from?
        label_primary_words = label.replace(" & ", " ").lower().split()[:2]
        label_bigram_lower = " ".join(label_primary_words)
        # Count occurrences in each signal source
        title_bigrams_flat = [p for p in title_only_phrases if " " in p]
        body_bigrams_flat = [p for p in extra_phrases if " " in p]
        heading_bigrams_flat = []
        for i_idx in indices:
            _, h_ph = _extract_body_phrases(None, posts[i_idx].headings)
            heading_bigrams_flat.extend([p for p in h_ph if " " in p])
        signal_source = {
            "title": title_bigrams_flat.count(label_bigram_lower),
            "body": body_bigrams_flat.count(label_bigram_lower),
            "heading": heading_bigrams_flat.count(label_bigram_lower),
        }

        # Reproduce internal scoring for detailed analysis (title-only for reporting)
        cl_bigrams = [p for p in title_only_phrases if " " in p]
        cl_unigrams = [p for p in title_only_phrases if " " not in p and p not in noise]

        bigram_tf = Counter(cl_bigrams)
        total_bigrams_count = len(cl_bigrams) or 1
        bigram_scores: dict[str, float] = {}
        for phrase, count in bigram_tf.items():
            parts = phrase.split()
            if all(p in noise for p in parts):
                continue
            tf = count / total_bigrams_count
            idf = np.log(n_docs_pre / (1 + corpus_phrases_pre.get(phrase, 0)))
            bigram_scores[phrase] = tf * idf

        unigram_tf = Counter(cl_unigrams)
        total_unigrams_count = len(cl_unigrams) or 1
        unigram_scores: dict[str, float] = {}
        for word, count in unigram_tf.items():
            tf = count / total_unigrams_count
            idf = np.log(n_docs_pre / (1 + corpus_words_pre.get(word, 0)))
            unigram_scores[word] = tf * idf

        top_bigrams = sorted(bigram_scores.items(), key=lambda x: -x[1])[:5]
        top_unigrams_scored = sorted(unigram_scores.items(), key=lambda x: -x[1])[:5]

        # Build title word doc frequency for proper-noun check (mirrors production)
        import re as _re
        _WORD_RE_E2E = _re.compile(r"[a-z]{3,}")
        _STOP_WORDS_E2E = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                           "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
                           "have", "has", "had", "do", "does", "did", "will", "would", "how",
                           "what", "when", "where", "why", "which", "who", "you", "your", "this",
                           "that", "more", "most", "very", "just", "also", "about", "not", "so"}
        _FORMAT_WORDS_E2E = {"definitive", "complete", "ultimate", "comprehensive", "step",
                             "guide", "beginner", "beginners", "advanced", "simple",
                             "easy", "quick", "proven", "essential", "actionable",
                             "powerful", "effective", "practical", "tips", "tricks"}
        _title_word_doc_freq: Counter = Counter()
        for t in cluster_titles:
            _title_word_doc_freq.update(set(_WORD_RE_E2E.findall(t.lower())) - _STOP_WORDS_E2E - _FORMAT_WORDS_E2E)

        min_bigram_freq = 1 if len(cluster_titles) < 5 else 2

        detail = {
            "cluster_id": cl_id,
            "post_count": len(indices),
            "label": label,
            "label_time_ms": label_time_ms,
            "cluster_titles": cluster_titles,
            "n_title_phrases": cl_title_count,
            "n_body_phrases": cl_body_count,
            "n_heading_phrases": cl_heading_count,
            "n_extra_phrases": len(extra_phrases),
            "n_bigrams": len(cl_bigrams),
            "n_unigrams": len(cl_unigrams),
            "unique_bigrams": len(set(cl_bigrams)),
            "unique_unigrams": len(set(cl_unigrams)),
            "top_bigrams": top_bigrams,
            "top_unigrams": top_unigrams_scored,
            "bigram_tf": bigram_tf,
            "title_word_doc_freq": _title_word_doc_freq,
            "min_bigram_freq": min_bigram_freq,
            "alternatives": alternatives,
            "desc_words": desc_words,
            "description": description,
            "is_specific": is_specific,
            "signal_source": signal_source,
        }
        cluster_label_details.append(detail)

        print(f"  Cluster {cl_id} ({len(indices)} posts): \"{label}\"  [{label_time_ms:.1f}ms]")
        print(f"    Phrases: title={cl_title_count}, body={cl_body_count}, heading={cl_heading_count}")
        src = signal_source
        print(f"    Label bigram \"{label_bigram_lower}\": title={src['title']}, body={src['body']}, heading={src['heading']}")
        if top_bigrams:
            best = top_bigrams[0]
            print(f"    Best title bigram: \"{best[0]}\" (tf-idf={best[1]:.4f}, freq={bigram_tf[best[0]]})")
        if top_unigrams_scored:
            best_uni = top_unigrams_scored[0]
            print(f"    Best unigram: \"{best_uni[0]}\" (tf-idf={best_uni[1]:.4f})")
        print(f"    Alternatives: {alternatives}")
        print(f"    Description: \"{description}\"")
        print(f"    Specific: {is_specific}")

    label_time = time.time() - label_start
    print(f"\n  Total labeling time: {label_time * 1000:.1f}ms")
    print(f"  Total phrases: title={total_title_phrases}, body={total_body_phrases}, heading={total_heading_phrases}")
    print()

    # ===================================================================
    # PHASE 6b: Near-Duplicate Dedup (replicates label_clusters_fast logic)
    # ===================================================================
    print("Phase 6b: Near-duplicate dedup...")

    def _primary_bigram_dedup(lbl: str) -> str:
        parts = lbl.replace(" & ", " ").split()[:2]
        return " ".join(p.lower() for p in parts)

    seen_primaries: dict[str, int] = {}
    dedup_changes: list[str] = []
    for i, d in enumerate(cluster_label_details):
        primary = _primary_bigram_dedup(d["label"])
        if primary in seen_primaries:
            old_label = d["label"]
            for alt in d["alternatives"]:
                alt_primary = _primary_bigram_dedup(alt)
                if alt_primary not in seen_primaries:
                    d["label"] = alt
                    primary = alt_primary
                    dedup_changes.append(f"  Cluster {d['cluster_id']}: \"{old_label}\" -> \"{alt}\" (near-dup of primary '{_primary_bigram_dedup(old_label)}')")
                    break
        seen_primaries[primary] = i

    if dedup_changes:
        for change in dedup_changes:
            print(change)
    else:
        print("  No near-duplicates found")
    print()

    # ===================================================================
    # PHASE 7: Label Quality Assessment
    # ===================================================================
    print("Phase 7: Label quality assessment...")

    # Check for common quality issues
    all_labels = [d["label"] for d in cluster_label_details]
    duplicate_labels = [l for l, c in Counter(all_labels).items() if c > 1]
    single_word_labels = [l for l in all_labels if " " not in l.replace(" & ", "")]
    generic_labels = [l for l in all_labels if l.lower() in ("general content", "miscellaneous")]
    amp_labels = [l for l in all_labels if "&" in l]

    print(f"  Total labels: {len(all_labels)}")
    print(f"  Unique labels: {len(set(all_labels))}")
    print(f"  Duplicate labels: {duplicate_labels if duplicate_labels else '(none)'}")
    print(f"  Labels with '&' qualifier: {len(amp_labels)}")
    print(f"  Single-word labels (no bigram): {len(single_word_labels)}")
    print(f"  Generic fallback labels: {len(generic_labels)}")

    # S6b-07: Assert label uniqueness across clusters
    if duplicate_labels:
        print(f"  WARNING: {len(duplicate_labels)} duplicate label(s) found: {duplicate_labels}")
        print("  Two clusters with the same label confuse the dashboard dropdown,")
        print("  ecosystem map legend, and PDF cluster table.")
    else:
        print(f"  PASS: All {len(all_labels)} labels are unique across clusters")
    assert len(set(all_labels)) == len(all_labels), (
        f"Label uniqueness violated: duplicates = {duplicate_labels}"
    )
    print()

    def _has_valid_best_bigram(d: dict) -> bool:
        """Check if a cluster's top bigram would be selected by production logic."""
        top_bi = d.get("top_bigrams", [])
        if not top_bi or top_bi[0][1] <= 0:
            return False
        phrase = top_bi[0][0]
        freq = d["bigram_tf"].get(phrase, 0)
        _min_bf = d.get("min_bigram_freq", 2)
        if freq < _min_bf:
            return False
        # Proper noun check: skip if all words appear in only 1 title
        parts = phrase.split()
        _twdf = d.get("title_word_doc_freq", {})
        if all(_twdf.get(w, 0) <= 1 for w in parts):
            return False
        return True

    # Classify label quality — multi-factor check
    _FUNCTION_WORDS = {"whom", "whose", "thee", "thou", "thy", "whereby", "thereof",
                       "whether", "whereas", "hence", "thus", "therefore", "really",
                       "actually", "literally", "basically", "simply"}

    # Build near-duplicate detection: labels sharing the same first 2 words
    def _primary_bigram_test(lbl: str) -> str:
        parts = lbl.replace(" & ", " ").split()[:2]
        return " ".join(p.lower() for p in parts)

    primary_bigram_counts = Counter(_primary_bigram_test(l) for l in all_labels)

    quality_counts = {"good": 0, "acceptable": 0, "vague": 0, "bad": 0}
    quality_details: list[tuple[str, str, str, str]] = []  # (cl_id, label, quality, reason)
    for d in cluster_label_details:
        label = d["label"]
        cl_id = d["cluster_id"]
        label_words = set(_WORD_RE.findall(label.lower()))
        has_function_word = bool(label_words & _FUNCTION_WORDS)
        primary = _primary_bigram_test(label)
        is_near_dup = primary_bigram_counts[primary] > 1

        # Check label-content mismatch: label bigram not in cluster's title top-5 bigrams
        title_top_bigrams = {b[0] for b in d["top_bigrams"][:5]} if d["top_bigrams"] else set()
        label_bigram_words = label.replace(" & ", " ").lower().split()[:2]
        label_as_bigram = " ".join(label_bigram_words)
        content_mismatch = label_as_bigram not in title_top_bigrams and len(title_top_bigrams) > 0

        reason = ""
        if label.lower() in ("general content", "miscellaneous"):
            quality = "vague"
            reason = "Generic fallback"
        elif has_function_word:
            quality = "bad"
            reason = f"Function word: {label_words & _FUNCTION_WORDS}"
        elif is_near_dup:
            quality = "acceptable"
            reason = f"Near-duplicate primary: '{primary}'"
        elif content_mismatch:
            quality = "acceptable"
            reason = f"Label bigram '{label_as_bigram}' not in title top-5"
        elif "&" in label and len(label.split()) <= 3:
            quality = "acceptable"
            reason = "Unigram pair"
        elif " " not in label:
            quality = "acceptable"
            reason = "Single word"
        else:
            quality = "good"
            reason = ""
        quality_counts[quality] += 1
        quality_details.append((str(cl_id), label, quality, reason))

    print("  Quality classification:")
    for q, count in quality_counts.items():
        pct = count / len(all_labels) * 100 if all_labels else 0
        print(f"    {q:12s} {count:3d} ({pct:.0f}%)")
    print()

    # ===================================================================
    # PHASE 8: Fallback Chain Analysis
    # ===================================================================
    print("Phase 8: Fallback chain analysis...")
    path_counts = {"bigram": 0, "bigram+qualifier": 0, "unigrams": 0, "fallback": 0}
    for d in cluster_label_details:
        label = d["label"]
        top_bi = d["top_bigrams"]
        if label.lower() in ("general content", "miscellaneous"):
            path_counts["fallback"] += 1
        elif _has_valid_best_bigram(d):
            if "&" in label:
                path_counts["bigram+qualifier"] += 1
            else:
                path_counts["bigram"] += 1
        elif "&" in label:
            path_counts["unigrams"] += 1
        else:
            path_counts["unigrams"] += 1

    for path, count in path_counts.items():
        print(f"    {path:20s} {count:3d} cluster(s)")
    print()

    # ===================================================================
    # WRITE REPORT
    # ===================================================================
    print("Phase 9: Generating report...")

    report_path = "../STEP6B-TEST-RESULTS.md"
    lines: list[str] = []

    lines.append(f"# Step 6b E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Prerequisite:** {n_posts} posts from Step 1 crawl + Step 3 clustering (synthetic embeddings)")
    lines.append(f"**Clusters labeled:** {n_clusters}")
    lines.append("**Note:** Clustering used synthetic embeddings (not real OpenAI). "
                 "Cluster composition differs from production; label quality assessment is valid "
                 "for the TF-IDF algorithm but cluster boundaries are artificial.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 6b-a: Site-Wide Stop Word Detection
    lines.append("## 6b-a. Site-Wide Stop Word Detection")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total titles analyzed | {n_posts} |")
    lines.append(f"| Stop word threshold | {threshold:.0f} occurrences ({threshold_pct:.0%} of {n_posts} titles) |")
    lines.append(f"| Site stops detected | {len(site_stops)} |")
    lines.append(f"| Stop words | {', '.join(sorted(site_stops)) if site_stops else '(none)'} |")
    lines.append(f"| Processing time | {stop_time * 1000:.2f}ms |")
    lines.append("")

    # Word frequency table
    lines.append("### Word Frequency Analysis (Top 20)")
    lines.append("")
    lines.append("| Word | Titles Containing | % | Stopped? |")
    lines.append("|------|------------------|---|----------|")
    for word, count in doc_freq.most_common(20):
        pct = count / n_posts * 100
        stopped = "YES" if word in site_stops else ""
        lines.append(f"| {word} | {count}/{n_posts} | {pct:.0f}% | {stopped} |")
    lines.append("")

    # 6b-b: Format Marker Stripping
    lines.append("## 6b-b. Format Marker Stripping")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Titles modified | {stripped_count}/{n_posts} ({stripped_count / n_posts * 100:.1f}%) |")
    lines.append(f"| Format markers checked | {len(_FORMAT_MARKERS)} patterns |")
    lines.append("| Leading patterns stripped | `How to`, `What Is`, `N Best/Top...` |")
    lines.append("| Trailing patterns stripped | Year (`in 2024`), site name (`- Copyblogger`) |")
    lines.append("")

    if strip_results:
        lines.append("### Stripping Examples")
        lines.append("")
        lines.append("| Original Title | After Stripping |")
        lines.append("|---------------|----------------|")
        for original, stripped in strip_results[:15]:
            orig_short = original[:65].replace("|", "\\|")
            strip_short = stripped[:65].replace("|", "\\|")
            lines.append(f"| {orig_short} | {strip_short} |")
        lines.append("")

    # 6b-c: Phrase Extraction
    lines.append("## 6b-c. Phrase Extraction")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total unigrams extracted | {len(all_unigrams)} |")
    lines.append(f"| Total bigrams extracted | {len(all_bigrams)} |")
    lines.append(f"| Unique unigrams | {len(set(all_unigrams))} |")
    lines.append(f"| Unique bigrams | {len(set(all_bigrams))} |")
    lines.append(f"| Phrases per title (mean) | {statistics.mean(phrases_per_title):.1f} |")
    lines.append(f"| Phrases per title (median) | {statistics.median(phrases_per_title):.1f} |")
    lines.append(f"| Phrases per title (range) | {min(phrases_per_title)}-{max(phrases_per_title)} |")
    lines.append("")

    lines.append("### Top 15 Unigrams (Corpus-Wide)")
    lines.append("")
    lines.append("| Unigram | Frequency | In Site Stops? |")
    lines.append("|---------|-----------|---------------|")
    for word, count in Counter(all_unigrams).most_common(15):
        in_stops = "YES" if word in site_stops else ""
        lines.append(f"| {word} | {count} | {in_stops} |")
    lines.append("")

    lines.append("### Top 15 Bigrams (Corpus-Wide)")
    lines.append("")
    lines.append("| Bigram | Frequency |")
    lines.append("|--------|-----------|")
    for phrase, count in Counter(all_bigrams).most_common(15):
        lines.append(f"| {phrase} | {count} |")
    lines.append("")

    # Multi-signal phrase diagnostic
    lines.append("## Multi-Signal Phrase Diagnostic")
    lines.append("")
    lines.append("| Source | Total Phrases | Notes |")
    lines.append("|--------|--------------|-------|")
    lines.append(f"| Titles (3x weight) | {total_title_phrases} | Extracted via `_extract_phrases` |")
    lines.append(f"| Body text (1x weight) | {total_body_phrases} | First 200 words of `body_html` |")
    lines.append(f"| H2/H3 headings (2x weight) | {total_heading_phrases} | From `headings` JSONB |")
    lines.append(f"| **Total input to TF-IDF** | **{total_title_phrases * 3 + total_body_phrases + total_heading_phrases * 2}** | **Weighted sum** |")
    lines.append("")
    if total_body_phrases == 0 and total_heading_phrases == 0:
        lines.append("**WARNING:** Body text and headings contributed zero phrases. "
                     "Multi-signal extraction is not adding value on this dataset. "
                     "Possible causes: `body_html` is null/empty, or headings JSONB "
                     "is missing/malformed. Labels are title-only.")
        lines.append("")

    # 6b-d: Per-Cluster TF-IDF Labeling
    lines.append("## 6b-d. Per-Cluster TF-IDF Labeling")
    lines.append("")

    for d in cluster_label_details:
        cl_id = d["cluster_id"]
        lines.append(f"### Cluster {cl_id} ({d['post_count']} posts) -> \"{d['label']}\"")
        lines.append("")

        # Cluster summary with multi-signal breakdown
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Label | **{d['label']}** |")
        lines.append(f"| Description | {d['description'] or '(none)'} |")
        lines.append(f"| Posts | {d['post_count']} |")
        lines.append(f"| Title phrases | {d['n_title_phrases']} |")
        lines.append(f"| Body phrases | {d['n_body_phrases']} |")
        lines.append(f"| Heading phrases | {d['n_heading_phrases']} |")
        lines.append(f"| Unique bigrams | {d['unique_bigrams']} |")
        lines.append(f"| Unique unigrams | {d['unique_unigrams']} |")
        lines.append(f"| Specific (validation) | {'YES' if d['is_specific'] else 'NO — label words appear in >50% of other clusters'} |")
        src = d["signal_source"]
        lines.append(f"| Label bigram source | title={src['title']}, body={src['body']}, heading={src['heading']} |")
        lines.append(f"| Alternatives | {', '.join(d['alternatives']) if d['alternatives'] else '(none)'} |")
        lines.append(f"| Description words | {', '.join(d['desc_words']) if d['desc_words'] else '(none)'} |")
        lines.append(f"| Labeling time | {d['label_time_ms']:.1f}ms |")
        lines.append("")

        # Top bigrams
        if d["top_bigrams"]:
            lines.append("**Top 5 Bigrams by TF-IDF:**")
            lines.append("")
            lines.append("| Bigram | TF-IDF Score | Frequency | Selected? |")
            lines.append("|--------|-------------|-----------|----------|")
            _found_selected = False
            for i, (phrase, score) in enumerate(d["top_bigrams"]):
                freq = d["bigram_tf"].get(phrase, 0)
                # Mirror production selection: score > 0, freq >= min_bigram_freq,
                # and NOT all words appearing in only 1 title (proper noun check)
                parts = phrase.split()
                _twdf = d.get("title_word_doc_freq", {})
                _min_bf = d.get("min_bigram_freq", 2)
                proper_noun = all(_twdf.get(w, 0) <= 1 for w in parts)
                selected = ""
                if not _found_selected and score > 0 and freq >= _min_bf and not proper_noun:
                    selected = "YES"
                    _found_selected = True
                lines.append(f"| {phrase} | {score:.4f} | {freq} | {selected} |")
            lines.append("")

        # Top unigrams
        if d["top_unigrams"]:
            lines.append("**Top 5 Unigrams by TF-IDF:**")
            lines.append("")
            lines.append("| Unigram | TF-IDF Score |")
            lines.append("|---------|-------------|")
            for word, score in d["top_unigrams"]:
                lines.append(f"| {word} | {score:.4f} |")
            lines.append("")

        # Sample titles
        lines.append("**Sample titles (first 8):**")
        lines.append("")
        for t in d["cluster_titles"][:8]:
            lines.append(f"- {t[:80]}")
        lines.append("")

    # Label summary table
    lines.append("## Label Summary")
    lines.append("")
    lines.append("| Cluster | Posts | Label | Quality | Labeling Path |")
    lines.append("|---------|-------|-------|---------|--------------|")
    for d, (_, _, quality, _reason) in zip(cluster_label_details, quality_details, strict=True):
        # Determine path
        top_bi = d["top_bigrams"]
        label = d["label"]
        if label.lower() in ("general content", "miscellaneous"):
            path = "Fallback"
        elif _has_valid_best_bigram(d):
            if "&" in label:
                path = "Bigram + qualifier"
            else:
                path = "Best bigram"
        elif "&" in label:
            path = "Top 2 unigrams"
        else:
            path = "Single unigram"
        lines.append(f"| {d['cluster_id']} | {d['post_count']} | {label} | {quality} | {path} |")
    lines.append("")

    # Quality assessment
    lines.append("## Label Quality Assessment")
    lines.append("")
    lines.append("| Quality | Count | % | Criteria |")
    lines.append("|---------|-------|---|----------|")
    lines.append(f"| Good | {quality_counts['good']} | "
                 f"{quality_counts['good'] / len(all_labels) * 100:.0f}% | "
                 f"Bigram-based, descriptive, no function words |")
    lines.append(f"| Acceptable | {quality_counts['acceptable']} | "
                 f"{quality_counts['acceptable'] / len(all_labels) * 100:.0f}% | "
                 f"Unigram pair or single word |")
    lines.append(f"| Bad | {quality_counts['bad']} | "
                 f"{quality_counts['bad'] / len(all_labels) * 100:.0f}% | "
                 f"Contains function/archaic words (whom, thee, etc.) |")
    lines.append(f"| Vague | {quality_counts['vague']} | "
                 f"{quality_counts['vague'] / len(all_labels) * 100:.0f}% | "
                 f"Generic fallback (\"General Content\", \"Miscellaneous\") |")
    lines.append("")

    # Fallback chain
    lines.append("### Fallback Chain Distribution")
    lines.append("")
    lines.append("| Path | Count | Description |")
    lines.append("|------|-------|-------------|")
    lines.append(f"| Best bigram | {path_counts['bigram']} | "
                 f"Top bigram with score > 0 and freq >= 2 |")
    lines.append(f"| Bigram + qualifier | {path_counts['bigram+qualifier']} | "
                 f"Best bigram + top unigram not in bigram |")
    lines.append(f"| Top unigrams | {path_counts['unigrams']} | "
                 f"No qualifying bigram; joined top 2 unigrams |")
    lines.append(f"| Fallback | {path_counts['fallback']} | "
                 f"\"General Content\" or \"Miscellaneous\" |")
    lines.append("")

    # Processing time
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Step | Time | Notes |")
    lines.append("|------|------|-------|")
    lines.append(f"| Crawl (Step 1 prerequisite) | {crawl_time:.1f}s | {len(raw_posts)} URLs |")
    lines.append(f"| Clustering (Step 3 prerequisite) | {cluster_time:.1f}s | Synthetic embeddings |")
    lines.append(f"| Site stop word detection | {stop_time * 1000:.2f}ms | {len(site_stops)} words stopped |")
    lines.append(f"| TF-IDF labeling (all clusters) | {label_time * 1000:.1f}ms | {n_clusters} clusters |")
    for d in cluster_label_details:
        lines.append(f"|   Cluster {d['cluster_id']} ({d['post_count']} posts) | "
                     f"{d['label_time_ms']:.1f}ms | \"{d['label']}\" |")
    total_6b_time = stop_time * 1000 + label_time * 1000
    lines.append(f"| **Total Step 6b** | **{total_6b_time:.1f}ms** | **Free (zero API calls)** |")
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")

    # Obs 1: Site stops
    if site_stops:
        lines.append(f"1. **{len(site_stops)} site-wide stop word(s) detected:** "
                     f"{', '.join(sorted(site_stops))}. "
                     f"These words appear in >= 30% of titles and are excluded from labels "
                     f"to prevent every cluster being labeled with site-wide vocabulary.")
    else:
        closest_word, closest_count = doc_freq.most_common(1)[0] if doc_freq else ("(none)", 0)
        lines.append(f"1. **No site-wide stop words detected** -- closest word '{closest_word}' "
                     f"at {closest_count}/{n_posts} ({closest_count / n_posts * 100:.0f}%), "
                     f"needs {threshold:.0f} (30%). "
                     f"Copyblogger titles are too diverse for the {n_posts}-post subset. "
                     f"Labels may contain site vocabulary that would be stopped on larger crawls.")
    lines.append("")

    # Obs 2: Format stripping
    lines.append(f"2. **Format stripping modified {stripped_count}/{n_posts} titles "
                 f"({stripped_count / n_posts * 100:.0f}%).** "
                 f"Most Copyblogger titles are short blog-style headlines (not 'The Definitive Guide to X'), "
                 f"so format markers are rare. The main stripping comes from trailing patterns "
                 f"(site name, year references).")
    lines.append("")

    # Obs 3: Bigram vs unigram
    bigram_labels = sum(1 for d in cluster_label_details
                       if d["top_bigrams"] and d["top_bigrams"][0][1] > 0
                       and d["bigram_tf"].get(d["top_bigrams"][0][0], 0) >= 2)
    lines.append(f"3. **{bigram_labels}/{n_clusters} clusters labeled via bigram path** -- "
                 f"bigrams produce more readable labels ('Content Promotion' vs 'Content'). "
                 f"The freq >= 2 requirement ensures the bigram appears in multiple titles, "
                 f"not just once by coincidence.")
    lines.append("")

    # Obs 4: Label uniqueness
    if duplicate_labels:
        lines.append(f"4. **{len(duplicate_labels)} duplicate label(s) detected:** "
                     f"{', '.join(duplicate_labels)}. "
                     f"This happens when two clusters share similar vocabulary. "
                     f"Claude backfill would differentiate these.")
    else:
        lines.append(f"4. **All {n_clusters} labels are unique** -- no duplicate labels. "
                     f"TF-IDF's inverse document frequency naturally pushes clusters toward "
                     f"different words.")
    lines.append("")

    # Obs 5: Quality
    lines.append(f"5. **Label quality: {quality_counts['good']} good, "
                 f"{quality_counts['acceptable']} acceptable, "
                 f"{quality_counts['vague']} vague.** "
                 f"{'All labels are at least acceptable.' if quality_counts['vague'] == 0 else ''}"
                 f"{'The vague labels would benefit from Claude backfill (~$0.02 per site).' if quality_counts['vague'] > 0 else ''}")
    lines.append("")

    # Obs 6: Speed
    lines.append(f"6. **Total labeling time: {total_6b_time:.1f}ms** for {n_clusters} clusters. "
                 f"TF-IDF labeling is effectively free -- pure Python text analysis with no "
                 f"API calls, no ML models, no GPU. Even a 1000-post site with 40 clusters "
                 f"would complete in < 1 second.")
    lines.append("")

    # Obs 7: Phrase extraction yield
    avg_phrases = statistics.mean(phrases_per_title)
    zero_phrase_titles = sum(1 for n in phrases_per_title if n == 0)
    lines.append(f"7. **Phrase extraction yields {avg_phrases:.1f} phrases/title on average.** "
                 f"{zero_phrase_titles} title(s) produced zero phrases (all words were stop words "
                 f"or format words). These titles contribute nothing to TF-IDF scoring "
                 f"and dilute cluster signal.")
    lines.append("")

    # Obs 8: Synthetic embeddings caveat
    lines.append("8. **Synthetic embeddings produce different clusters than real OpenAI embeddings.** "
                 "The cluster boundaries here are based on keyword injection, not semantic similarity. "
                 "TF-IDF labels are still valid because they operate on title text, not embeddings. "
                 "However, different cluster composition means different label results.")
    lines.append("")

    # Obs 9: Qualifier usage
    lines.append(f"9. **{len(amp_labels)} label(s) use '&' qualifiers.** "
                 f"The '&' connector appears when either: (a) a bigram is qualified by a top "
                 f"unigram not already in the bigram (e.g., 'Link Building & Outreach'), or "
                 f"(b) no bigram qualified and top 2 unigrams are joined (e.g., 'Sales & Seo').")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by `backend/scripts/test_step6b_e2e.py` -- "
                 "no database, no API calls.*")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n  Report written to {report_path}")
    print(f"\n=== Step 6b E2E complete -- {n_clusters} clusters labeled, "
          f"{total_6b_time:.0f}ms total ===")


if __name__ == "__main__":
    asyncio.run(main())
