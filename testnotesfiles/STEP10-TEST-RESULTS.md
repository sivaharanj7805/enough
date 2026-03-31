# Code Step 10 E2E Test Results: copyblogger.com

**Date:** 2026-03-28 23:05
**Pipeline Step:** Code Step 10 (Spec Step 7) — Recommendations
**Posts analyzed:** 149 (including 4 synthetic cannibalization test posts)
**Clusters:** 4
**Problems detected (Step 9):** 407
**Cannibalization pairs (Step 8):** 373
**Orphan posts:** 148
**Mode:** Crawl-only (no database, no Claude enrichment)
**Prerequisite:** Step 1 crawl (copyblogger.com, 150 max) + Step 6 clustering (synthetic embeddings) + Step 8 cannibalization + Step 9 problem detection

---

## 10a. Input Summary

### Problems by Type (Input to Recommendation Engine)

| Problem Type | Count | Has Template? |
|-------------|-------|--------------|
| `decay_mild` | 136 | YES |
| `seo_missing_meta` | 130 | YES |
| `seo_no_headings` | 99 | YES |
| `thin_below_cluster_avg` | 17 | YES |
| `seo_title_length` | 11 | YES |
| `seo_no_images` | 5 | YES |
| `decay_moderate` | 4 | YES |
| `thin_content` | 2 | YES |
| `decay_severe` | 2 | YES |
| `readability_too_complex` | 1 | YES |
| **Total** | **407** | **10/10 covered** |

### Cannibalization Pairs (Input from Step 8)

| # | Post A | Post B | Cosine | Severity | Resolution |
|---|--------|--------|--------|----------|-----------|
| 1 | Copyblogger - Content marketing too | Link Building Strategies for SEO: A | 0.848 | critical | merge |
| 2 | SEO Link Building Guide: The Defini | Link Building Strategies for SEO: A | 0.836 | critical | merge |
| 3 | How a Few Measly Words Can Dramatic | What Romance Novels Can Teach You A | 0.756 | critical | merge |
| 4 | 3 Coercive Copywriting Techniques | How a Few Measly Words Can Dramatic | 0.754 | critical | merge |
| 5 | Fight Copywriting Flab: How to Tone | How a Few Measly Words Can Dramatic | 0.753 | critical | merge |
| 6 | The 37 Signals Approach to Copywrit | How a Few Measly Words Can Dramatic | 0.746 | critical | merge |
| 7 | How a Few Measly Words Can Dramatic | Copywriting 101: How to Craft Compe | 0.744 | critical | merge |
| 8 | Copyblogger - Content marketing too | How a Few Measly Words Can Dramatic | 0.743 | critical | merge |
| 9 | How Copywriting Skills Can Improve  | How a Few Measly Words Can Dramatic | 0.726 | critical | merge |
| 10 | 17 Content Marketing Tips That Actu | Content Marketing Strategies for B2 | 0.711 | critical | merge |
| ... | | | | | (363 more) |

### Orphan Posts: 148

## 10b. Recommendation Output

### By Recommendation Type

| Recommendation Type | Count | % of Total | Source |
|-------------------|-------|-----------|--------|
| `optimize` | 39 | 32.2% | problem |
| `merge` | 33 | 27.3% | cannibalization |
| `expand` | 19 | 15.7% | problem |
| `interlink` | 13 | 10.7% | orphan_link |
| `refresh` | 11 | 9.1% | problem |
| `update` | 6 | 5.0% | problem |
| **Total** | **121** | **100%** | |

### By Priority

| Priority | Count | % of Total | Effort (hrs) | Histogram |
|----------|-------|-----------|-------------|-----------|
| critical | 0 | 0.0% | 0.0 | # |
| high | 51 | 42.1% | 81.5 | ##################### |
| medium | 44 | 36.4% | 39.5 | ################## |
| low | 26 | 21.5% | 10.2 | ########## |

### By Confidence

| Confidence | Count | % of Total |
|-----------|-------|-----------|
| high | 87 | 71.9% |
| medium | 18 | 14.9% |
| low | 16 | 13.2% |

### By Source

