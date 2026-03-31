# Pipeline Step 9: Problem Detection

> **Scope:** Everything that happens after Step 8 (cannibalization detection + chunk confirmation + role patching) and before Step 10 (recommendations). This step scans all posts for a site and flags content problems: decay, thin content, SEO issues, orphan pages, readability issues, publishing velocity decline, and AI readiness gaps. No recommendations, no actions — just diagnosis. Problems are idempotent: re-running clears and re-detects, preserving `first_detected_at` for continuing problems.

---

## Pipeline Position

After Step 8 stores cannibalization pairs in `cannibalization_pairs` and Step 8c patches roles post-cannibalization, the full pipeline runs problem detection:

```
Step 1: Crawl + Normalize (done)
Step 2: Embeddings (done)
Step 3: Readability Scoring (done)
Step 4: PageRank (done)
Step 5: Intent Classification (done)
Step 6: Clustering (UMAP + HDBSCAN) (done)
Step 6b: TF-IDF Cluster Labels (done)
Step 6c: AI Citability Scoring (done)
Step 7: Health Scoring (done)
Step 8: Cannibalization Detection (done)
Step 8b: Chunk Confirmation (done, optional)
Step 8c: Role Patch (done)
   |
Step 9.0: Data availability detection (GA4/GSC counts)              <- DB reads, <0.1s
Step 9.1: Preserve existing problem fingerprints (first_detected_at) <- DB read
Step 9.2: Clear old problems (idempotent DELETE)                    <- DB write
Step 9.3: Content decay detection (3 signals, needs GSC)            <- DB queries
Step 9.3+: Proxy decay detection (3 signals, crawl-based)           <- DB queries
Step 9.4: Thin content detection (3 checks, GA4 optional)           <- DB queries
Step 9.5: SEO issue detection (5 checks, fully crawl-based)         <- DB queries
Step 9.6: Orphan detection (crawl-based)                            <- DB queries
Step 9.7: Readability issues (industry-adaptive thresholds)         <- DB queries
Step 9.8: Velocity decline detection (sites table)                  <- DB queries
Step 9.9: AI readiness issues (ai_citability scores)                <- DB queries
Step 9.10: Related problem grouping                                  <- DB read+write
   |
Step 10: Recommendations (next pipeline step)
```

Each sub-step is independently error-handled via `try/except` — a failure in one detector doesn't kill subsequent ones. Partial results > no results.

### Step Mapping: Spec vs Code

The spec documents use Steps 1-7. The code in `ingestion.py:_run_full_pipeline` uses Steps 1-10b. This table maps between the two:

| Spec Step | Code Step | Service |
|-----------|-----------|---------|
| Step 1 | Step 1 | Crawl + Normalize |
| Step 2a | Step 2 | Embeddings |
| Step 2b | Step 3 | Readability |
| Step 2c | Step 4 | PageRank |
| Step 2d | Step 5 | Intent Classification |
| Step 3 | Step 6 | Clustering |
| Step 3h | Step 6b | TF-IDF Cluster Labels |
| (none) | Step 6c | AI Citability |
| Step 4 | Step 7 | Health Scoring |
| Step 5 | Step 8 | Cannibalization |
| (none) | Step 8b | Chunk Confirmation (optional) |
| (none) | Step 8c | Role Patch (post-cannibalization) |
| **Step 6** | **Step 9** | **Problem Detection (this document)** |
| Step 7 | Step 10 | Recommendations |
| (none) | Step 10b | Claude Enrichment (optional) |

In the full pipeline (`ingestion.py:_run_full_pipeline`), Step 9 maps to:
- **Code Step 9:** `ProblemDetector().detect_all(db, site_id)` — runs 9.0 through 9.10

### Progress Reporting

Unlike clustering (which reports sub-step progress via `on_progress` callback), problem detection has **no progress reporting**. The pipeline step label is set to `"problem_detection"` / `"analyzing"` in `crawl_jobs.current_step`, but no sub-step updates are emitted. This is acceptable because problem detection is fast (typically < 2 seconds for 150 posts).

