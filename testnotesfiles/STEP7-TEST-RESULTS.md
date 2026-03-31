# Step 7 E2E Test Results — Health Scoring: copyblogger.com

**Date:** 2026-03-28 19:24
**Posts scored:** 145
**Clusters:** 4
**Scoring mode:** Crawl-only (no GA4, no GSC)
**AI readiness:** Default 40.0 (no AI citability step)
**Prerequisite:** Step 1 crawl (copyblogger.com, 150 max) + Step 6 clustering (synthetic embeddings)
**Content profile:** Long-form (median 1977w, stddev 1990w)
**Role thresholds (crawl-only):** pillar >= 45, supporter >= 30, at_risk >= 15, dead_weight < 15

---

## 1. Weight Distribution (Crawl-Only Mode)

| # | Factor | Weight | Source |
|---|--------|--------|--------|
| 1 | ai_readiness | 28% | AI Citability scores (default 40.0) |
| 2 | content_depth | 20% | Crawl (word count vs cluster avg) |
| 3 | content_richness | 20% | Crawl proxy merged (predicted engagement + content structure / 2) |
| 4 | freshness | 15% | Crawl (publish_date / modified_date) |
| 5 | internal_links | 10% | Crawl (inbound link count, real resolution) |
| 6 | technical_seo | 7% | Crawl (meta, title, headings, OG, canonical, JSON-LD via eeat_metadata) |
| 7 | traffic_trend | 0% | GA4 (zeroed in crawl-only) |
| 8 | ranking | 0% | GSC (zeroed in crawl-only) |
| 9 | engagement | 0% | GA4 (zeroed in crawl-only) |
| | **Total** | **100%** | |

## 2. Per-Factor Score Distribution

| Factor | Min | Max | Mean | Median | Stddev | Weight |
|--------|-----|-----|------|--------|--------|--------|
| freshness | 10.0 | 79.0 | 29.8 | 30.0 | 5.8 | 15% |
| content_depth | 13.0 | 100.0 | 63.8 | 66.8 | 26.6 | 20% |
| internal_links | 0.0 | 100.0 | 0.7 | 0.0 | 8.3 | 10% |
| technical_seo | 25.0 | 75.0 | 41.4 | 37.5 | 9.5 | 7% |
| ai_readiness | 40.0 | 40.0 | 40.0 | 40.0 | 0.0 | 28% |
| content_richness | 37.5 | 75.8 | 46.4 | 43.1 | 7.2 | 20% |

## 3. Three Sample Posts: Full Factor Breakdowns

### BEST, MEDIAN, and WORST posts with every factor score and the math.

#### BEST Post: "How to Do Keyword Research: Steps, Examples, and Tools" (3229 words)

```
URL: https://copyblogger.com/keyword-research
Cluster: 2, Role: pillar
Inbound links: 0, Outbound links: 0
eeat_metadata: OG=True, canonical=True, JSON-LD=False
Publish date: 2024-05-29

Factor breakdown:
  freshness                   41.0 x 0.15 =  6.15
  content_depth              100.0 x 0.20 = 20.00
  internal_links               0.0 x 0.10 =  0.00
  technical_seo               62.5 x 0.07 =  4.38
  ai_readiness                40.0 x 0.28 = 11.20
  content_richness            75.8 x 0.20 = 15.17
                                            -----
  COMPOSITE                                 56.89 (clamped to 56.9)
```

#### MEDIAN Post: "What Facebook Can Teach You About Effective Blog Marketing" (1924 words)

```
URL: https://copyblogger.com/facebook-application-marketing
Cluster: 3, Role: supporter
Inbound links: 0, Outbound links: 0
eeat_metadata: OG=True, canonical=True, JSON-LD=False
Publish date: 2007-08-23

Factor breakdown:
  freshness                   30.0 x 0.15 =  4.50
  content_depth               60.2 x 0.20 = 12.04
  internal_links               0.0 x 0.10 =  0.00
  technical_seo               50.0 x 0.07 =  3.50
  ai_readiness                40.0 x 0.28 = 11.20
  content_richness            50.6 x 0.20 = 10.11
                                            -----
  COMPOSITE                                 41.35 (clamped to 41.3)
```

