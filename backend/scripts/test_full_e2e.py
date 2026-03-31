"""Full E2E test: Pipeline Steps 1 + 2 against a real site.

Runs crawl, normalize, readability, intent, AI citability — captures everything.
No database or API keys required.
"""

import asyncio
import json
import re
import time
from collections import Counter
from datetime import datetime

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


async def main():
    from app.services.normalizer import (
        NormalizedPost, filter_nav_links, filter_sitewide_headings,
        _strip_site_name_from_title, _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.services.readability import (
        compute_flesch_reading_ease, compute_grade_level,
    )
    from app.services.fast_intent import classify_intent
    from app.services.ai_citability import (
        compute_citability_score, compute_eeat_score,
        compute_schema_score, compute_extraction_score,
        generate_ai_problems,
    )
    from app.utils.url_normalize import normalize_url

    L = []  # report lines
    def w(s=""): L.append(s)

    w(f"# Full Pipeline E2E Test: {TARGET_DOMAIN}")
    w(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    w(f"**Target:** `{TARGET_SITEMAP}`")
    w(f"**Max pages cap:** {MAX_PAGES}")
    w(f"**Pipeline steps tested:** Step 1 (Crawl + Normalize) + Step 2 (Enrichment)")
    w()
    w("---")
    w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: CRAWL + NORMALIZE
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

    print("Step 1: Crawling...")
    t0 = time.time()
    raw_posts = await crawler.crawl()
    crawl_time = time.time() - t0

    skipped = getattr(crawler, '_skipped', [])
    skip_reasons = Counter(reason for _, reason in skipped)

    # Normalize
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

    # ── Step 1 Report ──
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

    # Content stats
    word_counts = [p.word_count for p in posts]
    w("## 1.3 Content Statistics")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Total posts | {total} |")
    w(f"| Total words | {sum(word_counts):,} |")
    w(f"| Avg word count | {sum(word_counts)//total:,} |")
    w(f"| Median word count | {sorted(word_counts)[total//2]:,} |")
    w(f"| Min word count | {min(word_counts):,} |")
    w(f"| Max word count | {max(word_counts):,} |")
    w()

    # Page types
    page_types = Counter(p.page_type for p in posts)
    w("### Page Type Distribution")
    w()
    w("| Type | Count | % |")
    w("|------|-------|---|")
    for pt, c in page_types.most_common():
        w(f"| {pt} | {c} | {c/total*100:.1f}% |")
    w()

    # Language
    langs = Counter(p.language for p in posts)
    w("### Language")
    w()
    w("| Language | Count |")
    w("|----------|-------|")
    for lang, c in langs.most_common():
        w(f"| {lang or 'None'} | {c} |")
    w()

    # Field coverage
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

    # Internal links
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

    # Heading structure
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

    # Top/bottom posts by word count
    by_words = sorted(posts, key=lambda p: p.word_count)

    w("## 1.7 Longest Posts")
    w()
    w("| # | Title | Words | Type |")
    w("|---|-------|-------|------|")
    for i, p in enumerate(by_words[-5:][::-1], 1):
        t = p.title[:55] + "..." if len(p.title) > 55 else p.title
        w(f"| {i} | {t} | {p.word_count:,} | {p.page_type} |")
    w()

    w("## 1.8 Shortest Posts")
    w()
    w("| # | Title | Words | Type |")
    w("|---|-------|-------|------|")
    for i, p in enumerate(by_words[:5], 1):
        t = p.title[:55] + "..." if len(p.title) > 55 else p.title
        w(f"| {i} | {t} | {p.word_count:,} | {p.page_type} |")
    w()

    # Posts missing dates
    no_dates = [p for p in posts if not p.publish_date and not p.modified_date]
    if no_dates:
        w("## 1.9 Posts Missing Both Dates")
        w()
        w(f"**{len(no_dates)} posts** have no publish_date or modified_date:")
        w()
        for p in no_dates[:10]:
            u = p.url.replace(f"https://{TARGET_DOMAIN}", "")
            w(f"- `{u}` -- {p.word_count} words, type: {p.page_type}")
        w()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: ENRICHMENT
    # ═══════════════════════════════════════════════════════════════════
    w("---")
    w()
    w("# STEP 2: Enrichment")
    w()

    # ── 2a: Embeddings (simulated) ──
    print("Step 2a: Embedding simulation...")
    embeddable = [p for p in posts if p.body_text and len(p.body_text.strip()) > 50]
    text_lengths = []
    short_count = 0
    long_count = 0
    total_chunks = 0
    for p in embeddable:
        text = f"{p.title}\n\n{p.body_text}"
        tl = len(text)
        text_lengths.append(tl)
        if tl <= 20000:
            short_count += 1
            total_chunks += 1
        else:
            long_count += 1
            # Simulate chunking
            chunks = 1
            remaining = tl - 20000
            chunk_body = 20000 - len(f"{p.title}\n\n") - 500  # overlap
            while remaining > 200:
                chunks += 1
                remaining -= chunk_body
            total_chunks += chunks

    total_chars = sum(text_lengths)
    est_tokens = total_chars / 4
    est_cost = est_tokens / 1_000_000 * 0.02
    batches = (short_count + 99) // 100

    w("## 2a. Embeddings (Simulated)")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts to embed | {len(embeddable)} |")
    w(f"| Short posts (single text, batchable) | {short_count} |")
    w(f"| Long posts (>20K chars, chunked) | {long_count} |")
    w(f"| Total chunks to embed | {total_chunks} |")
    w(f"| Total text chars | {total_chars:,} |")
    w(f"| Estimated tokens | ~{int(est_tokens):,} |")
    w(f"| Estimated cost | ${est_cost:.4f} |")
    w(f"| Batches (short posts) | {batches} |")
    w(f"| API calls (chunks + batches) | {batches + (total_chunks - short_count)} |")
    w(f"| Avg text length | {total_chars//len(embeddable):,} chars |")
    w(f"| Max text length | {max(text_lengths):,} chars |")
    w(f"| Posts hitting 20K truncation (now chunked) | {long_count} ({long_count/len(embeddable)*100:.1f}%) |")
    w()

    if long_count > 0:
        w("### Long Posts (Chunked)")
        w()
        w("| Title | Chars | Est. Chunks |")
        w("|-------|-------|-------------|")
        long_posts_detail = sorted(
            [(p, len(f"{p.title}\n\n{p.body_text}")) for p in embeddable if len(f"{p.title}\n\n{p.body_text}") > 20000],
            key=lambda x: -x[1]
        )
        for p, tl in long_posts_detail[:10]:
            t = p.title[:50] + "..." if len(p.title) > 50 else p.title
            chunks_est = 1 + max(0, (tl - 20000) // 15000) + 1
            w(f"| {t} | {tl:,} | {chunks_est} |")
        w()

    # ── 2b: Readability ──
    print("Step 2b: Readability...")
    t1 = time.time()
    readability = []
    for p in posts:
        if not p.body_text or len(p.body_text) < 100:
            continue
        fre = compute_flesch_reading_ease(p.body_text)
        grade = compute_grade_level(p.body_text)
        readability.append({"url": p.url, "title": p.title, "fre": fre, "grade": grade, "words": p.word_count})
    read_time = time.time() - t1

    fre_scores = [r["fre"] for r in readability]
    grade_scores = [r["grade"] for r in readability]
    avg_fre = sum(fre_scores) / len(fre_scores) if fre_scores else 0
    avg_grade = sum(grade_scores) / len(grade_scores) if grade_scores else 0

    w("## 2b. Readability Scores")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts scored | {len(readability)} |")
    w(f"| Processing time | {read_time:.3f}s |")
    w(f"| **Avg Flesch Reading Ease** | **{avg_fre:.1f}** |")
    w(f"| **Avg Grade Level** | **{avg_grade:.1f}** |")
    w(f"| Min FRE | {min(fre_scores):.1f} |")
    w(f"| Max FRE | {max(fre_scores):.1f} |")
    w()

    # Distribution
    w("### Distribution")
    w()
    w("| Range | Label | Count | % |")
    w("|-------|-------|-------|---|")
    ranges = [(90,100,"Very easy"),(80,89,"Easy"),(70,79,"Fairly easy"),
              (60,69,"Standard (sweet spot)"),(50,59,"Fairly difficult"),
              (30,49,"Difficult"),(0,29,"Very confusing")]
    for lo, hi, label in ranges:
        c = sum(1 for s in fre_scores if lo <= s <= hi)
        w(f"| {lo}-{hi} | {label} | {c} | {c/len(fre_scores)*100:.0f}% |")
    w()

    # Hardest / easiest
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

    # ── 2d: Intent ──
    print("Step 2d: Intent...")
    t2 = time.time()
    intents = []
    for p in posts:
        intent = classify_intent(p.title or "", p.url or "", p.word_count or 0)
        intents.append({"url": p.url, "title": p.title, "intent": intent})
    intent_time = time.time() - t2
    intent_dist = Counter(r["intent"] for r in intents)

    w("## 2d. Intent Classification")
    w()
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Posts classified | {len(intents)} |")
    w(f"| Processing time | {intent_time:.4f}s |")
    w()

    w("### Distribution")
    w()
    w("| Intent | Count | % |")
    w("|--------|-------|---|")
    for intent, c in intent_dist.most_common():
        w(f"| {intent} | {c} | {c/len(intents)*100:.1f}% |")
    w()

    non_info = [r for r in intents if r["intent"] != "informational"]
    if non_info:
        w("### Non-Informational Posts (All)")
        w()
        w("| Intent | Title | URL |")
        w("|--------|-------|-----|")
        for r in non_info:
            t = r["title"][:45] + "..." if len(r["title"]) > 45 else r["title"]
            u = r["url"].replace(f"https://{TARGET_DOMAIN}", "")
            w(f"| {r['intent']} | {t} | `{u}` |")
        w()

    # ── 2e: AI Citability ──
    print("Step 2e: AI Citability...")
    t3 = time.time()

    # Calculate site median word count for E-E-A-T scoring
    all_word_counts = sorted(p.word_count for p in posts if p.body_text)
    site_median_words = all_word_counts[len(all_word_counts) // 2] if all_word_counts else 0

    ai_results = []
    all_problems = []
    for p in posts:
        if not p.body_text:
            continue
        cite, cite_sig = compute_citability_score(p.body_text, p.body_html)
        eeat, eeat_sig = compute_eeat_score(
            p.body_html, crawl_eeat=p.eeat_signals,
            headings=p.headings, word_count=p.word_count,
            site_median_words=site_median_words,
            publish_date=p.publish_date, modified_date=p.modified_date,
        )
        schema, schema_sig = compute_schema_score(p.body_html)
        extract, extract_sig = compute_extraction_score(p.body_text, p.body_html, p.headings)
        all_sig = {**cite_sig, **{f"eeat_{k}": v for k, v in eeat_sig.items()},
                   **{f"schema_{k}": v for k, v in schema_sig.items()},
                   **{f"extract_{k}": v for k, v in extract_sig.items()}}
        problems = generate_ai_problems(p.url, p.title, cite, eeat, schema, extract, all_sig)
        all_problems.extend(problems)
        ai_results.append({
            "url": p.url, "title": p.title, "words": p.word_count,
            "cite": cite, "eeat": eeat, "schema": schema, "extract": extract,
            "signals": all_sig, "problems": len(problems),
        })
    ai_time = time.time() - t3

    def _avg(lst): return sum(lst)/len(lst) if lst else 0
    cite_scores = [r["cite"] for r in ai_results]
    eeat_scores = [r["eeat"] for r in ai_results]
    schema_scores = [r["schema"] for r in ai_results]
    extract_scores = [r["extract"] for r in ai_results]

    w("## 2e. AI Citability Scores")
    w()
    w("| Dimension | Avg | Min | Max | Median |")
    w("|-----------|-----|-----|-----|--------|")
    for name, scores in [("Citability", cite_scores), ("E-E-A-T", eeat_scores),
                          ("Schema", schema_scores), ("Extraction", extract_scores)]:
        s = sorted(scores)
        w(f"| {name} | {_avg(s):.1f} | {min(s)} | {max(s)} | {s[len(s)//2]} |")
    w()

    ai_ready = sum(1 for s in cite_scores if s >= 60)
    has_schema = sum(1 for s in schema_scores if s > 0)
    w(f"**AI-ready posts (citability >= 60):** {ai_ready} ({ai_ready/len(cite_scores)*100:.1f}%)")
    w(f"**Has any schema:** {has_schema} ({has_schema/len(schema_scores)*100:.1f}%)")
    w()

    # Score distribution buckets
    w("### Citability Distribution")
    w()
    w("| Range | Count | % |")
    w("|-------|-------|---|")
    for lo, hi, label in [(80,100,"Excellent"),(60,79,"Good"),(40,59,"Moderate"),(20,39,"Weak"),(0,19,"Poor")]:
        c = sum(1 for s in cite_scores if lo <= s <= hi)
        w(f"| {lo}-{hi} ({label}) | {c} | {c/len(cite_scores)*100:.0f}% |")
    w()

    w("### E-E-A-T Distribution")
    w()
    w("| Range | Count | % |")
    w("|-------|-------|---|")
    for lo, hi, label in [(80,100,"Excellent"),(60,79,"Good"),(40,59,"Moderate"),(20,39,"Weak"),(0,19,"Poor")]:
        c = sum(1 for s in eeat_scores if lo <= s <= hi)
        w(f"| {lo}-{hi} ({label}) | {c} | {c/len(eeat_scores)*100:.0f}% |")
    w()

    # Top 10 most AI-ready
    by_cite = sorted(ai_results, key=lambda r: r["cite"], reverse=True)
    w("### Most AI-Ready Posts (Top 10)")
    w()
    w("| # | Title | Cite | EEAT | Schema | Extract | Words |")
    w("|---|-------|------|------|--------|---------|-------|")
    for i, r in enumerate(by_cite[:10], 1):
        t = r["title"][:40] + "..." if len(r["title"]) > 40 else r["title"]
        w(f"| {i} | {t} | {r['cite']} | {r['eeat']} | {r['schema']} | {r['extract']} | {r['words']:,} |")
    w()

    # Bottom 10
    w("### Least AI-Ready Posts (Bottom 10)")
    w()
    w("| # | Title | Cite | EEAT | Schema | Extract | Words |")
    w("|---|-------|------|------|--------|---------|-------|")
    for i, r in enumerate(by_cite[-10:][::-1], 1):
        t = r["title"][:40] + "..." if len(r["title"]) > 40 else r["title"]
        w(f"| {i} | {t} | {r['cite']} | {r['eeat']} | {r['schema']} | {r['extract']} | {r['words']:,} |")
    w()

    # Problems
    problem_dist = Counter(p["problem_type"] for p in all_problems)
    w("## AI Readiness Problems")
    w()
    w(f"**Total problems:** {len(all_problems)} across {total} posts")
    w(f"**Avg problems per post:** {len(all_problems)/total:.1f}")
    w()
    w("| Problem Type | Count | % of Posts | Severity |")
    w("|-------------|-------|-----------|----------|")
    for ptype, count in problem_dist.most_common():
        sev = Counter(p["severity"] for p in all_problems if p["problem_type"] == ptype)
        sev_str = ", ".join(f"{s}={c}" for s, c in sev.most_common())
        w(f"| `{ptype}` | {count} | {count/total*100:.0f}% | {sev_str} |")
    w()

    # ── Sample Posts (3 different quality levels) ──
    w("---")
    w()
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

        # Key signals
        sig = r["signals"]
        w("**Key Signals:**")
        w()
        w("| Signal | Value |")
        w("|--------|-------|")
        signal_keys = [
            ("data_tables", "Data tables"),
            ("numbered_list_items", "Numbered list items"),
            ("first_person_markers", "First-person markers"),
            ("stats_mentions", "Statistics mentions"),
            ("definition_paragraphs", "Definition paragraphs"),
            ("entity_density_per_1k", "Entity density (per 1K words)"),
            ("citation_markers", "Citation markers"),
            ("question_headers", "Question-format headers"),
            ("total_headers", "Total headers"),
            ("question_header_ratio", "Question header ratio"),
            ("data_density_per_200w", "Data density (per 200 words)"),
            ("answer_first_200w", "Answer-first structure"),
            ("eeat_author_found", "Author found"),
            ("eeat_author_name", "Author name"),
            ("eeat_has_author_bio", "Author bio"),
            ("eeat_has_author_credentials", "Author credentials"),
            ("eeat_has_visible_date", "Visible date"),
            ("eeat_date_freshness_pts", "Date freshness pts"),
            ("eeat_date_age_days", "Date age (days)"),
            ("eeat_has_visible_updated_date", "Visible updated date"),
            ("eeat_has_author_schema", "Author schema (not scored)"),
            ("eeat_external_outbound_links", "External outbound links"),
            ("eeat_has_external_links", "Has external links"),
            ("eeat_has_contact_link", "Contact/About link"),
            ("eeat_word_count_above_median", "Word count above median"),
            ("eeat_h2_count", "H2 section count"),
            ("eeat_has_3plus_h2s", "Has 3+ H2 sections"),
            ("schema_has_schema", "Has JSON-LD schema"),
            ("schema_schema_types", "Schema types"),
            ("extract_direct_opening", "Direct opening"),
            ("extract_h2_with_direct_answer", "H2s with direct answer"),
            ("extract_total_h2", "Total H2s"),
            ("extract_has_faq_section", "FAQ section"),
            ("extract_faq_qa_pairs", "FAQ Q&A pairs"),
            ("extract_standalone_section_ratio", "Standalone section ratio"),
            ("quotable_paragraphs", "Quotable paragraphs"),
            ("extract_extractable_tables", "Extractable tables"),
        ]
        for key, label_str in signal_keys:
            val = sig.get(key)
            if val is not None and val != "" and val != [] and val != 0 and val is not False:
                w(f"| {label_str} | {val} |")
        w()

    # ── Readability x Citability correlation ──
    w("---")
    w()
    w("# CROSS-ANALYSIS")
    w()

    # Build lookup
    fre_lookup = {r["url"]: r["fre"] for r in readability}
    w("## Readability vs Citability")
    w()
    w("Do more readable posts score higher on AI citability?")
    w()
    easy = [r for r in ai_results if fre_lookup.get(r["url"], 0) >= 70]
    hard = [r for r in ai_results if fre_lookup.get(r["url"], 0) < 50]
    mid = [r for r in ai_results if 50 <= fre_lookup.get(r["url"], 0) < 70]
    w("| Readability | Posts | Avg Citability | Avg E-E-A-T |")
    w("|------------|-------|---------------|------------|")
    if easy: w(f"| Easy (FRE >= 70) | {len(easy)} | {_avg([r['cite'] for r in easy]):.1f} | {_avg([r['eeat'] for r in easy]):.1f} |")
    if mid: w(f"| Medium (FRE 50-69) | {len(mid)} | {_avg([r['cite'] for r in mid]):.1f} | {_avg([r['eeat'] for r in mid]):.1f} |")
    if hard: w(f"| Hard (FRE < 50) | {len(hard)} | {_avg([r['cite'] for r in hard]):.1f} | {_avg([r['eeat'] for r in hard]):.1f} |")
    w()

    # Word count vs citability
    w("## Word Count vs Citability")
    w()
    short_posts = [r for r in ai_results if r["words"] < 1000]
    med_posts = [r for r in ai_results if 1000 <= r["words"] < 3000]
    long_p = [r for r in ai_results if r["words"] >= 3000]
    w("| Length | Posts | Avg Citability | Avg Extraction |")
    w("|--------|-------|---------------|---------------|")
    if short_posts: w(f"| Short (<1K words) | {len(short_posts)} | {_avg([r['cite'] for r in short_posts]):.1f} | {_avg([r['extract'] for r in short_posts]):.1f} |")
    if med_posts: w(f"| Medium (1-3K words) | {len(med_posts)} | {_avg([r['cite'] for r in med_posts]):.1f} | {_avg([r['extract'] for r in med_posts]):.1f} |")
    if long_p: w(f"| Long (3K+ words) | {len(long_p)} | {_avg([r['cite'] for r in long_p]):.1f} | {_avg([r['extract'] for r in long_p]):.1f} |")
    w()

    # ── Timing summary ──
    w("---")
    w()
    w("# PROCESSING SUMMARY")
    w()
    w("| Step | Duration | External API | Cost |")
    w("|------|----------|-------------|------|")
    w(f"| 1. Crawl + Normalize | {crawl_time:.1f}s | None | $0 |")
    w(f"| 2a. Embeddings (simulated) | ~{(batches + long_count*2)/3:.1f}s | OpenAI | ~${est_cost:.4f} |")
    w(f"| 2b. Readability | {read_time:.3f}s | None | $0 |")
    w(f"| 2c. PageRank | ~0.5s (skipped in test) | None | $0 |")
    w(f"| 2d. Intent | {intent_time:.4f}s | None | $0 |")
    w(f"| 2e. AI Citability | {ai_time:.3f}s | None | $0 |")
    total_time = crawl_time + read_time + intent_time + ai_time
    w(f"| **Total** | **~{total_time:.0f}s** | | **~${est_cost:.4f}** |")
    w()

    # Write
    report = "\n".join(L)
    out = "FULL-E2E-RESULTS.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written to {out} ({len(L)} lines)")


if __name__ == "__main__":
    asyncio.run(main())
