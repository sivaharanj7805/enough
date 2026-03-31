# Step 9 E2E Test Results — Problem Detection: copyblogger.com

**Date:** 2026-03-28 20:20
**Posts analyzed:** 145
**Clusters:** 4
**Detection mode:** Crawl-only (no GA4, no GSC, no AI citability)
**Prerequisite:** Step 1 crawl (copyblogger.com, 150 max) + Step 3 clustering (synthetic embeddings)
**Note:** Proxy decay detection uses crawl dates and title patterns. Real decay detection requires GSC data.

---

## 9.0 Data Availability

| Data Source | Available | Impact |
|------------|-----------|--------|
| Crawl data | YES | All crawl-based detectors run |
| GA4 metrics | NO | thin_high_bounce skipped |
| GSC metrics | NO | content_decay (3 signals) skipped |
| AI citability | NO | ai_readiness skipped |
| Cluster data | YES (synthetic) | thin_below_cluster_avg runs |
| **Active detectors** | **8 / 10** | |

## 9.1 Thin Content Detection

### Absolute Thin Content

**Found: 2 posts**

| Post Title | URL | Word Count | Threshold | Type | Severity |
|-----------|-----|-----------|-----------|------|----------|
| Copyblogger - Content marketing tools and training... | / | 186 | 500 | default | high |
| Tubetorial Sold to SplashPress Media | /tubetorial-sold-to-splashpress-media | 472 | 500 | default | medium |

**Stats:** min=186, max=472, mean=329

### Below Cluster Average

**Found: 17 posts**

| Post Title | Word Count | Cluster Avg | Ratio | Severity |
|-----------|-----------|-------------|-------|----------|
| Copyblogger - Content marketing tools and training... | 186 | 2252 | 0.08 | medium |
| Tubetorial Sold to SplashPress Media | 472 | 2944 | 0.16 | medium |
| Do You Spend $10,000 a Month on Pay Per Click Ads? | 546 | 2944 | 0.19 | medium |
| The SEOmoz Landing Page Contest: Entries Judged by... | 503 | 2178 | 0.23 | medium |
| Great Copy Ranges From the Specific to the Precise | 708 | 2944 | 0.24 | medium |
| Here's Some Cool Copy for July 4th | 553 | 2178 | 0.25 | medium |
| A Call to Action Worthy of Response | 749 | 2944 | 0.25 | medium |
| Copywriting 101: How to Craft Compelling Copy | 573 | 2252 | 0.25 | medium |
| SEO for Bloggers | 580 | 2178 | 0.27 | medium |
| Are You Creating Bookmarkable Content? | 671 | 2252 | 0.30 | medium |
| Who Else is Going to SOBCon 2008? | 627 | 1923 | 0.33 | medium |
| The True Power of the Blog | 767 | 2252 | 0.34 | medium |
| Call Me Tonight if You Have a Question | 652 | 1923 | 0.34 | medium |
| Link Baiting Goes Mainstream | 739 | 2178 | 0.34 | medium |
| I’m Locked in Mortal Combat with Chris Garrett | 672 | 1923 | 0.35 | medium |
| The Ultimate (Free) Landing Page Resource | 757 | 2178 | 0.35 | medium |
| 58 of the World's Greatest Offers | 744 | 1923 | 0.39 | medium |

## 9.2 SEO Issue Detection

| Check | Problem Type | Count | % of Posts | Severity |
|-------|-------------|-------|-----------|----------|
| Missing meta description | `seo_missing_meta` | 126 | 86.9% | medium |
| Title length issue | `seo_title_length` | 11 | 7.6% | low-medium |
| No H2+ headings | `seo_no_headings` | 99 | 68.3% | medium |
| No internal links | `seo_no_internal_links` | 0 | 0.0% | high |
| No images detected | `seo_no_images` | 1 | 0.7% | low |
| **Total SEO issues** | | **237** | | |

### Missing meta description (sample)

- 5 Steps to Pay Per Click Advertising That Works (meta length: 0)
- It’s the End of AdSense as We Know It (And I Feel Fine) (meta length: 0)
- Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers (meta length: 0)
- For Whom the Blog Tips (It Tips For Thee) (meta length: 0)
- The True Power of the Blog (meta length: 0)
- ... and 121 more

### Title length issue (sample)

- What’s Your Story? (length: 18)
- Blogging Grows Up (length: 17)
- Discover the Secret Mind Control Method That Hypnotically Pe (length: 99)
- News Flash (length: 10)
- Link Karma (length: 10)
- ... and 6 more

### No H2+ headings (sample)

- 5 Steps to Pay Per Click Advertising That Works
- It’s the End of AdSense as We Know It (And I Feel Fine)
- For Whom the Blog Tips (It Tips For Thee)
- The True Power of the Blog
- Does the SEO Industry Have a Branding Problem?
- ... and 94 more