#### WORST Post: "The SEOmoz Landing Page Contest: Entries Judged by Live Multivariate Testing" (503 words)

```
URL: https://copyblogger.com/the-seomoz-landing-page-contest-entries-judged-by-live-multivariate-testing
Cluster: 2, Role: at_risk
Inbound links: 0, Outbound links: 0
eeat_metadata: OG=True, canonical=True, JSON-LD=False
Publish date: 2007-07-16

Factor breakdown:
  freshness                   30.0 x 0.15 =  4.50
  content_depth               18.5 x 0.20 =  3.69
  internal_links               0.0 x 0.10 =  0.00
  technical_seo               25.0 x 0.07 =  1.75
  ai_readiness                40.0 x 0.28 = 11.20
  content_richness            37.5 x 0.20 =  7.50
                                            -----
  COMPOSITE                                 28.64 (clamped to 28.6)
```

## 4. Composite Score Distribution

| Score Range | Count | % | Histogram |
|------------|-------|---|-----------|
| 0-10 | 0 | 0.0% | # |
| 10-20 | 0 | 0.0% | # |
| 20-30 | 3 | 2.1% | # |
| 30-40 | 58 | 40.0% | #################### |
| 40-50 | 79 | 54.5% | ########################### |
| 50-60 | 5 | 3.4% | # |
| 60-70 | 0 | 0.0% | # |
| 70-80 | 0 | 0.0% | # |
| 80-90 | 0 | 0.0% | # |
| 90-100 | 0 | 0.0% | # |

**Composite stats:** min=28.6, max=56.9, mean=40.7, median=41.3, stddev=6.4

## 5. Cross-Analysis Tables

### 5a. Composite vs Word Count

| Word Count | Posts | Avg Composite | Min | Max | Avg Freshness | Avg Tech SEO |
|------------|-------|---------------|-----|-----|---------------|-------------|
| 0-500 | 2 | 41.5 | 29.4 | 53.7 | 54.5 | 56.2 |
| 500-1000 | 27 | 32.1 | 28.6 | 36.6 | 29.2 | 35.9 |
| 1000-2000 | 45 | 37.7 | 32.3 | 44.7 | 29.6 | 39.4 |
| 2000+ | 71 | 45.8 | 39.2 | 56.9 | 29.6 | 44.3 |

### 5b. Composite vs Publish Year

| Year | Posts | Avg Composite | Min | Max | Avg Freshness | Avg Depth |
|------|-------|---------------|-----|-----|---------------|----------|
| 2006 | 36 | 39.0 | 29.9 | 48.6 | 29.4 | 60.2 |
| 2007 | 73 | 40.4 | 28.6 | 52.7 | 29.2 | 62.9 |
| 2008 | 32 | 42.3 | 31.3 | 49.9 | 29.4 | 71.2 |
| 2011 | 1 | 45.9 | 45.9 | 45.9 | 30.0 | 83.0 |
| 2024 | 1 | 56.9 | 56.9 | 56.9 | 41.0 | 100.0 |
| 2025 | 2 | 45.1 | 36.6 | 53.7 | 63.1 | 18.0 |

### 5c. Composite vs Cluster (avg per cluster)

| Cluster | Posts | Avg Composite | Min | Max | State | Top Role |
|---------|-------|---------------|-----|-----|-------|----------|
| 1 | 53 | 41.9 | 30.4 | 53.7 | forest | supporter |
| 3 | 44 | 40.6 | 29.4 | 52.7 | forest | supporter |
| 0 | 24 | 39.9 | 31.5 | 49.7 | forest | supporter |
| 2 | 24 | 38.8 | 28.6 | 56.9 | forest | supporter |

## 6. Per-Cluster Detail

Full role breakdown, top post, bottom post, highest-variance factor per cluster.

### Cluster 1 (53 posts, health=41.9, state=forest)

**Role breakdown:**
- supporter: 45
- pillar: 8

**Top post:** Copyblogger - Content marketing tools and training. (score=53.7, 186w)
**Bottom post:** Do You Know When to Stop Writing? (score=30.4, 963w)

**Highest-variance factor:** content_depth (stddev=25.9)

