# Pipeline Steps 2-5: Content Enrichment & Analytics Sync

> **Scope:** Everything that happens after Step 1 (crawl + normalize + store) and before Step 6 (clustering). This step enriches each post with embeddings (Step 2), readability scores (Step 3), PageRank (Step 4), and intent classification (Step 5), and syncs external analytics (GA4 + GSC). No clustering, no problem detection, no recommendations — just enriching raw posts with computed signals.
>
> **Note:** AI Citability scoring was originally documented here as Step 2e. It now runs at Code Step 6c (after clustering, before health scoring) so that the health scorer's 15% AI readiness weight is populated just before it's needed. See `PIPELINE-STEP3-CLUSTERING.md` Step Mapping table.

---

## Pipeline Position

After Step 1 stores posts in the `posts` table and internal links in `internal_links`, the full pipeline runs these sub-steps sequentially:

```
Step 1: Crawl + Normalize (done)
   ↓
Step 2a: Embeddings (OpenAI text-embedding-3-small)        ← $0.01-0.10 per site
Step 2b: Readability scoring (Flesch-Kincaid, pure Python)  ← free, ~0.5s
Step 2c: Internal PageRank (networkx, CPU-bound)            ← free, ~1s
Step 2d: Intent classification (regex patterns)             ← free, ~0.1s
[AI Citability moved to Code Step 6c — after clustering, before health scoring]
   ↓
Analytics Sync (runs independently, not blocking pipeline):
Step 2e: GA4 metrics sync (Google Analytics Data API)
Step 2f: GSC metrics sync (Search Console API)
   ↓
Step 3: Clustering (next pipeline step)
```

Each sub-step is independently error-handled via `_pipeline_step()` — a failure in readability scoring doesn't block embedding or clustering.

---

## 2a. Embedding Generation (`services/embeddings.py`)

### What It Does

Converts each post's text content into a 1536-dimensional dense vector using OpenAI's `text-embedding-3-small` model. These vectors are stored in pgvector and used downstream for:
- **Clustering** (UMAP + HDBSCAN groups similar posts)
- **Cannibalization detection** (cosine similarity between posts in the same cluster)
- **RAG/Oracle** (semantic search for user Q&A)
- **Content gap analysis** (find missing topics via vector space gaps)

### API & Model

| Parameter | Value |
|-----------|-------|
| **Model** | `text-embedding-3-small` |
| **Dimensions** | 1536 |
| **Max tokens per text** | 8,191 (model limit) |
| **Truncation** | 20,000 characters (~5,000 tokens) |
| **Batch size** | 100 texts per API call |
| **Rate limit** | 3 requests/second (self-imposed via `RateLimiter`) |
| **Cost** | ~$0.02 per 1M tokens → ~$0.0001 per post → ~$0.01-0.10 per site |

### Text Preparation (`_prepare_text`)

Each post's text is prepared as:
```
{title}\n\n{body_text}
```

Title is prepended because it carries dense keyword signals — "How to Build Backlinks for SEO" in the title ensures the embedding captures the topic even if body text is more narrative. Truncated to 20,000 chars if longer.

### Change Detection

The key optimization: **content_hash comparison**. The query only selects posts that need (re-)embedding:

```sql
SELECT p.id, p.title, p.body_text, p.content_hash
FROM posts p
LEFT JOIN post_embeddings pe ON pe.post_id = p.id
WHERE p.site_id = $1
  AND p.body_text IS NOT NULL AND p.body_text != ''
  AND (pe.id IS NULL OR pe.content_hash != p.content_hash)
```

This means:
- **New posts** (no embedding row yet): embedded
- **Changed posts** (content_hash differs from stored hash): re-embedded
- **Unchanged posts** (hash matches): skipped entirely — zero API cost

Since Step 1's content hash is now whitespace-normalized (fix #12), trafilatura upgrades that only change spacing won't trigger re-embeds.

### Batch Processing

Posts are processed in batches of 100:
1. Prepare 100 texts
2. One API call: `client.embeddings.create(model=MODEL, input=texts, dimensions=1536)`
3. Store each resulting vector individually via upsert

**Fallback on batch failure:** If the batch API call fails (e.g., one text is too long or contains invalid characters), falls back to single-text calls per post in that batch. This prevents one bad post from blocking the entire batch.

### Storage

```sql
INSERT INTO post_embeddings (post_id, embedding, model, content_hash)
VALUES ($1, $2::vector, $3, $4)
ON CONFLICT (post_id) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    content_hash = EXCLUDED.content_hash,
    updated_at = NOW()
```

Vector format: pgvector bracket notation `[0.123,0.456,...]` — the `_vector_to_pgvector()` helper serializes the Python list.

### `post_embeddings` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `post_id` | UUID | FK → `posts(id)` CASCADE, UNIQUE |
| `embedding` | vector(1536) | pgvector type |
| `model` | TEXT | `'text-embedding-3-small'` |
| `content_hash` | TEXT | Matches `posts.content_hash` when up-to-date |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### pgvector Index

