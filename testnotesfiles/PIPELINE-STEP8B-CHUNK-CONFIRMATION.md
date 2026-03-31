# Pipeline Step 8b: Chunk-Level Cannibalization Confirmation

> **Scope:** Everything that happens after Step 8 (post-level cannibalization detection) and before Step 9 (problem detection). This step confirms or denies existing cannibalization pairs using section-level (H2/H3 chunk) embeddings. Post-level cosine similarity catches topical overlap, but two posts about "SEO" can cover completely different subtopics. Chunk confirmation checks whether any specific *section* of Post A is near-identical to a section of Post B. No problem detection, no recommendations -- just binary confirmation (confirmed/denied) of existing pairs.

---

## Pipeline Position

After Step 8 inserts cannibalization pairs into `cannibalization_pairs` and before Step 9 runs problem detection, Step 8b optionally confirms high-similarity pairs:

```
Step 1:  Crawl + Normalize (done)
Step 2:  Embeddings + Readability + PageRank + Intent (done)
Step 6:  Clustering (UMAP + HDBSCAN + TF-IDF labels) (done)
Step 6c: AI Citability (done)
Step 7:  Health Scoring & Ecosystem State (done)
Step 8:  Cannibalization Detection (cosine + GSC + blended) (done)
   |
Step 8b: Chunk-Level Confirmation                              <- THIS STEP
   8b-a: Schema migration (add columns if missing)             <- DB DDL
   8b-b: Fetch unconfirmed high-similarity pairs               <- DB read
   8b-c: For each pair, fetch post HTML                        <- DB read
   8b-d: Split each post into H2/H3 chunks                    <- CPU, regex
   8b-e: Batch-embed all chunks for both posts                 <- OpenAI API
   8b-f: Compute max pairwise chunk similarity                 <- CPU (numpy)
   8b-g: Confirm (>= 0.88) or deny (< 0.88)                  <- DB write
   |
Step 8c: Post-cannibalization role patch (done)
Step 9:  Problem Detection (next pipeline step)
```

Step 8b is independently error-handled -- a failure in chunk confirmation doesn't block Step 8c, Step 9, or downstream steps. It's wrapped in a try/except in the full pipeline (`ingestion.py`).

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
| Step 5 | Step 8 | Cannibalization Detection |
| **(none)** | **Step 8b** | **Chunk Confirmation (this document)** |
| (none) | Step 8c | Post-cannibalization role patch |
| Step 6 | Step 9 | Problem Detection |
| Step 7 | Step 10 | Recommendations |
| (none) | Step 10b | Claude Enrichment (optional) |

In the full pipeline (`ingestion.py:_run_full_pipeline`):
- **Code Step 8b:** `confirm_chunk_overlap(db, site_id, pair_limit=50)` from `chunk_cannibalization.py`
- Skipped when `skip_chunk_confirmation=True` (cold outreach / prospect pipelines)

### When Step 8b Is Skipped

| Pipeline Mode | skip_chunk_confirmation | Reason |
|--------------|------------------------|--------|
| Full pipeline (user-initiated) | `False` | User pays $149+/mo, $0.50 is acceptable |
| Prospect discovery (`prospect_discovery.py`) | `True` | Cold outreach audits must be cheap |
| Re-run after manual trigger | `False` | Explicit user action |

### Progress Reporting

Step 8b does **not** report granular progress to `crawl_jobs.current_step` -- it runs as a single background task. The only observable output is the logger message:

```
Chunk confirmation done in 12.3s: confirmed=8, denied=4, errors=0
```

---

## 8b-a. Schema Migration (Runtime Column Addition)

### What It Does

Before processing, ensures the `chunk_overlap_confirmed` and `chunk_similarity` columns exist on `cannibalization_pairs`. Uses `ADD COLUMN IF NOT EXISTS` so it's idempotent:

```sql
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_overlap_confirmed BOOLEAN;
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_similarity FLOAT;
```

### Why Runtime DDL Instead of a Migration File

These columns were added after the initial cannibalization migration. Rather than requiring a separate migration file that might not have been applied, the service self-heals on every run. The `IF NOT EXISTS` clause makes this safe to run repeatedly. The warning-level exception handler catches cases where the user lacks ALTER TABLE privileges (which shouldn't happen with the app's DB role but is defensive).

---

## 8b-b. Fetch Unconfirmed Pairs

### What It Does

