# Step 8 E2E Test Results — Cannibalization: copyblogger.com

**Date:** 2026-03-28 20:08
**Posts:** 145 real (from crawl) + 4 synthetic (injected for validation) = 149 total
**Prerequisite:** Step 1 crawl + synthetic embeddings + Step 6 clustering + Step 7 health scores
**Note:** Embeddings are synthetic (keyword-injected random vectors), not real OpenAI embeddings. Cosine similarity distribution will differ with real embeddings.
**GSC data:** None (crawl-only mode -- no query overlap signal)

---

## 8a. Threshold Calibration

| Metric | Value |
|--------|-------|
| Pairs sampled | 500 |
| Similarity min | -0.0725 |
| Similarity median | 0.0056 |
| Similarity max | 0.7544 |
| Similarity stddev | 0.1478 |
| p85 (flag candidate) | 0.2805 |
| p92 (high candidate) | 0.3518 |
| p97 (critical candidate) | 0.4779 |
| Calibrated flag | 0.4000 |
| Calibrated high | 0.5000 |
| Calibrated critical | 0.6000 |
| **Thresholds used (defaults)** | **flag=0.45, high=0.55, critical=0.65** |
| Calibration time | 9.5ms |

### Pairwise Similarity Distribution

| Range | Count | % | Histogram |
|-------|-------|---|-----------|
| [-0.1, 0.0) | 206 | 41.2% | #################### |
| [0.0, 0.1) | 207 | 41.4% | #################### |
| [0.1, 0.2) | 4 | 0.8% | # |
| [0.2, 0.3) | 14 | 2.8% | # |
| [0.3, 0.4) | 43 | 8.6% | #### |
| [0.4, 0.5) | 19 | 3.8% | # |
| [0.5, 0.6) | 5 | 1.0% | # |
| [0.6, 0.7) | 1 | 0.2% | # |
| [0.7, 0.8) | 1 | 0.2% | # |
| [0.8, 1.0) | 0 | 0.0% | # |

## 8b-main. Entity Extraction

| Metric | Value |
|--------|-------|
| Titles with entity | 141/149 (94.6%) |
| Unique entities | 140 |
| Processing time | 11.0ms |

### Top Entities

| Entity | Posts | Example Title |
|--------|-------|--------------|
| thanks google | 2 | Thanks Google! |
| pay per click advertising | 1 | 5 Steps to Pay Per Click Advertising That Works |
| end adsense | 1 | It’s the End of AdSense as We Know It (And I Feel Fine) |
| adwords landing fiasco | 1 | Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers |
| seo industry branding | 1 | Does the SEO Industry Have a Branding Problem? |
| content dirty word | 1 | Why “Content” Has Become a Dirty Word |
| powerful blogging technique | 1 | The Most Powerful Blogging Technique There Is |
| aristotle top tips | 1 | Aristotle’s Top 3 Tips for Effective Blogging |
| titles story | 1 | Titles That Tell a Whole Story |
| blogging grows | 1 | Blogging Grows Up |
| telling people story | 1 | Telling People a Story They Want to Hear |
| magnetic headlines readers | 1 | Why Magnetic Headlines Attract More Readers |
| coercive copywriting techniques | 1 | 3 Coercive Copywriting Techniques |
| important words business | 1 | The 9 Most Important Words for Business Bloggers |
| shameless attention seeker | 1 | I am a Shameless Attention Seeker |

## 8c-main. Intent Classification

| Intent Group | Posts | % |
|-------------|-------|---|
| learning | 41 | 27.5% |
| opinion | 18 | 12.1% |
| case_study | 8 | 5.4% |
| shopping | 1 | 0.7% |
| (unclassified) | 81 | 54.4% |

## 8d. Cannibalization Detection

| Metric | Value |
|--------|-------|
| Clusters scanned | 4 |
| Total candidate pairs | 3094 |
| Pairs above cosine threshold | 2793 |
| Filtered (low blended score) | 304 |
| **Cannibalization pairs found** | **3** |
| Detection time | 126.1ms |

### Severity Distribution

| Severity | Count | % |
|----------|-------|---|
| critical | 1 | 33.3% |
| high | 1 | 33.3% |
| medium | 1 | 33.3% |

### Resolution Distribution

| Resolution | Count | % | Meaning |
|-----------|-------|---|---------|
| redirect | 0 | 0.0% | 301 redirect shorter to longer (cosine >= 0.95) |
| merge | 1 | 33.3% | Combine into stronger post (critical severity or cosine >= 0.85) |
| differentiate | 0 | 0.0% | Refocus each on its unique intent (different intents) |
| monitor | 2 | 66.7% | Add internal links, track over time (moderate overlap) |