---

## 9.0 Data Availability Detection (Graceful Degradation)

### What It Does

Before running any checks, the detector probes the database for GA4 and GSC data availability. This allows graceful degradation — the system works on crawl-only data from day one, adding richer signals as GA4/GSC are connected.

### Queries

```sql
-- Check GA4 data
SELECT COUNT(*) FROM ga4_metrics
WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1) LIMIT 1

-- Check GSC data
SELECT COUNT(*) FROM gsc_metrics
WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1) LIMIT 1
```

### Impact on Detection

| Detector | No Data | GA4 Only | GSC Only | Both |
|----------|---------|----------|----------|------|
| Content Decay (3 GSC signals) | SKIP | SKIP | RUN | RUN |
| Proxy Decay (3 crawl signals) | RUN | RUN | RUN (+ real decay) | RUN (+ real decay) |
| Thin: Absolute | RUN | RUN | RUN | RUN |
| Thin: Below cluster avg | RUN | RUN | RUN | RUN |
| Thin: High bounce | SKIP | RUN | SKIP | RUN |
| SEO Issues (4 checks)** | RUN | RUN | RUN | RUN |
| SEO: No internal links** | GATE | GATE | GATE | GATE |
| Orphan Detection** | GATE | GATE | GATE | GATE |
| Readability Issues | RUN | RUN | RUN | RUN |
| Velocity Decline | RUN | RUN | RUN | RUN |
| AI Readiness Issues* | RUN* | RUN* | RUN* | RUN* |

*AI readiness runs only if AI citability scores have been computed (Step 6c).

**Quality gate: Orphan detection and `seo_no_internal_links` are gated behind a link resolution rate check. If < 20% of outbound internal links resolve to crawled posts (typical on capped crawls), both checks are skipped to prevent inflated false positives. On a full crawl, the gate passes and both checks run normally.

**First-run profile (crawl only, no GA4/GSC, full crawl):** 9 of 11 detectors run. Content decay (GSC) and thin_high_bounce (GA4) are skipped. On a capped crawl, orphan + no_internal_links are also gated, leaving 7 of 11.

---

## 9.1 Preserve Problem Fingerprints

### What It Does

Before clearing old problems, the detector saves `first_detected_at` timestamps for each `(post_id, problem_type)` pair. When a problem is re-detected on the next run, this timestamp carries forward, preserving the "how long has this been a problem?" signal for the frontend.

```python
existing_problems = await db.fetch("""
    SELECT post_id, problem_type, first_detected_at
    FROM content_problems WHERE site_id = $1
""", site_id)

first_detected_map: dict[tuple, datetime] = {}
for ep in existing_problems:
    key = (str(ep["post_id"]), ep["problem_type"])
    if ep["first_detected_at"]:
        first_detected_map[key] = ep["first_detected_at"]
```

### Why This Matters

A problem that's existed for 6 months is more urgent than one detected yesterday. The frontend can use `first_detected_at` to prioritize long-standing issues. Without this preservation, every pipeline re-run would reset all problems to "just detected."

---

## 9.2 Clear Old Problems (Idempotent)

```sql
DELETE FROM content_problems WHERE site_id = $1
```

This makes problem detection fully idempotent — every run produces a complete fresh set of problems. The `first_detected_at` preservation in 9.1 means continuity is maintained despite the full clear.

---

## 9.3 Content Decay Detection (GSC-Dependent)

### What It Does

Detects posts whose search performance is declining. Uses three independent signals, each producing a different severity level.

### Signal 1: Traffic/Click Decline (90-day comparison)

Compares clicks in the last 90 days vs the previous 90 days. Only flags posts where the previous period had > 10 clicks (ignores low-traffic content).