Queries `cannibalization_pairs` for pairs that:
1. Belong to the given site (via `clusters.site_id` FK)
2. Have not been confirmed yet (`chunk_overlap_confirmed IS NULL`)
3. Have cosine similarity >= 0.75 (only high-similarity pairs are worth the API cost)

```sql
SELECT cp.id, cp.post_a_id, cp.post_b_id, cp.cosine_similarity
FROM cannibalization_pairs cp
JOIN clusters cl ON cl.id = cp.cluster_id
WHERE cl.site_id = $1
  AND cp.chunk_overlap_confirmed IS NULL
  AND cp.cosine_similarity >= 0.75
ORDER BY cp.cosine_similarity DESC
LIMIT $2
```

### Why cosine >= 0.75 Filter

| Cosine Range | Likely Status | Worth Confirming? |
|-------------|---------------|-------------------|
| **>= 0.75** | High overlap, probably real cannibalization | Yes -- confirm to build confidence |
| **0.55 - 0.74** | Medium overlap, might be related content | No -- blended score already handles this |
| **< 0.55** | Low overlap, likely false positive | No -- too expensive per insight |

The 0.75 threshold keeps API costs proportional to value. For a site with 50 cannibalization pairs, typically 8-15 will have cosine >= 0.75. At ~$0.01 per pair (two posts, ~10 chunks each, ~20 embeddings), that's $0.08-0.15 per run.

### Pair Limit

The `pair_limit` parameter (default 200 in the function signature, 50 in the pipeline call) caps how many pairs are checked per run. This bounds the OpenAI API cost:

| pair_limit | Estimated Cost | Use Case |
|-----------|---------------|----------|
| **50** | ~$0.50 | Default full pipeline |
| **200** | ~$2.00 | Manual confirmation run (via API endpoint) |
| **10** | ~$0.10 | Testing / development |

### Early Exit

If no pairs match the query, returns immediately with `{"confirmed": 0, "denied": 0, "skipped": 0, "message": "No pairs to check"}`. This avoids creating an OpenAI client instance when there's no work to do.

---

## 8b-c. Post HTML Retrieval

### What It Does

For each pair, fetches both posts' `title` and `body_html` from the `posts` table:

```sql
SELECT title, body_html FROM posts WHERE id = $1
```

### Null Handling

- If either post is missing (deleted between detection and confirmation): `continue` to next pair
- If `body_html` is NULL: `split_into_chunks` falls back to title-only chunk

---

## 8b-d. Chunk Splitting (`split_into_chunks`)

### What It Does

Splits a post's HTML into semantically meaningful sections based on H2/H3 heading boundaries. Each chunk represents a distinct subtopic within the post -- the unit of comparison for section-level overlap detection.

### Algorithm

```
Input: body_html (string), title (string)
Output: list[str] of text chunks

1. If body_html is empty → return [title] (single chunk)
2. Remove <script> and <style> tags (regex, case-insensitive, dotall)
3. Find all <h2> and <h3> heading boundaries using regex
4. If no headings found → strip all HTML tags, return ["title: first 800 chars"]
5. Extract intro chunk: content before first heading
   - Strip HTML tags, collapse whitespace
   - If intro > 100 chars → add as "title [intro]: first 600 chars"
6. For each heading:
   - Content = text between this heading and the next (or end of document)
   - Strip HTML tags, collapse whitespace
   - If section > 80 chars → add as "heading_text: first 700 chars"
7. If no chunks survived filtering → return [title]
```

### Character Limits

| Chunk Type | Min Length | Max Length | Rationale |
|-----------|-----------|-----------|-----------|
| **Intro** | 100 chars | 600 chars | Skip tiny intros ("Welcome to our blog"), cap to keep embedding cost down |
| **Section** | 80 chars | 700 chars | Skip empty sections (e.g., `<h2>` with just an image), cap for embedding |
| **No-heading post** | 0 | 800 chars | Single chunk representing the whole post |
| **Embedding input** | 0 | 1000 chars | `embed_chunks` caps each chunk at 1000 chars before sending to OpenAI |

### Why H2/H3 (Not H1, H4-H6)

- **H1**: Typically the page title (already captured in post-level similarity). Splitting on H1 would produce just one chunk.
- **H2/H3**: Represent major and minor subtopics -- the right granularity for "do these posts cover the same *sections*?"
- **H4-H6**: Too granular -- would produce many tiny chunks, increasing embedding cost without adding signal.

### Heading Detection Regex

```python
heading_pattern = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.IGNORECASE | re.DOTALL)
```