| Source | Count | % of Total |
|--------|-------|-----------|
| problem | 75 | 62.0% |
| cannibalization | 33 | 27.3% |
| orphan_link | 13 | 10.7% |

## 10c. Effort Estimation

| Metric | Value |
|--------|-------|
| Total estimated effort | 131.2 hours |
| Average effort per rec | 1.08 hours |
| High-priority effort | 81.5 hours |
| Medium-priority effort | 39.5 hours |
| Low-priority effort | 10.2 hours |

### Effort by Recommendation Type

| Rec Type | Count | Effort/Rec | Total Effort |
|----------|-------|-----------|-------------|
| `merge` | 33 | 2.00h | 66.0h |
| `expand` | 19 | 1.55h | 29.5h |
| `optimize` | 39 | 0.39h | 15.2h |
| `update` | 6 | 1.33h | 8.0h |
| `interlink` | 13 | 0.50h | 6.5h |
| `refresh` | 11 | 0.55h | 6.0h |

## 10d. Template Coverage

| Problem Type | Template? | Problems | Recs Generated | Coverage |
|-------------|----------|---------|---------------|----------|
| `decay_mild` | YES | 136 | 11 | 8% |
| `seo_missing_meta` | YES | 130 | 11 | 8% |
| `seo_no_headings` | YES | 99 | 11 | 11% |
| `thin_below_cluster_avg` | YES | 17 | 17 | 100% |
| `seo_title_length` | YES | 11 | 11 | 100% |
| `seo_no_images` | YES | 5 | 5 | 100% |
| `decay_moderate` | YES | 4 | 4 | 100% |
| `thin_content` | YES | 2 | 2 | 100% |
| `decay_severe` | YES | 2 | 2 | 100% |
| `readability_too_complex` | YES | 1 | 1 | 100% |

**Deduplication:** 407 problem instances -> 75 unique recommendations (81.6% deduped)
**Dedup rule:** One recommendation per (post_id, problem_type) pair

## 10e. Cannibalization Recommendations

### Summary

| Metric | Value |
|--------|-------|
| Total cannibalization recs | 33 |
| Action: merge | 33 |
| Priority: high | 33 |

### Top 30 Cannibalization Recommendations