| Metric | Threshold | Problem Type | Severity |
|--------|-----------|-------------|----------|
| Click decline > 60% | `recent_clicks < prev * 0.4` | `decay_severe` | high |
| Click decline > 30% | `recent_clicks < prev * 0.7` | `decay_moderate` | medium |

### Signal 2: Stale + Low Ranking

Posts that haven't been updated in 12+ months AND currently rank page 2+ (position > 10).

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| modified_date < 12 months ago AND avg_position > 10 | `decay_mild` | medium |

### Signal 3: Position Drop

Posts that historically ranked top 5 but now rank 10+.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| Best ever position <= 3 AND current position > 20 | `decay_severe` | high |
| Best ever position <= 5 AND current position > 10 | `decay_moderate` | medium |

### Proxy Decay (Crawl-Only Fallback — Always Runs)

Proxy decay runs regardless of GSC status — it's the crawl-only fallback, not a GSC supplement. Posts already flagged by GSC-based decay are skipped (queried from `content_problems` after GSC detection runs).

Uses three independent signals:

1. **Outdated year references:** Title contains a year 2+ years in the past (regex: `(19|20)\d{2}`, runtime-checked against `current_year - 1`). Catches years like 2007, 2015, 2022. → `decay_severe`
2. **Time-sensitive stale content:** Title contains "best", "top", "review", "pricing", "compare", "vs" AND not updated in 18+ months → `decay_moderate`
3. **General staleness:** Any post not updated in 18+ months that wasn't caught by signals 1-2 → `decay_mild` (medium severity)

The proxy field `{"proxy": True}` in details distinguishes these from GSC-backed decay detections.

---

## 9.4 Thin Content Detection

### What It Does

Flags posts that are too short to provide adequate value, using three complementary checks with content-type-aware thresholds.

### Check 1: Absolute Thin Content (Content-Type Aware)

Not all content needs to be 2000 words. The threshold adapts based on URL/title keywords:

| Content Type | URL/Title Keywords | Threshold | Rationale |
|-------------|-------------------|-----------|-----------|
| Comparison | `/compare`, `/vs-`, `comparison` | 500 words | Tables + comparison data are dense |
| Tutorial/Guide | `how-to`, `guide`, `tutorial`, `step-by-step`, `ultimate`, `complete`, `definitive`, `checklist` | 800 words | Tutorials need depth |
| Glossary/Definition | `/glossary`, `what-is`, `definition` | 200 words | Definitions should be concise |
| Default | (everything else) | 500 words | Standard blog content minimum |

**Multi-signal gate:** A post below the word count threshold is NOT flagged if it has:
- 2+ H2/H3 headings AND
- Images (detected in body_html) AND
- 5+ inbound internal links

This prevents false positives on well-structured visual content (infographics, short guides with images).

| Word Count vs Threshold | Severity |
|------------------------|----------|
| < 50% of threshold | `high` |
| 50-100% of threshold | `medium` |

### Check 2: Below Cluster Average

Flags posts whose word count is < 50% of their cluster's average, BUT only when:
- Post word count < 800 words (avoids flagging 3000-word posts in a 7000-word cluster)
- Cluster average > 1500 words (avoids flagging in clusters of naturally short content)

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| word_count < cluster_avg * 0.5 AND word_count < 800 AND cluster_avg > 1500 | `thin_below_cluster_avg` | medium |

### Check 3: High Bounce + Low Engagement (GA4 Required)

Flags posts where users leave quickly, indicating the content isn't meeting expectations.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| avg_bounce_rate > 80% AND avg_engagement_time < 30s | `thin_high_bounce` | high |

---

## 9.5 SEO Issue Detection (5 Checks)

### What It Does

Checks each post for basic on-page SEO issues. Fully crawl-based — no external data needed.

### Check 1: Missing Meta Description

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| No meta description OR length < 10 chars | `seo_missing_meta` | medium |

### Check 2: Title Length

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| Title < 20 chars (likely truncated/broken) | `seo_title_length` | medium |
| Title > 70 chars (cut off in SERPs) | `seo_title_length` | low |