```sql
-- HNSW index for fast approximate nearest neighbor search
-- Used by RAG/Oracle, cannibalization detection, content gap analysis
CREATE INDEX idx_post_embeddings_hnsw
    ON post_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

---

## 2b. Readability Scoring (`services/readability.py`)

### What It Does

Computes Flesch Reading Ease (0-100) and Flesch-Kincaid Grade Level for each post. Pure Python — no API calls, no external libraries.

### Formulas

**Flesch Reading Ease:**
```
206.835 - 1.015 × (words/sentences) - 84.6 × (syllables/words)
```

| Score | Level | Grade |
|-------|-------|-------|
| 90-100 | Very easy | 5th grade |
| 80-89 | Easy | 6th grade |
| 70-79 | Fairly easy | 7th grade |
| **60-69** | **Standard** | **8th-9th grade** ← sweet spot for blogs |
| 50-59 | Fairly difficult | 10th-12th grade |
| 30-49 | Difficult | College |
| 0-29 | Very confusing | Graduate |

**Flesch-Kincaid Grade Level:**
```
0.39 × (words/sentences) + 11.8 × (syllables/words) - 15.59
```
Returns US school grade (e.g., 8.0 = 8th grade reading level).

### Processing

1. Fetches all posts with `body_text` longer than 100 characters.
2. **Language check:** Uses `langdetect` to detect language from first 1000 chars. Skips non-English posts (Flesch-Kincaid is only valid for English).
3. Computes FRE + grade level.
4. **Paragraph-level breakdown:** Splits on `\n\n`, computes FRE for each paragraph > 50 chars. Flags paragraphs with FRE < 30 and > 20 words as "hard to read." Stores top 3 hardest as `readability_details` (JSONB).

### Syllable Counting

Pure Python heuristic:
- Split text into words (regex `\b[a-z]+\b`)
- Per word: count vowel groups (`[aeiouy]+`)
- Strip trailing silent 'e' (except `-le` endings)
- Minimum 1 syllable per word

### Storage

Updates `posts` table directly:

| Column | Type | Notes |
|--------|------|-------|
| `readability_score` | FLOAT | Flesch Reading Ease (0-100) |
| `grade_level` | FLOAT | Flesch-Kincaid Grade Level |
| `readability_details` | JSONB | Top 3 hardest paragraphs: `[{"index": 5, "flesch": 22.1, "preview": "..."}]` |

### Thresholds for Problem Detection

```python
READABILITY_TOO_COMPLEX = 40.0   # Below this → flag as problem
READABILITY_IDEAL_MIN = 60.0
READABILITY_IDEAL_MAX = 80.0
```

---

## 2c. Internal PageRank (`services/pagerank.py`)

### What It Does

Runs Google's PageRank algorithm on the site's internal link graph using `networkx`. Every post gets an Internal Authority Score (0-1) showing how much link juice flows to it.

This goes beyond binary "has links / doesn't" — a pillar post with 50 inbound links from dead-weight pages is different from one with 5 inbound links from other pillars.

### How It Works

1. Fetches all resolved internal links (both `source_post_id` and `target_post_id` must exist):
   ```sql
   SELECT il.source_post_id, il.target_post_id
   FROM internal_links il
   JOIN posts ps ON ps.id = il.source_post_id
   JOIN posts pt ON pt.id = il.target_post_id
   WHERE ps.site_id = $1 AND pt.site_id = $1
   ```

2. Fetches all post IDs (including those with no links).

3. Builds a `networkx.DiGraph` and runs `nx.pagerank(G, alpha=0.85)`:
   - `alpha=0.85` is the standard damping factor (15% chance of random jump)
   - `max_iter=100`, `tol=1e-6`
   - Fallback on convergence failure: `max_iter=200`, `tol=1e-4`
   - **CPU-bound** → offloaded to `asyncio.to_thread()`

4. If no internal links exist, assigns equal PageRank to all posts (`1/N`).

### Storage

Updates `post_health_scores.internal_pagerank` via batch `executemany`.

### Additional Capabilities

- `detect_broken_links()` — finds internal links whose `target_url` doesn't match any post (already NULL `target_post_id`)
- `count_outbound_links()` — counts external links per post (posts with 0 outbound lack citations — content quality signal)

---

## 2d. Intent Classification (`services/fast_intent.py`)

### What It Does

Classifies each post into one of four search intent categories:
- **Transactional** — pricing, signup, demo, free trial
- **Commercial** — best, top 10, vs, comparison, review, buyer's guide
- **Navigational** — login, support, contact, docs, about
- **Informational** — everything else (default)

### How It Works

Zero API calls. Three-tier pattern matching:

**Tier 1 — URL slug patterns (highest signal):**
```python
_TRANSACTIONAL_SLUGS = re.compile(r"(pricing|demo|trial|signup|get-started|plans)")
_COMMERCIAL_SLUGS = re.compile(r"(best-|top-|vs-|-comparison|-alternative|-review)")
_NAVIGATIONAL_SLUGS = re.compile(r"(login|signin|support|contact|docs|help|about|careers)")
```

**Tier 2 — Title + slug keyword patterns:**
```python
_TRANSACTIONAL = re.compile(r"\b(pricing|buy|purchase|sign\s*up|free\s*trial|demo|...)\b")
_COMMERCIAL = re.compile(r"\b(best|top\s*\d+|vs\.?|comparison|alternative|review|...)\b")
_NAVIGATIONAL = re.compile(r"\b(login|dashboard|support|contact|help\s*center|docs|...)\b")
```

**Tier 3 — Default:** Everything that doesn't match = `"informational"`.

Accuracy: ~85-90% for B2B/SaaS content.

### Storage

Updates `posts.content_intent` directly. Logs the distribution:
```
Fast intent classification: 147 posts — commercial=12, informational=130, navigational=3, transactional=2
```

---

## ~~2e.~~ AI Citability Scoring — MOVED TO CODE STEP 6c

> **This section is kept for reference.** AI Citability now runs at Code Step 6c (after clustering, before health scoring) in `ingestion.py:_run_full_pipeline`. The service code (`services/ai_citability.py`) is unchanged — only its position in the pipeline moved. See `PIPELINE-STEP3-CLUSTERING.md` for the current step mapping.

### What It Does

Scores each post on 4 dimensions of AI-era SEO readiness. **Zero API calls** — all signals derived from already-crawled `body_html` + `body_text`.

### Dimension 1: AI Citability Score (0-100)

How likely an AI system will cite/quote this post:

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Data tables (`<table>`) | 20 | HTML tag count |
| Numbered/ordered lists (`<ol>`) | 15 | `<li>` count in `<ol>` tags |
| First-person experience language | 20 | Regex: "in our testing", "we found", "I tested" |
| Original statistics/data | 20 | Regex: percentages, large numbers, "our data shows" |
| Definition paragraphs | 10 | Regex: "[Topic] is/are/refers to..." |
| Entity density (proper nouns per 1K words) | 10 | Title Case word sequences |
| Credible external citations | 5 | Regex: "according to", .gov, .edu, journal |
| Question-format H2/H3 headers | 15 | Regex: headers starting with what/how/why/when/... |
| Data density (data points per 200 words) | 10 | Numbers, percentages, dollar amounts |
| Answer-first structure (direct answer in first 200 words) | 10 | Pattern match in opening text |

### Dimension 2: E-E-A-T Score (0-100)

Experience, Expertise, Authoritativeness, Trustworthiness signals:

> E-E-A-T weights were calibrated across 4 iterations against Copyblogger (145 posts) and Backlinko (149 posts). The goal is a score range of 30-90 across a typical content marketing site, with post-specific signals creating meaningful variance between strong and weak posts.

**Site-wide signals (35 pts max):**

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Author byline present | 15 | `itemprop="author"`, `.author`, `.byline`, meta tag, text pattern "Written by", or crawl-time `eeat_metadata.author_name` |
| Author bio present | 10 | Bio section with class/id matching author/bio/contributor, or author page link |
| Contact/About page link | 10 | Links containing "contact", "about", "team" in body or crawl metadata |

**Post-specific signals (65 pts max):**

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Author credentials in bio | 10 | Credential keywords (CEO, PhD, years experience, founder, etc.) in bio text or nearby page text |
| Date freshness (graduated) | 0-15 | Uses most recent of modified_date/publish_date. ≤6mo = 15, 6-12mo = 10, 1-2yr = 5, >2yr = 0 |
| Post-level outbound links (graduated) | 0-15 | Count links in body to any external domain (excl. social share). 6+ = 15, 3-5 = 10, 1-2 = 5, 0 = 0 |
| Word count above site median | 10 | Post word count ≥ site median → 10 pts. Creates automatic ~50/50 variance |
| 3+ H2 sections | 15 | Count H2 headings in post. 3+ H2s = 15 pts. Well-structured posts signal editorial quality |

> **Note:** Author schema in JSON-LD is tracked as a signal (`has_author_schema`) but does **not** contribute to the E-E-A-T score. Schema signals belong in the Schema dimension — including them here would double-penalize sites without structured data.

### Dimension 3: Schema Score (0-100)

Structured data completeness:

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Has any JSON-LD schema | 30 | Parse `<script type="application/ld+json">` |
| Has high-value schema type (Article/FAQ/HowTo) | 30 | Check `@type` against whitelist |
| Article schema completeness (headline, date, author, image) | 30 | Check required field presence |
| Multiple schema types (bonus) | 10 | Count distinct `@type` values |

### Dimension 4: Extraction Score (0-100)

How easily an AI can extract a direct answer:

| Signal | Points | Detection Method |
|--------|--------|-----------------|
| Direct answer in first 100 words | 25 | Definitive statement + number/definition |
| H2 sections start with concise answer (15-80 words) | 25 | Pattern match after each H2/H3 |
| Definition paragraphs present | 20 | "[Topic] is/are/refers to..." |
| FAQ/Q&A structure | 20 | FAQ heading or ≥3 question-format H3s with short answers |
| Standalone section ratio (no pronoun starts) | 10 | Check first word after H2s for this/it/that |
| Structured lists under headings | 10 | `<ul>` and `<ol>` item count |
| Quotable paragraphs (10-40 words with numbers) | 10 | Short paragraphs with numbers + action verbs |
| Extractable comparison tables | 10 | Tables with ≥3 rows and ≥2 headers |

### Storage

Upserts into `post_health_scores`:

| Column | Type | Notes |
|--------|------|-------|
| `ai_citability_score` | FLOAT | 0-100 |
| `eeat_score` | FLOAT | 0-100 |
| `schema_score` | FLOAT | 0-100 |
| `extraction_score` | FLOAT | 0-100 |
| `ai_signals` | JSONB | All individual signal values for drill-down |

### Problem Generation

`generate_ai_problems()` converts low scores into actionable problems:

| Problem Type | Trigger | Severity |
|-------------|---------|----------|
| `low_ai_citability` | Citability < 40 | high if < 20, else medium |
| `weak_eeat` | E-E-A-T < 40 | high if < 20, else medium |
| `missing_schema` | Schema < 30 | medium |
| `poor_ai_structure` | Extraction < 40 | medium |
| `geo_no_faq_section` | No FAQ detected | medium |
| `geo_no_question_headers` | Question-format H2s < 30% | medium |
| `geo_low_data_density` | Data density < 0.5 per 200 words | medium |
| `geo_no_answer_first` | No direct answer in first 200 words | medium |
| `geo_missing_faq_schema` | Has FAQ content but no FAQPage schema | high |
| `geo_no_freshness_date` | No visible last-updated date | low |

---

## 2f. GA4 Analytics Sync (`services/ga4.py`)

### What It Does

Pulls per-URL traffic metrics from Google Analytics 4 Data API into `ga4_metrics`.

### Prerequisites

- User must have connected Google OAuth (`/sites/{site_id}/google/connect`)
- Encrypted `google_tokens` stored on `sites` table
- `ga4_property_id` must be set

### OAuth Flow

1. Frontend redirects to `/sites/{site_id}/google/connect`
2. Backend generates OAuth URL with HMAC-signed state (contains `site_id`)
3. User consents at Google
4. Google redirects to `/auth/google/callback` with auth code
5. Backend exchanges code for tokens, encrypts refresh_token with Fernet, stores on `sites.google_tokens`
6. Scopes requested: `webmasters.readonly` (GSC) + `analytics.readonly` (GA4)

### Incremental Sync

```sql
SELECT MAX(date) FROM ga4_metrics g JOIN posts p ON p.id = g.post_id WHERE p.site_id = $1
```

- **First sync:** Fetches 90 days of history
- **Subsequent syncs:** Only fetches from `last_sync_date + 1` to yesterday (GA4 data has ~24h lag)
- If `start_date > end_date`: no-op (already up to date)

### API Call

```python
RunReportRequest(
    property=f"properties/{property_id}",
    date_ranges=[DateRange(start_date=..., end_date=...)],
    dimensions=[Dimension(name="pagePath"), Dimension(name="date")],
    metrics=[
        Metric(name="screenPageViews"),
        Metric(name="sessions"),
        Metric(name="engagedSessions"),
        Metric(name="averageSessionDuration"),
        Metric(name="bounceRate"),
        Metric(name="conversions"),
    ],
    offset=offset,
    limit=10000,
)
```

- Paginated: 10,000 rows per request
- **Synchronous Google client** → wrapped in `asyncio.to_thread()` to avoid blocking
- Rate limited: 2 req/sec

### URL Matching

GA4 returns `pagePath` (e.g., `/blog/seo-guide`). The sync service builds a `path → post_id` map by parsing stored post URLs:

```python
parsed = urlparse(row["url"])
path = parsed.path.rstrip("/") or "/"
url_map[path] = row["id"]
```

Only rows matching a known post path are stored. Unmatched paths (404 pages, non-blog URLs) are silently skipped.

### Storage

```sql
INSERT INTO ga4_metrics (post_id, date, pageviews, sessions, engaged_sessions,
                         avg_engagement_time_seconds, bounce_rate, conversions)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (post_id, date) DO UPDATE SET ...
