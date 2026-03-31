# Pipeline Step 6c: AI Citability Scoring

> **Scope:** Everything that happens at Code Step 6c — after clustering + TF-IDF labels (Step 6/6b) and before health scoring (Step 7). This step scores every post on 4 AI-readiness dimensions: Citability, E-E-A-T, Schema, and Extraction. Zero external API calls — all signals derived from already-crawled `body_text`, `body_html`, and `eeat_metadata`. Scores are stored in `post_health_scores` and consumed downstream by health scoring (15% composite weight), problem detection, recommendations, audit reports, and PDF exports.

---

## Pipeline Position

After Step 6b stores TF-IDF cluster labels, the full pipeline runs AI citability scoring:

```
Step 1: Crawl + Normalize (done)
Step 2: Embeddings + Readability + PageRank + Intent (done)
Step 3: Clustering (UMAP + HDBSCAN + TF-IDF labels) (done)
   |
Step 6c.1: Fetch all posts with body_text for the site             <- DB read
Step 6c.2: Compute site-wide median word count                     <- CPU, <0.01s
Step 6c.3: For each post, compute 4 scores:
   Step 6c.3a: AI Citability Score (0-100)                         <- CPU, regex + HTML parse
   Step 6c.3b: E-E-A-T Score (0-100)                               <- CPU, regex + HTML parse
   Step 6c.3c: Schema Score (0-100)                                 <- CPU, JSON-LD parse
   Step 6c.3d: Extraction Score (0-100)                             <- CPU, regex + HTML parse
Step 6c.4: Upsert scores + signal JSON into post_health_scores     <- DB write (ON CONFLICT)
   |
Step 7: Health Scoring (next pipeline step — uses AI scores as 15% weight)
```

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
| **(none)** | **Step 6c** | **AI Citability (this document)** |
| Step 4 | Step 7 | Health Scoring |
| Step 5 | Step 8 | Cannibalization |
| (none) | Step 8b | Chunk Confirmation (optional) |
| Step 6 | Step 9 | Problem Detection |
| Step 7 | Step 10 | Recommendations |

In the full pipeline (`ingestion.py:_run_full_pipeline`), Step 6c maps to:
- **Code Step 6c:** `AICitabilityService().score_site(db, site_id)` — runs 6c.1 through 6c.4

**Why "6c" and not a spec step:** AI Citability was added after the original spec was written. It has no spec step number but occupies a critical pipeline position: it MUST run before health scoring (Step 7) because the composite health score includes AI readiness as a 15% weighted factor. Running it after clustering (Step 6) is a natural fit since it's post-level analysis that doesn't depend on cluster assignments.

### Progress Reporting

AI citability scoring logs progress every 100 posts (`logger.info("AI scoring: %d/%d posts done")`). The pipeline step label is set to `"ai_citability"` / `"analyzing"` in `crawl_jobs.current_step`. For typical sites (< 300 posts), the step completes in < 5 seconds so granular progress is unnecessary.

---

## 6c.1 Data Fetch

### What It Does

Fetches all posts for the site that have non-null `body_text`. Joins `post_health_scores` to support the upsert pattern (ON CONFLICT on `post_id`).

### Query

```sql
SELECT p.id, p.body_text, p.body_html, p.headings, p.eeat_metadata,
       p.word_count, p.publish_date, p.modified_date
FROM posts p
LEFT JOIN post_health_scores phs ON phs.post_id = p.id
WHERE p.site_id = $1 AND p.body_text IS NOT NULL
```

### Input Columns

| Column | Type | Source | Used By |
|--------|------|--------|---------|
| `body_text` | TEXT | Crawl (article extraction) | Citability, Extraction |
| `body_html` | TEXT | Crawl (article-area HTML only, NOT full page) | All 4 scores |
| `headings` | JSONB | Crawl (`[{"level": "h2", "text": "..."}]`) | E-E-A-T, Extraction |
| `eeat_metadata` | JSONB | Crawl (full-page E-E-A-T signals) | E-E-A-T |
| `word_count` | INTEGER | Crawl | E-E-A-T |
| `publish_date` | TIMESTAMPTZ | Crawl/meta | E-E-A-T (freshness) |
| `modified_date` | TIMESTAMPTZ | Crawl/meta | E-E-A-T (freshness, takes priority) |

**Important distinction:** `body_html` contains only the article content area, NOT the full page HTML (nav, footer, sidebar are stripped during crawl). However, `eeat_metadata` is extracted from the full page HTML during crawl — this is where site-wide signals like contact links and author schema live that aren't in the article body.