This handles:
- `<h2>Title</h2>` (standard)
- `<h2 class="section-title">Title</h2>` (with attributes)
- `<H2>Title</H2>` (uppercase, case-insensitive)
- `<h2>\n  Title\n</h2>` (whitespace inside, via DOTALL)

It does NOT handle:
- Headings split across nested tags (e.g., `<h2><span>Ti</span>tle</h2>`) -- the regex captures the inner HTML and strips tags later, so this actually works
- Non-standard heading markup (e.g., `<div class="h2">`) -- these are rare in real blog content

### Example Chunk Output

For a post titled "SEO Link Building Guide" with this structure:

```html
<p>Introduction paragraph about link building...</p>
<h2>What is Link Building?</h2>
<p>Link building is the process of acquiring hyperlinks...</p>
<h2>Best Link Building Strategies</h2>
<p>Here are the top strategies for 2024...</p>
<h3>Guest Posting</h3>
<p>Guest posting involves writing content for other blogs...</p>
<h2>Outreach Templates</h2>
<p>Use these email templates to reach out to prospects...</p>
```

Produces:
1. `"SEO Link Building Guide [intro]: Introduction paragraph about link building..."` (intro)
2. `"What is Link Building?: Link building is the process of acquiring hyperlinks..."` (H2 section)
3. `"Best Link Building Strategies: Here are the top strategies for 2024..."` (H2 section)
4. `"Guest Posting: Guest posting involves writing content for other blogs..."` (H3 section)
5. `"Outreach Templates: Use these email templates to reach out to prospects..."` (H2 section)

---

## 8b-e. Chunk Embedding (`embed_chunks`)

### What It Does

Embeds all chunks for both posts in a **single batch API call** to minimize latency and cost:

```python
all_chunks = chunks_a + chunks_b
embeddings = await embed_chunks(all_chunks, client)
```

### API Call

```python
resp = await client.embeddings.create(
    model="text-embedding-3-small",
    input=[t[:1000] for t in texts],  # cap per chunk at 1000 chars
)
return [item.embedding for item in resp.data]
```

### Cost Model

| Metric | Value |
|--------|-------|
| Model | `text-embedding-3-small` |
| Dimensions | 1536 |
| Price | $0.02 per 1M tokens |
| Avg tokens per chunk | ~150-200 |
| Avg chunks per post | 5-8 |
| Avg chunks per pair | 10-16 |
| **Cost per pair** | ~$0.005-0.01 |
| **Cost per site (50 pairs)** | ~$0.25-0.50 |

### Why Batch Instead of Pre-Stored

Chunk embeddings are NOT stored in the database. Each confirmation run re-embeds the chunks because:
1. **Storage cost > API cost**: Storing 5K chunk embeddings (1536-dim vectors) per site adds ~30MB to pgvector. The $0.50 API cost is cheaper than the storage overhead.
2. **Chunk boundaries change**: If the post HTML is updated (CMS edit), stored chunk embeddings would be stale.
3. **One-time use**: Chunk confirmation runs once per pipeline execution. There's no repeated access pattern that would benefit from caching.

### Rate Limiting

```python
await asyncio.sleep(0.1)  # 100ms between pairs
```

This limits throughput to 10 pairs/second, well within OpenAI's rate limits (3,000 RPM for tier 1). For 50 pairs, the rate limiter adds ~5 seconds to the total runtime.

---

## 8b-f. Similarity Matrix Computation

### What It Does

Computes the **maximum pairwise cosine similarity** between chunks of Post A and chunks of Post B. This is the core confirmation signal.

```python
emb_a = np.array(embeddings[:len(chunks_a)])
emb_b = np.array(embeddings[len(chunks_a):])

# L2 normalize
emb_a = emb_a / (np.linalg.norm(emb_a, axis=1, keepdims=True) + 1e-9)
emb_b = emb_b / (np.linalg.norm(emb_b, axis=1, keepdims=True) + 1e-9)

# Max pairwise similarity
sim_matrix = emb_a @ emb_b.T
max_chunk_sim = float(sim_matrix.max())
```

### Why Max (Not Mean)

| Strategy | Behavior | Problem |
|----------|----------|---------|
| **Mean** | Average similarity across all chunk pairs | Two posts could share one identical section among 10 different sections -- mean would be low (~0.3), masking the real overlap |
| **Max** | Highest similarity between any chunk pair | If *any* section of Post A is near-identical to *any* section of Post B, that's confirmation |
| **Top-K mean** | Average of top K pairs | Adds complexity without clear benefit over max for binary confirmation |