```

### `ga4_metrics` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `post_id` | UUID | FK → `posts(id)` CASCADE |
| `date` | DATE | Daily granularity |
| `pageviews` | INTEGER | `screenPageViews` from GA4 |
| `sessions` | INTEGER | |
| `engaged_sessions` | INTEGER | |
| `avg_engagement_time_seconds` | FLOAT | |
| `bounce_rate` | FLOAT | |
| `conversions` | INTEGER | |
| `created_at` | TIMESTAMPTZ | |
| Unique constraint | | `(post_id, date)` |

---

## 2g. GSC Analytics Sync (`services/gsc.py`)

### What It Does

Pulls per-URL search performance data from Google Search Console API into `gsc_metrics`. This is the most valuable analytics data — shows which queries each post ranks for, at what position, with how many impressions and clicks.

### Incremental Sync

Same pattern as GA4:
- **First sync:** 90 days of history
- **Subsequent syncs:** From `last_sync_date + 1` to `today - 3` (GSC data has ~3 day lag)

### API Call

```python
request_body = {
    "startDate": start_date.isoformat(),
    "endDate": end_date.isoformat(),
    "dimensions": ["page", "query", "date"],
    "rowLimit": 25000,      # GSC max per request
    "startRow": start_row,
}
```

- Paginated: 25,000 rows per request
- Returns: page URL × query × date × metrics
- Rate limited: 2 req/sec
- **Synchronous API client** → `asyncio.to_thread()`

### URL Matching

GSC returns full page URLs. The sync builds a broader URL map:

```python
url_map[row["url"].rstrip("/")] = row["id"]           # Full URL
url_map[f"{scheme}://{netloc}{path}"] = row["id"]      # Reconstructed URL
```

This handles minor URL format differences between GSC and stored URLs.

### Storage

```sql
INSERT INTO gsc_metrics (post_id, date, query, impressions, clicks, avg_position, ctr)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (post_id, date, query) DO UPDATE SET ...
```

### `gsc_metrics` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `post_id` | UUID | FK → `posts(id)` CASCADE |
| `date` | DATE | Daily granularity |
| `query` | TEXT | Search query that triggered the impression |
| `impressions` | INTEGER | Times the URL appeared in search results |
| `clicks` | INTEGER | Times users clicked through |
| `avg_position` | FLOAT | Average ranking position for this query |
| `ctr` | FLOAT | Click-through rate |
| `created_at` | TIMESTAMPTZ | |
| Unique constraint | | `(post_id, date, query)` |

### Database Indexes

```sql
CREATE INDEX idx_ga4_post_date ON ga4_metrics(post_id, date);
CREATE INDEX idx_gsc_post_date ON gsc_metrics(post_id, date);
CREATE INDEX idx_gsc_query ON gsc_metrics(query);
```

---

## Chunk Embeddings (for RAG & Section-Level Cannibalization)

### What It Does

In addition to whole-post embeddings (Step 2a), the system also generates **chunk-level embeddings** — splitting each post by H2/H3 headings and embedding each section independently.

### Why Chunks?

A "Technical SEO Guide" covering canonicals + sitemaps + robots.txt gets 3+ chunks, each compared independently against other posts. This catches 30-40% more true cannibalization than whole-post comparison, because two posts can have low overall similarity but high section-level overlap.

### Schema

> **Note:** These chunk tables are documented here for schema completeness but are populated and used by **Step 8b (Chunk Confirmation)**, not during Steps 2-5. See `PIPELINE-STEP8B-CHUNK-CONFIRMATION.md` for the chunk pipeline logic.

**`content_chunks` table:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `post_id` | UUID | FK → `posts(id)` CASCADE |
| `site_id` | UUID | FK → `sites(id)` CASCADE |
| `chunk_index` | INTEGER | 0-based order within post |
| `heading` | TEXT | H2/H3 heading that starts this chunk (NULL for intro) |
| `heading_level` | INTEGER | 2 for H2, 3 for H3, NULL for intro |
| `body_text` | TEXT | Chunk content |
| `word_count` | INTEGER | |
| `start_char` | INTEGER | Character offset in original body |
| `end_char` | INTEGER | |
| Unique constraint | | `(post_id, chunk_index)` |

**`chunk_embeddings` table:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `chunk_id` | UUID | FK → `content_chunks(id)` CASCADE, UNIQUE |
| `post_id` | UUID | FK → `posts(id)` CASCADE |
| `embedding` | vector(1536) | pgvector type |
| `created_at` | TIMESTAMPTZ | |

**HNSW index:**
```sql
CREATE INDEX idx_chunk_embeddings_hnsw
    ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