### Graceful Degradation

If a post has `body_text` but no `body_html`, the HTML-dependent signals (tables, lists, schema, H2 structure) will score 0. The text-based signals (first-person markers, statistics, definitions, entity density) still work from `body_text` alone. This typically only happens for malformed pages where the article extractor failed.

---

## 6c.2 Site-Wide Median Word Count

### What It Does

Computes the median word count across all posts in the site. This is used by the E-E-A-T scorer to determine whether a specific post is above or below the site's typical content depth.

```python
word_counts = sorted(r.get("word_count") or 0 for r in rows)
site_median_words = word_counts[len(word_counts) // 2] if word_counts else 0
```

### Why Per-Site, Not Global

A 500-word post on a news site (median: 400 words) is above average. The same 500-word post on a long-form blog (median: 2000 words) is thin content. Site-relative word count is a more meaningful trust signal than an absolute threshold.

---

## 6c.3a AI Citability Score (0-100)

### What It Measures

How likely an AI system (ChatGPT, Perplexity, Google AI Overview) will cite or quote this specific post. Based on empirical analysis of what content AI systems actually surface.

### Scoring Breakdown

Total possible points: ~165 (intentionally over-allocated). Capped at 100 via `min(sum, 100)`. This means different content types can reach 100 through different signal combinations — a data-heavy research post maxes out differently than an experience-rich case study.

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Data tables (`<table>`) | 20 | HTML: `soup.find_all("table")` — ≥ 1 table |
| Ordered lists (`<ol>`) | 7-15 | HTML: `soup.find_all("ol")` — ≥ 1 item = 7, ≥ 3 items = 15 |
| First-person experience | 10-20 | Regex: "in our testing", "we found", "I tested", etc. — ≥ 1 match = 10, ≥ 3 = 20 |
| Original statistics | 10-20 | Regex: percentages, large numbers + audience terms, "our data shows" — ≥ 1 = 10, ≥ 3 = 20 |
| Definition paragraphs | 5-10 | Regex: `^[A-Z]... is/are/refers to [a/an/the/...]` — requires article/determiner after verb to avoid false positives. ≥ 1 = 5, ≥ 2 = 10 |
| Entity density | 5-10 | Regex: Title Case word sequences per 1000 words — ≥ 8 = 5, ≥ 15 = 10 |
| External citations | 5 | Regex: "according to", ".gov", ".edu", "journal" — ≥ 2 citations |
| **GEO-1: Question-format headers** | **7-15** | H2/H3 starting with what/how/why/when/etc. — ratio ≥ 0.15 = 7, ≥ 0.30 = 15 |
| **GEO-1: Data density** | **5-10** | Data points per 200 words — ≥ 0.5 = 5, ≥ 1.0 = 10 |
| **GEO-1: Answer-first structure** | **10** | First 200 words contain definitive verb + number/definition |

### Key Regex Patterns

**First-person experience markers** (20 pts when ≥ 3 matches):
```python
FIRST_PERSON_PATTERNS = re.compile(
    r"\b(in our testing|when we (implemented|tested|tried|built|ran)|"
    r"we found|we discovered|in my experience|i tested|i found|"
    r"our (data|results|analysis|research|study|tests) (show|reveal|found|indicate)|"
    r"based on our|in practice|in real(-| )world|our team|we've been|"
    r"when i|after i|i've (been|used|tested|tried))\b",
    re.IGNORECASE,
)
```

**Original statistics markers** (20 pts when ≥ 3 matches):
```python
STATS_PATTERNS = re.compile(
    r"(\d+[\.,]?\d*\s*%|\d{4,}[\.,]?\d*\s*(users|companies|brands|sites|searches|queries|"
    r"customers|people|respondents|participants)|"
    r"\d+\s*(out of|in)\s*\d+|"
    r"(according to our|in our survey|our study|we surveyed|we analyzed|"
    r"we collected|our data|proprietary data))",
    re.IGNORECASE,
)
```

### Calibration Notes

- The over-allocation design means a research post with tables + stats + citations can hit 100 without any first-person experience
- A case study with experience markers + definitions + entity density can also hit 100 without data tables
- Posts scoring < 40 trigger `low_ai_citability` problem detection (severity: high if < 20, medium if < 40)

---

## 6c.3b E-E-A-T Score (0-100)

### What It Measures

Visible trust signals — what a human reader (or AI evaluator) would perceive as authoritative. NOT the same as Google's internal E-E-A-T evaluation; this measures the observable signals.

