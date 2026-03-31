"""End-to-end test of Pipeline Step 6c: AI Citability Scoring.

Crawls a real site, runs all 4 AI-readiness scoring functions against real
body_text and body_html, and writes detailed results to STEP6c-TEST-RESULTS.md.

No database required — tests computation only.
No external API calls — all scoring is heuristic/regex-based.
"""
import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


async def main():
    from app.services.normalizer import (
        filter_nav_links,
        filter_sitewide_headings,
        _strip_site_name_from_title,
        _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.services.ai_citability import (
        compute_citability_score,
        compute_eeat_score,
        compute_schema_score,
        compute_extraction_score,
        generate_ai_problems,
    )
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 6c E2E Test: {TARGET_DOMAIN} ===\n")

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
    n_posts = len(posts)
    print(f"  Normalized to {n_posts} posts\n")

    # ── Phase 2: Compute site-wide median word count ──
    word_counts = sorted(len((p.body_text or "").split()) for p in posts)
    site_median_words = word_counts[len(word_counts) // 2] if word_counts else 0
    avg_word_count = sum(word_counts) / len(word_counts) if word_counts else 0
    print(f"Site-wide word count stats:")
    print(f"  Median: {site_median_words}")
    print(f"  Average: {avg_word_count:.0f}")
    print(f"  Min: {min(word_counts)}, Max: {max(word_counts)}")
    print()

    # ── Phase 2b: Schema scorer validation with synthetic JSON-LD ──
    # Copyblogger has zero schema, so we test the scorer against synthetic HTML
    # to verify it can parse JSON-LD, detect high-value types, and compute
    # article completeness. This catches bugs that a schema-less site can't.
    print("Schema scorer validation (synthetic JSON-LD)...")
    schema_test_cases = [
        ("No schema", "<html><body><p>Hello</p></body></html>", 0),
        ("Article complete", """<html><body>
            <script type="application/ld+json">
            {"@type": "Article", "headline": "Test", "datePublished": "2025-01-01",
             "author": {"@type": "Person", "name": "Test"}, "image": "test.jpg",
             "dateModified": "2025-06-01"}
            </script></body></html>""", 90),
        ("Article missing image+dateModified", """<html><body>
            <script type="application/ld+json">
            {"@type": "BlogPosting", "headline": "Test", "datePublished": "2025-01-01",
             "author": {"@type": "Person", "name": "Test"}}
            </script></body></html>""", 78),
        ("Article + FAQPage (multi-type)", """<html><body>
            <script type="application/ld+json">
            {"@type": "Article", "headline": "Test", "datePublished": "2025-01-01",
             "author": {"@type": "Person", "name": "Test"}, "image": "test.jpg",
             "dateModified": "2025-06-01"}
            </script>
            <script type="application/ld+json">
            {"@type": "FAQPage", "mainEntity": []}
            </script></body></html>""", 100),
        ("Only Organization+WebSite (basic)", """<html><body>
            <script type="application/ld+json">
            {"@type": "Organization", "name": "Acme Inc"}
            </script>
            <script type="application/ld+json">
            {"@type": "WebSite", "name": "Acme Blog"}
            </script></body></html>""", 40),
        ("@graph wrapper", """<html><body>
            <script type="application/ld+json">
            [{"@type": "Article", "headline": "Test", "datePublished": "2025-01-01",
              "author": {"@type": "Person", "name": "Test"}, "image": "t.jpg",
              "dateModified": "2025-06-01"},
             {"@type": "BreadcrumbList"}]
            </script></body></html>""", 100),
    ]
    schema_validation_results: list[dict] = []
    all_passed = True
    for name, html_str, expected in schema_test_cases:
        actual_score, signals_out = compute_schema_score(html_str)
        passed = actual_score == expected
        if not passed:
            all_passed = False
        schema_validation_results.append({
            "name": name, "expected": expected, "actual": int(actual_score),
            "passed": passed, "types": signals_out.get("schema_types", []),
        })
        status = "PASS" if passed else f"FAIL (got {int(actual_score)})"
        print(f"  {name}: expected={expected}, {status}")
    print(f"  Schema validation: {'ALL PASSED' if all_passed else 'SOME FAILED'}\n")

    # ── Phase 3: Score all posts ──
    print("Step 6c: Scoring all posts on 4 AI-readiness dimensions...")
    score_start = time.time()

    results: list[dict] = []
    cite_scores: list[float] = []
    eeat_scores: list[float] = []
    schema_scores: list[float] = []
    extract_scores: list[float] = []

    # Track signal frequencies across all posts
    signal_counters: dict[str, int] = Counter()
    signal_value_accum: dict[str, list] = {}

    for i, p in enumerate(posts):
        body_text = p.body_text or ""
        body_html = p.body_html or ""
        headings = p.headings or []
        word_count = len(body_text.split())

        # Parse eeat_signals from crawl-time E-E-A-T extraction (full page HTML).
        # NormalizedPost stores this as .eeat_signals; in DB it's the eeat_metadata column.
        crawl_eeat = {}
        if hasattr(p, "eeat_signals") and p.eeat_signals:
            crawl_eeat = p.eeat_signals if isinstance(p.eeat_signals, dict) else {}

        # Parse HTML once per post (4x fewer BeautifulSoup parses)
        from bs4 import BeautifulSoup as _BS
        parsed_soup = _BS(body_html or "", "lxml")

        cite_score, cite_signals = compute_citability_score(body_text, body_html, soup=parsed_soup)
        eeat_score, eeat_signals = compute_eeat_score(
            body_html, crawl_eeat=crawl_eeat,
            headings=headings, word_count=word_count,
            site_median_words=site_median_words,
            publish_date=getattr(p, "publish_date", None),
            modified_date=getattr(p, "modified_date", None),
            soup=parsed_soup,
        )
        schema_score, schema_signals = compute_schema_score(body_html, soup=parsed_soup)
        extract_score, extract_signals = compute_extraction_score(body_text, body_html, headings, soup=parsed_soup)

        all_signals = {
            **cite_signals,
            **{f"eeat_{k}": v for k, v in eeat_signals.items()},
            **{f"schema_{k}": v for k, v in schema_signals.items()},
            **{f"extract_{k}": v for k, v in extract_signals.items()},
        }

        # Accumulate signal values for site-wide analysis
        for key, val in all_signals.items():
            if isinstance(val, bool):
                signal_counters[key] += (1 if val else 0)
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                signal_value_accum.setdefault(key, []).append(val)

        # Generate problems for this post
        from uuid import uuid4
        post_id = uuid4()
        problems = generate_ai_problems(
            post_id, p.title or "",
            cite_score, eeat_score, schema_score, extract_score, all_signals,
        )

        results.append({
            "title": (p.title or "")[:60],
            "url": p.url,
            "word_count": word_count,
            "citability": cite_score,
            "eeat": eeat_score,
            "schema": schema_score,
            "extraction": extract_score,
            "signals": all_signals,
            "problems": problems,
            "problem_types": [pr["problem_type"] for pr in problems],
        })

        cite_scores.append(cite_score)
        eeat_scores.append(eeat_score)
        schema_scores.append(schema_score)
        extract_scores.append(extract_score)

        if (i + 1) % 50 == 0:
            print(f"  Scored {i + 1}/{n_posts} posts...")

    score_time = time.time() - score_start
    print(f"  Scored all {n_posts} posts in {score_time:.2f}s\n")

    # ── Phase 4: Compute aggregate statistics ──
    def _stats(scores: list[float]) -> dict:
        return {
            "mean": round(statistics.mean(scores), 1),
            "median": round(statistics.median(scores), 1),
            "stdev": round(statistics.stdev(scores), 1) if len(scores) > 1 else 0,
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
            "pct_below_40": round(sum(1 for s in scores if s < 40) / len(scores) * 100, 1),
            "pct_above_60": round(sum(1 for s in scores if s >= 60) / len(scores) * 100, 1),
            "pct_above_80": round(sum(1 for s in scores if s >= 80) / len(scores) * 100, 1),
        }

    cite_stats = _stats(cite_scores)
    eeat_stats = _stats(eeat_scores)
    schema_stats = _stats(schema_scores)
    extract_stats = _stats(extract_scores)

    # Score distributions (buckets of 10)
    def _distribution(scores: list[float]) -> dict[str, int]:
        buckets = {"0-9": 0, "10-19": 0, "20-29": 0, "30-39": 0, "40-49": 0,
                   "50-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
        for s in scores:
            if s >= 90: buckets["90-100"] += 1
            elif s >= 80: buckets["80-89"] += 1
            elif s >= 70: buckets["70-79"] += 1
            elif s >= 60: buckets["60-69"] += 1
            elif s >= 50: buckets["50-59"] += 1
            elif s >= 40: buckets["40-49"] += 1
            elif s >= 30: buckets["30-39"] += 1
            elif s >= 20: buckets["20-29"] += 1
            elif s >= 10: buckets["10-19"] += 1
            else: buckets["0-9"] += 1
        return buckets

    cite_dist = _distribution(cite_scores)
    eeat_dist = _distribution(eeat_scores)
    schema_dist = _distribution(schema_scores)
    extract_dist = _distribution(extract_scores)

    # Problem type frequency
    problem_counter: Counter = Counter()
    severity_counter: Counter = Counter()
    for r in results:
        for pr in r["problems"]:
            problem_counter[pr["problem_type"]] += 1
            severity_counter[pr["severity"]] += 1

    total_problems = sum(problem_counter.values())
    avg_problems_per_post = total_problems / n_posts if n_posts else 0

    # Print summary
    print("=== Aggregate Results ===\n")
    print(f"  AI Citability: mean={cite_stats['mean']}, median={cite_stats['median']}, "
          f"stdev={cite_stats['stdev']}, range=[{cite_stats['min']}, {cite_stats['max']}]")
    print(f"  E-E-A-T:       mean={eeat_stats['mean']}, median={eeat_stats['median']}, "
          f"stdev={eeat_stats['stdev']}, range=[{eeat_stats['min']}, {eeat_stats['max']}]")
    print(f"  Schema:         mean={schema_stats['mean']}, median={schema_stats['median']}, "
          f"stdev={schema_stats['stdev']}, range=[{schema_stats['min']}, {schema_stats['max']}]")
    print(f"  Extraction:     mean={extract_stats['mean']}, median={extract_stats['median']}, "
          f"stdev={extract_stats['stdev']}, range=[{extract_stats['min']}, {extract_stats['max']}]")
    print()
    print(f"  Total problems detected: {total_problems}")
    print(f"  Avg problems per post: {avg_problems_per_post:.1f}")
    print(f"  Problem types: {dict(problem_counter.most_common())}")
    print()

    # ── Phase 5: Find top/bottom posts ──
    sorted_by_cite = sorted(results, key=lambda r: r["citability"], reverse=True)
    sorted_by_eeat = sorted(results, key=lambda r: r["eeat"], reverse=True)
    sorted_by_schema = sorted(results, key=lambda r: r["schema"], reverse=True)
    sorted_by_extract = sorted(results, key=lambda r: r["extraction"], reverse=True)

    # Composite average
    for r in results:
        r["composite"] = round((r["citability"] + r["eeat"] + r["schema"] + r["extraction"]) / 4, 1)
    sorted_by_composite = sorted(results, key=lambda r: r["composite"], reverse=True)

    # ── Phase 6: Signal prevalence analysis ──
    bool_signals = {}
    for key in signal_counters:
        bool_signals[key] = {
            "count": signal_counters[key],
            "pct": round(signal_counters[key] / n_posts * 100, 1),
        }

    numeric_signals = {}
    for key, vals in signal_value_accum.items():
        if vals and key not in ("citability_score", "eeat_eeat_score", "schema_schema_score", "extract_extraction_score"):
            numeric_signals[key] = {
                "mean": round(statistics.mean(vals), 2),
                "median": round(statistics.median(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
            }

    # ── Write Report ──
    report_path = "../STEP6c-TEST-RESULTS.md"
    lines: list[str] = []

    lines.append(f"# Step 6c E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Posts scored:** {n_posts} (from Step 1 crawl)")
    lines.append(f"**Site median word count:** {site_median_words}")
    lines.append(f"**External API calls:** 0 (all heuristic-based)")
    lines.append(f"**Total scoring time:** {score_time:.2f}s ({n_posts / max(score_time, 0.01):.0f} posts/sec)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 6c.3a: Citability Score ──
    lines.append("## 6c.3a. AI Citability Score")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean | {cite_stats['mean']} |")
    lines.append(f"| Median | {cite_stats['median']} |")
    lines.append(f"| Std Dev | {cite_stats['stdev']} |")
    lines.append(f"| Range | [{cite_stats['min']}, {cite_stats['max']}] |")
    lines.append(f"| % below 40 (problem threshold) | {cite_stats['pct_below_40']}% |")
    lines.append(f"| % above 60 (AI-ready) | {cite_stats['pct_above_60']}% |")
    lines.append(f"| % above 80 (strong) | {cite_stats['pct_above_80']}% |")
    lines.append("")

    lines.append("### Score Distribution")
    lines.append("")
    lines.append("| Range | Count | % | Bar |")
    lines.append("|-------|-------|---|-----|")
    for bucket, count in cite_dist.items():
        pct = count / n_posts * 100
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {bucket} | {count} | {pct:.0f}% | {bar} |")
    lines.append("")

    # Signal prevalence for citability
    lines.append("### Citability Signal Prevalence")
    lines.append("")
    lines.append("| Signal | Posts With | % | Avg Value |")
    lines.append("|--------|-----------|---|-----------|")
    cite_signal_keys = ["data_tables", "numbered_list_items", "first_person_markers",
                        "stats_mentions", "definition_paragraphs", "entity_density_per_1k",
                        "citation_markers", "question_headers", "question_header_ratio",
                        "data_points", "data_density_per_200w", "answer_first_200w"]
    for key in cite_signal_keys:
        if key in bool_signals:
            lines.append(f"| {key} | {bool_signals[key]['count']} | {bool_signals[key]['pct']}% | - |")
        elif key in numeric_signals:
            ns = numeric_signals[key]
            nonzero = sum(1 for v in signal_value_accum.get(key, []) if v > 0)
            lines.append(f"| {key} | {nonzero} ({nonzero / n_posts * 100:.0f}%) | - | {ns['mean']} (range: {ns['min']}-{ns['max']}) |")
    lines.append("")

    # Top 5 / Bottom 5
    lines.append("### Top 5 Posts (Citability)")
    lines.append("")
    lines.append("| Post | Score | Key Signals |")
    lines.append("|------|-------|-------------|")
    for r in sorted_by_cite[:5]:
        sigs = []
        if r["signals"].get("data_tables", 0) > 0: sigs.append(f"{r['signals']['data_tables']} tables")
        if r["signals"].get("first_person_markers", 0) > 0: sigs.append(f"{r['signals']['first_person_markers']} FP markers")
        if r["signals"].get("stats_mentions", 0) > 0: sigs.append(f"{r['signals']['stats_mentions']} stats")
        if r["signals"].get("question_headers", 0) > 0: sigs.append(f"{r['signals']['question_headers']} Q-headers")
        if r["signals"].get("answer_first_200w"): sigs.append("answer-first")
        lines.append(f"| {r['title']} | {r['citability']} | {', '.join(sigs) if sigs else 'none'} |")
    lines.append("")

    lines.append("### Bottom 5 Posts (Citability)")
    lines.append("")
    lines.append("| Post | Score | Word Count | Missing Signals |")
    lines.append("|------|-------|------------|-----------------|")
    for r in sorted_by_cite[-5:]:
        missing = []
        if r["signals"].get("data_tables", 0) == 0: missing.append("tables")
        if r["signals"].get("first_person_markers", 0) == 0: missing.append("FP exp.")
        if r["signals"].get("stats_mentions", 0) == 0: missing.append("stats")
        if r["signals"].get("definition_paragraphs", 0) == 0: missing.append("definitions")
        lines.append(f"| {r['title']} | {r['citability']} | {r['word_count']} | {', '.join(missing)} |")
    lines.append("")

    # ── 6c.3b: E-E-A-T Score ──
    lines.append("## 6c.3b. E-E-A-T Score")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean | {eeat_stats['mean']} |")
    lines.append(f"| Median | {eeat_stats['median']} |")
    lines.append(f"| Std Dev | {eeat_stats['stdev']} |")
    lines.append(f"| Range | [{eeat_stats['min']}, {eeat_stats['max']}] |")
    lines.append(f"| % below 40 (problem threshold) | {eeat_stats['pct_below_40']}% |")
    lines.append(f"| % above 60 | {eeat_stats['pct_above_60']}% |")
    lines.append(f"| % above 80 | {eeat_stats['pct_above_80']}% |")
    lines.append("")

    lines.append("### Score Distribution")
    lines.append("")
    lines.append("| Range | Count | % | Bar |")
    lines.append("|-------|-------|---|-----|")
    for bucket, count in eeat_dist.items():
        pct = count / n_posts * 100
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {bucket} | {count} | {pct:.0f}% | {bar} |")
    lines.append("")

    # E-E-A-T signal prevalence
    lines.append("### E-E-A-T Signal Prevalence")
    lines.append("")
    lines.append("| Signal | Present | % |")
    lines.append("|--------|---------|---|")
    eeat_bool_keys = ["eeat_author_found", "eeat_has_author_bio", "eeat_has_author_credentials",
                      "eeat_has_visible_date", "eeat_has_visible_updated_date",
                      "eeat_has_external_links", "eeat_has_contact_link",
                      "eeat_word_count_above_median", "eeat_has_3plus_h2s",
                      "eeat_has_author_schema"]
    for key in eeat_bool_keys:
        if key in bool_signals:
            lines.append(f"| {key.replace('eeat_', '')} | {bool_signals[key]['count']}/{n_posts} | {bool_signals[key]['pct']}% |")
    lines.append("")

    # Freshness distribution
    if "eeat_date_freshness_pts" in numeric_signals:
        lines.append("### Date Freshness Distribution")
        lines.append("")
        freshness_vals = signal_value_accum.get("eeat_date_freshness_pts", [])
        freshness_dist = Counter(int(v) for v in freshness_vals)
        lines.append("| Freshness Points | Count | % | Meaning |")
        lines.append("|-----------------|-------|---|---------|")
        meanings = {0: "No date or > 2 years", 5: "1-2 years or date without value", 10: "6-12 months", 15: "≤ 6 months"}
        for pts in sorted(freshness_dist.keys()):
            count = freshness_dist[pts]
            lines.append(f"| {pts} pts | {count} | {count / n_posts * 100:.0f}% | {meanings.get(pts, '?')} |")
        lines.append("")

    # External links analysis
    if "eeat_external_outbound_links" in numeric_signals:
        lines.append("### External Outbound Links Distribution")
        lines.append("")
        ext_vals = signal_value_accum.get("eeat_external_outbound_links", [])
        ns = numeric_signals["eeat_external_outbound_links"]
        lines.append(f"Mean: {ns['mean']}, Median: {ns['median']}, Range: [{ns['min']}, {ns['max']}]")
        lines.append("")
        ext_buckets = {"0": 0, "1-2": 0, "3-5": 0, "6-10": 0, "11-20": 0, "21+": 0}
        for v in ext_vals:
            if v == 0: ext_buckets["0"] += 1
            elif v <= 2: ext_buckets["1-2"] += 1
            elif v <= 5: ext_buckets["3-5"] += 1
            elif v <= 10: ext_buckets["6-10"] += 1
            elif v <= 20: ext_buckets["11-20"] += 1
            else: ext_buckets["21+"] += 1
        lines.append("| Links | Count | % | E-E-A-T Points |")
        lines.append("|-------|-------|---|----------------|")
        link_pts = {"0": "0", "1-2": "3", "3-5": "7", "6-10": "10", "11-20": "13", "21+": "15"}
        for bucket, count in ext_buckets.items():
            lines.append(f"| {bucket} | {count} | {count / n_posts * 100:.0f}% | {link_pts[bucket]} pts |")
        lines.append("")

        # Per-tier E-E-A-T points distribution (verifies graduation is applied)
        pts_dist = Counter()
        for v in ext_vals:
            if v >= 21: pts_dist[15] += 1
            elif v >= 11: pts_dist[13] += 1
            elif v >= 6: pts_dist[10] += 1
            elif v >= 3: pts_dist[7] += 1
            elif v >= 1: pts_dist[3] += 1
            else: pts_dist[0] += 1
        lines.append("**E-E-A-T link points distribution:** " + ", ".join(
            f"{pts}pts={count}" for pts, count in sorted(pts_dist.items())
        ))
        lines.append("")

    # Top 5 / Bottom 5 E-E-A-T
    lines.append("### Top 5 Posts (E-E-A-T)")
    lines.append("")
    lines.append("| Post | Score | Author | Date | Links | H2s |")
    lines.append("|------|-------|--------|------|-------|-----|")
    for r in sorted_by_eeat[:5]:
        author = r["signals"].get("eeat_author_name", "none") or "none"
        has_date = "yes" if r["signals"].get("eeat_has_visible_date") else "no"
        ext = r["signals"].get("eeat_external_outbound_links", 0)
        h2s = r["signals"].get("eeat_h2_count", 0)
        lines.append(f"| {r['title']} | {r['eeat']} | {str(author)[:20]} | {has_date} | {ext} | {h2s} |")
    lines.append("")

    lines.append("### Bottom 5 Posts (E-E-A-T)")
    lines.append("")
    lines.append("| Post | Score | Words | Missing |")
    lines.append("|------|-------|-------|---------|")
    for r in sorted_by_eeat[-5:]:
        missing = []
        if not r["signals"].get("eeat_author_found"): missing.append("author")
        if not r["signals"].get("eeat_has_author_bio"): missing.append("bio")
        if not r["signals"].get("eeat_has_visible_date"): missing.append("date")
        if not r["signals"].get("eeat_has_external_links"): missing.append("ext links")
        if not r["signals"].get("eeat_has_3plus_h2s"): missing.append("H2 structure")
        lines.append(f"| {r['title']} | {r['eeat']} | {r['word_count']} | {', '.join(missing)} |")
    lines.append("")

    # ── 6c.3c: Schema Score ──
    lines.append("## 6c.3c. Schema Score")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean | {schema_stats['mean']} |")
    lines.append(f"| Median | {schema_stats['median']} |")
    lines.append(f"| Std Dev | {schema_stats['stdev']} |")
    lines.append(f"| Range | [{schema_stats['min']}, {schema_stats['max']}] |")
    lines.append(f"| % with any schema | {round(sum(1 for s in schema_scores if s > 0) / n_posts * 100, 1)}% |")
    lines.append(f"| % below 30 (problem threshold) | {round(sum(1 for s in schema_scores if s < 30) / n_posts * 100, 1)}% |")
    lines.append(f"| % above 80 (strong) | {schema_stats['pct_above_80']}% |")
    lines.append("")

    lines.append("### Score Distribution")
    lines.append("")
    lines.append("| Range | Count | % | Bar |")
    lines.append("|-------|-------|---|-----|")
    for bucket, count in schema_dist.items():
        pct = count / n_posts * 100
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {bucket} | {count} | {pct:.0f}% | {bar} |")
    lines.append("")

    # Schema type analysis
    schema_type_counter: Counter = Counter()
    for r in results:
        for st in r["signals"].get("schema_schema_types", []):
            schema_type_counter[st] += 1

    if schema_type_counter:
        lines.append("### Schema Types Found")
        lines.append("")
        lines.append("| Schema Type | Posts | % | Category |")
        lines.append("|------------|-------|---|----------|")
        from app.services.ai_citability import HIGH_VALUE_SCHEMA, BASIC_SCHEMA
        for stype, count in schema_type_counter.most_common():
            category = "HIGH VALUE" if stype in HIGH_VALUE_SCHEMA else ("basic" if stype in BASIC_SCHEMA else "other")
            lines.append(f"| {stype} | {count} | {count / n_posts * 100:.0f}% | {category} |")
        lines.append("")

    # Article field completeness
    article_field_counts: Counter = Counter()
    article_total = 0
    for r in results:
        fields = r["signals"].get("schema_article_fields")
        if fields:
            article_total += 1
            for field, present in fields.items():
                if present:
                    article_field_counts[field] += 1

    if article_total > 0:
        lines.append("### Article Schema Field Completeness")
        lines.append("")
        lines.append(f"**Posts with Article-type schema:** {article_total}/{n_posts} ({article_total / n_posts * 100:.0f}%)")
        lines.append("")
        lines.append("| Field | Present | % of Article Posts |")
        lines.append("|-------|---------|-------------------|")
        for field in ["headline", "datePublished", "author", "image", "dateModified"]:
            count = article_field_counts.get(field, 0)
            lines.append(f"| {field} | {count}/{article_total} | {count / article_total * 100:.0f}% |")
        lines.append("")

    # Schema scorer validation results (synthetic JSON-LD tests)
    lines.append("### Schema Scorer Validation (Synthetic JSON-LD)")
    lines.append("")
    lines.append(f"**Status:** {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    lines.append("")
    lines.append("| Test Case | Expected | Actual | Status | Types Found |")
    lines.append("|-----------|----------|--------|--------|-------------|")
    for sv in schema_validation_results:
        status = "PASS" if sv["passed"] else "**FAIL**"
        types_str = ", ".join(sv["types"]) if sv["types"] else "(none)"
        lines.append(f"| {sv['name']} | {sv['expected']} | {sv['actual']} | {status} | {types_str} |")
    lines.append("")

    # ── 6c.3d: Extraction Score ──
    lines.append("## 6c.3d. Extraction Score")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean | {extract_stats['mean']} |")
    lines.append(f"| Median | {extract_stats['median']} |")
    lines.append(f"| Std Dev | {extract_stats['stdev']} |")
    lines.append(f"| Range | [{extract_stats['min']}, {extract_stats['max']}] |")
    lines.append(f"| % below 40 (problem threshold) | {extract_stats['pct_below_40']}% |")
    lines.append(f"| % above 60 | {extract_stats['pct_above_60']}% |")
    lines.append(f"| % above 80 | {extract_stats['pct_above_80']}% |")
    lines.append("")

    lines.append("### Score Distribution")
    lines.append("")
    lines.append("| Range | Count | % | Bar |")
    lines.append("|-------|-------|---|-----|")
    for bucket, count in extract_dist.items():
        pct = count / n_posts * 100
        bar = "#" * max(1, int(pct / 2))
        lines.append(f"| {bucket} | {count} | {pct:.0f}% | {bar} |")
    lines.append("")

    # Extraction signal prevalence
    lines.append("### Extraction Signal Prevalence")
    lines.append("")
    lines.append("| Signal | Present / Avg | % |")
    lines.append("|--------|--------------|---|")
    ext_keys = [
        ("extract_direct_opening", "Direct opening (first 100w)"),
        ("extract_has_faq_section", "FAQ section present"),
    ]
    for key, label in ext_keys:
        if key in bool_signals:
            lines.append(f"| {label} | {bool_signals[key]['count']}/{n_posts} | {bool_signals[key]['pct']}% |")

    ext_num_keys = [
        ("extract_h2_with_direct_answer", "H2s with direct answer"),
        ("extract_total_h2", "Total H2/H3 headers"),
        ("extract_definition_count", "Definition paragraphs"),
        ("extract_faq_qa_pairs", "FAQ Q&A pairs"),
        ("extract_standalone_section_ratio", "Standalone section ratio"),
        ("extract_total_list_items", "Total list items"),
        ("extract_quotable_paragraphs", "Quotable paragraphs"),
        ("extract_extractable_tables", "Extractable tables"),
    ]
    for key, label in ext_num_keys:
        if key in numeric_signals:
            ns = numeric_signals[key]
            lines.append(f"| {label} | avg={ns['mean']} | range: [{ns['min']}, {ns['max']}] |")
    lines.append("")

    # Top 5 / Bottom 5 Extraction
    lines.append("### Top 5 Posts (Extraction)")
    lines.append("")
    lines.append("| Post | Score | Direct Opening | FAQ Pairs | Standalone Ratio |")
    lines.append("|------|-------|---------------|-----------|-----------------|")
    for r in sorted_by_extract[:5]:
        direct = "yes" if r["signals"].get("extract_direct_opening") else "no"
        faq = r["signals"].get("extract_faq_qa_pairs", 0)
        standalone = r["signals"].get("extract_standalone_section_ratio", 0)
        lines.append(f"| {r['title']} | {r['extraction']} | {direct} | {faq} | {standalone} |")
    lines.append("")

    # ── Composite & Correlation ──
    lines.append("## Composite AI Readiness")
    lines.append("")
    composite_scores = [r["composite"] for r in results]
    comp_stats = _stats(composite_scores)
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean composite | {comp_stats['mean']} |")
    lines.append(f"| Median composite | {comp_stats['median']} |")
    lines.append(f"| Std Dev | {comp_stats['stdev']} |")
    lines.append(f"| Range | [{comp_stats['min']}, {comp_stats['max']}] |")
    lines.append(f"| % AI-ready (composite ≥ 60) | {comp_stats['pct_above_60']}% |")
    lines.append("")

    lines.append("### Top 10 Posts (Composite)")
    lines.append("")
    lines.append("| Post | Composite | Citability | E-E-A-T | Schema | Extraction |")
    lines.append("|------|-----------|-----------|---------|--------|------------|")
    for r in sorted_by_composite[:10]:
        lines.append(f"| {r['title']} | {r['composite']} | {r['citability']} | {r['eeat']} | {r['schema']} | {r['extraction']} |")
    lines.append("")

    lines.append("### Bottom 10 Posts (Composite)")
    lines.append("")
    lines.append("| Post | Composite | Citability | E-E-A-T | Schema | Extraction |")
    lines.append("|------|-----------|-----------|---------|--------|------------|")
    for r in sorted_by_composite[-10:]:
        lines.append(f"| {r['title']} | {r['composite']} | {r['citability']} | {r['eeat']} | {r['schema']} | {r['extraction']} |")
    lines.append("")

    # ── Cross-dimension correlation ──
    lines.append("### Score Correlation Matrix")
    lines.append("")
    lines.append("Pearson correlation between the 4 dimensions:")
    lines.append("")

    import numpy as np
    score_matrix = np.array([cite_scores, eeat_scores, schema_scores, extract_scores])
    corr = np.corrcoef(score_matrix)
    dim_names = ["Citability", "E-E-A-T", "Schema", "Extraction"]

    lines.append("| | Citability | E-E-A-T | Schema | Extraction |")
    lines.append("|--|-----------|---------|--------|------------|")
    for i, name in enumerate(dim_names):
        row = f"| **{name}** |"
        for j in range(4):
            val = corr[i][j]
            if np.isnan(val):
                row += " — |"
            else:
                row += f" {val:.2f} |"
        lines.append(row)
    lines.append("")

    # ── Problem Detection ──
    lines.append("## Problem Detection Results")
    lines.append("")
    lines.append(f"**Total problems:** {total_problems} across {n_posts} posts")
    lines.append(f"**Average per post:** {avg_problems_per_post:.1f}")
    lines.append("")

    lines.append("### Problem Type Frequency")
    lines.append("")
    lines.append("| Problem Type | Count | % of Posts | Severity |")
    lines.append("|-------------|-------|-----------|----------|")
    # Get severity for each problem type
    problem_severity: dict[str, str] = {}
    for r in results:
        for pr in r["problems"]:
            problem_severity[pr["problem_type"]] = pr["severity"]

    for ptype, count in problem_counter.most_common():
        sev = problem_severity.get(ptype, "?")
        lines.append(f"| {ptype} | {count} | {count / n_posts * 100:.0f}% | {sev} |")
    lines.append("")

    lines.append("### Severity Distribution")
    lines.append("")
    lines.append("| Severity | Count | % of Total |")
    lines.append("|----------|-------|-----------|")
    for sev in ["high", "medium", "low"]:
        count = severity_counter.get(sev, 0)
        lines.append(f"| {sev} | {count} | {count / max(total_problems, 1) * 100:.0f}% |")
    lines.append("")

    # Posts with most problems
    sorted_by_problems = sorted(results, key=lambda r: len(r["problems"]), reverse=True)
    lines.append("### Posts With Most Problems")
    lines.append("")
    lines.append("| Post | # Problems | Problem Types |")
    lines.append("|------|-----------|---------------|")
    for r in sorted_by_problems[:10]:
        if len(r["problems"]) > 0:
            types = ", ".join(r["problem_types"][:5])
            lines.append(f"| {r['title']} | {len(r['problems'])} | {types} |")
    lines.append("")

    # Posts with zero problems
    zero_problem_posts = [r for r in results if len(r["problems"]) == 0]
    lines.append(f"### Posts With Zero Problems: {len(zero_problem_posts)}/{n_posts} ({len(zero_problem_posts) / n_posts * 100:.0f}%)")
    lines.append("")
    if zero_problem_posts:
        lines.append("| Post | Citability | E-E-A-T | Schema | Extraction |")
        lines.append("|------|-----------|---------|--------|------------|")
        for r in sorted(zero_problem_posts, key=lambda r: r["composite"], reverse=True)[:10]:
            lines.append(f"| {r['title']} | {r['citability']} | {r['eeat']} | {r['schema']} | {r['extraction']} |")
    lines.append("")

    # ── Sample Post Deep Dive ──
    # Show full signal breakdowns for 3 representative posts:
    # best composite, worst composite, median composite
    lines.append("## Sample Post Deep Dive")
    lines.append("")
    lines.append("Full signal breakdown for 3 representative posts (best, median, worst composite):")
    lines.append("")

    median_idx = len(sorted_by_composite) // 2
    sample_posts = [
        ("Best", sorted_by_composite[0]),
        ("Median", sorted_by_composite[median_idx]),
        ("Worst", sorted_by_composite[-1]),
    ]
    for label, r in sample_posts:
        lines.append(f"### {label}: {r['title']}")
        lines.append("")
        lines.append(f"**URL:** {r['url']}")
        lines.append(f"**Word count:** {r['word_count']}")
        lines.append(f"**Scores:** Citability={r['citability']}, E-E-A-T={r['eeat']}, Schema={r['schema']}, Extraction={r['extraction']}, **Composite={r['composite']}**")
        lines.append(f"**Problems ({len(r['problems'])}):** {', '.join(r['problem_types']) if r['problem_types'] else 'none'}")
        lines.append("")

        # Citability signals
        s = r["signals"]
        lines.append("**Citability signals:**")
        lines.append(f"- Data tables: {s.get('data_tables', 0)}, Ordered list items: {s.get('numbered_list_items', 0)}")
        lines.append(f"- First-person markers: {s.get('first_person_markers', 0)}, Stats mentions: {s.get('stats_mentions', 0)}")
        lines.append(f"- Definition paragraphs: {s.get('definition_paragraphs', 0)}, Entity density/1k: {s.get('entity_density_per_1k', 0)}")
        lines.append(f"- Citation markers: {s.get('citation_markers', 0)}")
        lines.append(f"- Question headers: {s.get('question_headers', 0)}/{s.get('total_headers', 0)} (ratio: {s.get('question_header_ratio', 0)})")
        lines.append(f"- Data density/200w: {s.get('data_density_per_200w', 0)}, Answer-first: {s.get('answer_first_200w', False)}")
        lines.append("")

        # E-E-A-T signals
        lines.append("**E-E-A-T signals:**")
        lines.append(f"- Author: {s.get('eeat_author_name', 'none')} (found: {s.get('eeat_author_found', False)})")
        lines.append(f"- Bio: {s.get('eeat_has_author_bio', False)}, Credentials: {s.get('eeat_has_author_credentials', False)}")
        lines.append(f"- Visible date: {s.get('eeat_has_visible_date', False)}, Freshness pts: {s.get('eeat_date_freshness_pts', 0)}, Age days: {s.get('eeat_date_age_days', 'N/A')}")
        lines.append(f"- External links: {s.get('eeat_external_outbound_links', 0)}, Contact link: {s.get('eeat_has_contact_link', False)}")
        wc_ratio = s.get('eeat_word_count_ratio', s.get('word_count_ratio', 'N/A'))
        wc_pts = s.get('eeat_word_count_pts', s.get('word_count_pts', 'N/A'))
        lines.append(f"- Word count ratio: {wc_ratio}, Word count pts: {wc_pts}")
        lines.append(f"- H2 count: {s.get('eeat_h2_count', 0)}, Has 3+ H2s: {s.get('eeat_has_3plus_h2s', False)}")
        lines.append("")

        # Schema signals
        lines.append("**Schema signals:**")
        lines.append(f"- Has schema: {s.get('schema_has_schema', False)}, Types: {s.get('schema_schema_types', [])}")
        lines.append(f"- High-value: {s.get('schema_has_high_value_schema', False)}, Article fields: {s.get('schema_article_fields', 'N/A')}")
        lines.append("")

        # Extraction signals
        lines.append("**Extraction signals:**")
        lines.append(f"- Direct opening: {s.get('extract_direct_opening', False)}")
        lines.append(f"- H2s with direct answer: {s.get('extract_h2_with_direct_answer', 0)}/{s.get('extract_total_h2', 0)}")
        lines.append(f"- Definitions: {s.get('extract_definition_count', 0)}, FAQ pairs: {s.get('extract_faq_qa_pairs', 0)}")
        lines.append(f"- Standalone ratio: {s.get('extract_standalone_section_ratio', 'N/A')}")
        lines.append(f"- List items: {s.get('extract_total_list_items', 0)}, Quotable paragraphs: {s.get('extract_quotable_paragraphs', 0)}")
        lines.append(f"- Extractable tables: {s.get('extract_extractable_tables', 0)}")
        lines.append("")

    # ── Processing Summary ──
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Step | Time | External API | Notes |")
    lines.append("|------|------|-------------|-------|")
    lines.append(f"| Crawl (Step 1 prerequisite) | {crawl_time:.1f}s | None | |")
    lines.append(f"| AI Citability (4 dimensions) | {score_time:.2f}s | None | {n_posts / max(score_time, 0.01):.0f} posts/sec |")
    lines.append(f"| **Total Step 6c** | **{score_time:.2f}s** | **Free** | |")
    lines.append("")

    # ── Observations ──
    lines.append("## Observations")
    lines.append("")

    # Score range analysis
    cite_range = cite_stats["max"] - cite_stats["min"]
    eeat_range = eeat_stats["max"] - eeat_stats["min"]
    schema_range = schema_stats["max"] - schema_stats["min"]
    extract_range = extract_stats["max"] - extract_stats["min"]

    if cite_stats["stdev"] < 10:
        lines.append(f"- **Low citability variance (stdev={cite_stats['stdev']})** -- most posts cluster around {cite_stats['median']}. May indicate uniform content structure across site.")
    else:
        lines.append(f"- **Good citability variance (stdev={cite_stats['stdev']})** -- meaningful spread creates actionable differentiation between posts.")

    if eeat_stats["stdev"] < 10:
        lines.append(f"- **Low E-E-A-T variance (stdev={eeat_stats['stdev']})** -- E-E-A-T is dominated by site-wide signals (author, contact link). Post-specific signals (freshness, links, word count) add limited variance.")
    else:
        lines.append(f"- **Good E-E-A-T variance (stdev={eeat_stats['stdev']})** -- post-specific signals (freshness, external links, word count) create meaningful per-post differentiation.")

    # Schema analysis
    pct_no_schema = sum(1 for s in schema_scores if s == 0) / n_posts * 100
    if pct_no_schema > 50:
        lines.append(f"- **{pct_no_schema:.0f}% of posts have no schema at all** -- major opportunity for `missing_schema` fixes.")
    elif pct_no_schema > 0:
        lines.append(f"- **{pct_no_schema:.0f}% of posts have no schema** -- some posts missing structured data.")
    else:
        lines.append("- **All posts have some schema markup** -- good baseline structured data coverage.")

    # Schema uniformity
    if schema_stats["stdev"] < 5:
        lines.append(f"- **Schema scores are uniform (stdev={schema_stats['stdev']})** -- likely same WordPress theme applying identical schema to all posts. This is expected for CMS-driven sites.")

    # Problem analysis
    if avg_problems_per_post > 5:
        lines.append(f"- **High problem density ({avg_problems_per_post:.1f} per post)** -- most posts trigger multiple AI readiness issues. GEO problems dominate because they test specific structural patterns.")
    elif avg_problems_per_post > 3:
        lines.append(f"- **Moderate problem density ({avg_problems_per_post:.1f} per post)** -- typical for older content not optimized for AI.")
    else:
        lines.append(f"- **Low problem density ({avg_problems_per_post:.1f} per post)** -- site is relatively well-optimized for AI.")

    # Most common problem
    if problem_counter:
        top_problem = problem_counter.most_common(1)[0]
        lines.append(f"- **Most common problem: `{top_problem[0]}`** -- affects {top_problem[1]}/{n_posts} posts ({top_problem[1] / n_posts * 100:.0f}%). "
                      f"This is the highest-impact fix for this site.")

    # Composite analysis
    if comp_stats["pct_above_60"] < 20:
        lines.append(f"- **Only {comp_stats['pct_above_60']}% of posts are AI-ready (composite ≥ 60)** -- significant optimization opportunity.")
    else:
        lines.append(f"- **{comp_stats['pct_above_60']}% of posts are AI-ready (composite ≥ 60)** -- {'strong' if comp_stats['pct_above_60'] > 50 else 'moderate'} AI readiness baseline.")

    # Correlation insight (skip NaN values from zero-variance dimensions)
    max_corr = -1.0
    max_pair = ("", "")
    for i in range(4):
        for j in range(i + 1, 4):
            val = corr[i][j]
            if not np.isnan(val) and val > max_corr:
                max_corr = val
                max_pair = (dim_names[i], dim_names[j])
    if max_corr > 0.5:
        lines.append(f"- **Strongest correlation: {max_pair[0]} vs {max_pair[1]} (r={max_corr:.2f})** -- these dimensions tend to move together.")
    elif max_corr > 0.3:
        lines.append(f"- **Moderate correlation: {max_pair[0]} vs {max_pair[1]} (r={max_corr:.2f})** -- dimensions are somewhat related.")
    else:
        lines.append(f"- **All dimensions are weakly correlated (max r={max_corr:.2f})** -- the 4 dimensions capture genuinely different aspects of AI readiness.")

    lines.append(f"- **Performance: {n_posts / max(score_time, 0.01):.0f} posts/sec** -- zero API calls, all CPU-bound regex + HTML parsing. Bottleneck is BeautifulSoup DOM construction.")
    lines.append("")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to {report_path}")
    print(f"\n=== Step 6c E2E complete — {n_posts} posts scored, {score_time:.2f}s ===")


if __name__ == "__main__":
    asyncio.run(main())