### No images detected (sample)

- Copywriting 101: How to Craft Compelling Copy

## 9.3 Orphan Detection

**Found: 0 orphan posts** (no inbound internal links, >= 200 words)


## 9.4 Proxy Decay Detection

**Found: 142 decay problems** (proxy signals, no GSC)

| Severity | Signal | Count |
|----------|--------|-------|
| decay_severe | outdated_year_reference | 2 |
| decay_moderate | time_sensitive_stale | 4 |

### Sample Proxy Decay

- [decay_mild] 5 Steps to Pay Per Click Advertising That Works (237.5 months stale)
- [decay_mild] It’s the End of AdSense as We Know It (And I Feel Fine) (236.7 months stale)
- [decay_mild] Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers (236.1 months stale)
- [decay_mild] For Whom the Blog Tips (It Tips For Thee) (235.9 months stale)
- [decay_mild] The True Power of the Blog (235.9 months stale)
- [decay_mild] Does the SEO Industry Have a Branding Problem? (235.8 months stale)
- [decay_mild] Why “Content” Has Become a Dirty Word (235.6 months stale)
- [decay_mild] The Most Powerful Blogging Technique There Is (235.6 months stale)
- [decay_mild] What’s Your Story? (235.5 months stale)
- [decay_moderate] Aristotle’s Top 3 Tips for Effective Blogging (235.4 months stale)
- ... and 132 more

## 9.5 Readability Issues

**Industry detected:** agency (threshold: Flesch < 35.0)

**Found: 1 posts with poor readability** (Flesch < 35.0)

| Post Title | Flesch Score | Grade Level | Severity |
|-----------|-------------|-------------|----------|
| Copyblogger - Content marketing tools and training... | 31.1 | 12.6 | medium |

### Site-Wide Readability Distribution

| Score Range | Count | % | Histogram |
|------------|-------|---|-----------|
| 0-30 (very hard) | 0 | 0.0% | # |
| 30-50 (hard) | 2 | 1.4% | # |
| 50-60 (fairly hard) | 6 | 4.1% | ## |
| 60-70 (standard) | 50 | 34.5% | ################# |
| 70-80 (fairly easy) | 83 | 57.2% | ############################ |
| 80-100 (easy) | 4 | 2.8% | # |

## 9.6 Publishing Velocity

| Metric | Value |
|--------|-------|
| Posts with dates | 145 |
| Date range | 2006-06-14 to 2025-11-24 |
| Date range (days) | 7103 |
| Recent 90d posts | 0 |
| Previous 90d posts | 1 |
| Recent weekly velocity | 0 |
| Previous weekly velocity | 0.08 |
| Overall weekly velocity | 0.14 |
| **Peak velocity** | **1.4 posts/week in 2007 (73 posts)** |
| **Trend** | **declining** |
| **Would flag** | **velocity_decline (medium)** |

## Skipped Detectors

| Detector | Reason | Would Need |
|----------|--------|-----------|
| Content decay (3 signals) | No GSC data | `gsc_metrics` table with click/position data |
| Thin: high bounce | No GA4 data | `ga4_metrics` table with bounce_rate, engagement_time |
| AI readiness (5+ checks) | No AI citability scores | Step 6c (AI Citability) must run first |

## 9.7 Related Problem Grouping & Dedup

**Suppressed (orphan subsumes seo_no_internal_links):** 0
**Marked as related (thin cluster):** 2

| Group | Strategy | Problem Types | Affected Posts |
|-------|----------|-------------|---------------|
| Orphan cluster | SUPPRESS (delete secondary) | orphan, seo_no_internal_links | 0 |
| Thin cluster | MARK (annotate) | thin_content, thin_below_cluster_avg | 2 |

## Processing Summary

| Detector | Problems | Time | External API | Notes |
|----------|---------|------|-------------|-------|
| Thin content (absolute) | 2 | 2.9ms | None | Crawl-based |
| Thin content (cluster avg) | 17 | 2.9ms | None | Crawl-based |
| SEO: missing meta | 126 | 67.7ms | None | Crawl-based |
| SEO: title length | 11 | 67.7ms | None | Crawl-based |
| SEO: no headings | 99 | 67.7ms | None | Crawl-based |
| SEO: no internal links | 0 | 67.7ms | None | Crawl-based |
| SEO: no images | 1 | 67.7ms | None | Crawl-based |
| Orphan detection | 0 | 0.0ms | None | Crawl-based |
| Proxy decay (severe) | 2 | 0.0ms | None | Crawl-based |
| Proxy decay (moderate) | 4 | 0.0ms | None | Crawl-based |
| Readability issues | 1 | 755.7ms | None | Crawl-based |
| Velocity decline | 1 | 0.0ms | None | |
| **Total Step 9** | **399** | **826.4ms** | **Free** | |