### Cluster 3 (44 posts, health=40.6, state=forest)

**Role breakdown:**
- supporter: 35
- pillar: 7
- at_risk: 2

**Top post:** Writer's Block: The Cause and the Cure (score=52.7, 6412w)
**Bottom post:** Tubetorial Sold to SplashPress Media (score=29.4, 472w)

**Highest-variance factor:** content_depth (stddev=26.8)

### Cluster 0 (24 posts, health=39.9, state=forest)

**Role breakdown:**
- supporter: 20
- pillar: 4

**Top post:** How to Get 6,312 Subscribers to Your Business Blog in One Da (score=49.7, 5389w)
**Bottom post:** Call Me Tonight if You Have a Question (score=31.5, 652w)

**Highest-variance factor:** content_depth (stddev=25.5)

### Cluster 2 (24 posts, health=38.8, state=forest)

**Role breakdown:**
- supporter: 19
- pillar: 4
- at_risk: 1

**Top post:** How to Do Keyword Research: Steps, Examples, and Tools (score=56.9, 3229w)
**Bottom post:** The SEOmoz Landing Page Contest: Entries Judged by Live Mult (score=28.6, 503w)

**Highest-variance factor:** content_depth (stddev=28.5)

## 7. Factor Correlation Matrix (7x7 Pearson)

Pairwise Pearson correlation between the 7 crawl-only factors.
Pairs with |r| > 0.5 are marked with **bold**.

| | Fresh | Depth | Links | Tech | AI | Richness |
|---|---|---|---|---|---|---|
| Fresh | 1.00 | -0.11 | **0.71** | 0.35 | 0.00 | 0.19 |
| Depth | -0.11 | 1.00 | -0.16 | 0.34 | 0.00 | 0.32 |
| Links | **0.71** | -0.16 | 1.00 | 0.30 | 0.00 | 0.20 |
| Tech | 0.35 | 0.34 | 0.30 | 1.00 | 0.00 | **0.65** |
| AI | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| Richness | 0.19 | 0.32 | 0.20 | **0.65** | 0.00 | 1.00 |

**Strong correlations (|r| > 0.5):**
- freshness <-> internal_links: r=0.71 (positive)
- content_richness <-> technical_seo: r=0.65 (positive)

## 8. Score Distribution by Role

| Role | Count | % | Min | Max | Avg | Median |
|------|-------|---|-----|-----|-----|--------|
| supporter | 119 | 82.1% | 30.1 | 48.5 | 39.2 | 40.2 |
| pillar | 23 | 15.9% | 46.1 | 56.9 | 49.8 | 49.6 |
| at_risk | 3 | 2.1% | 28.6 | 29.9 | 29.3 | 29.4 |

**Range overlap analysis:**
- pillar [46.1-56.9] overlaps with supporter [30.1-48.5] in range [46.1-48.5]

## 9. Ecosystem State Decision Trace

For each cluster, every condition checked by `_assign_ecosystem_state`:

```
Cluster 1 (53 posts, health=41.9):
  seedbed? NO  (has_recent=False AND post_count=53 <= 3)
  swamp?   NO  (cannibalization_rate 0.0 <= 0.5)
  desert?  NO  (avg_freshness 30.1 >= 25)
  forest?  YES (has_pillar=True, cann_rate=0.0<0.2=True, health=41.9>38.0=True)
  Result:  forest
```

```
Cluster 3 (44 posts, health=40.6):
  seedbed? NO  (has_recent=False AND post_count=44 <= 3)
  swamp?   NO  (cannibalization_rate 0.0 <= 0.5)
  desert?  NO  (avg_freshness 29.5 >= 25)
  forest?  YES (has_pillar=True, cann_rate=0.0<0.2=True, health=40.6>38.0=True)
  Result:  forest
```

```
Cluster 0 (24 posts, health=39.9):
  seedbed? NO  (has_recent=False AND post_count=24 <= 3)
  swamp?   NO  (cannibalization_rate 0.0 <= 0.5)
  desert?  NO  (avg_freshness 29.2 >= 25)
  forest?  YES (has_pillar=True, cann_rate=0.0<0.2=True, health=39.9>38.0=True)
  Result:  forest
```