| # | Action | Priority | Cosine | Post A | Post B | Effort |
|---|--------|----------|--------|--------|--------|--------|
| 1 | merge | high | 0.848 | Copyblogger - Content marketin | Link Building Strategies for S | 2.0h |
| 2 | merge | high | 0.836 | SEO Link Building Guide: The D | Link Building Strategies for S | 2.0h |
| 3 | merge | high | 0.756 | How a Few Measly Words Can Dra | What Romance Novels Can Teach  | 2.0h |
| 4 | merge | high | 0.754 | 3 Coercive Copywriting Techniq | How a Few Measly Words Can Dra | 2.0h |
| 5 | merge | high | 0.753 | Fight Copywriting Flab: How to | How a Few Measly Words Can Dra | 2.0h |
| 6 | merge | high | 0.746 | The 37 Signals Approach to Cop | How a Few Measly Words Can Dra | 2.0h |
| 7 | merge | high | 0.744 | How a Few Measly Words Can Dra | Copywriting 101: How to Craft  | 2.0h |
| 8 | merge | high | 0.743 | Copyblogger - Content marketin | How a Few Measly Words Can Dra | 2.0h |
| 9 | merge | high | 0.726 | How Copywriting Skills Can Imp | How a Few Measly Words Can Dra | 2.0h |
| 10 | merge | high | 0.711 | 17 Content Marketing Tips That | Content Marketing Strategies f | 2.0h |
| 11 | merge | high | 0.699 | 3 Coercive Copywriting Techniq | The 37 Signals Approach to Cop | 2.0h |
| 12 | merge | high | 0.693 | 3 Coercive Copywriting Techniq | Fight Copywriting Flab: How to | 2.0h |
| 13 | merge | high | 0.690 | 3 Coercive Copywriting Techniq | Copywriting 101: How to Craft  | 2.0h |
| 14 | merge | high | 0.685 | Fight Copywriting Flab: How to | What Romance Novels Can Teach  | 2.0h |
| 15 | merge | high | 0.682 | Copyblogger - Content marketin | Copywriting 101: How to Craft  | 2.0h |
| 16 | merge | high | 0.680 | 3 Coercive Copywriting Techniq | What Romance Novels Can Teach  | 2.0h |
| 17 | merge | high | 0.679 | Copywriting 101: How to Craft  | What Romance Novels Can Teach  | 2.0h |
| 18 | merge | high | 0.678 | Copyblogger - Content marketin | The 37 Signals Approach to Cop | 2.0h |
| 19 | merge | high | 0.676 | Copyblogger - Content marketin | What Romance Novels Can Teach  | 2.0h |
| 20 | merge | high | 0.676 | 3 Coercive Copywriting Techniq | How Copywriting Skills Can Imp | 2.0h |
| 21 | merge | high | 0.676 | Fight Copywriting Flab: How to | Copywriting 101: How to Craft  | 2.0h |
| 22 | merge | high | 0.674 | The 37 Signals Approach to Cop | How Copywriting Skills Can Imp | 2.0h |
| 23 | merge | high | 0.674 | How Copywriting Skills Can Imp | Fight Copywriting Flab: How to | 2.0h |
| 24 | merge | high | 0.673 | The 37 Signals Approach to Cop | Fight Copywriting Flab: How to | 2.0h |
| 25 | merge | high | 0.673 | The 37 Signals Approach to Cop | Copywriting 101: How to Craft  | 2.0h |
| 26 | merge | high | 0.672 | Copyblogger - Content marketin | 3 Coercive Copywriting Techniq | 2.0h |
| 27 | merge | high | 0.672 | Copyblogger - Content marketin | Fight Copywriting Flab: How to | 2.0h |
| 28 | merge | high | 0.671 | How Copywriting Skills Can Imp | Copywriting 101: How to Craft  | 2.0h |
| 29 | merge | high | 0.670 | Copyblogger - Content marketin | How Copywriting Skills Can Imp | 2.0h |
| 30 | merge | high | 0.669 | The Force That Drives Social M | The Ready, Fire, Aim, Reload S | 2.0h |
| ... | | | | | | (3 more) |

### Resolution Logic (Step 8 Blended Scoring)

| Resolution | Action | Priority | Effort | Source |
|-----------|--------|----------|--------|--------|
| redirect | 301 redirect weaker -> stronger | critical | 0.5h | cosine >= 0.95 |
| merge | Merge content, then redirect | high | 2.0h | H2 Jaccard > 0.7 or critical severity |
| differentiate | Refocus on distinct angles | severity-based | 1.5h | slug/title overlap |
| monitor | Skip (not actionable) | — | — | low overlap, different intents |

**Resolution distribution:** merge=33
**Filtered out:** 340 of 373 pairs had resolution=monitor (skipped)

## 10f. Orphan Link Recommendations

**Generated:** 13 orphan link recommendations
**Per-post recs:** 13 | **Site-level recs:** 0
**Similarity threshold:** 0.20 minimum (negative/near-zero filtered out)
**Quality gate:** <20% with quality matches triggers site-level fallback

### Per-Post Orphan Recommendations

| # | Orphan Post | Word Count | Link Sources | Top Source Similarity |
|---|-----------|-----------|-------------|---------------------|
| 1 | Why the AdWords Landing Page Fiasco Won’t Hur | 1179 | 1 | 0.427 |
| 2 | For Whom the Blog Tips (It Tips For Thee) | 1267 | 1 | 0.454 |
| 3 | The True Power of the Blog | 767 | 1 | 0.475 |
| 4 | Why “Content” Has Become a Dirty Word | 2742 | 1 | 0.486 |
| 5 | The Most Powerful Blogging Technique There Is | 2718 | 1 | 0.474 |
| 6 | Aristotle’s Top 3 Tips for Effective Blogging | 2748 | 1 | 0.510 |
| 7 | Blogging Grows Up | 1085 | 1 | 0.447 |
| 8 | Why Magnetic Headlines Attract More Readers | 1977 | 1 | 0.493 |
| 9 | 3 Coercive Copywriting Techniques | 2260 | 1 | 0.672 |
| 10 | The 9 Most Important Words for Business Blogg | 1332 | 1 | 0.427 |
| 11 | How Great Headlines Score Traffic | 2777 | 1 | 0.468 |
| 12 | Five of Your Headlines… Remixed | 1626 | 1 | 0.482 |
| 13 | Everything You Need to Know About Writing Suc | 2225 | 1 | 0.489 |