## Per-Cluster Problem Density

| Cluster | Posts | Problems | Density (per post) | Top Problem Types |
|---------|-------|---------|-------------------|------------------|
| 0 | 24 | 67 | 2.8 | decay_mild=22, seo_missing_meta=20, seo_no_headings=18 |
| 1 | 53 | 137 | 2.6 | decay_mild=48, seo_missing_meta=44, seo_no_headings=32 |
| 2 | 24 | 70 | 2.9 | decay_mild=23, seo_missing_meta=20, seo_no_headings=19 |
| 3 | 44 | 125 | 2.8 | decay_mild=43, seo_missing_meta=42, seo_no_headings=30 |

## Top 10 Most Problematic Posts

| # | Post Title | Problems | Types |
|---|-----------|---------|-------|
| 1 | Tubetorial Sold to SplashPress Media | 5 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg, thin_content |
| 2 | The SEOmoz Landing Page Contest: Entries Judged by | 5 | decay_mild, seo_missing_meta, seo_no_headings, seo_title_length, thin_below_cluster_avg |
| 3 | SEO for Bloggers | 5 | decay_mild, seo_missing_meta, seo_no_headings, seo_title_length, thin_below_cluster_avg |
| 4 | The True Power of the Blog | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 5 | Call Me Tonight if You Have a Question | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 6 | Do You Spend $10,000 a Month on Pay Per Click Ads? | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 7 | Great Copy Ranges From the Specific to the Precise | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 8 | Link Baiting Goes Mainstream | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 9 | I’m Locked in Mortal Combat with Chris Garrett | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |
| 10 | Here's Some Cool Copy for July 4th | 4 | decay_mild, seo_missing_meta, seo_no_headings, thin_below_cluster_avg |

## Severity Distribution

| Severity | Count | % of Total | Histogram |
|----------|-------|-----------|-----------|
| high | 3 | 0.8% | # |
| medium | 390 | 97.7% | ################################################ |
| low | 6 | 1.5% | # |

## Severity Scores (Weight Table Verification)

Each problem type has a weight that produces a `severity_score` (0-100) stored in details JSON.

| Problem Type | Weight | Severity Score | Count in Test |
|-------------|--------|---------------|--------------|
| `decay_severe` | 0.95 | 95 | 2 |
| `seo_missing_meta` | 0.9 | 90 | 126 |
| `decay_moderate` | 0.9 | 90 | 4 |
| `missing_schema` | 0.9 | 90 | 0 |
| `low_ai_citability` | 0.85 | 85 | 0 |
| `seo_no_internal_links` | 0.8 | 80 | 0 |
| `intent_mismatch` | 0.8 | 80 | 0 |
| `weak_eeat` | 0.8 | 80 | 0 |
| `thin_content` | 0.7 | 70 | 2 |
| `decay_mild` | 0.7 | 70 | 136 |
| `velocity_decline` | 0.7 | 70 | 0 |
| `poor_ai_structure` | 0.7 | 70 | 0 |
| `geo_missing_faq_schema` | 0.7 | 70 | 0 |
| `readability_too_complex` | 0.6 | 60 | 1 |
| `orphan` | 0.6 | 60 | 0 |
| `serp_opportunity_missed` | 0.6 | 60 | 0 |
| `geo_no_faq_section` | 0.6 | 60 | 0 |
| `geo_no_answer_first` | 0.6 | 60 | 0 |
| `seo_no_headings` | 0.5 | 50 | 99 |
| `thin_below_cluster_avg` | 0.5 | 50 | 17 |
| `geo_no_data_tables` | 0.5 | 50 | 0 |
| `geo_no_experience_markers` | 0.5 | 50 | 0 |
| `geo_no_question_headers` | 0.5 | 50 | 0 |
| `geo_low_data_density` | 0.5 | 50 | 0 |
| `geo_no_freshness_date` | 0.5 | 50 | 0 |
| `seo_title_length` | 0.4 | 40 | 11 |
| `seo_no_images` | 0.3 | 30 | 1 |

## Top 10 Most Problematic Posts (by Severity Weight Sum)

Ranked by sum of problem weights, not raw problem count.

