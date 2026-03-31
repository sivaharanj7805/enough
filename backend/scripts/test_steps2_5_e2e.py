"""End-to-end test of Pipeline Steps 2-5: Enrichment.

Runs readability, intent classification, and AI citability scoring
against real crawled data from Step 1. Simulates embeddings (no OpenAI key needed).
No database required — tests computation only.
"""

import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime

TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150


async def main():
    from app.services.normalizer import (
        NormalizedPost,
        filter_nav_links,
        filter_sitewide_headings,
        _strip_site_name_from_title,
        _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.services.readability import (
        compute_flesch_reading_ease,
        compute_grade_level,
        ReadabilityScorer,
        READABILITY_TOO_COMPLEX,
    )
    from app.services.fast_intent import classify_intent
    from app.services.ai_citability import (
        compute_citability_score,
        compute_eeat_score,
        compute_schema_score,
        compute_extraction_score,
        generate_ai_problems,
    )
    from app.services.page_type_classifier import classify_page_type
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 2 E2E Test: {TARGET_DOMAIN} ===\n")

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

    print(f"  Normalized to {len(posts)} posts\n")

    # ── Phase 2a: Simulate Embeddings ──
    print("Step 2a: Embedding simulation...")
    embed_start = time.time()
    embeddable = [p for p in posts if p.body_text and len(p.body_text.strip()) > 50]
    text_lengths = [len(f"{p.title}\n\n{p.body_text}"[:20000]) for p in embeddable]
    total_chars = sum(text_lengths)
    est_tokens = total_chars / 4  # rough char-to-token ratio
    est_cost = est_tokens / 1_000_000 * 0.02  # $0.02 per 1M tokens
    batches_needed = (len(embeddable) + 99) // 100
    embed_time = time.time() - embed_start
    print(f"  Posts to embed: {len(embeddable)}")
    print(f"  Total text: {total_chars:,} chars (~{int(est_tokens):,} tokens)")
    print(f"  Estimated cost: ${est_cost:.4f}")
    print(f"  Batches needed: {batches_needed} (100 per batch)")
    print(f"  Estimated time: {batches_needed / 3:.1f}s (at 3 req/sec)\n")

    # ── Phase 2b: Readability ──
    print("Step 2b: Readability scoring...")
    read_start = time.time()
    readability_results = []
    for p in posts:
        if not p.body_text or len(p.body_text) < 100:
            continue
        fre = compute_flesch_reading_ease(p.body_text)
        grade = compute_grade_level(p.body_text)
        readability_results.append({
            "url": p.url, "title": p.title,
            "fre": fre, "grade": grade,
            "word_count": p.word_count,
        })
    read_time = time.time() - read_start

    fre_scores = [r["fre"] for r in readability_results]
    grade_scores = [r["grade"] for r in readability_results]
    avg_fre = sum(fre_scores) / len(fre_scores) if fre_scores else 0
    avg_grade = sum(grade_scores) / len(grade_scores) if grade_scores else 0
    too_complex = [r for r in readability_results if r["fre"] < READABILITY_TOO_COMPLEX]
    ideal = [r for r in readability_results if 60 <= r["fre"] <= 80]

    print(f"  Scored {len(readability_results)} posts in {read_time:.3f}s")
    print(f"  Avg Flesch Reading Ease: {avg_fre:.1f}")
    print(f"  Avg Grade Level: {avg_grade:.1f}")
    print(f"  In sweet spot (60-80): {len(ideal)} ({len(ideal)/len(readability_results)*100:.0f}%)")
    print(f"  Too complex (<40): {len(too_complex)} ({len(too_complex)/len(readability_results)*100:.0f}%)\n")

    # ── Phase 2d: Intent Classification ──
    print("Step 2d: Intent classification...")
    intent_start = time.time()
    intent_results = []
    for p in posts:
        intent = classify_intent(p.title or "", p.url or "", p.word_count or 0)
        intent_results.append({"url": p.url, "title": p.title, "intent": intent})
    intent_time = time.time() - intent_start
    intent_dist = Counter(r["intent"] for r in intent_results)
    print(f"  Classified {len(intent_results)} posts in {intent_time:.3f}s")
    for intent, count in intent_dist.most_common():
        print(f"    {intent}: {count} ({count/len(intent_results)*100:.1f}%)")
    print()

    # ── Phase 2e: AI Citability ──
    print("Step 2e: AI Citability scoring...")
    ai_start = time.time()

    # Calculate site median word count for E-E-A-T scoring
    all_word_counts = sorted(p.word_count for p in posts if p.body_text)
    site_median_words = all_word_counts[len(all_word_counts) // 2] if all_word_counts else 0

    ai_results = []
    all_problems = []
    for p in posts:
        if not p.body_text:
            continue
        cite_score, cite_signals = compute_citability_score(p.body_text, p.body_html)
        eeat_score, eeat_signals = compute_eeat_score(
            p.body_html, headings=p.headings, word_count=p.word_count,
            site_median_words=site_median_words,
            publish_date=p.publish_date, modified_date=p.modified_date,
        )
        schema_score, schema_signals = compute_schema_score(p.body_html)
        extract_score, extract_signals = compute_extraction_score(
            p.body_text, p.body_html, p.headings,
        )
        all_signals = {
            **cite_signals,
            **{f"eeat_{k}": v for k, v in eeat_signals.items()},
            **{f"schema_{k}": v for k, v in schema_signals.items()},
            **{f"extract_{k}": v for k, v in extract_signals.items()},
        }
        problems = generate_ai_problems(
            p.url, p.title, cite_score, eeat_score, schema_score, extract_score, all_signals,
        )
        all_problems.extend(problems)
        ai_results.append({
            "url": p.url, "title": p.title,
            "citability": cite_score, "eeat": eeat_score,
            "schema": schema_score, "extraction": extract_score,
            "signals": all_signals,
            "problem_count": len(problems),
        })
    ai_time = time.time() - ai_start

    cite_scores = [r["citability"] for r in ai_results]
    eeat_scores = [r["eeat"] for r in ai_results]
    schema_scores = [r["schema"] for r in ai_results]
    extract_scores = [r["extraction"] for r in ai_results]
    def _avg(lst): return sum(lst) / len(lst) if lst else 0

    print(f"  Scored {len(ai_results)} posts in {ai_time:.3f}s")
    print(f"  Avg Citability: {_avg(cite_scores):.1f}/100")
    print(f"  Avg E-E-A-T: {_avg(eeat_scores):.1f}/100")
    print(f"  Avg Schema: {_avg(schema_scores):.1f}/100")
    print(f"  Avg Extraction: {_avg(extract_scores):.1f}/100")
    print(f"  Total AI problems found: {len(all_problems)}")
    problem_dist = Counter(p["problem_type"] for p in all_problems)
    for ptype, count in problem_dist.most_common():
        print(f"    {ptype}: {count}")
    print()

    # ── Write Report ──
    report_path = "STEP2-TEST-RESULTS.md"
    lines = []
    lines.append(f"# Step 2 E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Prerequisite:** {len(posts)} posts from Step 1 crawl")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2a: Embeddings
    lines.append("## 2a. Embedding Analysis (Simulated)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Posts to embed | {len(embeddable)} |")
    lines.append(f"| Total text chars | {total_chars:,} |")
    lines.append(f"| Estimated tokens | ~{int(est_tokens):,} |")
    lines.append(f"| Estimated cost | ${est_cost:.4f} |")
    lines.append(f"| Batches needed | {batches_needed} |")
    lines.append(f"| Estimated time | {batches_needed / 3:.1f}s |")
    lines.append(f"| Avg text length | {total_chars // len(embeddable):,} chars |")
    lines.append(f"| Max text length | {max(text_lengths):,} chars |")
    lines.append(f"| Texts hitting 20K truncation | {sum(1 for l in text_lengths if l >= 20000)} |")
    lines.append("")

    # 2b: Readability
    lines.append("## 2b. Readability Scores")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Posts scored | {len(readability_results)} |")
    lines.append(f"| Processing time | {read_time:.3f}s |")
    lines.append(f"| **Avg Flesch Reading Ease** | **{avg_fre:.1f}** |")
    lines.append(f"| **Avg Grade Level** | **{avg_grade:.1f}** |")
    lines.append(f"| Min FRE | {min(fre_scores):.1f} |")
    lines.append(f"| Max FRE | {max(fre_scores):.1f} |")
    lines.append(f"| In sweet spot (60-80) | {len(ideal)} ({len(ideal)/len(readability_results)*100:.0f}%) |")
    lines.append(f"| Too complex (<40) | {len(too_complex)} ({len(too_complex)/len(readability_results)*100:.0f}%) |")
    lines.append("")

    # FRE distribution
    lines.append("### Readability Distribution")
    lines.append("")
    lines.append("| Range | Label | Count | % |")
    lines.append("|-------|-------|-------|---|")
    ranges = [(90, 100, "Very easy"), (80, 89, "Easy"), (70, 79, "Fairly easy"),
              (60, 69, "Standard"), (50, 59, "Fairly difficult"),
              (30, 49, "Difficult"), (0, 29, "Very confusing")]
    for lo, hi, label in ranges:
        count = sum(1 for s in fre_scores if lo <= s <= hi)
        lines.append(f"| {lo}-{hi} | {label} | {count} | {count/len(fre_scores)*100:.0f}% |")
    lines.append("")

    # Hardest to read
    hardest = sorted(readability_results, key=lambda r: r["fre"])[:5]
    lines.append("### Hardest to Read (Bottom 5)")
    lines.append("")
    lines.append("| Title | FRE | Grade | Words |")
    lines.append("|-------|-----|-------|-------|")
    for r in hardest:
        t = r["title"][:55] + "..." if len(r["title"]) > 55 else r["title"]
        lines.append(f"| {t} | {r['fre']:.1f} | {r['grade']:.1f} | {r['word_count']:,} |")
    lines.append("")

    # 2d: Intent
    lines.append("## 2d. Intent Classification")
    lines.append("")
    lines.append("| Intent | Count | % |")
    lines.append("|--------|-------|---|")
    for intent, count in intent_dist.most_common():
        lines.append(f"| {intent} | {count} | {count/len(intent_results)*100:.1f}% |")
    lines.append("")

    # Sample non-informational
    non_info = [r for r in intent_results if r["intent"] != "informational"]
    if non_info:
        lines.append("### Non-Informational Posts")
        lines.append("")
        lines.append("| Intent | Title | URL |")
        lines.append("|--------|-------|-----|")
        for r in non_info[:15]:
            t = r["title"][:50] + "..." if len(r["title"]) > 50 else r["title"]
            u = r["url"].replace(f"https://{TARGET_DOMAIN}", "")
            lines.append(f"| {r['intent']} | {t} | `{u}` |")
        lines.append("")

    # 2e: AI Citability
    lines.append("## 2e. AI Citability Scores")
    lines.append("")
    lines.append("| Dimension | Avg | Min | Max |")
    lines.append("|-----------|-----|-----|-----|")
    lines.append(f"| Citability | {_avg(cite_scores):.1f} | {min(cite_scores)} | {max(cite_scores)} |")
    lines.append(f"| E-E-A-T | {_avg(eeat_scores):.1f} | {min(eeat_scores)} | {max(eeat_scores)} |")
    lines.append(f"| Schema | {_avg(schema_scores):.1f} | {min(schema_scores)} | {max(schema_scores)} |")
    lines.append(f"| Extraction | {_avg(extract_scores):.1f} | {min(extract_scores)} | {max(extract_scores)} |")
    lines.append("")

    # AI-ready percentage
    ai_ready = sum(1 for s in cite_scores if s >= 60)
    lines.append(f"**AI-ready posts (citability ≥ 60):** {ai_ready} ({ai_ready/len(cite_scores)*100:.1f}%)")
    lines.append(f"**Has schema:** {sum(1 for s in schema_scores if s > 0)} ({sum(1 for s in schema_scores if s > 0)/len(schema_scores)*100:.1f}%)")
    lines.append("")

    # Top 5 most AI-ready
    top_ai = sorted(ai_results, key=lambda r: r["citability"], reverse=True)[:5]
    lines.append("### Most AI-Ready Posts (Top 5)")
    lines.append("")
    lines.append("| Title | Citability | E-E-A-T | Schema | Extraction |")
    lines.append("|-------|-----------|---------|--------|-----------|")
    for r in top_ai:
        t = r["title"][:50] + "..." if len(r["title"]) > 50 else r["title"]
        lines.append(f"| {t} | {r['citability']} | {r['eeat']} | {r['schema']} | {r['extraction']} |")
    lines.append("")

    # Worst 5
    bottom_ai = sorted(ai_results, key=lambda r: r["citability"])[:5]
    lines.append("### Least AI-Ready Posts (Bottom 5)")
    lines.append("")
    lines.append("| Title | Citability | E-E-A-T | Schema | Extraction |")
    lines.append("|-------|-----------|---------|--------|-----------|")
    for r in bottom_ai:
        t = r["title"][:50] + "..." if len(r["title"]) > 50 else r["title"]
        lines.append(f"| {t} | {r['citability']} | {r['eeat']} | {r['schema']} | {r['extraction']} |")
    lines.append("")

    # AI Problems
    lines.append("## AI Readiness Problems")
    lines.append("")
    lines.append(f"**Total problems found:** {len(all_problems)}")
    lines.append("")
    lines.append("| Problem Type | Count | Severity Distribution |")
    lines.append("|-------------|-------|----------------------|")
    for ptype, count in problem_dist.most_common():
        severities = Counter(p["severity"] for p in all_problems if p["problem_type"] == ptype)
        sev_str = ", ".join(f"{s}={c}" for s, c in severities.most_common())
        lines.append(f"| `{ptype}` | {count} | {sev_str} |")
    lines.append("")

    # Sample post detail
    sample = ai_results[len(ai_results) // 3]
    lines.append("## Sample Post Detail")
    lines.append("")
    lines.append(f"**Title:** {sample['title']}")
    lines.append(f"**URL:** `{sample['url']}`")
    lines.append(f"**Citability:** {sample['citability']}/100")
    lines.append(f"**E-E-A-T:** {sample['eeat']}/100")
    lines.append(f"**Schema:** {sample['schema']}/100")
    lines.append(f"**Extraction:** {sample['extraction']}/100")
    lines.append("")
    lines.append("**Signals:**")
    lines.append("```json")
    # Filter to interesting signals
    interesting = {k: v for k, v in sample["signals"].items()
                   if v and v != 0 and v != 0.0 and v != False and v != [] and v != ""}
    lines.append(json.dumps(interesting, indent=2, default=str))
    lines.append("```")
    lines.append("")

    # Summary
    lines.append("## Processing Summary")
    lines.append("")
    lines.append("| Step | Time | External API |")
    lines.append("|------|------|-------------|")
    lines.append(f"| Crawl (Step 1) | {crawl_time:.1f}s | None |")
    lines.append(f"| Embeddings (simulated) | ~{batches_needed / 3:.1f}s | OpenAI ${est_cost:.4f} |")
    lines.append(f"| Readability | {read_time:.3f}s | None |")
    lines.append(f"| Intent | {intent_time:.3f}s | None |")
    lines.append(f"| AI Citability | {ai_time:.3f}s | None |")
    lines.append(f"| **Total Step 2** | **~{batches_needed/3 + read_time + intent_time + ai_time:.1f}s** | **${est_cost:.4f}** |")
    lines.append("")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