---

## Summary: Data Available After Step 2

After Step 2 completes, the database contains (in addition to Step 1 data):

| Table | Records | Populated By |
|-------|---------|-------------|
| `post_embeddings` | 1 per post (1536-dim vector) | 2a: OpenAI embeddings |
| `posts.readability_score` | Flesch Reading Ease per post | 2b: Readability |
| `posts.grade_level` | Flesch-Kincaid grade per post | 2b: Readability |
| `posts.readability_details` | JSONB: hardest paragraphs | 2b: Readability |
| `post_health_scores.internal_pagerank` | Authority flow score per post | 2c: PageRank |
| `posts.content_intent` | informational/commercial/transactional/navigational | 2d: Intent |
| `post_health_scores.ai_citability_score` | AI citability (0-100) | **Moved to Code Step 6c** |
| `post_health_scores.eeat_score` | E-E-A-T (0-100) | **Moved to Code Step 6c** |
| `post_health_scores.schema_score` | Schema completeness (0-100) | **Moved to Code Step 6c** |
| `post_health_scores.extraction_score` | AI extraction readiness (0-100) | **Moved to Code Step 6c** |
| `post_health_scores.ai_signals` | JSONB: all individual signal values | **Moved to Code Step 6c** |
| `ga4_metrics` | Daily traffic per post (90 days) | 2e: GA4 sync |
| `gsc_metrics` | Daily search queries per post (90 days) | 2f: GSC sync |
| `content_chunks` | Sections split by H2/H3 | Chunk pipeline |
| `chunk_embeddings` | Per-section vectors | Chunk pipeline |