### Per-Cluster Pair Count

| Cluster | Posts | Candidate Pairs | Cannibalizing Pairs | Rate |
|---------|-------|-----------------|--------------------|----- |
| 1 | 57 | 1596 | 3 | 0.2% |
| 3 | 44 | 946 | 0 | 0.0% |
| 0 | 24 | 276 | 0 | 0.0% |
| 2 | 24 | 276 | 0 | 0.0% |

## 8d+. Sample Filtered Pairs (blended <= 0.35, cosine above threshold)

These pairs passed the cosine threshold but were filtered by the blended score. Verify they are genuine false positives:

| # | Cosine | Blended | Slug | Entity A | Entity B | Title Topic | H2 Jacc | Title A | Title B | Correct? |
|---|--------|---------|------|----------|----------|-------------|---------|---------|---------|----------|
| 1 | 0.488 | 0.153 | 0.000 | None | coercive copywr | 0.000 | 0.000 | The True Power of the Blog | 3 Coercive Copywriting Techniques | YES |
| 2 | 0.476 | 0.151 | 0.000 | None | signals copywri | 0.000 | 0.000 | The True Power of the Blog | The 37 Signals Approach to Copywrit | YES |
| 3 | 0.477 | 0.152 | 0.000 | None | copywriting ski | 0.000 | 0.000 | The True Power of the Blog | How Copywriting Skills Can Improve  | YES |
| 4 | 0.475 | 0.151 | 0.000 | None | fight copywriti | 0.000 | 0.000 | The True Power of the Blog | Fight Copywriting Flab: How to Tone | YES |
| 5 | 0.532 | 0.160 | 0.000 | None | measly words dr | 0.000 | 0.000 | The True Power of the Blog | How a Few Measly Words Can Dramatic | YES |

**Total filtered:** 304 pairs. Showing 5 samples above.

## 8d++. Per-Cluster Closest Misses (highest cosine pair NOT flagged)

These are the highest-similarity pairs that did NOT pass the cosine threshold. If any look like real cannibalization, the threshold may be too high:

| Cluster | Cosine | Threshold | Title A | Title B |
|---------|--------|-----------|---------|---------|
| 0 | 0.361 | 0.550 | Five Reasons Why the List Post is Dead | Don't Like Top 10 Lists? Tell a Story In |
| 1 | 0.548 | 0.550 | Why You Are Always Selling With Your Blo | How a Few Measly Words Can Dramatically  |
| 2 | 0.492 | 0.550 | Does the SEO Industry Have a Branding Pr | How to Do Keyword Research: Steps, Examp |
| 3 | 0.426 | 0.450 | The Ready, Fire, Aim, Reload Strategy fo | Twitter Writing Contest: Win an IPod Nan |

## 8e. Top Cannibalization Pairs (by Blended Score)

### Top 3 Pairs

| # | Source | Severity | Blended | Cosine | Resolution | Title A | Title B |
|---|--------|----------|---------|--------|-----------|---------|---------|
| 1 | synthetic | critical | 0.800 | 0.836 | merge | SEO Link Building Guide: The Definitive  | Link Building Strategies for SEO: A Comp |
| 2 | synthetic | high | 0.701 | 0.711 | monitor | 17 Content Marketing Tips That Actually  | Content Marketing Strategies for B2B Gro |
| 3 | real | medium | 0.408 | 0.690 | monitor | 3 Coercive Copywriting Techniques | Copywriting 101: How to Craft Compelling |

### Signal Breakdown (Top 5)

**Pair 1** (SYNTHETIC):
- Post A: `https://copyblogger.com/seo-link-building-guide/`
- Post B: `https://copyblogger.com/link-building-strategies-seo/`

| Signal | Value | Weight | Contribution |
|--------|-------|--------|-------------|
| Cosine similarity | 0.836 | 15% | 0.125 |
| Slug overlap | 1.000 | 20% | 0.200 |
| Entity+Intent | entity_a="seo link building guide", entity_b="link building strategies " | 25% | (composite) |
| Title topic overlap | 1.000 | 20% | 0.200 |
| H2 Jaccard | 0.500 | 20% | 0.100 |
| **Blended** | **0.800** | | **critical** |

**Pair 2** (SYNTHETIC):
- Post A: `https://copyblogger.com/content-marketing-tips/`
- Post B: `https://copyblogger.com/content-marketing-strategies/`