### Scoring Breakdown

Split into site-wide signals (present on most/all pages) and post-specific signals (vary per post):

**Site-wide signals (35 pts max):**

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Author byline present | 15 | Cascading detection: `eeat_metadata.author_name` → `<meta name="author">` → `.post-author`/`.byline` → `[rel="author"]` → `/authors/` links → `[itemprop="author"]` → "written by" text regex |
| Author bio section | 10 | HTML: class/id matching `author|bio|about.*author` — falls back to author page link |
| Contact/About page link | 10 | `eeat_metadata.has_contact_link` or HTML: links containing "contact", "about", "team" |

**Post-specific signals (65 pts max):**

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Author credentials in bio | 10 | Regex on bio text: CEO, PhD, "years of experience", "founder", etc. |
| Date freshness (graduated) | 0-15 | ≤ 6 months = 15, 6-12 months = 10, 1-2 years = 5, older = 0 |
| External outbound links (graduated) | 3-15 | ≥ 1 = 3, ≥ 3 = 7, ≥ 6 = 10, ≥ 11 = 13, ≥ 21 = 15 |
| Word count vs site median (graduated) | 0-10 | ≥ 2.0x = 10, ≥ 1.5x = 7, ≥ 1.0x = 5, ≥ 0.5x = 2, < 0.5x = 0 |
| H2 heading count (graduated) | 0-15 | 0 H2s = 0, 1-2 = 5, 3-5 = 10, 6+ = 15 |

### Author Detection Cascade

The E-E-A-T scorer uses a 7-level cascading author detection strategy, ordered from most reliable to least:

1. `eeat_metadata.author_name` (extracted from full page HTML during crawl)
2. `<meta name="author" content="...">` in body_html
3. Elements with class `post-author|byline|entry-author`
4. Links with `rel="author"`
5. Links matching `/authors?/[^/]+`
6. Elements with `itemprop="author"`
7. Text pattern: "written by [Name Name]" in first 3000 chars

This cascade is necessary because WordPress themes, custom CMSes, and static site generators all surface author information differently.

### Thin Content Cap

Posts with < 300 words have their E-E-A-T score capped at 50. Rationale: a stub page shouldn't outscore a substantive blog post just because it has the same site-wide signals (author, contact link). The cap ensures short pages can't exploit site-wide signals to inflate their trust score.

### Freshness Scoring

Uses `modified_date` if available, falling back to `publish_date`. The graduated scale:

| Age | Points | Rationale |
|-----|--------|-----------|
| ≤ 6 months | 15 | Recently updated — strong freshness signal |
| 6-12 months | 10 | Reasonably current |
| 1-2 years | 5 | Aging but not stale |
| > 2 years | 0 | Stale — no freshness credit |
| Date visible but value unknown | 5 | At least shows some date |
| No visible date | 0 | No freshness signal at all |

### Additional Tracked Signals

Two signals are tracked but NOT scored:
- `has_author_schema` — JSON-LD author schema present (tracked for debugging; schema signals belong in Schema Score)
- `has_visible_updated_date` — Visible "Last updated" / "Modified" text (tracked separately for `geo_no_updated_date` problem detection)

---

## 6c.3c Schema Score (0-100)

### What It Measures

Structured data completeness — how well the page communicates its content type and metadata to machines via JSON-LD schema markup.

### Scoring Breakdown

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Has any JSON-LD schema | 30 | `<script type="application/ld+json">` present and parseable |
| Has high-value schema type | 30 | `@type` in: Article, NewsArticle, BlogPosting, FAQPage, HowTo, TechArticle, Dataset, Review |
| Article schema completeness | up to 30 | Required fields: headline, datePublished, author, image, dateModified — proportional scoring |
| Multiple schema types bonus | 10 | ≥ 2 unique `@type` values across all JSON-LD blocks |

**High-value vs basic schema types:**

| High-Value (30 pts) | Basic (0 pts — but counts as "has schema") |
|---------------------|---------------------------------------------|
| Article, NewsArticle, BlogPosting | Organization, WebSite, BreadcrumbList, WebPage |
| FAQPage, HowTo, TechArticle | |
| Dataset, Review | |

### Article Completeness Detail

When an Article-type schema is found, five fields are checked:

```python
article_fields["headline"] = bool(item.get("headline"))
article_fields["datePublished"] = bool(item.get("datePublished"))
article_fields["author"] = bool(item.get("author"))
article_fields["image"] = bool(item.get("image"))
article_fields["dateModified"] = bool(item.get("dateModified"))
```