### Sample Link Suggestions (Top 3 Orphans)

**Orphan:** Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers

| Suggested Source | Similarity |
|-----------------|-----------|
| Copyblogger - Content marketing tools and training | 0.427 |

**Orphan:** For Whom the Blog Tips (It Tips For Thee)

| Suggested Source | Similarity |
|-----------------|-----------|
| Copyblogger - Content marketing tools and training | 0.454 |

**Orphan:** The True Power of the Blog

| Suggested Source | Similarity |
|-----------------|-----------|
| Copyblogger - Content marketing tools and training | 0.475 |


## 10g. Per-Cluster Recommendation Density

| Cluster | Label | Posts | Recs | Density | Top Rec Types |
|---------|-------|-------|------|---------|-------------|
| 0 | Words Business & People | 24 | 14 | 0.6 | expand=4, optimize=4, refresh=2 |
| 1 | Content Promotion & Blogg | 57 | 71 | 1.2 | merge=31, optimize=17, interlink=11 |
| 2 | Sales Letter & SEO | 24 | 12 | 0.5 | expand=5, optimize=5, refresh=1 |
| 3 | Social Media & Marketing | 44 | 24 | 0.5 | optimize=13, expand=5, refresh=4 |

## 10h. Top 10 Most Recommended Posts

| # | Post Title | Recs | Priority Mix | Rec Types |
|---|-----------|------|-------------|----------|
| 1 | Copyblogger - Content marketing tools and tra | 11 | high=10, medium=1 | expand, merge, optimize |
| 2 | 3 Coercive Copywriting Techniques | 7 | high=7 | interlink, merge |
| 3 | 5 Steps to Pay Per Click Advertising That Wor | 6 | medium=5, low=1 | optimize, refresh |
| 4 | The True Power of the Blog | 5 | medium=3, low=1, high=1 | expand, interlink, optimize, refresh |
| 5 | The 37 Signals Approach to Copywriting | 5 | high=5 | merge |
| 6 | For Whom the Blog Tips (It Tips For Thee) | 4 | medium=2, low=1, high=1 | interlink, optimize, refresh |
| 7 | Why “Content” Has Become a Dirty Word | 4 | medium=2, low=1, high=1 | interlink, optimize, refresh |
| 8 | How Copywriting Skills Can Improve Your Love  | 4 | high=4 | merge |
| 9 | Copywriting 101: How to Craft Compelling Copy | 3 | medium=1, low=1, high=1 | expand, merge, optimize |
| 10 | It’s the End of AdSense as We Know It (And I  | 3 | medium=2, low=1 | optimize, refresh |

## 10i. Sample Recommendations (One Per Type)

### expand

**Title:** Expand thin content: Copyblogger - Content marketing tools and training.
**Priority:** high | **Effort:** 2.0h | **Confidence:** high
**Summary:** This post has 186 words, which is below the 500-word threshold for default content. Expand to at least 2177 words to match cluster average.

**Actions:**
- Add 1991+ words of substantive content
- Research what top-ranking competitors cover that this post doesn't
- Add practical examples, case studies, or data points
- Consider adding an FAQ section addressing related questions

### optimize

**Title:** Add meta description: 5 Steps to Pay Per Click Advertising That Works
**Priority:** medium | **Effort:** 0.25h | **Confidence:** high
**Summary:** This post has no meta description. Google will auto-generate one, which is often suboptimal for CTR.

**Actions:**
- Write a 150-160 character meta description
- Include the primary keyword naturally
- Add a compelling reason to click (number, benefit, or question)
- Match search intent

### refresh

**Title:** Consider refreshing older content: 5 Steps to Pay Per Click Advertising That Wor
**Priority:** low | **Effort:** 0.5h | **Confidence:** low
**Summary:** This post hasn't been updated in 19.8 years. Periodic content refreshes maintain relevance and prevent gradual ranking decay.

**Actions:**
- Update the published/modified date after making substantive edits
- Check for outdated references, broken links, or stale examples
- Add a recent example, statistic, or data point
- Verify all external links still work

### update

**Title:** Refresh stale content: Aristotle’s Top 3 Tips for Effective Blogging
**Priority:** medium | **Effort:** 1.0h | **Confidence:** low
**Summary:** This post hasn't been updated in 19.6 years. AI citation risk: AI systems actively replace older sources with fresher competitors.

**Actions:**
- Update the 'Last updated' date after substantive edits
- Refresh statistics older than 6 months
- Add 1-2 new insights or data points
- Check the opening still answers the primary query

### merge

**Title:** Merge overlapping content: Link Building Strategies for SEO: A Complete Guide
**Priority:** high | **Effort:** 2.0h | **Confidence:** high
**Summary:** Same subtopics covered (cosine=0.848, severity=critical). Combine into stronger post.

**Actions:**
- Compare both posts section by section
- Move unique content from 'Copyblogger - Content marketing tools an' into 'Link Building Strategies f
- 301 redirect the merged post
- Update internal links

### interlink

**Title:** Fix orphan: Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers
**Priority:** high | **Effort:** 0.5h | **Confidence:** high
**Summary:** No inbound links. Link from 1 related posts.

**Actions:**
- This post has 0 inbound internal links.
- Add a contextual link from these relevant posts:
- Link from "Copyblogger - Content marketing tools and training." (similarity: 0.43)
- Use descriptive anchor text, not generic 'click here'.

## Processing Summary

| Sub-step | Recs | Time | External API | Notes |
|----------|------|------|-------------|-------|
| 10a. Problem-based templates | 75 | 0.0ms | None | 11 templates |
| 10b. Cannibalization recs | 33 | 0.0ms | None | redirect/merge/differentiate |
| 10c. Orphan link suggestions | 13 | 11.3ms | None | cosine similarity |
| 10d. Claude enrichment (Tier 2) | SKIPPED | - | Anthropic API | Crawl-only mode |
| **Total Step 10** | **121** | **11.3ms** | **Free** | |

### Prerequisite Timings

| Step | Time | Notes |
|------|------|-------|
| Crawl (Code Step 1) | 99.1s | |
| Clustering (Code Step 6) | 35.9s | |
| readability | 613.4ms | |
| cannibalization | 12.3ms | |
| seo_issues | 11.3ms | |
| proxy_decay | 1.5ms | |
| orphan_detection | 1.0ms | |
| thin_content | 0.6ms | |

## Observations

- **121 total recommendations** generated from 407 problems, 373 cannibalization pairs, and 148 orphan posts
- **Template coverage: 10/10 problem types** have matching templates
- **Deduplication removed 82%** of problem->rec mappings (one rec per post per type)
- **Total estimated effort: 131 hours** (3.3 work weeks)
- **High-priority recs: 51** (82 hours) — action first
- **Most common recommendation type:** `optimize` (39 recs)
- **Recommendation generation completed in 11ms** — zero API calls, zero cost (Tier 1 only)
- **Claude enrichment (Tier 2) skipped** — would add AI-generated strategic advice to top 10 recs for ~$0.02
- Synthetic embeddings produce different cannibalization pairs than real OpenAI embeddings — use results as structural validation only

## Data Quality Notes

| Factor | Impact | Notes |
|--------|--------|-------|
| Synthetic embeddings | High | Cannibalization pairs and orphan link suggestions differ from real OpenAI embeddings |
| No GA4/GSC data | Medium | Cannot detect traffic-based decay or performance-based cannibalization severity |
| No AI citability scores | Medium | GEO-related templates (low_ai_citability, weak_eeat, etc.) not triggered |
| No database | Low | Template logic, priority assignment, and effort estimation are identical to production |
| Crawl-only mode | Low | Problem detection uses same thresholds as production |