| Signal | Value | Weight | Contribution |
|--------|-------|--------|-------------|
| Cosine similarity | 0.711 | 15% | 0.107 |
| Slug overlap | 1.000 | 20% | 0.200 |
| Entity+Intent | entity_a="content marketing tips", entity_b="content marketing strateg" | 25% | (composite) |
| Title topic overlap | 0.667 | 20% | 0.133 |
| H2 Jaccard | 0.429 | 20% | 0.086 |
| **Blended** | **0.701** | | **high** |

**Pair 3** (REAL):
- Post A: `https://copyblogger.com/3-coercive-copywriting-techniques`
- Post B: `https://copyblogger.com/copywriting-101`

| Signal | Value | Weight | Contribution |
|--------|-------|--------|-------------|
| Cosine similarity | 0.690 | 15% | 0.104 |
| Slug overlap | 0.333 | 20% | 0.067 |
| Entity+Intent | entity_a="coercive copywriting tech", entity_b="copywriting 101" | 25% | (composite) |
| Title topic overlap | 0.500 | 20% | 0.100 |
| H2 Jaccard | 0.000 | 20% | 0.000 |
| **Blended** | **0.408** | | **medium** |


## 8f. Blended Score Distribution

| Score Range | Count | % | Severity |
|------------|-------|---|----------|
| [0.35, 0.40) | 0 | 0.0% | medium |
| [0.40, 0.45) | 1 | 33.3% | medium |
| [0.45, 0.50) | 0 | 0.0% | medium |
| [0.50, 0.55) | 0 | 0.0% | medium |
| [0.55, 0.60) | 0 | 0.0% | high |
| [0.60, 0.65) | 0 | 0.0% | high |
| [0.65, 0.70) | 0 | 0.0% | high |
| [0.70, 0.80) | 1 | 33.3% | high |
| [0.80, 1.01) | 1 | 33.3% | critical |

**Blended score stats:** min=0.408, max=0.800, mean=0.636, median=0.701, stddev=0.204

## 8g. Cosine vs Blended Score Comparison

Shows how the blended score differs from raw cosine similarity:

| Metric | Cosine | Blended | Difference |
|--------|--------|---------|------------|
| Mean | 0.746 | 0.636 | -0.110 |
| Median | 0.711 | 0.701 | -0.010 |
| Min | 0.690 | 0.408 | |
| Max | 0.836 | 0.800 | |

**Cosine-only would flag:** 3 pairs (>= 0.45)
**Blended actually flagged:** 3 pairs (> 0.35)
**Blended filtered out:** 304 pairs (cosine above threshold but blended <= 0.35)

## 8h. Chunk Splitting (Structure Only, No Embeddings)

| Metric | Value |
|--------|-------|
| Posts with chunks | 149/149 |
| Total chunks | 357 |
| Min chunks/post | 1 |
| Max chunks/post | 22 |
| Mean chunks/post | 2.4 |
| Median chunks/post | 1 |
| Splitting time | 92.6ms |

### Chunks per Post Distribution

| Range | Count | % |
|-------|-------|---|
| 1 (title only) | 103 | 69.1% |
| 2-3 | 13 | 8.7% |
| 4-5 | 20 | 13.4% |
| 6-10 | 10 | 6.7% |
| 11-20 | 2 | 1.3% |
| 21+ | 1 | 0.7% |

## 8i. Stronger Post Analysis

| Metric | Value |
|--------|-------|
| Mean health gap (stronger - weaker) | 2.3 |
| Median health gap | 0.0 |
| Max health gap | 7.0 |
| Min health gap | 0.0 |
| Pairs with health gap < 5 (close call) | 2 (66.7%) |

## 8j. Entity Extraction Failures

Titles where entity extraction returned None — showing what a correct entity would be:

| # | Title | Extracted | Suggested Entity |
|---|-------|-----------|-----------------|
| 1 | Copyblogger - Content marketing tools and training. | None | copyblogger content marketing |
| 2 | For Whom the Blog Tips (It Tips For Thee) | None | whom blog tips |
| 3 | The True Power of the Blog | None | true power blog |
| 4 | What’s Your Story? | None | story |
| 5 | Why People Want to Know What’s In It For *You* | None | people want know |
| 6 | Five Reasons Why the List Post is Dead | None | five reasons list |
| 7 | So You Think You're the Next Blog Superstar? | None | think next blog |
| 8 | What Does Creativity Mean to You? | None | does creativity mean |

**Total unmatched:** 8/149 (5%)

## 8k. Calibration Validation

| Metric | Value | Notes |
|--------|-------|-------|
| p85 raw | 0.2805 | Below floor 0.40 | 
| p92 raw | 0.3518 | Below floor 0.50 | 
| p97 raw | 0.4779 | Below floor 0.60 | 
| Floors triggered | 3/3 | All floors active — synthetic embeddings have lower similarity than real OpenAI embeddings |

