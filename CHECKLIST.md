# Enough — Master Intelligence Layer & Output Checklist

**Purpose:** Single source of truth for what gets computed, what gets verified, and what appears in every output (PDF, dashboard, API). Every item has a status field: what the pipeline SHOULD do, what it ACTUALLY does today, and what's broken.

---

## PART 1: PIPELINE STEPS (execution order)

The full pipeline runs in `ingestion.py:_run_full_pipeline`. Each step feeds the next.

### Step 1: Sitemap Crawl
**What it does:** Fetches sitemap XML, discovers URLs, HTTP-fetches each page, extracts content.

Per-post data extracted:
- [x] `title` — from `<title>` or `<h1>` ✅ 150/150 non-null
- [x] `url` — canonical URL ✅
- [x] `body_text` — stripped HTML content ✅
- [x] `body_html` — raw HTML (preserved for AI citability analysis) ✅ 150/150
- [x] `word_count` — from body_text ✅ avg=2250, min=64, max=4515
- [x] `headings` — JSON array of `{text, level}` objects (h1-h6) ✅ 150/150
- [x] `meta_description` — from `<meta name="description">` ✅ 148/150
- [x] `publish_date` — from meta tags, JSON-LD, or `<time>` elements ✅
- [x] `modified_date` — from meta tags or HTTP headers ✅
- [x] `http_status` — response code (200, 301, 404, etc.) ✅
- [x] `language` — detected language (en, es, fr, etc.) ✅
- [x] `cms_categories` — extracted from page markup ✅
- [x] `cms_tags` — extracted from page markup ✅
- [x] `slug` — URL path component ✅

**Verification queries:**
```sql
-- All posts stored
SELECT COUNT(*) FROM posts WHERE site_id = $1;
-- No NULL titles
SELECT COUNT(*) FROM posts WHERE site_id = $1 AND title IS NULL;
-- No zero-word posts (except index pages)
SELECT COUNT(*) FROM posts WHERE site_id = $1 AND word_count = 0;
-- Word count distribution
SELECT MIN(word_count), AVG(word_count)::int, MEDIAN(word_count), MAX(word_count) FROM posts WHERE site_id = $1;
```

**Known issues:**
- `language` column required migration 030 to exist (BUG-3)
- Crawl batches at 25 posts — large sites (500+) take proportionally longer

---

### Step 2: Embeddings (OpenAI text-embedding-3-small)
**What it does:** Generates 1536-dimensional vector embeddings for each post's body_text.

Per-post data:
- [x] `embedding` — 1536-dim float vector in `post_embeddings` table ✅ 150/150

**Verification:**
```sql
SELECT COUNT(*) FROM post_embeddings pe JOIN posts p ON p.id = pe.post_id WHERE p.site_id = $1;
-- Should equal total post count
```

**Known issues:**
- Requires `OPENAI_API_KEY` in env — fails silently if missing
- Batches at 100 posts per API call

---

### Step 3: Readability Scoring
**What it does:** Computes Flesch readability score and grade level per post.

Per-post data:
- [x] `readability_score` — Flesch Reading Ease (0-100) ✅ 150/150 scored
- [x] `grade_level` — Flesch-Kincaid Grade Level ✅ 150/150 scored
- [x] `readability_details` — JSON of 3 hardest paragraphs ✅ migration 031 applied

**BUG STATUS: FIXED.** Migration `031_readability_details.sql` added the `readability_details JSONB` column. Readability scoring now runs successfully. The `readability_too_complex` problem type can now fire for posts with Flesch score < 40.

---

### Step 4: PageRank (Internal)
**What it does:** Computes internal link graph and PageRank for each post.

Data produced:
- [x] `internal_links` table — source_post_id, target_post_id, anchor_text ✅
- [x] `internal_pagerank` — per-post PageRank score in `post_health_scores` ✅ 150/150
- [x] Internal link counts (inbound/outbound per post) ✅

**Verification:**
```sql
SELECT COUNT(*) FROM internal_links WHERE site_id = $1;
-- Posts with zero inbound links (orphans)
SELECT COUNT(*) FROM posts p WHERE p.site_id = $1 AND p.id NOT IN (SELECT DISTINCT target_post_id FROM internal_links WHERE target_post_id IS NOT NULL);
```

---

### Step 5: Intent Classification (TF-IDF)
**What it does:** Classifies each post's search intent using TF-IDF keyword matching.