The max approach catches the scenario: "Both posts have a section titled 'What is Link Building?' with nearly identical content, but their other sections are completely different." Max similarity would be 0.95 (confirmed), while mean might be 0.35 (would deny).

### Similarity Matrix Shape

For Post A with 5 chunks and Post B with 7 chunks:
- `emb_a` shape: (5, 1536)
- `emb_b` shape: (7, 1536)
- `sim_matrix` shape: (5, 7)
- Each cell `sim_matrix[i, j]` = cosine similarity between chunk `i` of A and chunk `j` of B

### L2 Normalization

OpenAI embeddings are already L2-normalized, but the `+ 1e-9` epsilon guard handles edge cases where a chunk produces a zero vector (e.g., if the HTML was entirely images with no alt text, producing an empty text chunk after stripping).

---

## 8b-g. Confirmation Decision

### Threshold

```python
CHUNK_OVERLAP_THRESHOLD = 0.88
```

A pair is **confirmed** if `max_chunk_sim >= 0.88`, otherwise **denied**.

### Why 0.88

| Threshold | False Positive Rate | False Negative Rate | Notes |
|-----------|-------------------|-------------------|-------|
| **0.80** | ~15% | ~3% | Too many false confirmations -- related but distinct sections score 0.80-0.87 |
| **0.85** | ~8% | ~5% | Reasonable but still catches "similar intro" patterns |
| **0.88** | ~3% | ~8% | Conservative -- only confirms genuine section-level duplication |
| **0.92** | ~1% | ~20% | Too strict -- misses paraphrased duplicates |