Synthetic embeddings (keyword-injected random vectors) produce a median pairwise similarity of 0.0056, far below real text-embedding-3-small which typically produces 0.15-0.35 median similarity. This means calibrated percentile values fall below the absolute floors, so floors override calibrated values. **This is expected behavior** for synthetic embeddings.

## 8l. Cross-Analysis: Cosine → Blended Pipeline

Of 3094 total candidate pairs in all clusters:

```
   3094 total candidate pairs
  →  2787 below cosine threshold (90.1%) — skipped
  →   307 above cosine threshold (9.9%)
      →   304 filtered by blended score ≤ 0.35 (99.0% of above-threshold)
      →     3 flagged as cannibalization (1.0% of above-threshold)
```

**Blended score false-positive prevention rate:** 99.0% — 304 pairs that cosine alone would have flagged were correctly filtered by the 5-signal blended score.

## Processing Summary

| Step | Time | External API | Notes |
|------|------|-------------|-------|
| Crawl (Step 1 prerequisite) | 82.6s | None | |
| Clustering (Step 6 prerequisite) | 45.8s | None | Synthetic embeddings |
| Health scoring (Step 7 prerequisite) | 218.8ms | None | Crawl-only mode |
| Threshold calibration | 9.5ms | None | 500 pairs sampled |
| Entity extraction | 11.0ms | None | Regex-based |
| Intent classification | 4.1ms | None | Keyword-based |
| Within-cluster detection | 126.1ms | None | 3094 pairs evaluated |
| Cross-cluster detection | 72.9ms | None | 0 candidates, 0 found |
| Chunk splitting | 92.6ms | None | Structure only |
| **Total Step 8** | **316ms** | **Free** | **No DB, no API** |

## Observations

1. **Cannibalization rate: 3/3094 pairs (0.1%)** -- low rate. Synthetic embeddings produce different similarity patterns than real OpenAI embeddings. With real embeddings, the distribution would be more concentrated around topically similar posts.

2. **Blended score filtered 304 pairs (99%)** -- posts that passed the cosine threshold (0.45) but scored <= 0.35 blended. These are 'content series' (topically similar but targeting different keywords/intents). Without blended scoring, these would be false positives.

3. **Entity extraction: 141/149 titles (95%)** -- good extraction rate. Copyblogger titles often use creative/editorial formats that don't match the standard entity patterns (X Review, How to X, N Best X). Real SEO sites (Backlinko, Ahrefs blog) typically have higher extraction rates.

4. **Intent classification: 68/149 posts (46%)** -- most common intent: learning (41 posts). Intent-aware threshold raises the flag threshold by +0.10 for cross-intent pairs, reducing false positives where posts target different search purposes.

5. **Severity: 1 critical, 1 high, 1 medium** -- 1 near-duplicate pairs detected. In crawl-only mode (no GSC), severity is determined entirely by the blended score: >0.80 = critical, >0.55 = high, >0.35 = medium.

6. **Resolution recommendations: 2 monitor, 1 merge, 0 redirect, 0 differentiate** -- 'monitor' dominates because most pairs have moderate overlap (cosine < 0.85, not critical severity). With real embeddings and higher cosine similarities, 'merge' and 'redirect' would be more common.

7. **Chunk splitting: 357 chunks from 149 posts** -- avg 2.4 chunks/post. Chunk confirmation (Step 8b) would embed these at ~$0.50/site via OpenAI, checking max pairwise chunk similarity >= 0.88 to confirm section-level overlap. Not run in this test (requires OpenAI API key).

8. **Stronger post determination: mean health gap = 2.3** -- small gap -- many close calls. In crawl-only mode (no traffic data), strength = health score only. With GA4 data, traffic is weighted 10x higher than health score, which would produce clearer winners.

9. **HNSW pre-filter: not applicable** -- this test uses in-memory cosine similarity (numpy dot product). In production with pgvector, clusters with 20+ posts use HNSW index to find top-10 nearest neighbors per post, reducing O(n²) to O(10n) candidates.

10. **Cross-cluster cannibalization: 0 pairs found** -- in-memory scan (top 5 neighbors per post, cosine >= 0.55 high threshold, different clusters). Checked 0 cross-cluster candidates. Production uses pgvector HNSW index for the same algorithm via `_detect_cross_cluster()`.

---

*Report generated by `backend/scripts/test_step5_e2e.py` -- crawl-only mode, no database, no OpenAI API.*