```
Cluster 2 (24 posts, health=38.8):
  seedbed? NO  (has_recent=False AND post_count=24 <= 3)
  swamp?   NO  (cannibalization_rate 0.0 <= 0.5)
  desert?  NO  (avg_freshness 30.5 >= 25)
  forest?  YES (has_pillar=True, cann_rate=0.0<0.2=True, health=38.8>38.0=True)
  Result:  forest
```

## 10. Edge Case Posts

Post that scored highest and lowest on each individual factor.

| Factor | Highest Score | Highest Post | Lowest Score | Lowest Post |
|--------|--------------|-------------|-------------|------------|
| freshness | 79.0 | Copyblogger - Content marketing tools an | 10.0 | Aristotle’s Top 3 Tips for Effective Blo |
| content_depth | 100.0 | Is it OK to Steal Someone’s Design? | 13.0 | Copyblogger - Content marketing tools an |
| internal_links | 100.0 | Copyblogger - Content marketing tools an | 0.0 | 5 Steps to Pay Per Click Advertising Tha |
| technical_seo | 75.0 | Copyblogger - Content marketing tools an | 25.0 | Blogging Grows Up |
| ai_readiness | 40.0 | Copyblogger - Content marketing tools an | 40.0 | Copyblogger - Content marketing tools an |
| content_richness | 75.8 | How to Do Keyword Research: Steps, Examp | 37.5 | Why “Content” Has Become a Dirty Word |

### Edge Case Detail

**freshness -- highest (79.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)
**freshness -- lowest (10.0):** Aristotle’s Top 3 Tips for Effective Blogging (2748w, composite=44.8, role=supporter)

**content_depth -- highest (100.0):** Is it OK to Steal Someone’s Design? (3775w, composite=46.9, role=supporter)
**content_depth -- lowest (13.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)

**internal_links -- highest (100.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)
**internal_links -- lowest (0.0):** 5 Steps to Pay Per Click Advertising That Works (2598w, composite=42.3, role=supporter)

**technical_seo -- highest (75.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)
**technical_seo -- lowest (25.0):** Blogging Grows Up (1085w, composite=32.3, role=supporter)

**ai_readiness -- highest (40.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)
**ai_readiness -- lowest (40.0):** Copyblogger - Content marketing tools and training. (186w, composite=53.7, role=pillar)

**content_richness -- highest (75.8):** How to Do Keyword Research: Steps, Examples, and Tools (3229w, composite=56.9, role=pillar)
**content_richness -- lowest (37.5):** Why “Content” Has Become a Dirty Word (2742w, composite=43.9, role=supporter)

## 11. Tech SEO with eeat_metadata (Head Tag Checks)

The crawl's `_extract_eeat_metadata` now extracts `has_og_tags`, `has_canonical`, 
`has_jsonld` booleans from `<head>`. These are passed to `_technical_seo_score` 
as the `eeat_metadata` parameter.

| Head Tag Signal | Posts With | Posts Without | Detection Rate |
|----------------|-----------|--------------|---------------|
| Open Graph tags | 145 | 0 | 100.0% |
| Canonical tag | 145 | 0 | 100.0% |
| JSON-LD schema | 0 | 145 | 0.0% |

**Head tag check distribution (out of 3 eeat_metadata checks):**

| Checks Passing | Posts | % |
|---------------|-------|---|
| 2/3 | 145 | 100.0% |

**Impact of eeat_metadata on tech SEO scores:**

- Average tech SEO **with** eeat_metadata: 41.4
- Average tech SEO **without** eeat_metadata: 16.4
- Delta: +25.0 points (eeat_metadata adds 25.0 to mean tech SEO)
- Max possible improvement: +37.5 (3 checks x 12.5 points each)

## 12. Factor Variance Contribution

Which factors contribute most to score differentiation between posts:

| Factor | Weighted Stddev | % of Total Variance | Weight |
|--------|----------------|--------------------|---------| 
| content_depth | 5.31 | 58.3% | 20% |
| content_richness | 1.43 | 15.7% | 20% |
| freshness | 0.87 | 9.5% | 15% |
| internal_links | 0.83 | 9.1% | 10% |
| technical_seo | 0.66 | 7.3% | 7% |
| ai_readiness | 0.00 | 0.0% | 28% |