**Not yet populated:**
- `clusters` / `post_clusters` — requires Step 3 (Clustering)
- `post_health_scores.composite_score` / `role` / `trend` — requires Step 4 (Health Scoring)
- `cannibalization_pairs` — requires Step 5
- `content_problems` — requires Step 6
- `recommendations` — requires Step 7

### Cost per Site

| Sub-step | External API | Estimated Cost |
|----------|-------------|---------------|
| Embeddings | OpenAI | ~$0.01-0.10 (depends on post count + length) |
| Readability | None | Free |
| PageRank | None | Free |
| Intent | None | Free |
| AI Citability | None | Free |
| GA4 Sync | Google (free tier) | Free |
| GSC Sync | Google (free tier) | Free |
| **Total** | | **~$0.01-0.10 per site** |

### Performance

| Sub-step | Estimated Time (150-post site) | Notes |
|----------|-------------------------------|-------|
| Embeddings | 5-15s | 2 batches of 100, 3 req/sec limit |
| Readability | <1s | Pure Python, no I/O |
| PageRank | <1s | networkx in thread |
| Intent | <0.5s | Regex only |
| AI Citability | 2-5s | HTML parsing per post |
| GA4 Sync | 5-30s | Depends on date range + data volume |
| GSC Sync | 10-60s | Depends on query volume |
| **Total** | **~20-110s** | |

THOUGHTS:

# Tended Pipeline — Complete Issues List

**Compiled from all Step 1 and Step 2 reviews.**
**Every issue has a priority, description, impact, and fix.**

---

## STEP 1: SITE CREATION & CONTENT INGESTION

### FIXED (confirmed in code)

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| S1-01 | WP meta description used excerpt instead of real meta tag | Launch blocker | ✅ Fixed |
| S1-02 | WP connector missing language + page_type | Launch blocker | ✅ Fixed |
| S1-03 | No canonical URL resolution | Launch blocker | ✅ Fixed |
| S1-04 | Internal links extracted from full page HTML instead of main content | Launch blocker | ✅ Fixed |
| S1-05 | No robots.txt checking | Launch blocker | ✅ Fixed |
| S1-06 | Dangerous "first `<time>` tag" date fallback | Launch blocker | ✅ Fixed |
| S1-07 | Skipped pages were silent — no logging | Launch blocker | ✅ Fixed |
| S1-08 | Orphaned crawl jobs — status mismatch + no staleness recovery | Launch blocker | ✅ Fixed |
| S1-09 | Crawl history erased on new crawl | Launch blocker | ✅ Fixed |
| S1-10 | WP connector ignores pages (only fetches /wp/v2/posts) | Pre-customer | ✅ Fixed |
| S1-11 | url_patterns no validation | Pre-customer | ✅ Fixed |
| S1-12 | Content hash sensitive to whitespace | Pre-customer | ✅ Fixed |
| S1-13 | Individual INSERT per post — 3N queries for N posts | Pre-scaling | ✅ Fixed |
| S1-14 | max_pages truncates arbitrarily (random/alphabetical sitemap order) | Pre-scaling | ✅ Fixed |
| S1-15 | No global per-domain rate limit across concurrent crawls | Pre-scaling | ✅ Fixed |
| S1-16 | BackgroundTask dies on process restart | Pre-scaling | ✅ Fixed |
| S1-17 | Link resolution Pass 2 SQL was redundant | Pre-scaling | ✅ Fixed |

### KNOWN LIMITATIONS (documented, not fixing)

| # | Issue | Impact | Mitigation |
|---|-------|--------|------------|
| S1-KL1 | Word count may overcount by 10-15% due to trafilatura artifacts (image alt text, caption text) | Word counts are directionally correct but not precise. "3,095 average" is correct for "deep-form content" label. Thin content detection still works because it's relative within the site. | Treat word counts as relative indicators within a site. Don't compare across tools. The descriptor labels (short-form, medium-form, long-form, deep-form) have wide enough ranges that 10-15% inflation doesn't change the label. |
| S1-KL2 | JS rendering only fires on framework markers (id="__next", _nuxt, data-reactroot) | Sites with custom JS renderers or uncommon SPA frameworks may produce empty body_text, causing posts to be skipped entirely. | Current detection covers Next.js, Nuxt, React, and Vue. These are 90%+ of content marketing sites you'll encounter in cold outreach. Sites with custom JS renderers would need manual url_patterns configuration. Not a problem for Backlinko, Copyblogger, or any WordPress/static site. |

### OPEN — From E2E Testing (Copyblogger)

---

#### S1-18: 50-character minimum content gate is too low

**Priority:** Fix before launch
**Found in:** Copyblogger E2E test

**Description:** The 50-character gate on body_text is meant to filter non-content pages (login, image galleries, tag archives). But it's too permissive. Copyblogger's "Thank You" page (18 words, ~80 characters) and a login page (19 words, ~85 characters) both passed the gate and entered the dataset as blog posts.

**Impact on reports:** These near-empty pages inflate post counts and drag down site averages (word count, readability, health score). If either page ends up in the Top 5 Posts Needing Attention, it looks like the tool is analyzing junk instead of real content. A prospect seeing "Thank You (score: 12)" in their Top 5 would question whether the tool understands their site.

**Fix:** Add a word count floor alongside the character floor. Require BOTH: body_text >= 50 characters AND word_count >= 100. A 100-word minimum means the shortest post in the dataset is at least a solid paragraph — enough content to meaningfully analyze. This filters "Thank You" (18 words) and login pages (19 words) without filtering legitimate short posts (a 100-word post is still ~500-600 characters, well above the 50-char gate).

**Files to change:** `services/sitemap.py` (in `_fetch_and_extract`, after body_text extraction), `services/wordpress.py` (in `_normalize_post`, after body_text extraction). Add check: `if len(body_text.split()) < 100: return None`

---

#### S1-19: Heading extraction includes sidebar/template headings

**Priority:** Fix before launch
**Found in:** Copyblogger E2E test

**Description:** Headings are extracted from the full page HTML, not just the main content area. This means sidebar headings ("Primary Sidebar," "Reader Interactions," "You might also like"), footer headings, and author byline H4s ("Brian Clark") are included in the heading analysis. The sitewide heading filter (80% threshold) doesn't catch these because the exact text varies per page (different "You might also like" recommendations on each post).