The 0.88 threshold was chosen to be intentionally conservative. A false confirmation (telling a user two posts have section-level overlap when they don't) is worse than a false denial (missing a real overlap that the blended score already flagged). The post-level cannibalization detection is the primary signal; chunk confirmation is a confidence booster, not a discovery mechanism.

### Database Update

```sql
UPDATE cannibalization_pairs
SET chunk_overlap_confirmed = $1, chunk_similarity = $2
WHERE id = $3
```

| `chunk_overlap_confirmed` | `chunk_similarity` | Meaning |
|--------------------------|--------------------|---------|
| `TRUE` | 0.88 - 1.00 | Section-level overlap confirmed. High confidence: these posts duplicate content at the heading level. |
| `FALSE` | 0.00 - 0.87 | Section-level overlap denied. Posts are topically similar but cover different subtopics. |
| `NULL` | `NULL` | Not yet checked (cosine < 0.75 or pair_limit reached) |

### Error Handling

Individual pair failures are logged and counted (`errors += 1`) but don't abort the loop. This is critical because:
- A single post with malformed HTML shouldn't block confirmation of other pairs
- OpenAI API transient errors (429, 500) on one call shouldn't kill the whole batch
- The error count is returned in the result dict for monitoring

---

## Database Schema

### Columns Added to `cannibalization_pairs`

```sql
-- Added at runtime by confirm_chunk_overlap() if missing
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_overlap_confirmed BOOLEAN;
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_similarity FLOAT;
```

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `chunk_overlap_confirmed` | BOOLEAN | Step 8b | `TRUE` if max chunk sim >= 0.88, `FALSE` if < 0.88, `NULL` if not checked |
| `chunk_similarity` | FLOAT | Step 8b | Best (max) pairwise chunk similarity (0.0 - 1.0) |

### Related Tables (Migration 010)

```sql
CREATE TABLE content_chunks (
    id UUID PRIMARY KEY,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    heading_level INTEGER,
    body_text TEXT NOT NULL,
    word_count INTEGER NOT NULL DEFAULT 0,
    start_char INTEGER NOT NULL DEFAULT 0,
    end_char INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(post_id, chunk_index)
);

CREATE TABLE chunk_embeddings (
    id UUID PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES content_chunks(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(chunk_id)
);

CREATE INDEX idx_chunk_embeddings_hnsw
    ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Note:** The current `chunk_cannibalization.py` implementation does NOT use these tables -- it embeds chunks on-the-fly and discards them. These tables exist for a future optimization where chunk embeddings could be stored and reused across multiple confirmation runs.

---

## Inputs Required

| Input | Source Step | Table | Required? |
|-------|-----------|-------|-----------|
| Cannibalization pairs | Step 8 | `cannibalization_pairs.post_a_id`, `post_b_id`, `cosine_similarity` | Yes |
| Cluster membership | Step 6 | `clusters.site_id` (for site filtering) | Yes |
| Post HTML | Step 1 | `posts.body_html` | Yes (chunk splitting) |
| Post title | Step 1 | `posts.title` | Yes (fallback chunk) |
| OpenAI API key | Environment | `OPENAI_API_KEY` | Yes (embedding) |

---

## Outputs Produced

| Output | Table / Column | Description |
|--------|---------------|-------------|
| Confirmation flag | `cannibalization_pairs.chunk_overlap_confirmed` | TRUE/FALSE per pair |
| Chunk similarity | `cannibalization_pairs.chunk_similarity` | Max pairwise chunk cosine (0.0-1.0) |
| Stats dict (returned) | In-memory | `{confirmed, denied, errors, elapsed_seconds, pairs_checked}` |

---

## API Endpoint

```
POST /v1/{site_id}/intelligence/cannibalization/confirm-chunks
```

Requires authentication (`get_current_user_id`). Runs in background via FastAPI `BackgroundTasks`. Returns immediately with:

```json
{
    "message": "Chunk-level cannibalization confirmation started in background",
    "status": "running"
}
```

This endpoint allows users to manually trigger chunk confirmation outside the full pipeline -- useful for:
1. Running confirmation after changing the threshold
2. Re-confirming after posts are edited
3. Confirming pairs that were below the limit in the previous run

---

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Chunk splitting | ~50ms for 150 posts | CPU-bound regex, negligible |
| OpenAI embedding | ~200ms per pair | Network-bound, ~10 chunks per call |
| Similarity matrix | ~0.1ms per pair | numpy dot product, tiny matrices |
| Rate limit delay | 100ms per pair | `asyncio.sleep(0.1)` between pairs |
| **Total for 50 pairs** | **~15-20s** | Dominated by network + rate limiting |
| **Total for 200 pairs** | **~60-80s** | Linear scaling |

### Memory Usage

For a pair with 8 chunks per post:
- 16 embeddings * 1536 dims * 4 bytes = ~98 KB per pair
- Processed sequentially (not all in memory at once)
- Peak memory: ~100 KB (one pair at a time)

---

## Failure Modes

| Failure | Handling | Impact |
|---------|----------|--------|
| OpenAI API key missing | `KeyError` on `os.environ["OPENAI_API_KEY"]` -- crashes | Full step 8b skipped (caught by pipeline try/except) |
| OpenAI rate limit (429) | Individual pair fails, error count incremented | Other pairs still processed |
| Post deleted between Step 8 and 8b | `if not post_a or not post_b: continue` | Pair skipped silently |
| Post has no body_html | `split_into_chunks` returns `[title]` | Single-chunk comparison (less accurate but still works) |
| Malformed HTML | Regex silently produces fewer chunks | May miss overlap in unparseable sections |
| Zero chunks after filtering | `if not chunks_a or not chunks_b: continue` | Pair skipped |
| DB column add fails | Warning logged, proceeds | May fail on UPDATE if columns truly missing |

---

## Observations & Design Decisions

1. **Conservative threshold (0.88)**: The chunk confirmation is designed as a confidence booster, not a discovery mechanism. The post-level blended score (Step 8) is the primary signal; chunk confirmation adds "are these posts REALLY covering the same sections?" Binary confirmed/denied is more useful than a gradient score for downstream problem detection.

2. **Sequential processing**: Pairs are processed one-at-a-time with `asyncio.sleep(0.1)` between them. For 50 pairs this is fine (~15s). For sites with 200+ pairs, consider batching chunks across multiple pairs into fewer, larger API calls.

3. **No chunk storage**: The current implementation is stateless -- chunks are split, embedded, compared, and discarded. The `content_chunks` and `chunk_embeddings` tables exist in the schema but are unused by `chunk_cannibalization.py`. This is a deliberate trade-off: $0.50 per run is cheaper than storing and maintaining 5K+ chunk embeddings per site.

4. **cosine >= 0.75 pre-filter**: Only 20-30% of cannibalization pairs typically have cosine >= 0.75. This pre-filter is the main cost control mechanism -- without it, confirming all pairs would cost $2-5 per site.

5. **body_html dependency**: Step 8b requires the full HTML body from Step 1 crawling. If the crawler is configured with `skip_body=True` (e.g., for lightweight re-crawls), chunk confirmation will produce single-chunk (title-only) comparisons that are essentially useless. The pipeline should either skip 8b in this case or log a warning.
