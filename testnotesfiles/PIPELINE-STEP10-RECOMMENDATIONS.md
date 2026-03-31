# Pipeline Step 10: Recommendations

> **Scope:** Everything that happens after Step 9 (problem detection) and constitutes the final pipeline step. This step generates actionable recommendations from detected problems, cannibalization pairs, and orphan pages using deterministic templates (Tier 1, zero API calls) and optionally enriches the top 10 recommendations with Claude-generated strategic advice (Tier 2, ~$0.02). No new data discovery — just synthesis of all upstream signals into prioritized, actionable output.

---

## Pipeline Position

After Step 9 stores problems in `content_problems` and Step 8 stores pairs in `cannibalization_pairs`, the full pipeline runs recommendations:

```
Step 1:  Crawl + Normalize (done)
Step 2:  Embeddings (done)
Step 3:  Readability (done)
Step 4:  PageRank (done)
Step 5:  Intent Classification (done)
Step 6:  Clustering (UMAP + HDBSCAN) (done)
Step 6b: TF-IDF Cluster Labels (done)
Step 6c: AI Citability (done)
Step 7:  Health Scoring (done)
Step 8:  Cannibalization Detection (done)
Step 8b: Chunk Confirmation (optional) (done)
Step 9:  Problem Detection (done)
   |
Step 10a: Clear old recommendations (idempotent DELETE)                  <- DB write
Step 10b: Fetch all content_problems with post details                   <- DB read
Step 10c: Fetch cluster averages (word count context)                    <- DB read
Step 10d: Build post→cluster mapping                                     <- DB read
Step 10e: Template matching & rendering (21 problem templates)           <- CPU, <10ms
Step 10f: Cannibalization recommendations (redirect/merge/differentiate) <- DB read + CPU
Step 10g: Orphan link suggestions (pgvector similarity search)           <- DB read (HNSW)
Step 10h: Batch INSERT all recommendations                               <- DB write
Step 10i: [Optional] Claude enrichment of top 10 recs (Tier 2)          <- Anthropic API
   |
Pipeline Complete
```

Each sub-step is independently error-handled via `_pipeline_step()` — a failure in Claude enrichment (Step 10i) doesn't block template-based recommendations.

### Step Mapping: Spec vs Code

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
| Step 6 | Step 9 | Problem Detection |
| **Step 7** | **Step 10** | **Recommendations (this document)** |
| (none) | Step 10b | Claude Enrichment (optional) |

In the full pipeline (`ingestion.py:_run_full_pipeline`), Step 10 maps to:
- **Code Step 10:** `generate_fast_recommendations(db, site_id)` — runs 10a through 10h
- **Code Step 10b:** `auto_enrich_top_recs(db, site_id)` — runs 10i (Claude enrichment, optional)

---

## Input Data Sources

Recommendations synthesize signals from every upstream pipeline step:

| Source | Table | What's Used | Required? |
|--------|-------|------------|-----------|
| Problem detection (Step 9) | `content_problems` | problem_type, severity, details JSON | YES |
| Posts (Step 1) | `posts` | title, word_count, url, readability_score, content_intent, language | YES |
| Clusters (Step 6) | `clusters` + `post_clusters` | cluster label, avg word count per cluster | YES |
| Cannibalization (Step 8) | `cannibalization_pairs` | post pairs, cosine_similarity, severity, cluster_id | YES |
| Embeddings (Step 2) | `post_embeddings` | embedding vectors for orphan link similarity | YES (for orphan recs) |
| Internal links (Step 1) | `internal_links` | source/target for orphan detection | YES (for orphan recs) |

---

## Sub-Step Details

### 10a. Clear Old Recommendations

```sql
DELETE FROM recommendations WHERE site_id = $1
```

Idempotent — re-running the pipeline produces a fresh set of recommendations every time. No historical tracking (unlike `content_problems` which preserves `first_detected_at`).

### 10b. Fetch Problems with Post Details

Joins `content_problems` with `posts` to get full context for template rendering. Filters out very short pages (<100 words) — these are tool pages, redirects, or index pages that don't warrant content recommendations.

Ordered by severity (critical → high → medium → low), then by problem_type for deterministic output.

### 10c–10d. Cluster Context

Fetches per-cluster average word count (used by `thin_content` and `thin_below_cluster_avg` templates to set expansion targets). Builds a `post_id → (cluster_id, cluster_label, avg_word_count)` mapping.

### 10e. Template Matching & Rendering (Tier 1)

The core of the recommendation engine. 23 templates mapped to problem types:

| Template Key | Rec Type | Problem Type | Priority Logic | Effort (hrs) |
|-------------|----------|-------------|---------------|-------------|
| `thin_content` | expand | thin_content | high if <300w, else medium | 2.0 |
| `thin_below_cluster_avg` | expand | thin_below_cluster_avg | medium if >500w, else high | 1.5 |
| `seo_title_length` | optimize | seo_title_length | low | 0.25 |
| `seo_missing_meta` | optimize | seo_missing_meta | medium | 0.25 |
| `seo_no_images` | optimize | seo_no_images | low | 0.5 |
| `readability_too_complex` | optimize | readability_too_complex | medium | 1.0 |
| `orphan` | interlink | orphan | high | 0.5 |
| `decay_severe` | update | decay_severe | high | 2.0 |
| `decay_moderate` | update | decay_moderate | medium | 1.0 |
| `low_ai_citability` | improve_ai_citability | low_ai_citability | high if <20, else medium | 2.0 |
| `weak_eeat` | strengthen_eeat | weak_eeat | high if <20, else medium | 1.0 |
| `missing_schema` | add_schema | missing_schema | high | 0.5 |
| `poor_ai_structure` | improve_ai_structure | poor_ai_structure | medium | 1.5 |
| `geo_no_faq_section` | add_faq_section | geo_no_faq_section | medium | 1.0 |
| `geo_no_question_headers` | reformat_headers_geo | geo_no_question_headers | medium | 0.5 |
| `geo_low_data_density` | increase_data_density | geo_low_data_density | medium | 1.5 |
| `geo_no_answer_first` | add_answer_first | geo_no_answer_first | medium | 0.5 |
| `geo_missing_faq_schema` | add_faq_schema | geo_missing_faq_schema | high | 0.5 |
| `geo_no_updated_date` | add_freshness_signal | geo_no_updated_date | low | 0.25 |
| `decay_mild` | refresh | decay_mild | low | 0.5 |
| `seo_no_headings` | optimize | seo_no_headings | medium | 0.5 |

Each template produces:
- **title**: Formatted from `title_tpl` with post context
- **summary**: Static (`summary_tpl`) or dynamic (`summary_fn`) explanation
- **actions**: 3-5 specific action items with context-aware formatting
- **priority**: Computed by `priority_fn` using problem details
- **effort_hours**: Fixed estimate per template
- **confidence**: high (objective issues like thin/orphan/schema), medium (contextual), low (structural)

**Deduplication:** One recommendation per `(post_id, problem_type)` pair. If a post has the same problem type flagged multiple times, only the first is processed.

### 10f. Cannibalization Recommendations