**Impact on reports:** 
- The "13% question-format H2 headers" metric is diluted — if a site has 100 real article H2s and 50 sidebar/template H2s, the percentage is calculated against 150 instead of 100, making question-format percentages artificially lower
- E-E-A-T heading analysis counts non-article headings as content structure
- The heading count per post is inflated (Copyblogger sample shows 12 headings, but only 1-2 are actual article headings; the rest are sidebar/template)
- Thin content detection that uses heading-to-word-count ratios would be skewed

**Fix:** Extract headings from main_content element only, not from full page HTML. Use the same content container logic already used for body HTML extraction: `soup.find("main") or soup.find("article") or soup.find("div", class_=lambda c: "content" in c or "post" in c or "entry" in c)`. This is consistent with fix S1-04 where you already moved internal link extraction to main content only. Apply the same approach to headings.

**Files to change:** `services/sitemap.py` (in `_fetch_and_extract`, heading extraction section). Change from `soup.find_all(re.compile(r"^h[1-6]$"))` to `main_content.find_all(re.compile(r"^h[1-6]$"))` where `main_content` is the already-identified content container.

---

#### S1-20: Documentation doesn't match code after fix S1-04

**Priority:** Fix before launch (documentation only)
**Found in:** Review of updated Step 1 spec

**Description:** Fix S1-04 changed internal link extraction to use main_content only. But Section 9 of the main Step 1 documentation still says "All `<a href>` in the full page HTML (not just main content) pointing to the same domain." The spec contradicts the code.

**Impact on reports:** No impact on report accuracy — the code is correct. But if anyone (including future-you) reads the spec to understand the system behavior, they'll get the wrong answer. This matters because the spec is your system-of-record documentation.

**Fix:** Update Section 9 (internal links) and Section 6 (heading extraction, once S1-19 is fixed) in the Step 1 documentation to reflect that both internal links and headings are now extracted from main_content, not full page HTML.

---

#### S1-21: Author bylines extracted as headings

**Priority:** Low — fix if heading extraction moves to main content
**Found in:** Copyblogger E2E test

**Description:** The heading structure sample shows `H4: Brian Clark` as a heading. This is the author byline styled as an H4, not a real content heading. Many WordPress themes wrap author names in heading tags for styling purposes.

**Impact on reports:** Minor. Author bylines as H4s would slightly inflate heading counts and could affect heading-level distribution analysis. If your E-E-A-T scoring checks for author names in headings as an E-E-A-T signal, a byline-as-heading could create a false positive (or true positive, depending on interpretation).

**Fix:** This is likely resolved by S1-19 (extracting headings from main content only), since author bylines are typically in the post header/meta area, not inside the `<article>` or `<main>` content container. Verify after implementing S1-19 — if bylines are still appearing, add a filter for H4/H5/H6 headings that match known author name patterns (short text, 1-3 words, no verbs).

---

## STEP 2: EMBEDDING, READABILITY, INTENT, AI CITABILITY

---

#### S2-01: E-E-A-T author name extraction is corrupted

**Priority:** Fix before launch
**Found in:** Copyblogger E2E test

**Description:** The sample post shows `eeat_author_name: "Brian ClarkBrian Clark is the founder of Copyblogger, themid"`. The author name field is concatenated with the start of the author bio, truncated mid-word ("themid" is likely "the mid..." or "the middle"). The extraction logic is grabbing the author name element plus adjacent sibling text without a delimiter or boundary.