## 13. Top 10 Posts by Composite Score

| # | Score | Role | Fresh | Depth | Tech | Links | Richness | WC | Title |
|---|-------|------|-------|-------|------|-------|----------|----|----|
| 1 | 56.9 | pillar | 41 | 100 | 62 | 0 | 76 | 3229 | How to Do Keyword Research: Steps, Examples,  |
| 2 | 53.7 | pillar | 79 | 13 | 75 | 100 | 64 | 186 | Copyblogger - Content marketing tools and tra |
| 3 | 52.7 | pillar | 30 | 100 | 62 | 0 | 63 | 6412 | Writer's Block: The Cause and the Cure |
| 4 | 51.1 | pillar | 30 | 97 | 50 | 0 | 62 | 4469 | 7 Warning Signs That You're Drunk on Your Own |
| 5 | 50.8 | pillar | 30 | 100 | 56 | 0 | 56 | 14267 | How to Write Ebooks that Sell |
| 6 | 49.9 | pillar | 30 | 88 | 62 | 0 | 61 | 2715 | A 20-Step Process For Finding Your 1,000 True |
| 7 | 49.8 | pillar | 30 | 100 | 62 | 0 | 49 | 8227 | The Snowboard, the Subdural Hematoma, and the |
| 8 | 49.8 | pillar | 30 | 100 | 38 | 0 | 57 | 4652 | How a Few Measly Words Can Dramatically Impro |
| 9 | 49.7 | pillar | 30 | 100 | 56 | 0 | 51 | 5389 | How to Get 6,312 Subscribers to Your Business |
| 10 | 49.7 | pillar | 30 | 86 | 50 | 0 | 66 | 2500 | The Problem with Waffly Headlines |

## 14. Bottom 10 Posts by Composite Score

| # | Score | Role | Fresh | Depth | Tech | Links | Richness | WC | Title |
|---|-------|------|-------|-------|------|-------|----------|----|----|
| 1 | 31.6 | supporter | 30 | 25 | 31 | 0 | 43 | 767 | The True Power of the Blog |
| 2 | 31.5 | supporter | 30 | 23 | 38 | 0 | 43 | 652 | Call Me Tonight if You Have a Question |
| 3 | 31.4 | supporter | 30 | 28 | 38 | 0 | 38 | 935 | The Force That Drives Social Media Traffic |
| 4 | 31.3 | supporter | 30 | 22 | 38 | 0 | 43 | 671 | Are You Creating Bookmarkable Content? |
| 5 | 30.8 | supporter | 30 | 19 | 38 | 0 | 43 | 553 | Here's Some Cool Copy for July 4th |
| 6 | 30.4 | supporter | 10 | 32 | 38 | 0 | 43 | 963 | Do You Know When to Stop Writing? |
| 7 | 30.1 | supporter | 30 | 20 | 25 | 0 | 43 | 580 | SEO for Bloggers |
| 8 | 29.9 | at_risk | 30 | 20 | 38 | 0 | 38 | 546 | Do You Spend $10,000 a Month on Pay Per Click |
| 9 | 29.4 | at_risk | 30 | 18 | 38 | 0 | 38 | 472 | Tubetorial Sold to SplashPress Media |
| 10 | 28.6 | at_risk | 30 | 18 | 25 | 0 | 38 | 503 | The SEOmoz Landing Page Contest: Entries Judg |

## 15. Ecosystem State per Cluster

| Cluster | Posts | Health | State | Pillar | Supporter | At Risk | Dead Weight |
|---------|-------|--------|-------|--------|-----------|---------|-------------|
| 1 | 53 | 41.9 | forest | 8 | 45 | 0 | 0 |
| 3 | 44 | 40.6 | forest | 7 | 35 | 2 | 0 |
| 0 | 24 | 39.9 | forest | 4 | 20 | 0 | 0 |
| 2 | 24 | 38.8 | forest | 4 | 19 | 1 | 0 |

### State Summary