Reads pre-computed pairs from `cannibalization_pairs` (populated by Step 8's 5-signal blended scoring) and generates one recommendation per actionable pair. Uses Step 8's `resolution` column directly — no re-computation of thresholds.

| Step 8 Resolution | Action | Priority | Effort | Rec Type |
|-------------------|--------|----------|--------|----------|
| `redirect` | 301 redirect weaker -> stronger | critical/high | 0.5h | merge |
| `merge` | Combine unique sections, then redirect | high/medium | 2.0h | merge |
| `differentiate` | Refocus each on a distinct angle | medium | 1.5h | differentiate |
| `monitor` | Skipped — not actionable | — | — | — |

**Key fields from Step 8:** `resolution` (action type), `severity` (mapped to priority), `stronger_post_id` (which post to keep), `severity_score` (numeric 0-100 blended score).

**Stronger post selection:** Uses Step 8's `stronger_post_id` which is computed from health score (30%) + traffic percentile (70%), or health score alone in crawl-only mode.

**Filters:** Word count >= 100 on both posts; same-language pairs only; deduplication via normalized pair keys.

**AI content metadata:** Each cannibalization rec stores cluster_id, both URLs, cosine similarity, resolution, and severity_score in `ai_generated_content` JSON for the frontend consolidation flow.

### 10g. Orphan Link Suggestions (pgvector RAG)

For each orphan post (no inbound internal links), uses pgvector HNSW index to find the 5 most semantically similar posts that already have inbound links. These become suggested link sources.

Each orphan recommendation includes:
- The orphan post's title and URL
- Top 3 link source suggestions with similarity scores
- Suggested anchor text (derived from orphan title)

**Stored in `ai_generated_content`:** Full link_targets array with post_id, title, URL, similarity score, and suggested anchor text — used by the frontend to render one-click "Add link" actions.

**Limit:** Max 20 orphan posts processed per site (prevents timeout on very large sites).

### 10h. Batch INSERT

All recommendations are inserted in a single `executemany` call with `ON CONFLICT DO NOTHING` for idempotency.

### 10i. Claude Enrichment (Tier 2, Optional)

After template-based recommendations are stored, the pipeline optionally calls `auto_enrich_top_recs()` to:
1. Fetch the top 10 recommendations by priority
2. Send each to Claude (Sonnet) with post context
3. Store Claude's strategic advice in `ai_generated_content`

**Cost:** ~$0.02 per site (10 recs x ~200 tokens each)
**Model:** claude-sonnet-4-20250514
**Non-fatal:** If enrichment fails, template-based recommendations remain intact.

---

## Output Schema

Recommendations are stored in the `recommendations` table:

```sql
CREATE TABLE recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    problem_id UUID REFERENCES content_problems(id) ON DELETE SET NULL,
    recommendation_type TEXT NOT NULL,  -- expand, optimize, interlink, merge, differentiate, update, add_schema, ...
    priority TEXT NOT NULL,            -- critical, high, medium, low
    estimated_effort_hours FLOAT,
    estimated_impact TEXT,             -- high, medium, low
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    specific_actions JSONB NOT NULL DEFAULT '[]',
    ai_generated_content JSONB DEFAULT '{}',
    confidence TEXT,                   -- high, medium, low
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, in_progress, completed, dismissed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Recommendation Types (from migration 037)

```
merge, refresh, optimize, delete, expand, interlink, growth,
differentiate, redirect, update,
add_schema, improve_ai_citability, strengthen_eeat, improve_ai_structure,
add_faq_section, reformat_headers_geo, increase_data_density,
add_answer_first, add_faq_schema, add_freshness_signal
```

---

## Confidence Scoring

| Confidence | Problem Types | Rationale |
|-----------|--------------|-----------|
| high | thin_content, seo_missing_meta, orphan, missing_schema, seo_no_images, seo_title_length | Objectively measurable (word count, presence/absence) |
| medium | readability_too_complex, thin_below_cluster_avg, improve_ai_citability, poor_ai_structure | Context-dependent (thresholds, cluster averages) |
| low | All others | Structural suggestions, subjective assessment |

Cannibalization recommendations use: high if cosine >= 0.85, else medium.
Orphan recommendations: always high (orphan detection is 100% objective).

---

## Template Architecture

### Static vs Dynamic Templates

Templates use two rendering strategies:

**Static templates** (`summary_tpl` + `actions_tpl`): Simple `str.format()` with a context dict. Used when the recommendation text is predictable from the problem type alone.

```python
"summary_tpl": "This post has {word_count} words, which is below the {threshold}-word threshold."
```

**Dynamic templates** (`summary_fn` + `actions_fn`): Lambda functions that receive the full context dict and return conditional text. Used when the recommendation varies based on details (e.g., title too short vs too long).

```python
"summary_fn": lambda d: (
    f"Title is only {d['title_length']} characters..."
    if d.get("title_length", 50) < 30
    else f"Title is {d['title_length']} characters..."
)
```

### Context Dict

Every template receives a context dict with these fields:

| Field | Source | Used By |
|-------|--------|---------|
| `title` | posts.title (truncated to 80 chars) | All templates |
| `word_count` | posts.word_count | thin_content, thin_below_cluster_avg |
| `url` | posts.url | All templates |
| `threshold` | problem details or default 500 | thin_content |
| `content_type` | posts.content_intent or "general" | thin_content |
| `target_words` | max(cluster_avg, threshold) | thin_content |
| `words_needed` | max(0, cluster_avg - word_count) | thin_content, thin_below_cluster_avg |
| `cluster_avg` | cluster avg word count | thin_below_cluster_avg |
| `title_length` | len(posts.title) | seo_title_length |
| `readability_score` | posts.readability_score | readability_too_complex |
| `citability_score` | problem details | low_ai_citability |
| `eeat_score` | problem details | weak_eeat |
| `schema_score` | problem details | missing_schema |
| `extraction_score` | problem details | poor_ai_structure |

### Priority Functions

Each template defines a `priority_fn` that receives the context dict and returns a priority string:

| Priority | Meaning | Templates |
|---------|---------|-----------|
| critical | Near-identical duplicates (cos >= 0.99) | Cannibalization only |
| high | Actionable, high-impact fixes | thin_content (<300w), orphan, decay_severe, missing_schema, low_ai_citability (<20), weak_eeat (<20) |
| medium | Important but less urgent | Most templates |
| low | Nice-to-have optimizations | seo_title_length, seo_no_images, geo_no_updated_date |

---

## Performance Characteristics

| Sub-step | Time | API Calls | Cost |
|----------|------|-----------|------|
| Clear old recs | <1ms | 0 | Free |
| Fetch problems + context | 5-20ms | 0 | Free |
| Template matching (21 templates) | <10ms | 0 | Free |
| Cannibalization recs | 5-15ms | 0 | Free |
| Orphan link suggestions (pgvector) | 50-200ms | 0 | Free |
| Batch INSERT | 10-50ms | 0 | Free |
| **Total Tier 1** | **~100-300ms** | **0** | **Free** |
| Claude enrichment (Tier 2) | 3-10s | 10 | ~$0.02 |

---

## Crawl-Only Mode (No Database)

When running without a database (E2E test mode), recommendations can be generated locally by:
1. Using in-memory problem detection results from Step 9
2. Using in-memory cannibalization pairs from Step 8
3. Using in-memory embeddings for orphan similarity (cosine similarity, no HNSW)
4. Skipping the DB INSERT step
5. Skipping Claude enrichment

This tests the template matching logic, priority assignment, effort estimation, and action generation without any external dependencies.

---

## Code Location

| File | What |
|------|------|
| `app/services/fast_recommendations.py` | Tier 1 template engine (21 templates, cannibalization recs, orphan recs) |
| `app/services/on_demand_enrichment.py` | Tier 2 Claude enrichment (`auto_enrich_top_recs`) |
| `app/routers/ingestion.py` | Pipeline orchestration (calls Step 10 + 10b) |
| `backend/scripts/test_step10_e2e.py` | E2E test (crawl-only, no DB) |

---

## Downstream Consumers

Recommendations are consumed by:

| Consumer | What It Uses | How |
|----------|-------------|-----|
| Dashboard `QuestsPanel.tsx` | All recs, sorted by priority | SWR fetch from `/v1/sites/{id}/recommendations` |
| PDF Report `pdf_report.py` | Top 10 recs by priority | Included in executive summary |
| Weekly Email `weekly_report.py` | New recs since last email | Summary of new recommendations |
| Consolidation Flow | Cannibalization recs with `ai_generated_content` | Frontend uses stored URLs + cosine for redirect downloads |

---

## GEO-Specific Templates (2026 AI-Era)

Six templates target AI citability and Generative Engine Optimization:

| Template | Signal | Why It Matters |
|---------|--------|----------------|
| `low_ai_citability` | AI Citability Score < threshold | Posts lacking signals AI systems use to select content for citation |
| `weak_eeat` | E-E-A-T Score < threshold | 96% of AI Overview citations come from high E-E-A-T content |
| `missing_schema` | No JSON-LD detected | Structured data makes content extractable by AI systems |
| `poor_ai_structure` | Low AI Extraction Score | Content doesn't front-load answers or use clear Q&A structure |
| `geo_no_faq_section` | No FAQ section | AI systems extract Q&A pairs directly from FAQ sections |
| `geo_no_question_headers` | Low question-header ratio | AI matches natural language prompts to question-format headers |
| `geo_low_data_density` | Few data points per 200 words | AI systems preferentially cite content with specific statistics |
| `geo_no_answer_first` | No TL;DR in first 200 words | AI extracts the first passage that directly answers a prompt |
| `geo_missing_faq_schema` | FAQ content without FAQPage schema | Structured FAQ schema makes Q&A directly extractable |
| `geo_no_updated_date` | No visible update timestamp | AI systems favor content with recent modification dates |

These templates are only triggered when Step 6c (AI Citability) and Step 9 (Problem Detection) detect the corresponding problems. In crawl-only mode without AI citability scoring, only the structural GEO checks are triggered.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Template format error (missing key) | Warning logged, rec skipped, other recs continue |
| No problems detected | Zero recs generated, no error |
| No cannibalization pairs | Cannibalization section returns 0 recs |
| No orphan posts | Orphan section returns 0 recs |
| pgvector query fails | Orphan recs skipped, problem recs intact |
| Claude enrichment fails | Tier 1 recs remain, `ai_generated_content` stays null |
| DB INSERT fails | Exception propagated to pipeline orchestrator |

---

## Idempotency

Step 10 is fully idempotent:
1. `DELETE FROM recommendations WHERE site_id = $1` clears all previous recs
2. Fresh recs generated from current upstream data
3. `ON CONFLICT DO NOTHING` handles any edge-case duplicates

Re-running the pipeline produces identical recommendations given identical upstream data.


THOUGHTS:

**Rating: 38/100**

I rated this 62/100 last time. That was too generous. Looking at it again after my recalibration, this step is fundamentally broken in ways that make the product unusable at $149/month. The recommendation engine is the final output — it's what the customer reads, what the PDF contains, what justifies the subscription. And right now it produces 664 recommendations where 56% are false positives, 20% are the single most common problem type with zero actionable output, and 3% suggest linking from pages with negative semantic similarity.

---

## CRITICAL — THE PRODUCT DOESN'T WORK

**S7-01/02/03: 373 cannibalization recommendations are false positives from a cosine-only scan that bypasses Step 8's blended scoring**

This is unchanged from my last review. The E2E confirms it:

Step 8 found **3 pairs** using the 5-signal blended scoring system (cosine 15%, slug 20%, entity+intent 25%, title topic 20%, H2 Jaccard 20%). The blended score filtered out 304 pairs (99% false-positive prevention rate). Step 8's output is stored in `cannibalization_pairs` with severity, resolution, and stronger_post already computed.

Step 10 ignores all of that. The spec explicitly describes its own cosine-only thresholds: "≥ 0.99 → 301 redirect, 0.90-0.99 → merge, < 0.90 → differentiate." The E2E shows 373 "differentiate" recommendations, all medium priority, all 1.5h effort. One post ("How a Few Measly Words Can Dramatically Improve Your Blog Headlines") appears in **48 separate cannibalization recommendations**.

A customer opening their dashboard sees: "You have 373 posts competing with each other." For a 145-post site, that's 2.6 cannibalization issues per post. The customer's reaction: "This tool thinks everything is cannibalizing everything. It doesn't understand my site."

The spec's Section 10f says it "fetches all cannibalization pairs from `cannibalization_pairs`" — but the resolution logic uses raw cosine thresholds, not the `resolution` column that Step 8 already computed. And the 373 pairs in the E2E input don't match Step 8's 3 pairs — the recommendation engine is running its own detection, not reading Step 8's output.

**Fix:** Replace all of Section 10f with: query `cannibalization_pairs` for the site, generate one recommendation per pair using the `resolution` column (redirect/merge/differentiate/monitor), use `severity` for priority, use `stronger_post_id` for the action text. This produces 3 recommendations instead of 373. One hour of work.

**S7-04: decay_mild has no working template — 136 problems produce 0 recommendations**

The E2E has an internal contradiction. The input summary (Section 10a) says decay_mild "Has Template? YES." The template coverage table (Section 10d) says "NO" with 0 recs generated at 0% coverage. The observations say "Untemplated problem types: decay_mild."

Either a template was added but doesn't work, or the input summary is wrong. Either way, 136 posts (94% of all posts, 33% of all problems) have a detected problem with zero corresponding recommendation. The customer sees "136 posts have content decay" in the problems dashboard but gets no guidance on what to do about it.

For a 2007-era blog like Copyblogger, content staleness is THE dominant issue. Every post that isn't flagged for year references or time-sensitive keywords gets decay_mild. These are the majority of stale content. The customer needs: "Update your last-modified date, check for broken links, add a recent example or statistic, verify external references still exist."

**Fix:** Add a working `decay_mild` template with rec_type "refresh", priority "low", effort 0.5h, confidence "low". Verify it generates recs. 15 minutes.

**S7-05/06: Orphan link suggestions recommend linking from pages with negative semantic similarity**

Orphan #1: "5 Steps to Pay Per Click Advertising" → suggested link from "Copyblogger homepage" at similarity **-0.015**. Negative cosine means these posts point in opposite directions in embedding space. This isn't "weak match" — it's "anti-match."

Orphan #11: "Titles That Tell a Whole Story" → similarity -0.009. Orphan #13: "Telling People a Story They Want to Hear" → similarity -0.037.

Every single orphan recommendation suggests linking from exactly 1 post: the Copyblogger homepage. Because it's the only post with any inbound links on this capped crawl. The customer reads: "Link to '5 Steps to Pay Per Click Advertising' from your homepage (similarity: -0.01)." That's not actionable advice — that's noise.

**Fix:** Add a minimum similarity threshold (0.20). If the best match is below threshold, don't generate the orphan recommendation. When link resolution < 20% (same quality gate as Step 9), skip orphan link recs entirely. Generate a single site-level recommendation instead: "Your internal linking structure needs attention — run a full crawl to get actionable link suggestions." 30 minutes.

---

## FIX BEFORE FIRST PAID CUSTOMER

**S7-07: 99 identical "add headings" + 130 identical "add meta description" recommendations**

229 of 271 problem-based recommendations are nearly identical optimize recs. The customer scrolls through page after page of "Add H2 headings to [post title]" with the same 4 action items. This isn't actionable — it's a wall of noise that buries the 6 actually-interesting update/expand recommendations.

**Fix:** For problem types affecting > 30% of posts, generate one site-level recommendation ("99 of your 145 posts lack H2 headings — start with your top 10 by health score") plus per-post recommendations only for the top 10 posts. This drops 229 near-identical recs to ~22 targeted ones. 1 hour.

**S7-09: Staleness text says "6-12 months" for a 19-year-old post**

The update template for "Aristotle's Top 3 Tips for Effective Blogging" says "hasn't been updated in 6-12 months." The post is from 2006 — it's 235 months old. The template uses a static string instead of pulling the actual staleness from `content_problems.details`.

A prospect who knows their post is from 2006 reads "hasn't been updated in 6-12 months" and immediately loses trust in the tool's accuracy.

**Fix:** Use the actual staleness period from problem details: `months_stale = details.get("months_stale", 0)`. Format as "hasn't been updated in X years" when > 24 months. 15 minutes.

**S7-10: The E2E input summary contradicts the template coverage table**

The input summary says decay_mild "Has Template? YES" but template coverage says NO with 0% coverage. One of these is wrong. If the input summary is auto-generated from template registration but the template doesn't actually produce output, there's a code path where a template exists but fails silently. Investigate which is correct. 10 minutes.

---

## MODERATE ISSUES

**S7-08: 695 hours total estimated effort is paralyzing, not motivating**

The cold outreach PDF promises quick wins and a 30-day plan. Showing "695 hours of work" doesn't fit. After fixing S7-01 (373→3 cannibalization recs) and S7-07 (aggregating common problems), total effort drops to ~50-80 hours, which is more realistic. The dashboard should present effort by priority tier: "Quick wins: 5 hours, High priority: 19 hours, Full optimization: 695 hours."

**S7-11: Cluster 1 has 454 recommendations (density 8.0 per post) — 346 are false cannibalization recs**

After fixing S7-01, Cluster 1 would have ~108 recs (density 1.9) — comparable to the other clusters at 2.2-2.5. The current 8.0 density is entirely from the cosine-only cannibalization scan producing 346 false pairs within this single cluster.

**S7-12: The spec lists `decay_mild` in neither the template table (Section 10e) nor mentions it as missing**

The spec's template table has 19 templates but no `decay_mild` entry. There's also no "known gap" or "TODO" noting the missing template. The spec reads as if the template set is complete. This documentation gap makes it easy to miss the fact that your most common problem type has no recommendation.

---

## POST-FIX PROJECTION

After the three critical fixes (2-3 hours total):

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total recs | 664 | ~160-180 | -73% |
| Cannibalization recs | 373 | 3 | -99% |
| decay_mild recs | 0 | 136 | +136 |
| Orphan recs | 20 | 0-5 | -75% |
| Problem recs | 271 | 271 | unchanged |
| Dominant rec type | differentiate (56%) | optimize (45%) | problem-based recs lead |
| Total effort | 695h | ~80-100h | realistic |

After the first-paid-customer fixes (1.5 hours more):

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Near-identical recs | 229 | ~22 | -90% |
| Stale text accuracy | "6-12 months" (wrong) | "19 years" (correct) | accurate |
| Actionable rec count | ~30 | ~50-60 | meaningful |

The product goes from "664 recommendations dominated by false positives" to "50-60 prioritized recommendations that accurately describe what's wrong and what to do about it." That's a $149 product.

---

## SUMMARY

### Critical — Fix Before Launch (3 items, 2 hours)

| # | Issue | Effort |
|---|-------|--------|
| S7-01/02/03 | Cannibalization recs bypass Step 8's blended scoring — read from `cannibalization_pairs`, use `resolution` column | 1 hour |
| S7-04 | decay_mild template missing or broken — 136 problems → 0 recs | 15 min |
| S7-05/06 | Orphan recs with negative similarity + only homepage as source — add similarity threshold + quality gate | 30 min |

### Fix Before First Customer (3 items, 1.5 hours)

| # | Issue | Effort |
|---|-------|--------|
| S7-07 | 229 identical optimize recs — aggregate site-level recs for > 30% problems | 1 hour |
| S7-09 | "6-12 months" staleness for 19-year-old post — use actual age | 15 min |
| S7-10 | Input summary says decay_mild has template, coverage says no — investigate contradiction | 10 min |

### Post-Launch (2 items)

| # | Issue | Effort |
|---|-------|--------|
| S7-08 | 695 hours total effort is paralyzing — show by priority tier | UX decision |
| S7-12 | Spec doesn't document missing decay_mild template | 5 min |

### The honest assessment

38/100. I was at 62 last time and that was too generous. This is the step that produces what the customer pays for. Right now it produces 664 recommendations where the majority are false, the most common problem type generates nothing, and the orphan suggestions are nonsensical. The template engine itself is well-designed — 21 templates with context-aware rendering, confidence levels, effort estimates, and priority logic. The architecture is good. But the output is unusable.

The three critical fixes (S7-01, S7-04, S7-05/06) take 2 hours and transform the output from "broken" to "functional." The two customer fixes (S7-07, S7-09) take 1.5 hours and transform it from "functional" to "professional." That's 3.5 hours to go from 38/100 to approximately 82/100. This is your highest-leverage work before launch.

THOUGHTS:

**Rating: 68/100**

Significant improvement from the 38/100 baseline. Four of the six issues I flagged are fixed and verified. But the cannibalization integration is still wrong — better than before, but wrong in a different way now.

---

## WHAT'S FIXED — VERIFIED IN E2E

**S7-04 (decay_mild template): FIXED.** Template exists, generates 11 recommendations with rec_type "refresh", priority "low", effort 0.5h. The sample recommendation says "hasn't been updated in 19.8 years" — correct staleness text pulled from problem details. Coverage: 11/136 = 8%, which is the expected result of site-level aggregation (1 site-level + 10 per-post for top posts).

**S7-05/06 (orphan similarity threshold): FIXED.** Orphan recs dropped from 20 to 13. The minimum similarity is now 0.427 (lowest in the table). All negative-similarity orphans are filtered out — "5 Steps to Pay Per Click Advertising" (-0.015), "Titles That Tell a Whole Story" (-0.009), "Telling People a Story They Want to Hear" (-0.037) are all gone. The 0.20 minimum threshold is working.

**S7-07 (site-level aggregation): FIXED.** This is the biggest improvement. Problem-based recs dropped from 271 to 75 (82% dedup). The pattern is clear: seo_missing_meta went from 130 → 11 recs, seo_no_headings from 99 → 11 recs, decay_mild from 0 → 11 recs. Each generates 1 site-level rec + 10 per-post recs for the top posts. The customer sees 11 focused recommendations instead of 130 identical ones.

**S7-09 (staleness text): FIXED.** The update template now shows "hasn't been updated in 19.6 years" for Aristotle's post. The refresh template shows "19.8 years." Both pull actual staleness from problem details. No more "6-12 months" for 19-year-old content.

**S7-10 (template coverage contradiction): FIXED.** Input summary shows 10/10 covered. Template coverage table shows 10/10. No contradiction.

---

## WHAT'S IMPROVED BUT STILL BROKEN

**S7-01/02/03: Cannibalization recs reduced from 373 to 33 — but 33 is still wrong**

Priority: CRITICAL — still the #1 issue
Found in: E2E test (Section 10e)

The good news: the recommendation engine now reads from `cannibalization_pairs` and filters by resolution. 340 of 373 pairs with resolution="monitor" were correctly skipped. That's the fix I asked for — reading the resolution column and skipping non-actionable pairs.

The bad news: **33 "merge" recommendations survived, and most are false positives.** Look at the pairs:

- Pair 3: "How a Few Measly Words" vs "What Romance Novels Can Teach You" (cosine 0.756) → merge
- Pair 4: "3 Coercive Copywriting Techniques" vs "How a Few Measly Words" (cosine 0.754) → merge
- Pair 7: "How a Few Measly Words" vs "Copywriting 101" (cosine 0.744) → merge

"How a Few Measly Words Can Dramatically Improve Your Blog Headlines" appears in **8 of the top 10** cannibalization recommendations. The system is telling the customer to merge a post about headline writing with a post about romance novel copywriting techniques, a post about coercive persuasion, a post about general copywriting fundamentals, and 5 other unrelated posts. That's not cannibalization — that's "these posts are all about writing" which is what you'd expect on a copywriting blog.

The root cause: **the E2E's Step 8 is still producing 373 pairs from cosine-only scanning, not 3 pairs from the blended scoring system.** The input table shows 373 pairs all with resolution="merge." But Step 8's actual blended scoring found only 3 pairs (1 critical, 1 high, 1 medium). The resolution column is being set by the E2E test's own cosine-only logic, not by Step 8's `_recommend_resolution()` function which considers slug overlap, H2 Jaccard, and title topic.

In production, Step 8 would insert 3 pairs into `cannibalization_pairs`. Step 10 would read those 3 pairs and generate 1-3 recommendations (skipping any with resolution="monitor"). The customer would see 1-3 cannibalization recommendations, not 33.

**The recommendation engine fix is correct.** It reads from `cannibalization_pairs`, uses the resolution column, and skips monitor pairs. The problem is that the E2E test feeds in 373 cosine-only pairs instead of 3 blended-score pairs. This means:
- Production behavior: **likely correct** (3 pairs → 1-3 recs)
- E2E validation: **misleading** (373 pairs → 33 recs, most false)

**Fix:** The E2E test's Step 8 substitute needs to use the blended scoring system, not cosine-only detection. Alternatively, run the actual Step 8 blended scoring code in the E2E test. The recommendation engine code is probably fine — the test is feeding it bad input. But you need to verify by running the full pipeline end-to-end on a real site.

**S7-13: The spec still describes cosine-only resolution logic in Section 10f**

Priority: Fix documentation
Found in: Spec (Section 10f)

The spec says: "≥ 0.99 → 301 redirect, 0.90-0.99 → merge, < 0.90 → differentiate." But the E2E's resolution logic section now says "Step 8 Blended Scoring" and describes redirect/merge/differentiate/monitor based on H2 Jaccard, slug overlap, etc. The spec needs to be updated to match the code: "Resolution is read from `cannibalization_pairs.resolution`, computed by Step 8's signal-aware rules."

---

## NEW ISSUES FROM THIS E2E

**S7-14: All 33 cannibalization recs are "merge" — zero differentiate, zero redirect, zero monitor**

Priority: Investigate — resolution logic may be too aggressive
Found in: E2E test (Section 10e)

Every surviving cannibalization recommendation has action="merge" and priority="high." The resolution logic section shows: "merge=33, Filtered out: 340 monitor." There are zero "differentiate" and zero "redirect" recommendations.

In the E2E input, all 373 pairs show resolution="merge." This seems wrong — Step 8's `_recommend_resolution()` would produce a mix of merge/differentiate/monitor based on the pair's signals. If ALL 373 pairs have resolution="merge," the resolution assignment in the E2E's Step 8 substitute is likely defaulting to "merge" for everything instead of using the signal-aware rules.

With real Step 8 output (3 pairs), the resolutions should be: pair 1 (synthetic, cosine 0.836, blended 0.800) → merge (critical severity), pair 2 (synthetic, cosine 0.711, blended 0.701) → monitor (high severity but not critical), pair 3 (real, cosine 0.690, blended 0.408) → monitor (medium severity). So the customer would see **1 merge recommendation** and 0 others (monitors are skipped).

**S7-15: Copyblogger homepage still generates 11 recommendations including "expand thin content"**

Priority: Low — cascades from S1-23/S4-30
Found in: E2E test (Section 10h, #1 most recommended post)

"Copyblogger - Content marketing tools and training" (186 words, page_type "landing") is the #1 most-recommended post with 11 recommendations including "Expand thin content" (high priority, 2.0h effort) suggesting to add 1,991 words. Telling a customer to add 2,000 words to their homepage is bad advice.

This cascades from the homepage being in the dataset (S1-23) and being scored as a pillar (S4-30). The recommendation engine correctly identifies it as thin content (186 words) but doesn't know it's a homepage that shouldn't be expanded.

**S7-16: All orphan recs still point to the homepage as the only link source**

Priority: Expected on capped crawl — not a code bug
Found in: E2E test (Section 10f)

All 13 orphan recommendations suggest linking from exactly 1 post: "Copyblogger - Content marketing tools and training." The similarity threshold (0.20) correctly filtered out the worst suggestions, but every surviving orphan still only has 1 link source option because the homepage is the only post with inbound links.

On a full crawl, multiple posts would have inbound links, producing diverse link suggestions. The quality gate (skip orphan recs when link resolution < 20%) should probably fire here — with only 1 post having links, the suggestions are technically above the similarity threshold but practically useless (all say "link from your homepage").

---

## SUMMARY

### What's Fixed (5 items)

| # | Issue | Status |
|---|-------|--------|
| S7-04 | decay_mild template | FIXED — 11 refresh recs generated |
| S7-05/06 | Orphan negative similarity | FIXED — 0.20 threshold, 13 recs (was 20) |
| S7-07 | 229 identical recs | FIXED — site-level aggregation, 75 problem recs (was 271) |
| S7-09 | "6-12 months" staleness | FIXED — shows "19.8 years" |
| S7-10 | Template coverage contradiction | FIXED — 10/10 consistent |

### Still Broken (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S7-01/02/03 | E2E feeds 373 cosine-only pairs instead of Step 8's 3 blended pairs — recommendation engine code is likely correct but E2E doesn't validate production behavior. 33 false "merge" recs survive. | Fix E2E to use blended scoring, or run full pipeline E2E (30 min) |

### New Issues (3 items)

| # | Issue | Effort |
|---|-------|--------|
| S7-13 | Spec still describes cosine-only resolution logic | 10 min (doc fix) |
| S7-14 | All 373 input pairs have resolution="merge" — E2E Step 8 substitute not using signal-aware resolution | 30 min (fix E2E test) |
| S7-15 | Homepage gets "expand to 2000 words" recommendation | Post-launch (page_type filter) |

### Not a Bug (1 item)

| # | Observation |
|---|-------------|
| S7-16 | All orphan recs point to homepage — expected on capped crawl with 1 linked post |

### The honest assessment

68/100. Up from 38. The five fixes transformed the output from unusable to approaching-shippable. Total recs dropped from 664 to 121. The site-level aggregation (S7-07) is the single best improvement — turning 229 walls-of-identical-recs into 22 focused recommendations. The staleness text fix means the product no longer lies about post ages. The orphan threshold means no more negative-similarity suggestions.

But the cannibalization integration remains the gap. The recommendation engine's code change (reading resolution, skipping monitor) is correct. The problem is the E2E test feeds it 373 cosine-only pairs with resolution="merge" instead of Step 8's 3 blended-score pairs. In production, this probably works correctly — Step 8 inserts 3 pairs, Step 10 reads 3 pairs. But "probably works" isn't validated. You need either a fixed E2E test or a full pipeline run on Backlinko to confirm.

After fixing the E2E's Step 8 input (30 min) or validating on Backlinko (the run you need to do anyway), the rating would be 80-82. The remaining 18-20 points: homepage-as-content cascading through recommendations (-5), all orphan recs pointing to one source (-4), no production validation of the full Step 8 → Step 10 integration (-5), and spec documentation still describing the old cosine-only logic (-4).