Note: 60-70 is intentionally allowed for descriptive SaaS titles. Only truly problematic lengths are flagged.

### Check 3: No H2+ Headings

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| No H2, H3, or H4 headings in content | `seo_no_headings` | medium |

### Check 4: No Internal Links

**Quality gate:** This check is skipped when the internal link resolution rate is below 20% (capped crawl protection). On a capped crawl (e.g., 150 of 3000 URLs), most link targets don't exist in the dataset, inflating false positives to near 100%. The resolution rate is computed before running any link-dependent checks.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| Zero internal links to OR from the post (link resolution >= 20%) | `seo_no_internal_links` | high |

### Check 5: No Images

Multiple image patterns are checked: `<img>`, `<picture>`, `<figure>`, `<svg>`, `data-src=`, `srcset=`, `background-image:`, `loading="lazy"`.

**Trafilatura XML bypass:** If body_html starts with `<doc` (trafilatura XML output), the image check is skipped entirely — trafilatura strips all media elements so we can't determine image presence. No false positive is created.

**Body length gate:** Only flags posts with `body_html > 200 chars` — avoids flagging stub pages.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| No image patterns in body_html (not trafilatura, body > 200 chars) | `seo_no_images` | low |

---

## 9.6 Orphan Content Detection

### What It Does

Flags posts with zero inbound internal links — these are invisible to both users and search engines following the site's internal link graph.

**Quality gate:** Orphan detection is skipped entirely when internal link resolution rate is below 20%. This prevents false positives on capped crawls where most link targets fall outside the crawled dataset. The same gate protects `seo_no_internal_links` in Step 9.5.

```sql
SELECT p.id, p.title FROM posts p
WHERE p.site_id = $1
  AND (p.word_count IS NULL OR p.word_count >= 200)
  AND NOT EXISTS (
      SELECT 1 FROM internal_links il WHERE il.target_post_id = p.id
  )
```

**Why the 200-word filter:** Pages under 200 words are likely index/hub/tool pages that don't need inbound links. Only content pages (200+ words) are checked.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| Zero inbound links AND word_count >= 200 (link resolution >= 20%) | `orphan` | high |

---

## 9.7 Readability Issues (Industry-Adaptive)

### What It Does

Flags posts with poor readability using industry-adaptive Flesch Reading Ease thresholds. A B2B SaaS blog legitimately needs more complex language than a consumer lifestyle blog.

### Industry Detection

Uses `industry_benchmarks.detect_industry()` which scores cluster labels against keyword lists. The agency category includes marketing/SEO keywords (`"seo"`, `"content marketing"`, `"copywriting"`, `"blogging"`, `"content strategy"`) so content marketing blogs are classified as agency (Flesch threshold 35) rather than defaulting to 50.

```python
industry = detect_industry(cluster_labels, [])
```

### Thresholds

| Industry | Flesch Threshold | Rationale | Example Sites |
|----------|-----------------|-----------|--------------|
| SaaS | < 35 | Technical audience expects complexity | HubSpot, Intercom |
| Agency | < 35 | Professional audience (incl. SEO/content marketing blogs) | Copyblogger, Backlinko |
| Ecommerce | < 50 | General consumer audience | Shopify blog |
| Media | < 55 | Broad audience needs accessibility | TechCrunch |
| Default | < 50 | Standard threshold | General blogs |

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| Flesch < 30 | `readability_too_complex` | high |
| Flesch < threshold (>= 30) | `readability_too_complex` | medium |

Research context: 63% of top-ranking content scores 60-80 on the Flesch scale.

---

## 9.8 Velocity Decline Detection

### What It Does

Detects if the site's publishing velocity has dropped significantly, creating a single site-level problem (attached to the most recent post). Includes peak velocity period for context (e.g., "peaked at 2.3 posts/week in 2019").

Peak velocity is computed as the best publishing year by post count, converted to weekly rate.