| State | Clusters | Meaning |
|-------|----------|---------|
| forest | 4 | Healthy (has pillar, low cann, health > 38 crawl-only / > 50 with traffic) |
| meadow | 0 | Everything else (default) |
| seedbed | 0 | New cluster (<= 3 posts, recent content) |
| swamp | 0 | High cannibalization (>50%) or large without pillar |
| desert | 0 | Stale content (avg freshness < 25) |

## 16. Internal Link Analysis (Real Resolution)

- Total internal links resolved: 1
- Posts with 0 inbound links (orphans): 144/145 (99.3%)
- Posts with 0 outbound links: 144/145 (99.3%)
- Max inbound links: 1 (Copyblogger - Content marketing tools and training)

| Inbound Links | Posts | % | Avg Composite |
|--------------|-------|---|---------------|
| 0 | 144 | 99.3% | 40.6 |
| 1-2 | 1 | 0.7% | 53.7 |
| 3-5 | 0 | 0.0% | - |
| 6-10 | 0 | 0.0% | - |
| 11+ | 0 | 0.0% | - |

## 17. Processing Time

| Step | Time | Notes |
|------|------|-------|
| Crawl (Step 1) | 79.9s | 148 URLs |
| Clustering (Step 6) | 34.7s | Synthetic embeddings |
| Factor scoring (all) | 124.1ms | Pure computation |
|   content_depth | 81.7ms | |
|   technical_seo | 18.0ms | |
|   content_structure | 13.3ms | |
|   predicted_engagement | 9.5ms | |
|   freshness | 1.1ms | |
|   engagement | 0.5ms | |
|   traffic_trend | 0.0ms | |
|   ranking | 0.0ms | |
| Composite scoring | 160.8ms | Weights + clamp |
| **Total Step 7** | **285ms** | **No DB, no API calls** |

## 18. Observations

1. **AI readiness contributes zero variance** -- all posts have the default 40.0 score. In production with real AI citability scores (range 10-90), AI readiness (36% weight) would be the dominant differentiator. In this test, it adds a flat 14.4 to every composite.

2. **Traffic, ranking, and engagement are zeroed** -- expected in crawl-only mode. Traffic trend returns 'unknown' with score 30.0 for all posts. Ranking score for position 100 = 0.0. Engagement with defaults (bounce=0.5, time=60s) = 32.0. These contribute 0 to composite because their weights are 0%.

3. **Score spread is 28.2 points** (range 28.6-56.9). This is narrow. With real AI citability scores, spread would be wider.

4. **Freshness distribution:** 0 posts score >= 80 (recent), 142 posts score < 40 (stale). Mean freshness: 29.8.

5. **Internal link resolution:** 1/145 posts have resolved inbound links (score > 0). 144 posts are orphans (0 inbound). Mean link score: 0.7. This uses real crawled internal_links with URL matching, not a fake 0-everywhere default.

6. **Technical SEO with eeat_metadata:** 0 posts score >= 87.5 (7/8 checks). Mean tech SEO: 41.4. eeat_metadata detection: OG=145, canonical=145, JSON-LD=0. Delta vs without eeat_metadata: +25.0 points.

7. **Role distribution (crawl-only thresholds):** pillar=23 (>= 45), supporter=119 (>= 30), at_risk=3 (>= 15), dead_weight=0 (< 15). No posts can be 'competitor' because cannibalization_pairs is empty on first run.

8. **Ecosystem states:** forest=4, meadow=0, seedbed=0, swamp=0, desert=0. Without cannibalization data, swamp can only trigger on cann_rate > 0.5 (always 0 on first run). Desert requires avg freshness < 25.

9. **Score clamping:** 0 posts clamped to floor (10), 0 posts clamped to ceiling (95). No clamping occurred.

10. **Content richness (merged factor)** -- avg=46.4, max=75.8. Merges predicted_engagement + content_structure to eliminate triple-counting with tech_seo. Readability IS feeding into predicted_engagement component.

11. **Content depth vs word count correlation:** r=0.74. Strong correlation. Content depth also factors in cluster average comparison and quality bonuses (lists, images, tables, external links), so it is not just a word count proxy.

---

*Report generated by `backend/scripts/test_step4_e2e.py` (deep analysis) -- crawl-only mode, no database, eeat_metadata enabled.*