Points = `(complete_fields / total_fields) * 30`. A fully complete Article schema earns 30/30. Missing `dateModified` drops it to 24/30.

### Typical Score Ranges

| Scenario | Expected Score | Breakdown |
|----------|---------------|-----------|
| No JSON-LD at all | 0 | Nothing to score |
| Only Organization + WebSite schema | 30 | Has schema (30), no high-value type (0) |
| Article with all fields | 90 | Has schema (30) + high-value (30) + complete article (30) |
| Article + FAQPage (multi-type) | 100 | Above + multi-type bonus (10), capped at 100 |
| WordPress default (basic Article, no image) | 78 | Has schema (30) + high-value (30) + 4/5 fields (24) |

---

## 6c.3d Extraction Score (0-100)

### What It Measures

How easily an AI system can extract a direct answer from this content. Measures structural properties that make content "AI-snackable" — frontloaded answers, concise section openers, FAQ structure.

### Scoring Breakdown

Total possible points: ~130 (intentionally over-allocated, same design as citability). Capped at 100.

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Direct opening (first 100 words) | 25 | Contains definitive verb ("is", "means", "refers to") or number or definition pattern |
| H2/H3 sections with concise answers | 12-25 | Paragraphs after H2/H3: 15-80 words, starts with definitive statement — ratio ≥ 0.25 = 12, ≥ 0.5 = 25 |
| Definition paragraphs | 10-20 | Same tightened pattern as citability: requires article/determiner after verb — ≥ 1 = 10, ≥ 2 = 20 |
| FAQ/Q&A structure | 5-20 | FAQ heading or ≥ 3 question-format H3s with short answer paragraphs |
| Standalone sections (no pronoun starts) | 5-10 | Posts with < 2 H2s get 0.5 (neutral). Otherwise: ratio ≥ 0.5 = 5, ≥ 0.8 = 10 |
| Lists under H2 sections | 5-10 | UL/OL list items: ≥ 2 = 5, ≥ 5 = 10 |
| **GEO-5: Quote-worthy paragraphs** | **5-10** | 10-40 word paragraphs with a number AND a claim verb (increase/decrease/boost/etc.) — ≥ 1 = 5, ≥ 3 = 10 |
| **GEO-5: Extractable comparison tables** | **10** | Tables with ≥ 3 rows and ≥ 2 header columns |

### Standalone Section Test

This is a unique signal: sections that start with pronouns ("This technique...", "It works by...") are hard for AI to extract independently because they require context from the previous section. Sections that start with topic sentences ("Content marketing is...") can be quoted standalone.

```python
# Count H2 sections where the next paragraph starts with a pronoun
pronoun_starts = 0
for h2 in soup.find_all("h2"):
    next_p = h2.find_next_sibling("p")
    if next_p:
        first_word = next_p.get_text(strip=True).split()[0]
        if first_word.lower() in ("this", "it", "that", "these", "those", "they", "he", "she"):
            pronoun_starts += 1
total_h2_count = len(soup.find_all("h2"))
if total_h2_count < 2:
    standalone_ratio = 0.5  # neutral — not enough sections to evaluate
else:
    standalone_ratio = 1 - (pronoun_starts / total_h2_count)
```

---

## 6c.4 Score Storage (Upsert)

### What It Does

For each post, all 4 scores + a merged signal JSON are upserted into `post_health_scores`:

```sql
INSERT INTO post_health_scores (post_id, ai_citability_score, eeat_score, schema_score, extraction_score, ai_signals)
VALUES ($6, $1, $2, $3, $4, $5)
ON CONFLICT (post_id) DO UPDATE SET
    ai_citability_score = EXCLUDED.ai_citability_score,
    eeat_score = EXCLUDED.eeat_score,
    schema_score = EXCLUDED.schema_score,
    extraction_score = EXCLUDED.extraction_score,
    ai_signals = EXCLUDED.ai_signals
```

### Signal JSON Structure

The `ai_signals` JSONB column stores the merged signal dictionaries from all 4 scorers. E-E-A-T and Schema signals are prefixed to avoid key collisions:

```json
{
  "data_tables": 2,
  "numbered_list_items": 5,
  "first_person_markers": 3,
  "stats_mentions": 1,
  "definition_paragraphs": 2,
  "entity_density_per_1k": 12.5,
  "citation_markers": 4,
  "question_headers": 3,
  "total_headers": 8,
  "question_header_ratio": 0.38,
  "data_points": 7,
  "data_density_per_200w": 1.2,
  "answer_first_200w": true,
  "citability_score": 85,
  "eeat_author_found": true,
  "eeat_author_name": "Brian Dean",
  "eeat_has_author_bio": true,
  "eeat_has_author_credentials": true,
  "eeat_has_visible_date": true,
  "eeat_date_freshness_pts": 15,
  "eeat_date_age_days": 120,
  "eeat_has_visible_updated_date": true,
  "eeat_external_outbound_links": 8,
  "eeat_has_external_links": true,
  "eeat_has_contact_link": true,
  "eeat_word_count_above_median": true,
  "eeat_word_count_ratio": 1.63,
  "eeat_word_count_pts": 7,
  "eeat_h2_count": 7,
  "eeat_has_3plus_h2s": true,
  "eeat_eeat_score": 85,
  "schema_has_schema": true,
  "schema_schema_types": ["Article", "BreadcrumbList", "Organization"],
  "schema_has_high_value_schema": true,
  "schema_article_fields": {"headline": true, "datePublished": true, "author": true, "image": true, "dateModified": true},
  "schema_schema_score": 100,
  "extract_direct_opening": true,
  "extract_h2_with_direct_answer": 4,
  "extract_total_h2": 7,
  "extract_definition_count": 2,
  "extract_has_faq_section": false,
  "extract_faq_qa_pairs": 0,
  "extract_standalone_section_ratio": 0.86,
  "extract_total_list_items": 12,
  "extract_quotable_paragraphs": 3,
  "extract_extractable_tables": 1,
  "extract_extraction_score": 80
}
```

### Idempotency

The `ON CONFLICT (post_id) DO UPDATE` pattern means re-running AI citability overwrites previous scores. This is safe and desirable — the scores are deterministic (same HTML → same scores), so re-running after a re-crawl picks up any content changes.

---

## Downstream Consumers

### Health Scoring (Step 7) — 15% Weight

`health_scoring.py` reads the 4 AI scores and computes an average as "Factor 10: AI Readiness":

```python
ai_readiness_score = average(ai_citability_score, eeat_score, schema_score, extraction_score)
# Weight: W_AI_READINESS = 0.15 (15% of composite health score)
# Fallback: 40.0 (neutral) if any score is NULL
```

The 15% weight is static but the health scorer dynamically rebalances other factors when GA4/GSC data is missing, so in a crawl-only scenario (most common on first run), AI readiness effectively has higher influence.

### Problem Detection (Step 9)

`problem_detection.py:_detect_ai_readiness_issues()` calls `generate_ai_problems()` from `ai_citability.py`, which produces 4 standard problems plus 5 GEO-specific granular problems:

**Standard problems (from 4 main scores):**

| Problem Type | Trigger | Severity |
|-------------|---------|----------|
| `low_ai_citability` | citability < 40 | high (< 20) / medium |
| `weak_eeat` | eeat < 40 | high (< 20) / medium |
| `missing_schema` | schema < 30 | medium |
| `poor_ai_structure` | extraction < 40 | medium |

**GEO-specific problems (from signal details):**

| Problem Type | Trigger | Severity |
|-------------|---------|----------|
| `geo_no_faq_section` | No FAQ section detected | medium |
| `geo_no_question_headers` | 0 total headers OR < 30% question-format (with ≥ 3 headers) | medium |
| `geo_low_data_density` | < 0.5 data points per 200 words | medium |
| `geo_no_answer_first` | First 200 words don't answer the query | medium |
| `geo_missing_faq_schema` | Has FAQ content but no FAQPage schema | high |
| `geo_no_updated_date` | No visible "Last updated"/"Modified" date | low |

### Other Consumers

| Consumer | What It Reads | Purpose |
|----------|--------------|---------|
| Audit Report Router | avg scores, % with schema, % AI-ready | Site-level aggregation for reports |
| Intelligence Router | avg citability/eeat/schema/extraction | Stats API endpoint |
| PDF Report Service | All 4 scores per post | AI readiness section in PDF |
| Fast Recommendations | Scores per post | AI-specific improvement recommendations |

---

## Performance Characteristics