| Condition | Problem Type | Severity |
|-----------|-------------|----------|
| `velocity_trend = 'declining'` on sites table | `velocity_decline` | medium |

Research context: Consistent publishing (3+/week) drives 3.5x more traffic. Slowed publishing correlates with 25-40% traffic decline within 60 days.

---

## 9.9 AI Readiness Issues

### What It Does

Detects AI-era SEO problems: low citability, weak E-E-A-T, missing schema, poor extraction structure, and GEO-specific issues. Only runs if AI citability scores have been computed by Step 6c.

Uses `generate_ai_problems()` from `ai_citability.py` which checks each post's scores:

| Score Check | Threshold | Problem Type | Severity |
|------------|-----------|-------------|----------|
| AI Citability < 40 | < 20: high, < 40: medium | `low_ai_citability` | high/medium |
| E-E-A-T < 40 | < 20: high, < 40: medium | `weak_eeat` | high/medium |
| Schema < 30 | -- | `missing_schema` | medium |
| Extraction < 40 | -- | `poor_ai_structure` | medium |
| No FAQ section | -- | `geo_no_faq_section` | medium |

### GEO-Specific Problem Types

These are 2026 Generative Engine Optimization signals:

| Problem Type | Detection Logic |
|-------------|----------------|
| `geo_no_faq_section` | No FAQ section detected |
| `geo_no_data_tables` | No data tables in content |
| `geo_no_experience_markers` | No first-person experience signals |
| `geo_no_question_headers` | No question-format H2/H3 headers |
| `geo_low_data_density` | Low density of stats/data points |
| `geo_no_answer_first` | Primary query not answered in first 200 words |
| `geo_missing_faq_schema` | No FAQPage JSON-LD schema |
| `geo_no_freshness_date` | No visible date/update signal |

---

## 9.10 Related Problem Grouping & Deduplication

### What It Does

After all detectors run, the system deduplicates and groups related problems on the same post. Two strategies are used:

**Suppress groups:** When both problems functionally represent the same issue with the same customer action, the secondary problem is **deleted** entirely. This prevents double-counting in headline issue totals.

**Mark groups:** When problems are related but represent distinct actionable items, the secondary is kept but annotated with `details.related_to` pointing to the root.

### Groups

| Group | Problem Types | Root | Strategy | Rationale |
|-------|--------------|------|----------|-----------|
| Orphan cluster | `seo_no_internal_links` + `orphan` | `orphan` | **SUPPRESS** (delete secondary) | Same action: add internal links. "Orphan" subsumes "no internal links." |
| Thin cluster | `thin_content` + `thin_below_cluster_avg` | `thin_content` | **MARK** (annotate) | Related but different: one is absolute, the other is relative to cluster. |

Suppressed problem counts are subtracted from `counts["seo"]` so the logged summary accurately reflects the final DB state.

---

## Problem Type Weights (Severity Scoring)

Each problem type has a weight used to compute a `severity_score` (0-100) stored in the details JSON. The "most problematic posts" ranking in the audit report and API sorts by sum of these weights, not raw problem count.

### Traditional SEO Problems

| Problem Type | Weight | Severity Score |
|-------------|--------|---------------|
| `decay_severe` | 0.95 | 95 |
| `seo_missing_meta` | 0.9 | 90 |
| `decay_moderate` | 0.9 | 90 |
| `seo_no_internal_links` | 0.8 | 80 |
| `intent_mismatch` | 0.8 | 80 |
| `thin_content` | 0.7 | 70 |
| `decay_mild` | 0.7 | 70 |
| `velocity_decline` | 0.7 | 70 |
| `readability_too_complex` | 0.6 | 60 |
| `orphan` | 0.6 | 60 |
| `serp_opportunity_missed` | 0.6 | 60 |
| `seo_no_headings` | 0.5 | 50 |
| `thin_below_cluster_avg` | 0.5 | 50 |
| `seo_title_length` | 0.4 | 40 |
| `seo_no_images` | 0.3 | 30 |