**Impact on reports:**
- If the scoring logic uses author name consistency across posts (same author = higher E-E-A-T), then "Brian ClarkBrian Clark is the founder..." and "Brian Clark" would be treated as different authors, breaking consistency scoring
- If the author name appears in the PDF report (it currently doesn't, but might in future features), it would look broken
- The `eeat_author_found: true` flag itself is correct — an author IS present. But the extracted name is garbage
- Any downstream feature that displays or matches author names will produce incorrect results

**Fix:** In the author extraction logic, stop at the first element boundary. If using BeautifulSoup, the issue is likely that `.get_text()` is called on a container element that includes both the author name and the bio, rather than on the specific name element. Find the narrowest element that contains just the author name. Common patterns:
- `<span class="author-name">Brian Clark</span>` → extract from this span only
- `<a rel="author" href="...">Brian Clark</a>` → extract from the anchor text only
- `<meta name="author" content="Brian Clark">` → extract from the content attribute

Add a character limit (50 chars) and a sanity check: if the extracted name contains more than 4 words, it's probably name + bio, so truncate at the first sentence boundary or period.

**Files to change:** `services/ai_citability.py` (or wherever E-E-A-T scoring extracts author signals)

---

#### S2-02: E-E-A-T scores have a ceiling of 55 — too low for authoritative sites

**Priority:** Fix before launch
**Found in:** Copyblogger E2E test

**Description:** The E-E-A-T max score across all 145 Copyblogger posts is 55/100. Copyblogger is one of the most recognized content marketing authorities on the internet — founded by Brian Clark, published since 2006, cited across the industry, visible author attribution, author bios, publish dates on 99% of posts. A max E-E-A-T of 55 suggests the scoring model has a ceiling that prevents even the best-attributable content from scoring above the midpoint.

**Impact on reports:**
- The E-E-A-T dimension in the spider chart will always show as "moderate" or below, even for sites with excellent author attribution. This makes the spider chart less useful as a differentiator — if every site gets 40-55 regardless of actual E-E-A-T signals, the dimension doesn't communicate anything
- The AI Readiness headline ("Your content scores X on AI citability — but Y on structured data") uses E-E-A-T as one of four dimensions. If E-E-A-T is capped at 55, it always looks like a problem area even when it's not
- A prospect who knows their site has strong author attribution will question why E-E-A-T is 55 and lose trust in the tool's accuracy
- For Backlinko (which we report at 59), the score is slightly above Copyblogger's max — check whether Backlinko's 59 is the model's actual ceiling rather than a meaningful score

**Fix:** Audit the E-E-A-T scoring weights. Common issue: the scoring model likely allocates points across signals like this:
- Author name visible: X points
- Author bio present: X points  
- Author credentials/links: X points
- Publish date visible: X points
- Modified date visible: X points
- Schema.org author markup: X points
- Multiple authors across site: X points

If "Schema.org author markup" carries significant weight (e.g., 30-40 points out of 100), then no site without structured data can score above 60-70 regardless of how strong their visible E-E-A-T signals are. Schema signals should NOT be part of E-E-A-T scoring — they belong in the Schema dimension. E-E-A-T should measure visible trust signals that a human reader would perceive: author name, bio, credentials, dates, editorial standards, about page quality. Remove any schema-related signals from the E-E-A-T scorer and redistribute those points to the visible trust signals.

**Files to change:** `services/ai_citability.py` (E-E-A-T scoring section)

---

#### S2-03: Schema signals may be bleeding into E-E-A-T scoring

**Priority:** Fix before launch — verify and fix if confirmed
**Found in:** Copyblogger E2E test (inferred from S2-02)

**Description:** This is the suspected root cause of S2-02. If the E-E-A-T scorer includes signals like "has Person schema," "has author JSON-LD," or "has Organization schema," then sites without structured data are penalized twice: once in the Schema dimension (correctly) and again in the E-E-A-T dimension (incorrectly). The four AI Readiness dimensions should be independent — each measures a different aspect, and no finding should affect two dimensions.

**Impact on reports:** Double-penalization makes the AI Readiness analysis less useful. If a site with zero structured data gets penalized in both Schema AND E-E-A-T, the spider chart collapses on two axes instead of one. The "collapsed Schema axis" is your visual differentiator — it's most powerful when it's the ONLY collapsed axis, showing one clear problem to fix. If E-E-A-T is also suppressed because of the same root cause, the visual message becomes "everything is broken" instead of "one thing is broken."

**Fix:** List every signal that contributes to the E-E-A-T score. If any signal references structured data, JSON-LD, schema.org, or any machine-readable markup, move it to the Schema scorer. E-E-A-T should be calculated exclusively from:
- Visible author name in HTML (not schema)
- Visible author bio/about section in HTML
- Visible credentials (degrees, certifications, job titles) in HTML
- Visible publish date in HTML
- Visible modified/updated date in HTML
- About page exists and is linked
- Editorial policy or standards page exists
- Author page exists with multiple posts attributed
- Site age / domain history (if available)

None of these require structured data. A site can score 90+ on E-E-A-T with zero schema if it has strong visible trust signals.

---

#### S2-04: Intent classifier produces false positives on clickbait/opinion titles

**Priority:** Low — fix if intent drives downstream recommendations
**Found in:** Copyblogger E2E test

**Description:** Several posts are misclassified:
- "Aristotle's Top 3 Tips for Effective Blogging" → `commercial` (should be `informational`)
- "Why I Won't Buy Seth Godin's Meatball Sundae" → `transactional` (should be `informational` — "buy" in a negative context triggered false positive)
- "Discover the Secret Mind Control Method That Hypno..." → `transactional` (clickbait title, actually an informational blog post)
- "Twitter Writing Contest: Win an IPod Nano" → `commercial` (should be `informational` or `navigational` for an archived contest)
- "Don't Like Top 10 Lists? Tell a Story Instead" → `commercial` (clearly `informational`)

The classifier appears to be keyword-matching on title text ("buy," "discover," "contest," "win," "top") without considering page content or context.

**Impact on reports:** Currently intent is not surfaced in the PDF audit report. If it stays internal-only, this is cosmetic. But if intent classification feeds into recommendation generation (e.g., different optimization strategies for commercial vs informational content), misclassified posts would get wrong recommendations. 

**Fix (if needed):** Two options:
1. Weight page content more heavily than title. The title "Why I Won't Buy..." has a negative sentiment around "buy" — the classifier should check for negation patterns before flagging transactional intent
2. Use a two-stage classifier: title-based rough classification, then body-text-based verification. If the body text is 2,000 words of opinion/analysis with no product mentions, CTAs, or pricing, override the title-based classification to informational

**Priority justification:** Only fix this if intent is used downstream. Check: does intent appear in health scoring, problem detection, or recommendation generation? If yes, fix it. If it's only used in the dashboard/analytics view, defer.

---

#### S2-05: 20K character truncation affects 18% of posts

**Priority:** Low — monitor, fix if it causes scoring inaccuracies
**Found in:** Copyblogger E2E test

**Description:** 26 of 145 posts (18%) hit the 20,000 character embedding truncation limit. This means the embedding vectors for these posts represent only the first ~4,000 words. For Copyblogger's longest posts (14,267 words, 10,543 words, 9,516 words), the embedding captures less than half the content.

**Impact on reports:**
- **Clustering:** Probably fine. The first 4,000 words of a long article establish the topic well enough for clustering. A 14,000-word article about ebook writing isn't going to cluster differently based on content after word 4,000
- **Cannibalization detection:** Probably fine. Cosine similarity between two truncated posts still captures topic overlap. If two posts are about the same topic, the first 4,000 words of each will be similar enough to detect
- **AI citability scoring:** Not affected — citability is calculated from full body_text, not from embeddings
- **Health scoring:** Not affected — uses full body_text metrics

**Fix (if needed):** If you observe clustering or cannibalization accuracy issues with long-form content, consider a chunked embedding approach: split the text into 20K-char chunks, embed each chunk separately, and use the mean vector. But this doubles or triples embedding cost for long posts. Only implement if truncation causes demonstrable accuracy problems.

**Verification:** Check whether any of the 26 truncated posts appear in the "Least AI-Ready" bottom 5. If truncation is causing scoring artifacts, the longest posts would appear as low-scoring — which would be wrong, since long-form content is typically more structured and citable. The current bottom 5 are all short posts (35-word "The Art of the Joint Venture" type posts), so truncation doesn't appear to be causing scoring issues for this site.

---

#### S2-06: Freshness date problem count doesn't match publish date coverage

**Priority:** Fix before launch — verify logic
**Found in:** Copyblogger E2E test

**Description:** Step 1 reports `publish_date` coverage of 99.3% (146/147 posts have publish dates). But Step 2 reports `geo_no_freshness_date` as a problem on 144/145 posts (99.3% of posts have this problem). These numbers seem contradictory — if 99.3% of posts HAVE a publish date, how can 99.3% of posts be flagged for NO freshness date?

**Possible explanations:**
1. The freshness date problem detector is looking for `modified_date` (2% coverage), not `publish_date` (99.3% coverage). If the problem means "no visible last-updated signal," then 144/145 is correct because Copyblogger almost never sets `modified_date`
2. The problem detector is looking for a VISIBLE date in the HTML (e.g., a human-readable "Updated March 2026" on the page), not just the metadata field. Posts can have `publish_date` in their metadata but no visible date on the page
3. There's a bug where the freshness check is using the wrong field

**Impact on reports:** The `geo_no_freshness_date` problem feeds into the issue count (628 for Backlinko, 619 for Copyblogger). If this problem is flagging posts that DO have dates, the total issue count is inflated. More importantly, the freshness bullet in the Content Profile ("81% updated in last 12 months") and the freshness-related recommendations would be based on different data than the problem count, creating internal inconsistency in the report.

**Fix:** Clarify what `geo_no_freshness_date` means and verify the logic:
- If it means "no modified_date" → the count is correct (Copyblogger rarely sets modified dates), but rename it to `geo_no_modified_date` for clarity
- If it means "no visible freshness signal on page" → verify by checking actual page HTML for visible date text
- If it means "no publish_date OR modified_date" → the count is wrong, should be 1/145 not 144/145

**Files to change:** `services/ai_citability.py` or `services/problem_detection.py` (wherever `geo_no_freshness_date` is generated)

---

#### S2-07: AI citability scoring — verify that scoring uses full body_text, not truncated embedding text

**Priority:** Low — verify only
**Found in:** Copyblogger E2E test (inferred)

**Description:** The AI citability scorer calculates signals like `numbered_list_items`, `definition_paragraphs`, `entity_density_per_1k`, `total_headers`, `answer_first_200w`, `extract_total_h2`, `extract_definition_count`, and `extract_standalone_section_ratio`. These should all be calculated from the full `body_text` or `body_html` in the database, not from the 20K-truncated text used for embeddings.

**Impact on reports:** If citability scoring uses the truncated text, long posts would have artificially low scores for signals like `total_list_items` and `total_headers` because the scorer only sees the first 4,000 words. The current results don't suggest this is happening (the longest posts score high on citability), but verify explicitly.

**Fix:** No code change needed if confirmed working correctly. Add a comment in the scoring code: "# Uses full body_text from database, not truncated embedding text" to prevent future regressions.

---

## ALL ISSUES — RESOLVED

Every issue identified across both review rounds has been fixed. No outstanding items.

---

### Round 1 Fixes (2026-03-27)

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| **S2-01** | E-E-A-T author name corrupted ("Brian ClarkBrian Clark is the founder...") | Extract from narrowest child element (`<a>`, `<span>`, `<strong>`). Added >4 word sanity check. | `services/ai_citability.py` |
| **S2-02/S2-03** | E-E-A-T ceiling of 55. Schema signals bleeding into E-E-A-T (15pts for `has_author_schema`). | Removed schema from E-E-A-T scoring. Rebalanced: author 20→25, bio 20→25, date 15→10, links 15→20, contact 15→20. Total: 100pts, all visible signals. **Result: Copyblogger 55→80/100.** | `services/ai_citability.py` |
| **S2-06** | `geo_no_freshness_date` misleading — checks for modified/updated signals, not publish dates. Contradicts 99% publish_date coverage. | Renamed to `geo_no_updated_date`. Updated description, recommendation mapping, PDF label, and CHECK constraint. | `services/ai_citability.py`, `services/fast_recommendations.py`, `services/pdf_report.py`, `migrations/040_rename_freshness_problem.sql` |
| **S2-08** | Citability (135pts) and Extraction (130pts) exceed 100. | Verified `min(sum, 100)` cap on all 4 dimensions. Documented intentional over-allocation in docstrings. | `services/ai_citability.py` |

### Round 2 Fixes (2026-03-27)

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| **S1-20** | Step 1 doc says "full page HTML" for links/headings — code uses main_content. | Updated doc sections 6 (headings) and 9 (links) to say "main content area." | `PIPELINE-STEP1-INGESTION.md` |
| **S1-21** | Author byline H4s ("Brian Clark") still in headings after S1-19. | Added filter in `_extract_headings`: H4-H6 headings with 1-3 Title Case words (proper name pattern) are skipped as likely bylines. | `services/sitemap.py` |
| **S2-04** | Intent false positives: "Won't Buy" → transactional, "Top 3 Tips" → commercial. | Added negation detection before "buy". Moved "best/top N" to title-start-only check. Required `best-`/`top-N-` at slug START, not mid-slug. 10/10 test cases pass. | `services/fast_intent.py` (full rewrite) |
| **S2-05** | 20K char truncation lost content from 18% of posts. | Added `_prepare_text_chunked()` — long posts split into overlapping 20K chunks, embedded separately, mean-pooled into one vector. Short posts still batch normally. | `services/embeddings.py` |
| **S2-07** | Verify citability uses full body_text, not truncated embedding text. | Confirmed: reads `p.body_text`/`p.body_html` from DB. Added docstring comment to prevent regression. | `services/ai_citability.py` |
| **S2-10** | PageRank useless on capped crawls (4.4% link resolution → near-uniform scores). | Added 20% resolution rate quality gate. Below threshold → equal PageRank assigned + warning log. Prevents garbage values feeding health scoring. | `services/pagerank.py` |
| **S2-11** | Intent classifier uses zero body text — known limitation. | Documented in module docstring and function docstring. Negation fix (S2-04) mitigates the worst false positives. | `services/fast_intent.py` |

### S2-09: Chunk Embeddings — Status Note

Chunk-level embeddings (splitting posts by H2/H3 sections) exist in the schema (`content_chunks`, `chunk_embeddings` tables) and are used by `chunk_cannibalization.py` in Step 8b of the pipeline. They are **separate** from the whole-post embeddings in Step 2a. The whole-post embedding now uses mean-pooled chunks for long posts (S2-05 fix), but the section-level chunk embeddings for cannibalization detection are generated later in the pipeline, not during Step 2.

### Known Limitations (not fixing)

| # | Issue | Reason |
|---|-------|--------|
| S1-KL1 | Word count overcounting by 10-15% from trafilatura artifacts | trafilatura is best available; manual extraction doesn't scale |
| S1-KL2 | JS rendering only fires on specific framework markers | Covers Next.js, Nuxt, React, Vue — the major SSR frameworks |
| GA4 path matching | Uses full path (not slug), so `/blog/seo-guide` and `/resources/seo-guide` are different keys | Reviewed and confirmed correct — no collision risk |