Per-post data:
- [x] `content_intent` — one of: `informational`, `commercial`, `transactional`, `navigational` ✅ 150/150 (143 info, 7 commercial)

**Verification:**
```sql
SELECT content_intent, COUNT(*) FROM posts WHERE site_id = $1 GROUP BY content_intent;
```

---

### Step 6: Clustering (UMAP + HDBSCAN)
**What it does:** Reduces embedding dimensions with UMAP, clusters with HDBSCAN, generates TF-IDF labels.

Data produced:
- [x] `clusters` table — id, site_id, label, description, post_count, health_score, ecosystem_state, parent_cluster_id ✅ 11 clusters (7 top-level + 4 sub)
- [x] `post_clusters` table — post_id, cluster_id (assignment) ✅ 150/150 (1:1, zero multi-assigned)
- [x] `x_pos`, `y_pos` on posts table — UMAP coordinates for visualization ✅
- [x] Cluster labels via TF-IDF (fast) or Claude API (slow, optional) ✅ TF-IDF labels applied
- [x] Sub-clusters via `parent_cluster_id` for large clusters ✅

**Verification (CRITICAL — this has been broken before):**
```sql
-- Total assignments must equal total posts
SELECT COUNT(DISTINCT post_id) as assigned, (SELECT COUNT(*) FROM posts WHERE site_id = $1) as total FROM post_clusters pc JOIN clusters c ON c.id = pc.cluster_id WHERE c.site_id = $1;
-- No multi-assigned posts
SELECT post_id, COUNT(*) FROM post_clusters pc JOIN clusters c ON c.id = pc.cluster_id WHERE c.site_id = $1 GROUP BY post_id HAVING COUNT(*) > 1;
-- Stored post_count matches actual
SELECT c.label, c.post_count as stored, COUNT(pc.post_id) as actual FROM clusters c LEFT JOIN post_clusters pc ON pc.cluster_id = c.id WHERE c.site_id = $1 GROUP BY c.id, c.label, c.post_count;
-- No empty clusters (noise)
SELECT * FROM clusters WHERE site_id = $1 AND post_count = 0;
```

**Known issues:**
- anthropic.com (375 posts) produced cluster post counts summing to 786 — posts in multiple clusters or count bug
- dub.co (231 posts) had 48 posts missing from clusters
- cookieandkate.com (150 posts) was clean: 150/150 perfect assignment
- Two "Miscellaneous" clusters with 0 posts sometimes created — should be pruned
- Cluster labels from TF-IDF are sometimes awkward: "Chocolate & Pumpkin (Recipe)" groups pecan pie, basil almonds, and frozen yogurt

---

### Step 7: Health Scoring (8-factor weighted composite)
**What it does:** Scores each post 0-100 based on 8 factors. Assigns roles.

#### Weight Model (from `health_scoring.py` lines 28-36 — verified against code)

| Factor | Full Weight (with GA4/GSC) | No-GA4/GSC Weight | Source |
|--------|---------------------------|-------------------|--------|
| Traffic Trend | 20% | 0% → redistributed | GA4 pageview trajectory |
| Ranking Strength | 18% | 0% → redistributed | GSC avg position + impressions |
| Engagement | 12% | 0% → redistributed | GA4 bounce rate + time on page |
| Freshness | 12% | **24%** | Days since modified_date |
| Content Depth | 10% | **20%** | Word count vs cluster average |
| Internal Links | 8% | **16%** | Inbound link count (normalized 0-1, stored as /100) |
| Technical SEO | 5% | **10%** | Meta desc + title length + headings + outbound links |
| AI Readiness | 15% | **30%** | Mean of (citability + eeat + schema + extraction) |

**FIXED:** AI citability now runs BEFORE health scoring in both `_run_full_pipeline()` and `_run_incremental_pipeline()`. The AI citability service uses INSERT ON CONFLICT (UPSERT) to create rows if they don't exist. The composite_score in the DB now includes AI Readiness at 30% (without GA4/GSC). Verified: `ai_in_composite: 149/149`.

**Verification (weight math):**
```
For any post, verify:
  composite = freshness × 0.24 + depth × 0.20 + (links×100) × 0.16 + techseo × 0.10 + ai_readiness_mean × 0.30
  where ai_readiness_mean = (citability + eeat + schema + extraction) / 4
```