### AI Readiness Problems

| Problem Type | Weight | Severity Score |
|-------------|--------|---------------|
| `missing_schema` | 0.9 | 90 |
| `low_ai_citability` | 0.85 | 85 |
| `weak_eeat` | 0.8 | 80 |
| `poor_ai_structure` | 0.7 | 70 |
| `geo_missing_faq_schema` | 0.7 | 70 |
| `geo_no_faq_section` | 0.6 | 60 |
| `geo_no_answer_first` | 0.6 | 60 |
| `geo_no_data_tables` | 0.5 | 50 |
| `geo_no_experience_markers` | 0.5 | 50 |
| `geo_no_question_headers` | 0.5 | 50 |
| `geo_low_data_density` | 0.5 | 50 |
| `geo_no_freshness_date` | 0.5 | 50 |

Problems not in either table default to weight 0.5 (score 50).

---

## Database Schema

```sql
CREATE TABLE content_problems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    problem_type TEXT NOT NULL,          -- see CHECK constraint below
    severity TEXT NOT NULL,              -- 'low', 'medium', 'high', 'critical'
    details JSONB DEFAULT '{}',          -- problem-specific metadata
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    first_detected_at TIMESTAMPTZ,       -- preserved across re-runs
    resolved_at TIMESTAMPTZ,
    UNIQUE (post_id, problem_type)       -- one problem per type per post
);
```

Allowed `problem_type` values (migration 037):
```
decay_mild, decay_moderate, decay_severe,
thin_content, thin_below_cluster_avg, thin_high_bounce,
seo_missing_meta, seo_title_length, seo_no_headings, seo_no_internal_links, seo_no_images,
orphan, cannibalization,
readability_too_complex,
low_ai_citability, weak_eeat, missing_schema, poor_ai_structure,
geo_no_faq_section, geo_no_data_tables, geo_no_experience_markers,
geo_no_question_headers, geo_low_data_density, geo_no_answer_first,
geo_missing_faq_schema, geo_no_freshness_date,
velocity_decline, intent_mismatch, serp_opportunity_missed
```

---

## Error Handling

Each detector call in `detect_all()` is wrapped in its own `try/except` block. If one detector crashes (e.g., malformed HTML in a post breaks `_detect_seo_issues()`), the exception is logged via `logger.exception()` and the count for that detector is set to 0. All subsequent detectors still run. This ensures partial results are returned rather than no results.

```python
# Example: thin content detector wrapped with fault isolation
try:
    counts["thin"] = await self._detect_thin_content(db, site_id, has_ga4=has_ga4)
except Exception:
    logger.exception("Thin content detection failed for site %s", site_id)
    counts["thin"] = 0
```

The related problem grouping step (`_group_related_problems`) is also wrapped — if deduplication fails, the raw problem set is preserved.

---

## Performance Characteristics

| Sub-step | Typical Time | Bottleneck |
|----------|-------------|-----------|
| Data availability detection | < 10ms | DB index scan |
| Preserve fingerprints | < 50ms | DB sequential scan |
| Clear old problems | < 10ms | DB index delete |
| Content decay (3 signals) | ~100ms | 3 complex CTEs with GSC joins |
| Proxy decay | ~50ms | DB scan + regex |
| Thin content (3 checks) | ~100ms | Cluster avg CTE + GA4 joins |
| SEO issues (5 checks) | ~200ms | Full post scan + subquery per post |
| Orphan detection | ~50ms | NOT EXISTS subquery |
| Readability issues | ~50ms | Industry detection + DB scan |
| Velocity decline | ~10ms | Single row lookup |
| AI readiness issues | ~100ms | Post scan + per-post score check |
| Related problem grouping | ~50ms | Group-by + updates |
| **Total** | **~0.5-1.5s** | **DB queries** |

The entire step is DB-bound. No CPU-heavy computation, no external API calls. For a 150-post site, problem detection completes in under 2 seconds.

---

## Testing Strategy (Crawl-Only)