| # | Post Title | Weight Sum | Problem Count | Types (with weights) |
|---|-----------|-----------|--------------|---------------------|
| 1 | Tubetorial Sold to SplashPress Media | 3.3 | 5 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5), thin_content(0.7) |
| 2 | The SEOmoz Landing Page Contest: Entries Judg | 3.0 | 5 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), seo_title_length(0.4), thin_below_cluster_avg(0.5) |
| 3 | SEO for Bloggers | 3.0 | 5 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), seo_title_length(0.4), thin_below_cluster_avg(0.5) |
| 4 | Who Else is Going to SOBCon 2008? | 2.8 | 4 | decay_severe(0.95), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |
| 5 | Twitter Writing Contest: Win an IPod Nano For | 2.7 | 4 | decay_moderate(0.9), seo_missing_meta(0.9), seo_no_headings(0.5), seo_title_length(0.4) |
| 6 | The True Power of the Blog | 2.6 | 4 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |
| 7 | Call Me Tonight if You Have a Question | 2.6 | 4 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |
| 8 | Do You Spend $10,000 a Month on Pay Per Click | 2.6 | 4 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |
| 9 | Great Copy Ranges From the Specific to the Pr | 2.6 | 4 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |
| 10 | Link Baiting Goes Mainstream | 2.6 | 4 | decay_mild(0.7), seo_missing_meta(0.9), seo_no_headings(0.5), thin_below_cluster_avg(0.5) |

## PDF Report Preview (Simulated)

Problems that would appear in the cold outreach PDF, prioritized by severity weight:

| Priority | Problem Type | Weight | Affected Posts | % | PDF Section |
|----------|-------------|--------|---------------|---|------------|
| 1 | `decay_severe` | 0.95 | 2 | 1.4% | Key Findings |
| 2 | `seo_missing_meta` | 0.9 | 126 | 86.9% | Quick Wins |
| 3 | `decay_moderate` | 0.9 | 4 | 2.8% | 30-Day Plan |
| 4 | `decay_mild` | 0.7 | 136 | 93.8% | 30-Day Plan |
| 5 | `thin_content` | 0.7 | 2 | 1.4% | Key Findings |
| 6 | `readability_too_complex` | 0.6 | 1 | 0.7% | 30-Day Plan |
| 7 | `seo_no_headings` | 0.5 | 99 | 68.3% | Quick Wins |
| 8 | `thin_below_cluster_avg` | 0.5 | 17 | 11.7% | Key Findings |
| 9 | `seo_title_length` | 0.4 | 11 | 7.6% | Quick Wins |
| 10 | `seo_no_images` | 0.3 | 1 | 0.7% | Quick Wins |

### Generated Problem Text (Top 3)

**1. decay_severe** (Key Findings):
> 2 posts reference outdated years in their titles. Update the year, refresh the data, and republish — Google rewards updated content with a ranking boost.

**2. seo_missing_meta** (Quick Wins):
> Add meta descriptions to 126 posts — prioritize your top 10 by traffic. A compelling 150-character description improves CTR by 5.8% on average.

**3. decay_moderate** (30-Day Plan):
> 4 time-sensitive posts haven't been updated in 18+ months. Refresh pricing, statistics, and recommendations to maintain accuracy and rankings.


## Problem Density vs Content Metrics

| Problem Count | Posts | Avg Word Count | Avg Has Headings | Avg Composite Score |
|-------------|-------|---------------|-----------------|-------------------|
| 0 (clean) | 1 | 3229 | 100% | 93.7 |
| 1-2 | 48 | 3336 | 90% | 42.9 |
| 3-4 | 93 | 1961 | 2% | 18.7 |
| 5+ | 3 | 518 | 0% | 10.0 |

*Composite is a simplified crawl-only proxy (40% freshness + 30% depth + 30% structure). Production uses 10 weighted factors.*

## first_detected_at Preservation

**Note:** This crawl-only test cannot verify `first_detected_at` preservation because it does not
use a database. In production, `detect_all()` preserves timestamps by:

1. Reading existing `(post_id, problem_type) -> first_detected_at` from `content_problems`
2. Storing the map in `self._first_detected_map`
3. Passing `COALESCE($6, NOW())` in every INSERT with the preserved timestamp
4. Using `COALESCE(content_problems.first_detected_at, EXCLUDED.first_detected_at)` in ON CONFLICT

**Verification requires:** Two sequential pipeline runs against the same site with a real database.
The second run should show `first_detected_at` timestamps from the first run for continuing problems.

## Observations

- **399 total problems** across 145 posts (2.8 avg per post)
- **1 clean posts (0.7%)** have zero detected problems
- **Most common problem:** `decay_mild` (136 posts, 93.8%)
- **99 posts lack H2+ headings** -- older content may predate modern heading best practices
- **Site-wide readability:** mean Flesch 71, median 72
- **Publishing velocity:** 0.14 posts/week overall, trend is declining
- **Detection completed in 826ms** -- all crawl-based, zero API calls, zero cost
- Crawl-only mode provides ~70% problem coverage. Adding GA4/GSC would unlock content decay and bounce-rate detection.