| Metric | Typical Value | Notes |
|--------|---------------|-------|
| Posts per second | ~25-30 | Single HTML parse per post, lxml parser (measured: 28 posts/sec on copyblogger.com) |
| Memory per post | ~200KB | HTML + parsed DOM shared across 4 scorers |
| Total time (150 posts) | 5-6 seconds | All CPU, no I/O wait (measured: 5.26s for 145 posts) |
| Total time (1000 posts) | 35-40 seconds | Linear scaling (estimated from 28 posts/sec) |
| External API calls | **0** | All signals from crawled data |
| Cost per site | **$0.00** | Free — no AI calls |
| DB writes | 1 upsert per post | Batched via asyncpg |

### Why Zero API Calls Matter

Most competitor tools use GPT-4 to evaluate content quality (at $0.01-0.10 per post). This service scores 150 posts in seconds for free by using heuristic signals that correlate with what AI systems actually cite. The tradeoff: heuristics are less nuanced than LLM evaluation, but they're fast, cheap, and deterministic.

---

## Design Decisions

### Why 4 Separate Dimensions Instead of 1 Score

A single "AI readiness score" would hide actionable information. A post with great content (high citability) but no schema markup (score 0) needs a different fix than a well-structured post (high extraction) with no first-person experience (low citability). The 4-dimension model maps directly to specific improvement actions.

### Why Scores Cap at 100 Despite > 100 Points Available

Intentional over-allocation allows different content types to reach 100 through different signal combinations. A data-heavy research paper doesn't need first-person markers. A practitioner case study doesn't need data tables. Both can achieve 100/100 citability through their own strengths.

### Why E-E-A-T Uses eeat_metadata From Full Page HTML

The article extractor strips nav, footer, and sidebar during crawl. But E-E-A-T signals (author schema, contact links, about pages) live in the page chrome. The `eeat_metadata` column (added in migration 041) stores these full-page signals separately, allowing E-E-A-T scoring to see what the article body alone can't provide.

### Why This Runs After Clustering, Not in Step 2

1. **No dependency on embeddings or clusters** — but health scoring (Step 7) needs AI scores, so it must run before Step 7
2. **Pipeline ordering clarity** — Step 2 is "enrichment" (embeddings + readability + PageRank + intent). AI citability is "analysis" — it doesn't create data for other steps to consume (except health scoring)
3. **Re-run behavior** — In the re-analysis pipeline (`_run_full_reanalysis`), AI citability also runs before health scoring to ensure scores are fresh

---

## Database Schema

### Columns on `post_health_scores`

```sql
-- Migration 018_ai_citability_columns.sql
ALTER TABLE post_health_scores
    ADD COLUMN IF NOT EXISTS ai_citability_score FLOAT,
    ADD COLUMN IF NOT EXISTS eeat_score FLOAT,
    ADD COLUMN IF NOT EXISTS schema_score FLOAT,
    ADD COLUMN IF NOT EXISTS extraction_score FLOAT,
    ADD COLUMN IF NOT EXISTS ai_signals JSONB DEFAULT '{}';
```

### Source Column on `posts`

```sql
-- Migration 041_eeat_metadata.sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS eeat_metadata JSONB DEFAULT '{}';
```

**`eeat_metadata` JSONB structure** (populated by `_extract_eeat_metadata()` in `sitemap.py` from full page HTML):

```json
{
  "author_name": "Brian Clark",           // From <meta name="author">, .byline, /author/ links
  "schema_types": ["Article", "WebSite"], // @type values from all JSON-LD blocks
  "has_author_schema": true,              // Any JSON-LD block has "author" key
  "has_visible_date": true,               // <time datetime>, article:published_time meta, date-class elements, or date text patterns
  "has_contact_link": true,               // Any <a> with href/text containing "contact", "about", "team"
  "credible_link_count": 3,               // Links to .gov, .edu, pubmed, reuters, etc.
  "has_og_tags": true,                    // Any <meta property="og:*"> present
  "has_canonical": true,                  // <link rel="canonical"> present
  "has_jsonld": true                      // At least one JSON-LD schema block present
}
```

Keys are consumed by: E-E-A-T scorer (`author_name`, `has_contact_link`, `has_visible_date`), health scoring (`has_og_tags`, `has_canonical`, `has_jsonld` for technical SEO factor), and problem detection (`has_visible_date` for freshness checks).

### UNIQUE Constraint

```sql
-- Migration 030_e2e_schema_fixes.sql
ALTER TABLE post_health_scores
    ADD CONSTRAINT post_health_scores_post_id_unique UNIQUE (post_id);
```

This constraint enables the `ON CONFLICT (post_id) DO UPDATE` upsert pattern used by both AI citability and health scoring.

---

## Post-E2E Fix Log (2026-03-28)

10 issues identified from the initial Copyblogger E2E run. All fixed and verified:

| Issue | Problem | Fix | Before → After |
|-------|---------|-----|----------------|
| S6c-01 | External links: 6+ = 15pts, zero variance | Graduated 5-tier: ≥1=3, ≥3=7, ≥6=10, ≥11=13, ≥21=15 | All posts got 15 → 3-15 range |
| S6c-02 | Author name "none" despite author_found=true | Generic selector cascade now tries nested `<a>` text and full element text | none → "Brian Clark", "Jon Nastor" |
| S6c-03 | has_visible_date at 3.4% (regression) | E2E test was reading `p.eeat_metadata` instead of `p.eeat_signals`; enhanced crawler date detection with date-class elements and text patterns | 3.4% → 100% |
| S6c-04 | has_contact_link at 9.7% (same root cause) | Same fix as S6c-03 — eeat_signals now properly passed | 9.7% → 100% |
| S6c-05 | Definition paragraphs avg 15 (over-detecting) | Tightened regex: require article/determiner after verb | avg 15.08 → 3.4 |
| S6c-06 | Standalone ratio 1.0 for all posts | Posts with < 2 H2s get 0.5 (neutral) instead of 1.0 | avg 1.0 → 0.51 |
| S6c-07 | E-E-A-T avg 54.8 vs Step 2's 64.9 | Fixed by S6c-03/04 (eeat_signals now passed) | 54.8 → 62.7 (range 30-90 matches) |
| S6c-08 | geo_no_question_headers skips 0-H2 posts | Now fires on posts with 0 total headers too | 36 → 36 (Copyblogger has no 0-header posts) |
| S6c-09 | Extraction 63% in 60-69 band | Fixed by S6c-05 (definition fix drops baseline) | stdev 13.8 → 16.8 |
| S6c-10 | Correlation matrix shows "nan" | Display "—" for zero-variance dimensions | nan → — |

### Post-E2E Fix Log Round 2 (2026-03-28)

9 additional issues identified from the round 1 verification run. All addressed:

| Issue | Problem | Fix | Before → After |
|-------|---------|-----|----------------|
| S6c-11 | E-E-A-T stdev decreased 7.5→6.3 despite signal fixes | Verified link graduation applied; added word count graduation (5-tier: 0/2/5/7/10 based on ratio to site median) | Binary 10-pt swing → 5-tier 0-10 range |
| S6c-12 | Citability floor dropped 35→30 | Verified: correct behavior from definition fix (S6c-05). Low-signal posts now correctly score lower. | No fix needed |
| S6c-13 | Extraction floor dropped 35→10 | Verified: "Here's Some Cool Copy for July 4th" (553w, no headings, no FAQ) correctly scores 10. | No fix needed |
| S6c-14 | Composite 44/100 dragged by Schema=0 | Added "biggest gap" indicator to AIReadinessCard frontend component. Shows which dimension is dragging the composite down when gap ≥ 20 points. | No gap hint → "Schema Markup (0/100) is your biggest gap" |
| S6c-15 | Citability/E-E-A-T correlation r=0.56 | 31% shared variance. Not high enough (0.8+) to distort results. No fix for $149 product. | No fix needed — monitor |
| S6c-16 | E2E test only shows aggregates, not per-post signals | Added "Sample Post Deep Dive" section: full signal breakdown for best, median, and worst composite posts | No deep dive → 3 posts with full signal tables |
| S6c-17 | Direct opening 89.7% — limited differentiation | Verified: correctly identifies 10% with weak openings. 25-point weight appropriate for answer-first structure. | No fix needed |
| S6c-18 | has_author_credentials jumped 88.3%→99.3% | Fallback was searching 5000 chars of body text for credential keywords (false positives). Tightened to only search bio text or first 800 chars near author name. | 99.3% (144/145) → 89.0% (129/145) |
| S6c-19 | Schema scorer never tested on schema-having content | Added 6 synthetic JSON-LD test cases: no schema, complete Article, incomplete Article, multi-type, basic-only, @graph array. ALL PASSED. | 0 test cases → 6 (all pass) |

### Final Scores After All Fixes (copyblogger.com, 145 posts)