Since problem detection is heavily DB-dependent, the E2E test in `test_step9_e2e.py` extracts the detection logic and runs it against crawled post data in memory. The test mirrors production behavior including quality gates, deduplication, industry detection, and all three proxy decay signals.

| Detector | Crawl-Only Testable | What's Simulated |
|----------|-------------------|-----------------|
| Thin content (absolute) | YES | Direct word_count check with content-type-aware thresholds |
| Thin content (cluster avg) | YES | Use clustering output for cluster averages |
| SEO: missing meta | YES | Check crawled meta_description |
| SEO: title length | YES | Check crawled title |
| SEO: no headings | YES | Check crawled headings (from posts.headings JSONB) |
| SEO: no internal links | GATED | Skipped if link resolution < 20% (capped crawl protection) |
| SEO: no images | YES | Check crawled body_html (trafilatura XML bypass + body length gate) |
| Orphan detection | GATED | Skipped if link resolution < 20% (capped crawl protection) |
| Proxy decay (3 signals) | YES | Year regex `(19|20)\d{2}` + time-sensitive + general staleness |
| Content decay (GSC) | NO | Needs GSC data |
| Thin: high bounce | NO | Needs GA4 data |
| Readability | YES | Flesch computed locally; industry-adaptive threshold via `detect_industry()` |
| Velocity decline | YES | Computed from publish_date distribution; includes peak velocity period |
| AI readiness | NO | Needs AI citability scores |
| Quality gate | YES | Computes link resolution rate, skips orphan/links when < 20% |
| Dedup | YES | Suppresses seo_no_internal_links when orphan co-exists on same post |

Additional test sections:
- **Severity Scores** — full weight table with counts per problem type
- **Top 10 by Weight Sum** — ranked by severity weight, not raw count
- **PDF Report Preview** — maps problems to PDF sections with generated text
- **Problem Density vs Metrics** — cross-references problem count with word count, headings, and composite score
- **first_detected_at** — documents preservation mechanism

This gives ~80% coverage on crawl-only data. Only GSC decay, GA4 bounce, and AI readiness require external data.

---

## Implementation Reference

### Source Files

| File | Purpose |
|------|---------|
| `backend/app/services/problem_detection.py` | `ProblemDetector` class — all detection logic |
| `backend/app/services/ai_citability.py` | `generate_ai_problems()` — AI readiness issue generation |
| `backend/app/services/industry_benchmarks.py` | `detect_industry()` — industry classification for readability thresholds |
| `backend/app/routers/ingestion.py:_run_full_pipeline` | Pipeline orchestration — calls `ProblemDetector().detect_all()` at Step 9 |
| `backend/scripts/test_step9_e2e.py` | E2E test script — crawl-only problem detection validation |
| `backend/migrations/001_initial_schema.sql` | `content_problems` table definition |

### Key Design Decisions

1. **Idempotent via DELETE + re-insert:** Rather than updating individual problems, the system clears all problems and re-detects from scratch. This is simpler and guarantees consistency, while `first_detected_at` preservation maintains temporal continuity.

2. **Quality gate for link-based checks:** Capped crawls (common in cold outreach: 150 of 3000 URLs) make link-based checks unreliable. The 20% resolution rate threshold prevents false positives.

3. **Content-type-aware thin thresholds:** A 400-word comparison table is not thin content. A 400-word "ultimate guide" is. Keyword matching in URL/title adapts thresholds per content type.

4. **Industry-adaptive readability:** Technical SaaS content legitimately needs complex language. A one-size-fits-all Flesch threshold would flag every developer tool blog.

5. **Proxy decay as crawl-only fallback:** New users won't have GSC connected on day one. Proxy decay (year references, staleness, time-sensitive keywords) provides immediate value with zero external dependencies.

6. **Severity weight scoring:** Raw problem count is misleading (5 low-severity issues ≠ 1 severe issue). The weight table enables meaningful prioritization in the audit report.
