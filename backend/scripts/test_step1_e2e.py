"""End-to-end test of Pipeline Step 1: Crawl + Normalize.

Runs the SitemapCrawler against a real SEO marketing website,
captures all output, and writes results to a markdown report.
No database required — tests crawl + extraction only.
"""

import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime

# Target: copyblogger.com — well-known content marketing site, mid-size
TARGET_DOMAIN = "copyblogger.com"
TARGET_SITEMAP = f"https://{TARGET_DOMAIN}/sitemap.xml"
MAX_PAGES = 150  # Cap for test run


async def main():
    from app.services.normalizer import (
        NormalizedPost,
        compute_content_hash,
        filter_nav_links,
        filter_sitewide_headings,
        _strip_site_name_from_title,
        _strip_html_from_meta,
    )
    from app.services.sitemap import SitemapCrawler
    from app.utils.url_normalize import normalize_url

    print(f"=== Step 1 E2E Test: {TARGET_DOMAIN} ===\n")

    # ── Phase 1: Crawl ──
    progress_log = []

    def on_progress(processed, total):
        progress_log.append((processed, total, time.time()))
        print(f"  Progress: {processed}/{total}")

    crawler = SitemapCrawler(
        sitemap_url=TARGET_SITEMAP,
        domain=TARGET_DOMAIN,
        delay_seconds=0.5,
        max_pages=MAX_PAGES,
        concurrency=10,
        max_retries=3,
        timeout_seconds=30.0,
        on_progress=on_progress,
    )

    start = time.time()
    print("Starting crawl...")
    posts = await crawler.crawl()
    crawl_duration = time.time() - start

    # Collect skip data
    skipped = getattr(crawler, '_skipped', [])
    skip_reasons = Counter(reason for _, reason in skipped)

    print(f"\nCrawl complete: {len(posts)} posts in {crawl_duration:.1f}s")
    print(f"Skipped: {len(skipped)} URLs")

    # ── Phase 2: Normalize (simulate what save_normalized_posts does) ──
    print("\nRunning normalization...")

    # Dedup by normalized URL
    seen_urls = set()
    deduped = []
    dupes_removed = 0
    for post in posts:
        norm = normalize_url(post.url)
        if norm not in seen_urls:
            seen_urls.add(norm)
            post.url = norm
            deduped.append(post)
        else:
            dupes_removed += 1

    # Title cleaning
    for post in deduped:
        post.title = _strip_site_name_from_title(post.title)
        post.meta_description = _strip_html_from_meta(post.meta_description)

    # Nav link filtering
    links_map = {p.url: p.internal_links for p in deduped}
    headings_map = {p.url: p.headings for p in deduped}
    filtered_links = filter_nav_links(links_map)
    filtered_headings = filter_sitewide_headings(headings_map)

    nav_links_removed = 0
    headings_removed = 0
    for post in deduped:
        old_link_count = len(post.internal_links)
        post.internal_links = filtered_links.get(post.url, post.internal_links)
        nav_links_removed += old_link_count - len(post.internal_links)

        old_heading_count = len(post.headings)
        post.headings = filtered_headings.get(post.url, post.headings)
        headings_removed += old_heading_count - len(post.headings)

    # ── Phase 3: Compute statistics ──
    print("Computing statistics...\n")

    word_counts = [p.word_count for p in deduped]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    median_words = sorted(word_counts)[len(word_counts) // 2] if word_counts else 0

    # Page types
    page_types = Counter(p.page_type for p in deduped)

    # Languages
    languages = Counter(p.language for p in deduped)

    # Date coverage
    has_publish = sum(1 for p in deduped if p.publish_date)
    has_modified = sum(1 for p in deduped if p.modified_date)
    has_meta_desc = sum(1 for p in deduped if p.meta_description)
    has_headings = sum(1 for p in deduped if p.headings)

    # Internal links stats
    total_links = sum(len(p.internal_links) for p in deduped)
    posts_with_links = sum(1 for p in deduped if p.internal_links)
    avg_links = total_links / len(deduped) if deduped else 0

    # Link target resolution (simulate — check how many link targets match known URLs)
    known_urls = {p.url for p in deduped}
    resolvable = 0
    unresolvable = 0
    for post in deduped:
        for link in post.internal_links:
            norm_target = normalize_url(link.target_url)
            if norm_target in known_urls:
                resolvable += 1
            else:
                unresolvable += 1

    # HTTP status codes
    status_codes = Counter(p.http_status for p in deduped)

    # Heading depth
    h1_count = sum(1 for p in deduped for h in p.headings if h.get("level") == "h1")
    h2_count = sum(1 for p in deduped for h in p.headings if h.get("level") == "h2")
    h3_count = sum(1 for p in deduped for h in p.headings if h.get("level") == "h3")

    # Shortest/longest posts
    sorted_by_words = sorted(deduped, key=lambda p: p.word_count)
    shortest_5 = sorted_by_words[:5]
    longest_5 = sorted_by_words[-5:][::-1]

    # Posts without dates (freshness concern)
    no_dates = [p for p in deduped if not p.publish_date and not p.modified_date]

    # Content hash uniqueness
    hash_counts = Counter(p.content_hash for p in deduped)
    duplicate_content = {h: c for h, c in hash_counts.items() if c > 1}

    # ── Phase 4: Write report ──
    report_path = "STEP1-TEST-RESULTS.md"

    lines = []
    lines.append(f"# Step 1 E2E Test Results: {TARGET_DOMAIN}")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Target:** `{TARGET_SITEMAP}`")
    lines.append(f"**Max pages cap:** {MAX_PAGES}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Crawl summary
    lines.append("## 1. Crawl Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Duration** | {crawl_duration:.1f}s |")
    lines.append(f"| **URLs discovered** | {crawler._total} |")
    lines.append(f"| **Posts extracted** | {len(posts)} |")
    lines.append(f"| **Posts after dedup** | {len(deduped)} |")
    lines.append(f"| **Duplicates removed** | {dupes_removed} |")
    lines.append(f"| **URLs skipped** | {len(skipped)} |")
    lines.append(f"| **Extraction rate** | {len(posts)/crawler._total*100:.1f}% | " if crawler._total > 0 else "| **Extraction rate** | N/A |")
    lines.append(f"| **Avg time per URL** | {crawl_duration/crawler._total:.2f}s |" if crawler._total > 0 else "")
    lines.append("")

    # Skip reasons
    if skip_reasons:
        lines.append("### Skip Reasons")
        lines.append("")
        lines.append("| Reason | Count |")
        lines.append("|--------|-------|")
        for reason, count in skip_reasons.most_common():
            lines.append(f"| {reason} | {count} |")
        lines.append("")

        # Sample skipped URLs
        lines.append("### Sample Skipped URLs (first 10)")
        lines.append("")
        for url, reason in skipped[:10]:
            lines.append(f"- `{url}` — {reason}")
        lines.append("")

    # Normalization
    lines.append("## 2. Normalization Results")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Nav links removed** | {nav_links_removed} |")
    lines.append(f"| **Sitewide headings removed** | {headings_removed} |")
    lines.append(f"| **URL duplicates removed** | {dupes_removed} |")
    lines.append("")

    # Content stats
    lines.append("## 3. Content Statistics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Total posts** | {len(deduped)} |")
    lines.append(f"| **Avg word count** | {avg_words:.0f} |")
    lines.append(f"| **Median word count** | {median_words} |")
    lines.append(f"| **Min word count** | {min(word_counts) if word_counts else 0} |")
    lines.append(f"| **Max word count** | {max(word_counts) if word_counts else 0} |")
    lines.append(f"| **Total words** | {sum(word_counts):,} |")
    lines.append("")

    # Page types
    lines.append("### Page Type Distribution")
    lines.append("")
    lines.append("| Type | Count | % |")
    lines.append("|------|-------|---|")
    for ptype, count in page_types.most_common():
        lines.append(f"| {ptype} | {count} | {count/len(deduped)*100:.1f}% |")
    lines.append("")

    # Languages
    lines.append("### Language Distribution")
    lines.append("")
    lines.append("| Language | Count |")
    lines.append("|----------|-------|")
    for lang, count in languages.most_common():
        lines.append(f"| {lang or 'None (undetected)'} | {count} |")
    lines.append("")

    # HTTP status codes
    lines.append("### HTTP Status Codes")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for status, count in status_codes.most_common():
        lines.append(f"| {status} | {count} |")
    lines.append("")

    # Field coverage
    lines.append("## 4. Field Coverage")
    lines.append("")
    lines.append("| Field | Has Value | Missing | Coverage |")
    lines.append("|-------|-----------|---------|----------|")
    total = len(deduped)
    lines.append(f"| publish_date | {has_publish} | {total - has_publish} | {has_publish/total*100:.1f}% |")
    lines.append(f"| modified_date | {has_modified} | {total - has_modified} | {has_modified/total*100:.1f}% |")
    lines.append(f"| meta_description | {has_meta_desc} | {total - has_meta_desc} | {has_meta_desc/total*100:.1f}% |")
    lines.append(f"| headings | {has_headings} | {total - has_headings} | {has_headings/total*100:.1f}% |")
    lines.append(f"| language | {total - languages.get(None, 0)} | {languages.get(None, 0)} | {(total - languages.get(None, 0))/total*100:.1f}% |")
    lines.append("")

    # Internal links
    lines.append("## 5. Internal Link Graph")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Total internal links** | {total_links} |")
    lines.append(f"| **Posts with >= 1 link** | {posts_with_links} ({posts_with_links/total*100:.1f}%) |")
    lines.append(f"| **Avg links per post** | {avg_links:.1f} |")
    lines.append(f"| **Resolvable (target is a known post)** | {resolvable} ({resolvable/(resolvable+unresolvable)*100:.1f}%) |" if (resolvable+unresolvable) > 0 else "")
    lines.append(f"| **Unresolvable (target not in posts)** | {unresolvable} |")
    lines.append(f"| **Nav links filtered out** | {nav_links_removed} |")
    lines.append("")

    # Heading structure
    lines.append("## 6. Heading Structure")
    lines.append("")
    lines.append(f"| Level | Total Count | Avg per Post |")
    lines.append(f"|-------|-------------|-------------|")
    lines.append(f"| H1 | {h1_count} | {h1_count/total:.1f} |")
    lines.append(f"| H2 | {h2_count} | {h2_count/total:.1f} |")
    lines.append(f"| H3 | {h3_count} | {h3_count/total:.1f} |")
    lines.append("")

    # Longest posts
    lines.append("## 7. Longest Posts (Top 5)")
    lines.append("")
    lines.append("| # | Title | Words | URL |")
    lines.append("|---|-------|-------|-----|")
    for i, p in enumerate(longest_5, 1):
        title = p.title[:60] + "..." if len(p.title) > 60 else p.title
        url_short = p.url.replace(f"https://{TARGET_DOMAIN}", "")
        lines.append(f"| {i} | {title} | {p.word_count:,} | `{url_short}` |")
    lines.append("")

    # Shortest posts
    lines.append("## 8. Shortest Posts (Bottom 5)")
    lines.append("")
    lines.append("| # | Title | Words | Page Type | URL |")
    lines.append("|---|-------|-------|-----------|-----|")
    for i, p in enumerate(shortest_5, 1):
        title = p.title[:60] + "..." if len(p.title) > 60 else p.title
        url_short = p.url.replace(f"https://{TARGET_DOMAIN}", "")
        lines.append(f"| {i} | {title} | {p.word_count:,} | {p.page_type} | `{url_short}` |")
    lines.append("")

    # Posts without dates
    if no_dates:
        lines.append("## 9. Posts Missing Both Dates")
        lines.append("")
        lines.append(f"**{len(no_dates)} posts** have no publish_date or modified_date:")
        lines.append("")
        for p in no_dates[:15]:
            url_short = p.url.replace(f"https://{TARGET_DOMAIN}", "")
            lines.append(f"- `{url_short}` — {p.word_count} words, type: {p.page_type}")
        if len(no_dates) > 15:
            lines.append(f"- ... and {len(no_dates) - 15} more")
        lines.append("")

    # Duplicate content
    if duplicate_content:
        lines.append("## 10. Duplicate Content (Same Hash)")
        lines.append("")
        lines.append(f"**{len(duplicate_content)} content hashes** appear on multiple URLs:")
        lines.append("")
        for h, count in duplicate_content.items():
            matching = [p for p in deduped if p.content_hash == h]
            lines.append(f"- Hash `{h[:12]}...` appears {count}x:")
            for p in matching:
                url_short = p.url.replace(f"https://{TARGET_DOMAIN}", "")
                lines.append(f"  - `{url_short}` ({p.word_count} words)")
        lines.append("")

    # Sample post detail
    lines.append("## 11. Sample Post (Full Detail)")
    lines.append("")
    sample = deduped[len(deduped) // 2] if deduped else None  # Pick middle post
    if sample:
        lines.append(f"**URL:** `{sample.url}`")
        lines.append(f"**Title:** {sample.title}")
        lines.append(f"**Slug:** {sample.slug}")
        lines.append(f"**Word Count:** {sample.word_count}")
        lines.append(f"**Page Type:** {sample.page_type}")
        lines.append(f"**Language:** {sample.language}")
        lines.append(f"**HTTP Status:** {sample.http_status}")
        lines.append(f"**Publish Date:** {sample.publish_date}")
        lines.append(f"**Modified Date:** {sample.modified_date}")
        lines.append(f"**Content Hash:** `{sample.content_hash}`")
        lines.append(f"**Meta Description:** {sample.meta_description[:200] if sample.meta_description else 'None'}{'...' if sample.meta_description and len(sample.meta_description) > 200 else ''}")
        lines.append(f"**Categories:** {sample.cms_categories}")
        lines.append(f"**Tags:** {sample.cms_tags}")
        lines.append(f"**Internal Links:** {len(sample.internal_links)}")
        lines.append(f"**Headings:** {len(sample.headings)}")
        lines.append("")
        if sample.headings:
            lines.append("**Heading Structure:**")
            lines.append("```")
            for h in sample.headings[:15]:
                indent = "  " * (int(h["level"].replace("h", "")) - 1)
                lines.append(f"{indent}{h['level'].upper()}: {h['text'][:80]}")
            if len(sample.headings) > 15:
                lines.append(f"  ... and {len(sample.headings) - 15} more")
            lines.append("```")
            lines.append("")
        if sample.internal_links:
            lines.append("**Internal Links (first 10):**")
            lines.append("")
            for link in sample.internal_links[:10]:
                lines.append(f"- [{link.anchor_text or '(no anchor)'}]({link.target_url})")
            if len(sample.internal_links) > 10:
                lines.append(f"- ... and {len(sample.internal_links) - 10} more")
            lines.append("")
        lines.append("**Body Text (first 500 chars):**")
        lines.append("```")
        lines.append(sample.body_text[:500])
        lines.append("```")
        lines.append("")

    # Robots.txt outcome — expanded diagnostics (S1-30)
    lines.append("## 12. Robots.txt & Crawl Behavior")
    lines.append("")
    lines.append(f"| Setting | Value |")
    lines.append(f"|---------|-------|")
    lines.append(f"| **User-Agent** | `Tended/0.1 (Content Intelligence Bot)` |")
    lines.append(f"| **Rate limit** | 2 req/sec (shared domain limiter) |")
    lines.append(f"| **Concurrency** | 10 concurrent fetches |")
    lines.append(f"| **Timeout** | 30s per URL |")
    lines.append(f"| **Retries** | 3 per URL |")
    lines.append("")

    robots_filtered = getattr(crawler, '_robots_filtered', 0)
    robots_rules = getattr(crawler, '_robots_rules', [])
    lines.append("### robots.txt Filtering")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **URLs filtered by robots.txt** | {robots_filtered} |")
    lines.append(f"| **Disallow rules found** | {len(robots_rules)} |")
    lines.append("")

    if robots_rules:
        lines.append("**Disallow rules (first 20):**")
        lines.append("```")
        for rule in robots_rules[:20]:
            lines.append(rule)
        if len(robots_rules) > 20:
            lines.append(f"... and {len(robots_rules) - 20} more")
        lines.append("```")
        lines.append("")

    if robots_filtered == 0:
        lines.append("> No URLs were filtered by robots.txt. Either there are no disallow rules for the Tended user-agent, or all discovered URLs are allowed.")
        lines.append("")

    # Canonical URL handling — diagnostics (S1-29)
    lines.append("## 13. Canonical URL Handling")
    lines.append("")
    canonical_redirects = getattr(crawler, '_canonical_redirects', [])
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Posts with canonical redirect** | {len(canonical_redirects)} |")
    lines.append(f"| **Posts with canonical = fetched URL** | {len(deduped) - len(canonical_redirects)} |")
    lines.append("")

    if canonical_redirects:
        lines.append("### Canonical Redirects (URL changed)")
        lines.append("")
        lines.append("| Fetched URL | Canonical URL |")
        lines.append("|-------------|---------------|")
        for orig, canon in canonical_redirects[:20]:
            orig_short = orig.replace(f"https://{TARGET_DOMAIN}", "")
            canon_short = canon.replace(f"https://{TARGET_DOMAIN}", "")
            lines.append(f"| `{orig_short}` | `{canon_short}` |")
        if len(canonical_redirects) > 20:
            lines.append(f"| ... | {len(canonical_redirects) - 20} more |")
        lines.append("")
    else:
        lines.append("> No canonical URL redirects detected. All pages have canonical URLs matching their fetched URLs (or no canonical tag).")
        lines.append("")

    # Non-content page type analysis — diagnostics (S1-23)
    lines.append("## 14. Non-Content Page Types (Landing/Index)")
    lines.append("")
    non_content = [p for p in deduped if p.page_type in ("landing", "index")]
    content_pages = [p for p in deduped if p.page_type not in ("landing", "index")]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Content pages (blog/product/doc/glossary)** | {len(content_pages)} |")
    lines.append(f"| **Non-content pages (landing/index)** | {len(non_content)} |")
    lines.append(f"| **Non-content % of dataset** | {len(non_content)/len(deduped)*100:.1f}% |" if deduped else "")
    lines.append("")

    if non_content:
        lines.append("### Non-Content Pages Detail")
        lines.append("")
        lines.append("| Title | Words | Page Type | URL |")
        lines.append("|-------|-------|-----------|-----|")
        for p in sorted(non_content, key=lambda x: x.word_count):
            title = p.title[:50] + "..." if len(p.title) > 50 else p.title
            url_short = p.url.replace(f"https://{TARGET_DOMAIN}", "")
            lines.append(f"| {title} | {p.word_count} | {p.page_type} | `{url_short}` |")
        lines.append("")
        lines.append("> **Downstream recommendation:** Exclude `page_type = 'landing'` and `'index'` from content-quality analysis (health scoring, problem detection, recommendations). These structural pages don't benefit from blog-oriented advice like 'add H2 headings' or 'thin content' flags.")
        lines.append("")
    else:
        lines.append("> No landing or index pages in dataset. All pages are content types (blog/product/documentation/glossary).")
        lines.append("")

    # Capped crawl caveat
    lines.append("## 15. Capped Crawl Caveats")
    lines.append("")
    lines.append(f"This test was capped at **{MAX_PAGES} URLs**. On a full crawl:")
    lines.append("")
    lines.append(f"- **Internal link resolution** would improve from {resolvable/(resolvable+unresolvable)*100:.1f}% to an estimated 60-80% (more target URLs in the dataset)" if (resolvable+unresolvable) > 0 else "")
    lines.append(f"- **Nav link detection** threshold (80%) would be more accurate with a larger denominator")
    lines.append(f"- **Page type distribution** may shift — capped crawls favor short-path pages (hub/pillar) due to depth-first sorting")
    lines.append(f"- **Content hash duplicates** may increase — more pages = more chances for boilerplate overlap")
    lines.append("")
    lines.append("> Run a full (uncapped) crawl on Backlinko to validate link resolution, modified_date coverage, and canonical handling on a site with modern SEO infrastructure.")
    lines.append("")

    # Write
    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport written to {report_path}")
    print(f"Posts: {len(deduped)}, Links: {total_links}, Duration: {crawl_duration:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