| Dimension | Initial | Round 1 | Round 2 | Round 3 | Trend |
|-----------|---------|---------|---------|---------|-------|
| Citability | mean=59.8, stdev=13.9 | mean=57.5, stdev=15.3 | mean=57.5, stdev=15.3 | mean=57.5, stdev=15.3 | Stable, good variance |
| E-E-A-T | mean=54.8, stdev=7.5 | mean=62.7, stdev=6.3 | mean=60.6, stdev=5.8 | mean=60.6, stdev=5.7 | Mean recovered; stdev plateau at ~6 is site-specific |
| Schema | mean=0.0 | mean=0.0 | mean=0.0 | mean=0.0 | Expected (no JSON-LD on site) |
| Extraction | mean=65.3, stdev=13.8 | mean=55.9, stdev=16.8 | mean=55.9, stdev=16.8 | mean=55.9, stdev=16.8 | Stable, good variance |
| Composite | mean=45.0 | mean=44.0 | mean=43.5 | mean=43.5 | Stable |

### Post-E2E Fix Log Round 3 (2026-03-28)

6 issues identified from the round 2 analysis. All fixed:

| Issue | Problem | Fix | Before → After |
|-------|---------|-----|----------------|
| S6c-20 | E-E-A-T stdev declining, binary H2 signal (3+=15, else=0) too rare | Graduated H2 count: 0=0, 1-2=5, 3-5=10, 6+=15. Creates spread across all posts, not just the 1.4% with 3+ H2s. | Binary 0/15 → 4-tier 0/5/10/15 |
| S6c-21 | External link graduation unverified in E2E output | Added per-tier E-E-A-T link points distribution to E2E. Verified: 10pts=24 posts, 13pts=98 posts, 15pts=23 posts. | No distribution → explicit per-tier counts |
| S6c-22 | 18 posts/sec — 4x redundant HTML parsing per post | Refactored all 4 compute_* functions to accept optional pre-parsed `soup` param. `score_site()` now parses once, passes to all 4 scorers. Already using lxml. | 18 posts/sec → 28 posts/sec (56% faster) |
| S6c-23 | Spec had two conflicting link graduation scales | Round 1 fix log said "3-tier 10/13/15". Code is actually 5-tier (≥1=3, ≥3=7, ≥6=10, ≥11=13, ≥21=15). Fixed fix log entry. | Conflicting → consistent 5-tier |
| S6c-24 | eeat_metadata JSON structure undocumented | Added full JSONB schema reference: 9 keys with types, sources, and consumers. | Undocumented → documented |
| S6c-25 | Round 2 full E2E results not included | Round 3 E2E saved as STEP6c-TEST-RESULTS.md with all sections: distributions, signal prevalence, schema validation (6 tests, all pass), link tier distribution, sample post deep dive (3 posts), observations. | Missing → saved |

### 25 Issues Across 3 Rounds — All Fixed

S6c-01 through S6c-25: 25 issues identified, investigated, and resolved across 3 rounds of E2E testing. 14 required code changes, 5 required test improvements, 3 were documentation fixes, and 3 were verified as correct behavior.

### All Previously Open Issues — Now Resolved

| Issue | Was | Now |
|-------|-----|-----|
| S6c-20 | E-E-A-T stdev declining, binary H2 signal too rare | **FIXED.** H2 graduated: 0=0, 1-2=5, 3-5=10, 6+=15. Range [35, 87]. Stdev 5.7 is Copyblogger-specific (uniform age/author). |
| S6c-21 | Link graduation unverified in E2E | **FIXED.** Per-tier counts: 10pts=24, 13pts=98, 15pts=23. 5-tier confirmed. |
| S6c-23 | Two conflicting link scales in spec | **FIXED.** Fix log corrected to 5-tier (≥1=3, ≥3=7, ≥6=10, ≥11=13, ≥21=15). |
| S6c-24 | eeat_metadata undocumented | **FIXED.** Full 9-key JSONB schema added to Database Schema section. |
| S6c-25 | No full E2E output | **FIXED.** STEP6c-TEST-RESULTS.md: full distributions, signal prevalence, schema validation (6/6), link tier breakdown, sample post deep dive (3 posts), observations. |

### Performance After Single-Parse Optimization

| Metric | Before (4x parse) | After (1x parse) | Improvement |
|--------|-------------------|-------------------|-------------|
| Posts/sec | 18 | 28 | **56% faster** |
| 145 posts | 7.95s | 5.26s | **34% reduction** |
| Estimated 1000 posts | 55s | 36s | |

**All previously open items (S6c-20 through S6c-25) were resolved in Round 3.** The link graduation scale is verified as 5-tier in code, per-tier distribution is in the E2E output, eeat_metadata JSONB schema is documented, H2 count signal is graduated, and the full E2E results are saved with sample post deep dives. See Round 3 fix log above.