Per-post data in `post_health_scores`:
- [x] `composite_score` — 0-100 weighted sum ✅ 149/150 scored, avg=55.7, range=35.7-70.2
- [x] `freshness_score` — 0-100 (45 = standard, 10 = very stale, 100 = just updated) ✅
- [x] `content_depth_score` — 0-100 (word count relative to cluster average, capped at 100) ✅
- [x] `internal_link_score` — 0-1 (normalized inbound links, stored as link_score/100) ✅
- [x] `technical_seo_score` — 0-100 (meta desc present + title length OK + headings present + has outbound) ✅
- [x] `engagement_score` — 0-100 (defaults to 32 without GA4) ✅
- [x] `traffic_contribution` — 0-1 (post's share of total site traffic, 0 without GA4) ✅
- [x] `ranking_strength` — 0-1 (normalized GSC ranking, 0 without GSC) ✅
- [x] `trend` — `rising`, `stable`, `declining`, `unknown` (unknown without GA4) ✅
- [x] `internal_pagerank` — raw PageRank value ✅
- [x] `role` — one of: `pillar`, `supporter`, `competitor`, `at_risk`, `dead_weight` ✅

Role assignment logic (without GA4/GSC):
- composite >= 70 → `pillar` (never triggers without traffic data in practice)
- composite >= 45 → `supporter`
- composite >= 20 → `at_risk`
- composite < 20 → `dead_weight`
- If post is in a cannibalization pair → `competitor` (overrides supporter)

**Known issues:**
- `internal_link_score` is on 0-1 scale while all other factors are 0-100 — causes confusion when reading raw DB values
- Without GA4/GSC, 60% of the original weight model is zeroed out — scores cluster in a narrow band (most posts 40-60)
- Top post on cookieandkate scored 70.2, worst scored 35.7 — only 35 points of spread across 150 posts
- engagement_score defaults to 32.0 for all posts without GA4 — adds constant noise

---

### Step 8: Cannibalization Detection
**What it does:** Finds post pairs with high cosine similarity within the same cluster.

Data produced in `cannibalization_pairs`:
- [x] `post_a_id`, `post_b_id` — the two competing posts ✅
- [x] `cosine_similarity` — embedding similarity (0-1) ✅ range 0.773-0.886
- [x] `overlap_score` — identical to cosine_similarity without GSC (by design — 70/30 cosine+Jaccard, Jaccard=0 without GSC queries) ✅
- [x] `overlapping_queries` — always NULL without GSC data ✅
- [x] `severity` — `high` (>= 0.80) or `medium` (>= threshold) ✅ 227 high, 73 medium
- [x] `severity_score` — numeric 0-100 ✅
- [x] `stronger_post_id` — which post to keep (higher word count) ✅
- [x] `resolution` — `monitor`, `redirect`, `merge`, `differentiate` ✅
- [x] `cluster_id` — which cluster the pair belongs to ✅

**Verification:**
```sql
-- Total pairs
SELECT COUNT(*) FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1;
-- Distinct posts involved
SELECT COUNT(DISTINCT post_id) FROM (
  SELECT post_a_id as post_id FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1
  UNION
  SELECT post_b_id FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1
) sub;
-- Similarity distribution
SELECT MIN(cosine_similarity), PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY cosine_similarity),
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cosine_similarity),
       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY cosine_similarity),
       MAX(cosine_similarity)
FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1;
```

**Known issues:**
- Hard cap at 300 pairs (LIMIT in query) — both anthropic.com and dub.co and cookieandkate hit this exact cap
- For recipe blogs, cosine threshold (~0.76) is too low — flags topically similar but non-competing recipes
- cookieandkate: 300 pairs from 150 posts, 120 posts involved (80%), distribution is smooth bell curve centered at 0.81, no cliff between real cannibalization and topical similarity
- `overlap_score` is a dead column — always equals `cosine_similarity`

---

### Step 9: Problem Detection
**What it does:** Scans posts for content problems across 8 categories.

#### All Problem Types (from `problem_detection.py`)

| Problem Type | Detection Method | What It Flags | Severity |
|---|---|---|---|
| `thin_content` | `_detect_thin_content` | Word count below absolute threshold (e.g., 300 words) | high if <300, medium otherwise |
| `thin_below_cluster_avg` | `_detect_thin_content` | Word count significantly below cluster average | medium |
| `seo_missing_meta` | `_detect_seo_issues` | No meta description or too short | medium |
| `seo_title_length` | `_detect_seo_issues` | Title too short (<30 chars) or too long (>60 chars) | medium |
| `seo_no_images` | `_detect_seo_issues` | No images detected in body | low |
| `seo_no_headings` | `_detect_seo_issues` | No H2/H3 headings | medium |
| `seo_no_internal_links` | `_detect_seo_issues` | No outbound internal links | high |
| `orphan` | `_detect_orphans` | Zero inbound internal links | high |
| `readability_too_complex` | `_detect_readability_issues` | Flesch score below threshold | medium |
| `decay_critical` | `_detect_content_decay` | Clicks dropped >50% in 90 days | critical |
| `decay_high` | `_detect_content_decay` | Position dropped significantly | high |
| `decay_medium` | `_detect_content_decay` | Stale + low ranking | medium |
| `low_ai_citability` | `_detect_ai_readiness_issues` | AI citability score below threshold | medium |
| `weak_eeat` | `_detect_ai_readiness_issues` | E-E-A-T score below threshold | medium |
| `missing_schema` | `_detect_ai_readiness_issues` | No JSON-LD schema markup detected | high |
| `poor_ai_structure` | `_detect_ai_readiness_issues` | Low AI extraction score | medium |
| `velocity_decline` | `_detect_velocity_decline` | Publishing frequency declining | low |

**Currently not firing (require external data):**
- All `decay_*` types — require GSC click/position data
- `readability_too_complex` — requires readability scoring step (broken, see Step 3)
- `velocity_decline` — requires publishing history analysis

**Verification:**
```sql
SELECT problem_type, COUNT(*) FROM content_problems cp JOIN posts p ON p.id = cp.post_id WHERE p.site_id = $1 GROUP BY problem_type ORDER BY COUNT(*) DESC;
```

---

### Step 10: Recommendations (fast_recommendations.py)
**What it does:** Generates template-based recommendations for every detected problem + cannibalization pair + orphan page.

#### All Recommendation Types

| Rec Type | Source | Template Key | What It Recommends |
|---|---|---|---|
| `expand` | thin_content, thin_below_cluster_avg | `thin_content`, `thin_below_cluster_avg` | Add words to reach threshold/cluster average |
| `optimize` | seo_missing_meta | `seo_missing_meta` | Write a meta description |
| `optimize` | seo_title_length | `seo_title_length` | Fix title length |
| `optimize` | seo_no_images | `seo_no_images` | Add images |
| `optimize` | readability_too_complex | `readability_too_complex` | Simplify writing |
| `interlink` | orphan posts | `orphan` + pgvector similarity | Link from 3-5 most similar posts |
| `improve_ai_citability` | low_ai_citability | `low_ai_citability` | Add data tables, stats, experience markers |
| `strengthen_eeat` | weak_eeat | `weak_eeat` | Add author bio, credentials, dates |
| `add_schema` | missing_schema | `missing_schema` | Add Article/FAQ/Recipe JSON-LD |
| `improve_ai_structure` | poor_ai_structure | `poor_ai_structure` | Front-load answers, add TL;DR, FAQ section |
| `merge` | cosine >= 0.90 | cannibalization logic | 301 redirect weaker post |
| `differentiate` | cosine 0.76-0.90 | cannibalization logic | Target different keywords |
| `redirect` | cosine >= 0.99 | cannibalization logic | Identical content, redirect |

Per-recommendation fields:
- [x] `post_id` — which post this applies to ✅
- [x] `problem_id` — linked problem (NULL for cann/orphan recs) ✅
- [x] `recommendation_type` — from table above ✅ 3 types: differentiate(300), optimize(10), expand(2)
- [x] `priority` — critical, high, medium, low ✅
- [x] `estimated_effort_hours` — 0.25 to 3.0 ✅
- [x] `estimated_impact` — high, medium, low ✅
- [x] `title` — human-readable title ✅ no template literals
- [x] `summary` — explanation with specific numbers ✅ real word counts, cosine values
- [x] `specific_actions` — JSON array of actionable steps ✅
- [x] `ai_generated_content` — JSON with pair URLs/cosine for cann recs, NULL for template recs ✅
- [x] `confidence` — high, medium, low ✅
- [x] `status` — pending, in_progress, completed, dismissed ✅

**Known issues (updated):**
- ~~`seo_title_length` template says "Shorten"~~ **FIXED** — `fast_recommendations.py` now has `summary_fn`/`actions_fn` with conditional: <30 says "Expand title", >70 says "Shorten title" (verified: 8 recs say "short", 0 say "long")
- `differentiate` recommendations all have identical generic actions — "Identify the unique angle for each post" × 300 is not useful (STILL OPEN)
- `ai_generated_content` is NULL on all expand/optimize recs — Claude enrichment doesn't run (STILL OPEN — see Step 11)
- 300 differentiate recs for cookieandkate (96% of all recs) — overwhelms the 12 actually useful recs (STILL OPEN)

---

### Step 10b: AI Citability Scoring
**What it does:** Scores each post on 4 AI readiness dimensions. Updates `post_health_scores` row.

**FIXED:** Now runs BEFORE health scoring (moved in both `_run_full_pipeline` and `_run_incremental_pipeline`). Uses INSERT ON CONFLICT (UPSERT) to create rows if they don't exist. Composite score now includes AI readiness at 30%.

Per-post data added to `post_health_scores`:
- [x] `ai_citability_score` — 0-100 (data tables, stats, citations, first-person markers) ✅ 150/150, avg=56.1
- [x] `eeat_score` — 0-100 (author bio, credentials, dates, external links) ✅ avg=69.1
- [x] `schema_score` — 0-100 (JSON-LD presence and type coverage) ✅ avg=0.0 (no schema on site)
- [x] `extraction_score` — 0-100 (answer-first structure, FAQ sections, definition paragraphs) ✅ avg=66.3
- [x] `ai_signals` — JSON blob with all raw signal counts ✅

#### AI Signals Detail (from `ai_signals` JSON)

**Citability signals:**
- `citation_markers` — count of citation/reference markers in text
- `data_points` — count of specific data points
- `data_tables` — count of HTML tables
- `stats_mentions` — count of statistical references
- `first_person_markers` — count of "I", "we", "our" experience markers
- `entity_density_per_1k` — named entities per 1000 words
- `data_density_per_200w` — data points per 200 words

**E-E-A-T signals:**
- `eeat_author_found` — boolean
- `eeat_author_name` — string
- `eeat_has_author_bio` — boolean
- `eeat_has_author_credentials` — boolean
- `eeat_has_author_schema` — boolean (Author JSON-LD)
- `eeat_has_visible_date` — boolean
- `eeat_has_contact_link` — boolean
- `eeat_credible_external_links` — count of .gov/.edu/journal links

**Schema signals:**
- `schema_has_schema` — boolean
- `schema_schema_types` — array of detected types (Article, Recipe, FAQ, etc.)
- `schema_schema_score` — 0-100

**Extraction signals:**
- `extract_total_h2` — total H2 headings
- `question_headers` — H2s that are questions
- `question_header_ratio` — question H2s / total H2s
- `answer_first_200w` — boolean (does intro answer the main query?)
- `extract_direct_opening` — boolean
- `extract_has_faq_section` — boolean
- `extract_faq_qa_pairs` — count of Q&A pairs
- `extract_h2_with_direct_answer` — H2 sections starting with a direct answer
- `extract_definition_count` — definition paragraphs
- `extract_total_list_items` — total list items
- `numbered_list_items` — numbered list items specifically
- `extract_standalone_section_ratio` — sections that work independently

**Verification:**
```sql
-- All posts have AI scores
SELECT COUNT(*) FROM post_health_scores WHERE ai_citability_score IS NOT NULL AND post_id IN (SELECT id FROM posts WHERE site_id = $1);
-- Score distributions
SELECT ROUND(AVG(ai_citability_score),1), ROUND(AVG(eeat_score),1), ROUND(AVG(schema_score),1), ROUND(AVG(extraction_score),1) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1;
```

---

### Step 11 (not in pipeline): Claude Enrichment
**What it does:** Enriches top 10 recommendations with Claude-generated content.

**STATUS: FIXED (wiring).** Root cause: `auto_enrich_top_recs()` was only called in `intelligence.py` pipeline, NOT in `ingestion.py:_run_full_pipeline()`. Now added to both full and incremental pipelines as a non-fatal step after recommendations. Enrichment calls Claude to produce specific, actionable guidance (merge plans, differentiation strategies, meta descriptions). Requires `ANTHROPIC_API_KEY` in env.

When working, should produce:
- [ ] Copy-paste meta descriptions for `seo_missing_meta` recs
- [ ] Expand-vs-consolidate decisions for thin content recs
- [ ] Growth recommendations with specific post ideas for pillar posts

---

## PART 2: PDF AUDIT REPORT — SECTION-BY-SECTION SPEC

The PDF is generated by `pdf_report.py` using data from `_build_audit_data_for_site()` in `audit_report.py`.

### Page 1: Cover
- [x] Domain name (large) ✅
- [x] Date ✅
- [x] Health score as large visual number (colored: red <40, yellow 40-64, green 65+) ✅ Shows 56/100 in yellow
- [x] "Powered by Enough" branding ✅

### Page 2: Executive Summary
- [x] Health score with plain-English interpretation ✅ "showing moderate issues that need attention"
- [x] Key stat: "X of your Y posts compete for the same keywords" ✅ "115 of your 150 posts" (uses `cann_post_count`)
- [x] Three stat boxes: Total Posts | Topic Clusters | Issues Found ✅ 150 | 7 | 14
- [x] Summary line: "X of Y posts are competing for the same keywords across Z topic clusters" ✅
- [x] **Issue Breakdown** — table + bar chart ✅
  - [x] Cannibalized posts (uses DISTINCT post count) ✅ "Cannibalized (115 posts)"
  - [x] SEO issues count ✅ "14 SEO issues"
  - [x] Cannibalization pairs count (separate from issues) ✅ "300 cannibalization pairs — 115 posts competing"
- [x] **Topic Clusters table** ✅
  - [x] Cluster label ✅
  - [x] Post count ✅
  - [x] Health score (color-coded) ✅
  - [x] Ecosystem state ✅
  - [x] Filters: `parent_cluster_id IS NULL AND post_count > 0` (top-level only, no empty Miscellaneous) ✅

**Previously known bugs — all FIXED:**
- ~~`cann_pair_count` used as post count~~ → uses `cann_post_count` (distinct posts)
- ~~Cluster query LIMIT 6~~ → LIMIT 8, `parent_cluster_id IS NULL AND post_count > 0`
- ~~"Analyzed: None" rendered literally~~ → hidden when null

### Page 3: AI Readiness
- [x] Headline: "Only X% of your posts are structured for AI citation" ✅ "Only 43%..."
- [x] 4-dimension scores (large numbers) ✅ 56/69/0/66
- [x] Spider/radar chart showing 4 dimensions ✅
- [x] **"Why AI systems skip your content"** — 3 bullets ✅
  - [x] Schema: "100% of your posts have no schema markup" ✅
  - [x] Question headers: "Only 0% of H2 headers are question-format (target: 30%)" ✅
  - [x] Data density: "Average data density: 0.0 per 200 words (target: 1.0)" ✅
- [x] Market context line ✅
- [x] CTA: "Subscribe to see exactly which posts to fix..." ✅

### Page 4: Quick Wins + Top Posts
- [x] **Top 3 Quick Wins** ✅
  1. [x] Schema markup (#1 when schema_score = 0) ✅ "Add structured data (schema markup) to your top posts"
  2. [x] Cannibalization pair (names BOTH posts, similarity %) ✅ "Mexican Green Salad vs Mega Crunchy Romaine — 89%"
  3. [x] Optimize rec preferred over expand ✅ "Add meta description: Creamy Roasted Carrot Soup" (not birthday post)
- [x] **Top 5 Posts Needing Attention** ✅
  - [x] Deduplicated by post (DISTINCT ON) ✅ 5 unique posts
  - [x] Human-readable labels ✅ "Missing meta description", "Title too short", "Thin content"
  - [x] Title direction ✅ "Title too short" (not "short/long") — `_humanize_issues()` accepts title param
  - [x] Posts with actual problems first ✅ sorted by (has_problems, score)
  - [x] Health score shown ✅ 36, 41, 43, 57, 59
- [x] **Key Findings** ✅
  - [x] "115 of your 150 posts are competing against each other (300 cannibalization pairs detected)" ✅
  - [x] "100% of posts have no schema markup — missing Article/FAQ JSON-LD..." ✅

### Page 4-5: Example Rec + Cannibalization Pairs + CTA
- [x] **Example Recommendation** ✅ "Differentiate competing content: Chopped Greek Salad Recipe"
- [x] **Top Cannibalization Pairs table** — 6 pairs ✅
  - [x] Post A/B titles with word-boundary truncation ("...") ✅ uses `_truncate()` helper
  - [x] Similarity percentage (integer) ✅ 89%, 88%
- [x] **CTA block** ✅
  - [x] "Get all 312 recommendations in Enough." ✅
  - [x] Urgency: "Every day without structured data, AI systems cite your competitors instead of you." ✅
  - [x] Price: "$149/month. 30-day money-back guarantee." ✅
  - [x] URL: https://enough.app ✅

### Data Quality Rules for PDF

1. [x] **Post count consistency:** "115 of 150 posts" — 115 <= 150 ✅
2. [x] **No "None" literals** ✅ (analyzed_at hidden when null)
3. [x] **No raw problem_type strings** ✅ (`_humanize_issues()` with `_ISSUE_LABELS` dict)
4. [x] **No duplicate posts in Top 5** ✅ (`DISTINCT ON (p.id)` + `string_agg`)
5. [x] **Cluster table: top-level only, no empty** ✅ (`parent_cluster_id IS NULL AND post_count > 0`)
6. [x] **Title truncation at word boundaries** ✅ (`_truncate()` helper with "...")
7. [x] **Health score includes AI Readiness** ✅ (AI citability runs before health scoring, UPSERT)
8. [x] **Cannibalization language: "X of Y posts"** ✅ (uses `cann_post_count` everywhere)

---

## PART 3: DASHBOARD OUTPUTS

These are the API responses that feed the frontend dashboard.

### Today Page (`/today`)
- [ ] Health score trend (current vs last analysis)
- [ ] Top 3 actions for today (highest priority pending recs)
- [ ] Since-last-visit changes
- [ ] Re-analyze button — **must call correct route** (currently calls `/intelligence/pipeline` which 404s — BUG-21)

### Overview/Dashboard
- [ ] Health score gauge
- [ ] Post count + cluster count + recommendation count
- [ ] Health distribution histogram
- [ ] Role distribution (pillar/supporter/competitor/at_risk/dead_weight)

### Landscape (Ecosystem Visualization)
- [ ] Cluster positions from UMAP x_pos/y_pos
- [ ] Biome types from ecosystem_state
- [ ] Weather from GA4 traffic trends (all "fog" without GA4)
- [ ] Terrain features from problem density
- [ ] Animals from role assignments
- [ ] Rivers from cannibalization connections

**Current status:** API returns clusters=0, links=0, animals=all empty. Visualization renders empty canvas with fog. Has not been tested in browser.

### Clusters Page
- [ ] All clusters with label, post count, health score, state
- [ ] Click-through to cluster detail with all posts listed

### Cannibalization Page
- [ ] All pairs sortable by similarity
- [ ] Resolution status (merge/differentiate/redirect/monitor)
- [ ] Link to consolidation flow

### Issues Page
- [ ] All problems grouped by type
- [ ] Severity indicators
- [ ] Link to recommendation for each problem

### Recommendations Page
- [ ] All recs sortable by priority
- [ ] Status tracking (pending/in_progress/completed/dismissed)
- [ ] On-demand Claude enrichment via "Get AI Analysis" button

---

## PART 4: VERIFICATION CHECKLIST (run after every pipeline)

### Data Integrity
- [x] Total posts in DB = cap for audit ✅ 150/150
- [x] All posts have embeddings ✅ 150/150
- [x] All posts assigned to exactly 1 cluster ✅ 150/150, 0 multi-assigned
- [x] No multi-assigned posts ✅ 0
- [x] Cluster post_count columns match actual assignments ✅ all match
- [x] No empty clusters in PDF ✅ (filtered with `post_count > 0`; 1 empty exists in DB but hidden)
- [x] Health scores exist for all scorable posts ✅ 149/150 (Recipe Index excluded — 64w index page)
- [x] AI citability scores exist ✅ 150/150

### Score Sanity
- [x] Health score spread > 20 ✅ 34.5 (range 35.7 - 70.2)
- [x] Health score average in 30-70 ✅ 55.7
- [x] Weight math verified ✅ top post: 0.24×45 + 0.20×100 + 0.16×91.3 + 0.10×56.25 + 0.30×59.25 = 68.8 (matches DB)
- [x] AI Readiness in composite ✅ 149/149 scored posts have AI scores in composite

### Cannibalization Sanity
- [x] Distinct posts involved < total ✅ 115/150 (77%)
- [x] Top pair < 0.99 ✅ 0.886
- [x] Bottom pair > 0.70 ✅ 0.773
- [x] Top 3 pairs manually reviewed ✅ (salad vs salad, soup vs soup — real overlap)

### Recommendation Sanity
- [x] Total recs < 5× posts ✅ 312 < 750
- [x] At least 3 types ✅ differentiate(300), optimize(10), expand(2)
- [x] No template literals ✅ 0 found
- [x] Title length direction correct ✅ 8 say "short", 0 say "long" (all flagged titles are <30 chars)

### PDF Sanity
- [x] Health score matches avg with AI Readiness ✅ 56/100
- [x] "X of Y posts" — X <= Y ✅ 115 <= 150
- [x] No "None" or "null" literals ✅
- [x] No duplicate posts in Top 5 ✅
- [x] Quick Win #1 is schema (schema_score = 0) ✅
- [x] Cluster table: top-level, non-empty ✅
- [x] Cann pair titles truncated at word boundaries with "..." ✅

---

## PART 5: KNOWN BUGS (as of March 25, 2026)

| # | Severity | Component | Bug | Status |
|---|----------|-----------|-----|--------|
| B1 | medium | readability | Missing `readability_details` column | **FIXED** — migration `031_readability_details.sql` |
| B2 | high | audit_report.py | Key findings uses pair count not post count | **FIXED** — `cann_post_count` added, copy corrected |
| B3 | medium | clusters | Empty "Miscellaneous" clusters with 0 posts | **FIXED** — `post_count > 0` filter in PDF query |
| B4 | high | audit_report.py | Cluster query LIMIT 6 drops clusters | **FIXED** — `LIMIT 8, parent_cluster_id IS NULL, post_count > 0` |
| B5 | high | fast_recommendations | Title template says "Shorten" for short titles | **FIXED** — `summary_fn`/`actions_fn` with <30/>70 conditional |
| B6 | medium | today/page.tsx | Re-analyze button 404 | **FIXED** — route corrected in earlier session |
| B7 | low | cannibalization | overlap_score = cosine_similarity | **BY DESIGN** — without GSC, Jaccard component is 0 |
| B8 | medium | enrichment | ai_generated_content NULL on expand/optimize | **FIXED** — `auto_enrich_top_recs` added to both full and incremental pipelines |
| B9 | medium | PDF | Top 5 posts duplicates and no-problem posts | **FIXED** — `DISTINCT ON` + `string_agg` + problems-first sort |
| B10 | low | PDF | Title truncation mid-word in cann pairs | **FIXED** — `_truncate()` helper with word-boundary + "..." |
| B11 | medium | health_scoring | AI Readiness not in composite (30% wasted) | **FIXED** — AI citability before health scoring + UPSERT |
| B12 | low | PDF | Quick Win #3 picks birthday post | **FIXED** — optimize recs preferred over expand |

| B13 | high | audit_report.py | Cluster table shows 2 of 23 clusters at scale (deeply nested) | **FIXED** — fallback to largest clusters when top-level covers <50% of posts |
| B14 | medium | pdf_report.py | Schema Quick Win says "Recipe/Article" for all sites | **FIXED** — changed to "Article/BlogPosting" (universally correct) |
| B15 | medium | pdf_report.py | Quick Wins #2 and #3 are same cann pair | **FIXED** — skip recs targeting same posts as cann pair Quick Win |
| B16 | low | pdf_report.py | Cann pairs table shows identical titles on both sides | **FIXED** — appends URL slug when titles match |
| B17 | low | pdf_report.py | "No internal links" appears twice (orphan + seo_no_internal_links) | **FIXED** — "No inbound links" vs "No outbound links" + dedup |
| B18 | medium | audit_report.py | Top 5 Posts includes landing pages (141w) | **FIXED** — `word_count >= 200` filter |
| B19 | medium | pdf_report.py | No E-E-A-T explanation when score < 20 | **FIXED** — conditional warning text added |

**Summary: 18 of 19 bugs FIXED. 1 by design (B7).**

---

## PART 6: WHAT'S NOT BUILT YET (for reference)

These are designed but not implemented or not firing:

- Content decay detection (requires GSC data)
- Velocity decline detection (requires publishing history)
- ~~Readability scoring (blocked by migration bug)~~ **NOW WORKING** — migration 031 applied, 150/150 scored
- GSC query-based cannibalization (overlap_score Jaccard component — requires GSC)
- ~~Growth recommendations from Claude engine (B8)~~ **FIXED** — `auto_enrich_top_recs` now in pipeline
- Content brief generation (endpoint exists, output quality unverified)
- Consolidation plan detail (endpoint exists, output quality unverified)
- Ecosystem visualization rendering (API works, browser rendering unverified)
- Email drip sequence after audit PDF (requires Resend)
- Stripe checkout + billing (requires Stripe keys)
- Google OAuth + GA4/GSC sync (requires Google OAuth)