# Pipeline Step 6b: TF-IDF Cluster Labeling

> **Scope:** Everything that happens after Step 6 (UMAP + HDBSCAN clustering + sub-clustering + noise assignment + 2D map positions) and before Step 6c (AI citability scoring). This step generates human-readable topic labels and descriptions for each cluster using multi-signal TF-IDF on titles (3x weight), H2 headings (2x), and body text (1x). Zero API calls -- pure Python text analysis. Also performs negative label validation, label deduplication, and auto-generates one-sentence descriptions.

---

## Pipeline Position

After Step 6 stores clusters in `clusters` + `post_clusters` (with placeholder labels), the full pipeline runs TF-IDF labeling:

```
Step 1: Crawl + Normalize (done)
Step 2: Embeddings + Readability + PageRank + Intent (done)
Step 6: Clustering (UMAP + HDBSCAN + sub-clustering + 2D map) (done)
   |
Step 6b-a: Fetch all post titles for the site                         <- DB read
Step 6b-b: Compute site-wide stop words (adaptive 15/20/30%)          <- CPU, <5ms
Step 6b-c: Pre-compute corpus IDF stats once                          <- CPU, ~5ms
Step 6b-d: Fetch cluster -> post title/body/heading mappings (batch)  <- DB read
Step 6b-e: For each cluster:
           - Extract phrases from titles (3x weight)
           - Extract top-10 uni + top-5 bi from body text (1x, capped)
           - Extract phrases from H2/H3 headings (2x weight)
           - Filter UI noise (80+ social/nav/HTML artifact words)
           - Score phrases with TF-IDF
           - Select best bigram + smart connector + qualifier
           - Validate alternative labels (filter garbage)
           - Build up to 3 validated alternative labels
           - Collect description words
Step 6b-f: Negative label validation (cross-cluster specificity check) <- CPU
Step 6b-g: Near-duplicate dedup (primary-bigram overlap detection)     <- CPU
Step 6b-h: Exact-duplicate dedup (append qualifier for remaining)      <- CPU
Step 6b-i: Generate one-sentence descriptions                         <- CPU
Step 6b-j: Batch UPDATE clusters SET label, description               <- DB write (1 query)
   |
Step 6c: AI Citability (next pipeline step)
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
| **Step 3h** | **Step 6b** | **TF-IDF Cluster Labels (this document)** |
| (none) | Step 6c | AI Citability |
| Step 4 | Step 7 | Health Scoring |
| Step 5 | Step 8 | Cannibalization |
| Step 6 | Step 9 | Problem Detection |
| Step 7 | Step 10 | Recommendations |

In the full pipeline (`ingestion.py:_run_full_pipeline`), Step 6b maps to:
- **Code Step 6b:** `label_clusters_fast(db, site_id)` -- from `services/fast_cluster_labels.py`

Claude label backfill (`backfill_claude_labels`) runs separately via the intelligence router, not in the default pipeline -- it's an optional quality upgrade costing ~$0.02 per site.

### Error Handling

Like all pipeline sub-steps, Step 6b is wrapped in `_pipeline_step()`:

```python
await _pipeline_step(pool, site_id, "cluster_labels", "clustering",
                     lambda db: label_clusters_fast(db, site_id))
```

If labeling fails, the pipeline continues. Clusters keep their placeholder labels from Step 6 (e.g., "Cluster 1 (18 posts)"). The frontend can render clusters with any label -- placeholder labels are ugly but functional.

---

## 6b-a. Fetch All Titles

### Query

```sql
SELECT title FROM posts WHERE site_id = $1
```

Returns all titles, including those in noise clusters or parent clusters. The full set is needed for accurate IDF -- a word that appears in 50% of all titles is common (low IDF) regardless of which cluster it's in.

### Output

`all_title_list: list[str]` -- typically 50-500 titles. Used for site stop detection, IDF corpus, and negative label validation.

---

## 6b-b. Site-Wide Stop Word Detection (`_compute_site_stops`)

### What It Does

Auto-detects words that appear across too many titles to be useful as cluster labels. For an SEO blog, this catches "seo", "search", "content", "marketing".

### Adaptive Threshold

The threshold scales with site size to handle both small niche sites and large diverse sites:

```python
if n_docs < 100:
    threshold = n_docs * 0.15   # Aggressive for small niche sites
elif n_docs < 300:
    threshold = n_docs * 0.20   # Moderate for B2B content blogs
else:
    threshold = n_docs * 0.30   # Standard for large sites
```

| Site Size | Threshold | Example |
|-----------|-----------|---------|
| 50 posts | 7.5 (15%) | "seo" in 8/50 = stopped |
| 150 posts | 30 (20%) | "blog" in 11/150 = NOT stopped |
| 500 posts | 150 (30%) | "marketing" in 160/500 = stopped |

### Why Adaptive

A fixed 30% threshold doesn't work for small sites. On a 50-post niche SEO blog, "seo" might appear in 40% of titles -- but at 30% threshold that's 15 titles needed, and 40% of 50 is only 20. With the 15% threshold for small sites, the stop word kicks in at just 7.5 titles, correctly catching site-wide vocabulary.

---

## 6b-c. Pre-compute Corpus IDF Stats (`_build_corpus_stats`)

### What It Does

Computes corpus-level phrase and word frequencies once, shared across all cluster labeling calls. Previously this was recomputed inside `_tfidf_label()` for every cluster -- N redundant iterations.

```python
def _build_corpus_stats(all_titles, site_stops) -> tuple[Counter, Counter, int]:
    noise = _FORMAT_WORDS | site_stops
    corpus_phrases: Counter = Counter()
    corpus_words: Counter = Counter()
    for t in all_titles:
        corpus_phrases.update(set(_extract_phrases(t)))
        stripped = _strip_format(t)
        corpus_words.update(set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS - noise)
    return corpus_phrases, corpus_words, len(all_titles) or 1
```

### Performance Impact

| Site Size | Before (N × titles) | After (1 × titles) | Savings |
|-----------|---------------------|---------------------|---------|
| 150 posts, 12 clusters | 1,800 phrase extractions | 150 | 12x |
| 1000 posts, 40 clusters | 40,000 phrase extractions | 1,000 | 40x |

---

## 6b-d. Batch Cluster Data Fetch

### What It Does

Fetches titles, body HTML, and headings for all cluster posts in a single query. The body and heading data enables multi-signal labeling.

### Query

```sql
SELECT pc.cluster_id, p.title, p.body_html, p.headings
FROM posts p
JOIN post_clusters pc ON pc.post_id = p.id
WHERE pc.cluster_id = ANY($1::uuid[])
```

### Data Grouping

```python
titles_by_cluster: dict[UUID, list[str]]
body_by_cluster: dict[UUID, list[tuple[str | None, str | None]]]  # (body_html, headings)
```

---

## 6b-e. Multi-Signal Phrase Extraction

### Signal Weighting

| Signal | Weight | Per Post | 24-Post Cluster | % of Pool | Why |
|--------|--------|----------|-----------------|-----------|-----|
| **Titles** | 3x | ~7 phrases × 3 = ~21 | ~504 | ~40% | Most concise topic indicator |
| **H2/H3 Headings** | 2x | ~5 phrases × 2 = ~10 | ~240 | ~19% | Specific topic indicators, often more precise than creative titles |
| **Body text** | 1x | ~15 phrases (capped) | ~360 | ~29% | Captures topic vocabulary missed by creative headlines |

### Body Text Extraction (`_extract_body_phrases`) — Capped

Body phrases are **capped to top 10 unigrams + top 5 bigrams per post** (ranked by raw frequency in that post's text). Without capping, 200 body words produce ~350 phrases per post, making body 90%+ of the pool and drowning out title/heading signals.

```python
def _extract_body_phrases(body_html, headings,
                          max_body_unigrams=10, max_body_bigrams=5):
    # Body: strip HTML, extract first 200 content words, filter UI noise
    words = [w for w in _WORD_RE.findall(text) if w not in all_noise][:200]
    # Rank by frequency, keep top N
    uni_counts = Counter(words)
    top_unis = [w for w, _ in uni_counts.most_common(max_body_unigrams)]  # Top 10
    bi_counts = Counter(bigrams_from(words))
    top_bis = [b for b, _ in bi_counts.most_common(max_body_bigrams)]     # Top 5
    body_phrases = top_unis + top_bis  # ~15 per post

    # Headings: parse H2/H3 from JSONB (no cap — headings are already concise)
    return (body_phrases, heading_phrases)
```

### UI Noise Filter (`_UI_NOISE`)

Body text from HTML includes navigation, social buttons, and markup artifacts. A dedicated filter removes 80+ UI/nav words:

| Category | Examples |
|----------|---------|
| Social | tweet, share, pin, facebook, twitter, linkedin |
| Navigation | menu, close, toggle, next, previous, sidebar |
| HTML artifacts | class, swp, div, span, href, src, rdf, xml |
| URLs/domains | https, http, www, com, org, php |
| Contraction fragments | don, didn, doesn, isn, wasn |
| CMS | wordpress, theme, plugin, widget |

### Why Body Text Helps

A cluster of 15 posts about "link building" where 10 titles use creative headlines ("The Skyscraper Technique", "Why Nobody Links to You") would produce a vague title-only label. But every post's body contains "link building", "backlinks" repeatedly. The body signal captures this — the capped top-10 unigrams from each post surface the dominant topic vocabulary without overwhelming title signals.

### Why Headings Help

A post titled "The Complete Guide" has an H2 "Link Building Strategies for 2026" — the H2 contains the actual topic. Sub-clusters where parent titles are broad but H2s are specific benefit most from this signal.

---

## 6b-f. Format Marker Stripping (`_strip_format`)

### Over-Strip Guard

The trailing pattern strip (`[-–|:].{0,30}$`) now checks that enough content remains:

```python
candidate = re.sub(r"\s*[-–|:].{0,30}$", "", lower)
if len(candidate.split()) >= 3:
    lower = candidate  # Safe to strip
# Otherwise: keep original (e.g., "AI: The Future" stays intact)
```

| Input | Result | Guard? |
|-------|--------|--------|
| "SEO Copywriting: The Definitive Guide" | "seo copywriting" (3 words) | Stripped |
| "AI: The Future" | "ai: the future" (1 word after strip) | Kept |
| "Link Building Strategy - Backlinko" | "link building strategy" (3 words) | Stripped |

---

## 6b-g. Acronym Casing (`_smart_title`)

### The Problem

Python's `.title()` produces "Seo" not "SEO". For a product selling to SEO professionals, this looks unprofessional.

### The Fix

25 known marketing/tech acronyms are uppercased instead of title-cased:

```python
_ACRONYMS = frozenset({
    "seo", "sem", "ppc", "cta", "roi", "b2b", "b2c", "saas", "api",
    "html", "css", "cro", "kpi", "url", "cpc", "cpm", "ctr",
    "serp", "eeat", "llm", "ux", "ui", "smm", "pr", "roas", "lp",
})

def _smart_title(word: str) -> str:
    if word.lower() in _ACRONYMS:
        return word.upper()
    return word.title()
```

| Input | `.title()` | `_smart_title()` |
|-------|-----------|-----------------|
| "seo" | "Seo" | "SEO" |
| "b2b" | "B2B" | "B2B" |
| "link" | "Link" | "Link" |
| "roas" | "Roas" | "ROAS" |

---

## 6b-h. Smart Connectors (`_connect_label_parts`)

### The Problem

Every multi-part label used "&" blindly: "Content Promotion & Blogging", "Social Media & Marketing". This gets repetitive and misses compound nouns that flow naturally without a connector.

### The Fix

35 known marketing compound nouns are recognized:

```python
_COMPOUND_NOUNS = frozenset({
    "link building", "email marketing", "content marketing", "content strategy",
    "social media", "keyword research", "search engine", "landing page",
    "lead generation", "affiliate marketing", "digital marketing", ...
})

def _connect_label_parts(primary, qualifier):
    pair = f"{primary.lower()} {qualifier.lower()}"
    if pair in _COMPOUND_NOUNS:
        return f"{primary} {qualifier}"       # "Content Marketing" (no &)
    if reverse_pair in _COMPOUND_NOUNS:
        return f"{qualifier} {primary}"       # Reorder if needed
    return f"{primary} & {qualifier}"         # "Sales & SEO" (with &)
```

| Primary | Qualifier | Result | Why |
|---------|-----------|--------|-----|
| "Content" | "Marketing" | "Content Marketing" | Known compound noun |
| "Link" | "Building" | "Link Building" | Known compound noun |
| "Sales" | "SEO" | "Sales & SEO" | Not a compound noun |
| "Email" | "Marketing" | "Email Marketing" | Known compound noun |

---

## 6b-i. TF-IDF Scoring & Label Selection (`_tfidf_label`)

### Signature

```python
def _tfidf_label(
    cluster_titles, all_titles, site_stops=frozenset(),
    corpus_phrases=None, corpus_words=None, n_docs=None,
    extra_phrases=None,
) -> tuple[str, list[str], list[str]]:
    # Returns (label, alternative_labels, description_words)
```

### Algorithm

1. **Extract phrases from titles** (3x weight via repetition)
2. **Add extra phrases** from body text (1x) and headings (2x, weighted by caller)
3. **Separate bigrams and unigrams**, filter unigrams against noise
4. **Score bigrams by TF-IDF** (skip if both parts are noise)
5. **Score unigrams by TF-IDF**
6. **Select best bigram** (freq >= 2 for clusters >= 5 posts, freq >= 1 for < 5 posts)
7. **Build label** using smart connector (`_connect_label_parts`)
8. **Build up to 3 alternative labels** from 2nd-6th bigrams + unigram pairs, validated
9. **Collect description words** (top unigrams not in label)

### Alternative Label Validation

Alternatives are filtered by `_is_valid_alt` to prevent garbage:

```python
def _is_valid_alt(alt_label):
    alt_words = set(_WORD_RE.findall(alt_label.lower()))
    if alt_words & _UI_NOISE:         return False  # HTML artifacts
    if len(alt_words) < 2:            return False  # Single word
    if alt_label == label:            return False  # Same as primary
    # Reject if neither word appears in >= 2 cluster titles
    # (catches noise from single creative titles: "Obedience School")
    if not any(title_word_freq[w] >= 2 for w in alt_words):
        return False
    # Reject proper noun phrases (both words capitalized in title text)
    # Catches product names: "Teaching Sells", "Chris Garrett"
    if both_words_capitalized_in_title(alt_label):
        return False
    return True
```

The candidate pool is expanded from top 4 to top 6 bigrams to compensate for filtered candidates.

### Primary Bigram Proper Noun Filter

The primary bigram selection also filters out likely proper nouns/product names. A bigram is skipped if ALL its words appear in only 1 cluster title (unique to a single creative title, not a cluster-wide theme):

```python
# Skip bigrams from single titles: "Teaching Sells" (1 title), "Chris Garrett" (1 title)
# Keep bigrams from multiple titles: "Content Promotion" (3 titles), "Landing Page" (2 titles)
if all(title_word_doc_freq[w] <= 1 for w in parts):
    continue
```

### Small Cluster Bigram Threshold

```python
min_bigram_freq = 1 if len(cluster_titles) < 5 else 2
```

Small clusters (2-4 posts, typically sub-clusters) use freq >= 1 because bigrams rarely appear twice in 2-4 titles. This prevents all sub-cluster labels from falling back to vague unigram pairs.

### Fallback Chain

| Priority | Path | Condition | Example |
|----------|------|-----------|---------|
| 1 | Best bigram | Score > 0, freq >= threshold | "Link Building" |
| 2 | Bigram + qualifier | Bigram + top unigram not in bigram, via smart connector | "Content Promotion & Blogging" |
| 3 | Top 2 unigrams | No qualifying bigram, via smart connector | "Business & People" |
| 4 | Single unigram | Only 1 unigram scored | "Freelance" |
| 5 | Most common raw unigram | All scored 0 | "Marketing" |
| 6 | "General Content" | No phrases at all | "General Content" |

---

## 6b-j. Negative Label Validation (`_validate_label_specificity`)

### What It Does

After labeling, checks whether each label actually differentiates its cluster from others. If a label's words appear in more than 50% of other clusters' titles, the stop-word detector missed site-wide vocabulary.

```python
def _validate_label_specificity(label, cluster_idx, all_cluster_titles) -> bool:
    label_words = extract_content_words(label)
    hits = count(other clusters where ALL label_words appear in their titles)
    return hits / n_other_clusters <= 0.5
```

### Replacement Logic

If validation fails, the system tries each alternative label in order. The first alternative that passes validation replaces the primary label.

### Example

| Label | Cluster 0 titles | Cluster 1 titles | Cluster 2 titles | Specific? |
|-------|-----------------|-----------------|-----------------|-----------|
| "Content Marketing" | Contains "content" + "marketing" | Contains "content" + "marketing" | Contains "content" + "marketing" | NO (3/3 clusters) |
| Alt: "Email Outreach" | Contains "email" + "outreach" | No "outreach" | No "email" | YES (0/2 others) |

---

## 6b-k. Label Deduplication (Two-Pass)

### Pass 1: Near-Duplicate Primary Bigram Dedup

Labels sharing the same first 2 words (primary bigram) are near-duplicates even if qualifiers differ. E.g., "Social Media & People" and "Social Media & Blog" would confuse customers in the dashboard.

```python
def _primary_bigram(label):
    return " ".join(label.replace(" & ", " ").split()[:2]).lower()

seen_primaries = {}
for i, label in enumerate(labels):
    primary = _primary_bigram(label)
    if primary in seen_primaries:
        # Replace with top alternative that has a different primary
        for alt in alternatives[i]:
            if _primary_bigram(alt) not in seen_primaries:
                labels[i] = alt
                break
    seen_primaries[_primary_bigram(labels[i])] = i
```

### Pass 2: Exact Duplicate Dedup

After near-dedup, any remaining exact duplicates get a qualifying unigram appended:

```python
label_counts = Counter(labels)
for i, label in enumerate(labels):
    if label_counts[label] > 1:
        # Find top unigram not in label
        labels[i] = f"{label} ({_smart_title(unique_word)})"
```

### Example

| Before | After | Reason |
|--------|-------|--------|
| Cluster 3: "Social Media & People" | "Social Media & People" | First claim on "social media" primary |
| Cluster 0: "Social Media & Blog" | "Teaching Sells & Blog" | Near-dup, replaced with alternative |

---

## 6b-l. Description Generation (`_generate_description`)

### What It Does

Generates a one-sentence description from the top TF-IDF unigrams not already in the label. Fills the `clusters.description` column that was previously empty in fast mode.

```python
def _generate_description(label, desc_words) -> str:
    filtered = [w for w in desc_words if w.lower() not in label.lower()]
    if len(filtered) == 1:
        return f"Posts covering {filtered[0].lower()}."
    if len(filtered) == 2:
        return f"Posts covering {filtered[0].lower()} and {filtered[1].lower()}."
    return f"Posts covering {', '.join(...)}, and {filtered[-1].lower()}."
```

### Examples (from Copyblogger E2E)

| Label | Description Words | Generated Description |
|-------|------------------|----------------------|
| "Content Promotion & Writing" | ["Blogging", "Copywriting"] | "Posts covering blogging and copywriting." |
| "Social Media & People" | ["Marketing"] | "Posts covering marketing." |
| "Landing Page & Keyword" | ["SEO", "Google"] | "Posts covering seo and google." |

Description words are filtered to only include words appearing in >= 2 cluster titles, preventing single-post noise words ("muse", "naked", "fear") from leaking in.

---

## DB Operations

### Read Operations (3 queries)

| # | Query | Returns |
|---|-------|---------|
| 1 | `SELECT title FROM posts WHERE site_id = $1` | All titles for IDF corpus + site stops |
| 2 | `SELECT id, post_count FROM clusters WHERE site_id = $1` | All cluster IDs |
| 3 | `SELECT pc.cluster_id, p.title, p.body_html, p.headings FROM posts p JOIN post_clusters pc ...` | Batch cluster-title-body-heading mapping |

### Write Operations (1 query)

```sql
UPDATE clusters SET label = u.label, description = u.description
FROM unnest($1::uuid[], $2::text[], $3::text[]) AS u(id, label, description)
WHERE clusters.id = u.id
```

Single batch `unnest()` query for all clusters -- 1 round trip regardless of cluster count.

---

## Claude Label Backfill (Optional)

### When It Runs

- **NOT in the default pipeline** -- `_run_full_pipeline` only calls `label_clusters_fast`
- **Triggered via intelligence router:** `POST /{site_id}/intelligence/cluster`
- **Can be run standalone** via `backfill_claude_labels(db, site_id)`

### API Call

| Parameter | Value |
|-----------|-------|
| Model | `claude-sonnet-4-20250514` |
| Max tokens | 20 |
| Input titles | Up to 15 (sorted by word count DESC) |
| Output | 2-4 word topic label, stripped of quotes |

### TF-IDF vs Claude Quality

| Aspect | TF-IDF | Claude |
|--------|--------|--------|
| Accuracy | ~75% good, ~15% acceptable, ~10% vague (single-site test; varies by content style) | ~90% good, ~10% acceptable |
| Cost | Free | ~$0.02/site |
| Latency | < 100ms | 10-20s |
| Handles ambiguity | Uses body text + headings as fallback signals | Understands semantic themes natively |
| Non-English | English only | Multilingual |
| Deterministic | Yes | No |

### Cost

| Site Size | Clusters | Estimated Cost | Time |
|-----------|----------|---------------|------|
| 50 posts | ~5 | ~$0.005 | ~5s |
| 150 posts | ~12 | ~$0.012 | ~10s |
| 500 posts | ~25 | ~$0.025 | ~15s |
| 1000+ posts | ~40 | ~$0.040 | ~20s |

---

## Performance Estimates

| Sub-step | Time (150 posts, ~12 clusters) | Time (1000 posts, ~40 clusters) | Notes |
|----------|-------------------------------|--------------------------------|-------|
| Fetch all titles | <5ms | <10ms | One SELECT |
| Compute site stops | <5ms | ~10ms | Adaptive threshold (15/20/30%) |
| Pre-compute corpus stats | ~5ms | ~20ms | One-time IDF computation |
| Batch fetch titles+body+headings | <15ms | ~30ms | One JOIN query |
| TF-IDF labeling (all clusters) | ~130ms | ~400ms | Multi-signal with capped body (10 uni + 5 bi per post) |
| Negative validation | <5ms | ~20ms | Cross-cluster string matching |
| Near-dup + exact dedup | <5ms | ~10ms | Primary-bigram check + Counter |
| Description generation | <1ms | <5ms | String formatting |
| Batch UPDATE (unnest) | <5ms | <10ms | Single round trip |
| **Total Step 6b** | **~175ms** | **~500ms** | **Free (zero API calls)** |

**Cost:** Free. No external API calls. Pure Python text analysis + DB reads/writes.

---

## Table Schema

### Columns Written by Step 6b

| Table | Column | Type | Written By |
|-------|--------|------|-----------|
| `clusters` | `label` | TEXT | Batch unnest UPDATE |
| `clusters` | `description` | TEXT | Batch unnest UPDATE |

### Downstream Consumers

| Service | How Label Is Used |
|---------|------------------|
| `health_scoring.py` | Logging ("Scoring cluster: {label}") |
| `cannibalization.py` | Report context |
| `problem_detection.py` | Problem descriptions |
| `ecosystem_visuals.py` | Frontend ecosystem map |
| `pdf_report.py` | PDF audit report cluster table |
| Intelligence API | `ClusterSummary.label` + `.description` |


THOUGHTS:

**Rating: 79/100** (up from ~70 implied in my previous review)

The architectural improvements are substantial — multi-signal extraction, pre-computed IDF, negative label validation, smart connectors, acronym casing, description generation, batch unnest writes, and the over-strip guard. The spec is well-written and the design decisions are sound. But the E2E test reveals that several of these improvements aren't actually working or aren't being validated.

---

## PREVIOUSLY IDENTIFIED — STATUS CHECK

**S6b-01 (acronym casing "Seo"): FIXED.** Cluster 2 now shows "Sales Letter & SEO" — correct casing. The `_smart_title` function with 25 acronyms is working.

**S6b-02 (stop word threshold too high): NOT WORKING.** The spec describes adaptive thresholds (15% for <100, 20% for 100-300, 30% for 300+). With 145 posts, the threshold should be `145 × 0.20 = 29`. But the E2E test shows "Stop word threshold: 44 occurrences (30% of 145 titles)." The code is still using the fixed 30% threshold, not the adaptive one. See S6b-10.

**S6b-03 (small cluster bigram threshold): IMPLEMENTED IN SPEC.** The spec shows `min_bigram_freq = 1 if len(cluster_titles) < 5 else 2`. But Cluster 0 (24 posts) uses freq >= 2, so no small clusters were tested. With synthetic embeddings, there are no sub-clusters. This needs validation on a site with sub-clusters.

**S6b-04 (redundant IDF computation): FIXED.** `_build_corpus_stats` computes once, passed to all cluster labeling calls. Clean refactor.

**S6b-05 (over-stripping after colons): FIXED.** The 3-word minimum guard is implemented. "Once More With Feeling: Has Your Writing Got Soul?" → "once more with feeling" (3 words, passes guard).

---

## NEW ISSUES

**S6b-10: Adaptive stop word threshold is in the spec but not in the E2E test output**

Priority: Fix before launch
Found in: Copyblogger E2E test

The spec says threshold = `n_docs × 0.20` for sites with 100-300 posts. 145 posts × 0.20 = 29 titles needed to trigger a stop word. But the E2E shows "Stop word threshold: 44 occurrences (30% of 145 titles)." At 30%, the threshold is 44. At 20%, it would be 29.

With a 29 threshold, no words would be stopped either — "blog" at 11 is still below 29. But the gap matters: on a 150-post SEO blog where "seo" appears in 35 titles (24%), the 20% threshold (30) would catch it but the 30% threshold (45) would not. That's exactly the scenario the adaptive threshold was designed for.

Either the adaptive threshold code wasn't implemented (spec-only change), or the test script is hardcoding 30%. Check the actual `_compute_site_stops` function — does it use the adaptive logic or the old fixed 30%?

Files to check: `services/fast_cluster_labels.py` (`_compute_site_stops`)

---

**S6b-11: "Whom Blog & Business" is a bad label rated as "good"**

Priority: Fix before launch
Found in: Copyblogger E2E test (Cluster 0)

"Whom Blog & Business" as a cluster label would make any customer cringe. "Whom" is not a topic word — it's from the title "For Whom the Blog Tips (It Tips For Thee)," a literary reference. The label reads like word salad, not a topic description.

Two separate problems here. First, "whom" should be in `_STOP_WORDS` or `_FORMAT_WORDS`. It's a relative pronoun that has no business in a cluster label. Add it to the stop word list along with other relative pronouns that might leak through: "whom," "whose," "whereby," "thereof."

Second, the quality assessment in the E2E test rated this "good" when it's clearly not. The test's quality criteria appear to be: "has a bigram = good, has unigrams = acceptable, fallback = vague." But that's too permissive — "Whom Blog" is a unigram pair, not a meaningful topic description. The quality assessment should check whether the label words are actual topic nouns, not just whether the labeling path produced a result. At minimum, change the test to flag labels where any word is a function word (pronoun, conjunction, preposition).

Fix: Add "whom," "whose," "thee," "thou," "thy" to `_STOP_WORDS`. Re-run — Cluster 0 would then get "Business & People" (the next unigrams), which is the same label as the previous E2E run and is genuinely acceptable.

Files to change: `services/fast_cluster_labels.py` (`_STOP_WORDS`)

---

**S6b-12: The multi-signal extraction (body text + headings) shows no evidence of working**

Priority: Investigate
Found in: Copyblogger E2E test

The spec describes body text (1x) and H2 headings (2x) as additional signals. But the E2E phrase extraction section shows nearly identical numbers to the previous run: 565 unigrams (was 560), 420 bigrams (was 415). If body text from 145 posts (first 200 words each = ~29,000 words) and headings were contributing, the phrase counts should be dramatically higher — probably 2,000+ unigrams and 1,500+ bigrams.

Possible explanations: (A) the multi-signal extraction is implemented in the spec but not in the code, (B) the E2E test is only counting title-derived phrases, not the full multi-signal set, or (C) body_html is null or empty for most posts (trafilatura XML issue from S6-09), so the body extraction produces nothing.

The labels are also identical to the previous run (same 4 labels), which is suspicious. If body text and headings were contributing new phrase signals, at least one label should have changed.

Fix: Add a diagnostic section to the E2E test showing: "Phrases from titles: X, Phrases from headings: Y, Phrases from body: Z, Total: X+Y+Z." If headings and body contribute near-zero phrases, investigate whether `body_html` and `headings` are being passed to `_extract_body_phrases`. If they're null for most posts, the multi-signal extraction is dead code.

---

**S6b-13: The E2E test doesn't show generated descriptions**

Priority: Fix test
Found in: Copyblogger E2E test (missing)

The spec describes `_generate_description` producing one-sentence descriptions like "Posts covering outreach, backlinks, and guest." The E2E test doesn't show any descriptions. For a $149 product, the cluster description appears in the dashboard and API responses. The test should show: for each cluster, the generated description and the description words that fed it.

---

**S6b-14: The E2E test doesn't show negative label validation results**

Priority: Fix test
Found in: Copyblogger E2E test (missing)

The spec describes `_validate_label_specificity` checking whether labels differentiate between clusters. The E2E test doesn't show validation results. Add: for each label, show the cross-cluster hit rate and whether validation passed. If "Content Promotion & Blogging" contains words that appear in 3/4 clusters, the validation should flag it — and the test should show whether it did.

---

**S6b-15: The E2E test doesn't show alternative labels**

Priority: Fix test
Found in: Copyblogger E2E test (missing)

The spec describes building up to 3 alternative labels per cluster, stored in `clusters.metadata`. The E2E test doesn't show alternatives. For the product, alternatives serve two purposes: Claude backfill can use them as suggestions, and the dashboard could let customers choose. The test should show all 3 alternatives per cluster to verify the selection logic.

---

**S6b-16: Smart connector didn't trigger on any label — all 4 use "&"**

Priority: Low — verify on Backlinko
Found in: Copyblogger E2E test

All 4 labels use "&": "Content Promotion & Blogging," "Social Media & Marketing," "Whom Blog & Business," "Sales Letter & SEO." None triggered the compound noun recognition. This is correct for these specific labels — none of the primary+qualifier pairs are in the `_COMPOUND_NOUNS` list.

On Backlinko with real clusters, you'd expect labels like "Link Building" (compound noun, no "&"), "Email Marketing" (compound noun, no "&"), "Keyword Research" (compound noun, no "&"). The smart connector feature would get its real workout there.

No fix needed. But verify on Backlinko that compound nouns are recognized and connectors are suppressed correctly.

---

**S6b-17: The batch unnest UPDATE is in the spec but the test doesn't verify it**

Priority: Low — verify
Found in: Copyblogger E2E test

The spec shows a single `UPDATE ... FROM unnest()` query for all labels + descriptions. The previous version used N individual UPDATE queries. The E2E test doesn't show DB operations or verify the batch query was used. This is a performance improvement (25 round trips → 1), but on 4 clusters the difference is invisible.

---

**S6b-18: TF-IDF accuracy claim improved from "70% good" to "85% good" but the evidence doesn't support it**

Priority: Low — update claim
Found in: Step 6b spec (Claude Label Backfill section)

The spec says "~85% good, ~10% acceptable, ~5% vague." The E2E test shows 4/4 labels rated "good" (100%). But "Whom Blog & Business" is demonstrably NOT good (S6b-11). The real distribution on this test is 3/4 good (75%), 0/4 acceptable, 1/4 bad. The 85% claim should be based on testing across multiple sites with real embeddings, not this one synthetic test.

---

## SUMMARY

### Fix Before Launch (2 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-10 | Adaptive stop word threshold not applied (30% used instead of 20%) | 15 min to verify code matches spec |
| S6b-11 | "Whom Blog & Business" — add "whom/thee/thou" to stop words, fix quality assessment | 10 min |

### Investigate (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6b-12 | Multi-signal extraction (body + headings) shows no evidence of working | 30 min to add diagnostic output and verify |

### Fix Test (3 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-13 | Test doesn't show generated descriptions | 15 min |
| S6b-14 | Test doesn't show negative label validation results | 15 min |
| S6b-15 | Test doesn't show alternative labels | 15 min |

### Low Priority (3 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-16 | Smart connector didn't trigger — verify on Backlinko | Verify only |
| S6b-17 | Batch unnest UPDATE not verified in test | Low |
| S6b-18 | 85% good accuracy claim not evidence-based | Update after multi-site testing |

### Previously Fixed (4 items)

S6b-01 (acronym casing), S6b-04 (redundant IDF), S6b-05 (over-stripping), plus the structural improvements (multi-signal design, descriptions, validation, dedup, smart connectors, batch writes).

### The honest assessment

The 79/100 rating reflects a well-architected step where most of the new features (multi-signal extraction, negative validation, descriptions, alternatives) are designed correctly in the spec but aren't verified in the E2E test. The architecture went from "simple TF-IDF on titles" to "multi-signal TF-IDF with body text, headings, negative validation, smart connectors, descriptions, and alternatives" — that's a significant upgrade that would justify the $149 price point IF it's actually working in code.

The two launch blockers are trivial (stop words list + adaptive threshold verification). The real risk is S6b-12: if the multi-signal extraction isn't actually running, the labels are still title-only, which means the headline improvement ("85% good") is based on features that don't exist yet. Verify body/heading contribution with the diagnostic output, and the rating would jump to 87-90 once confirmed.

The real test, as always, is Backlinko with real embeddings. That's where you'll see "Link Building" (compound noun, no "&"), "Email Marketing" (compound noun, no "&"), site stops catching "seo" and "content," and the multi-signal extraction pulling topic words from H2 headings that creative titles missed.

THOUGHTS (ALL IMPLEMENTED):

**All issues S6b-19 through S6b-25 are fixed.** See below for status.

## S6b-19 through S6b-25 — STATUS

**S6b-19 (near-duplicate labels): FIXED.** Added primary-bigram dedup in `label_clusters_fast`. Labels sharing the same first 2 words (e.g., "Social Media & People" / "Social Media & Blog") now force the second label to use its top alternative. Result: Cluster 0 became "Teaching Sells & Blog" instead of duplicating Cluster 3's "Social Media" primary.

**S6b-20 (body text dominance at 90%): FIXED.** Changed `_extract_body_phrases` from returning all phrases from 200 words (~350 per post) to returning top 10 unigrams + top 5 bigrams per post (~15 per post). Body phrases dropped from 44,315 to 2,175. Weighted pool is now: titles 40% (969×3=2907), headings 29% (1047×2=2094), body 30% (2175×1). Hierarchy restored: titles > headings > body.

**S6b-21 ("Keyword Research & Online" worse than title-only): FIXED.** Consequence of S6b-20 fix. With capped body phrases, title signal reasserted. Cluster 2 is now "Keyword Research & SEO" — body contributes "keyword research" (from post bodies) while title contributes "SEO" (from titles). Best of both worlds.

**S6b-22 ("Article Writing" replaced "Content Promotion"): FIXED.** Consequence of S6b-20 fix. Cluster 1 is now "Content Promotion & Writing" — title bigram "content promotion" (freq=3) back as primary.

**S6b-23 (garbage alternatives "Full Color", "Locked Mortal"): FIXED.** Added `_is_valid_alt()` filter in `_tfidf_label` that rejects alternatives containing UI noise words, single-word labels, or exact duplicates. Also expanded alt candidate pool from top 4 to top 6 bigrams. Alternatives are now: "Content Marketing", "Landing Page", "Sales Letter", "SEO Book".

**S6b-24 (generic descriptions): FIXED.** Consequence of S6b-20 fix. With title-dominant pool, description words are now topic-specific: "Posts covering blogging, copywriting, and muse." instead of body-noise like "Posts covering post, headline, and people."

**S6b-25 (quality assessment too permissive): FIXED.** Added near-duplicate detection (labels sharing primary bigram) and label-content mismatch detection (label bigram not in cluster's title top-5). Quality now correctly rates 2/4 as "good" and 2/4 as "acceptable" instead of blindly rating all 4 "good".

---

## PREVIOUSLY IDENTIFIED — STATUS CHECK (rounds 1-3)

**S6b-10 (adaptive threshold): FIXED.** Threshold now shows "29 occurrences (20% of 145 titles)" — exactly `145 × 0.20 = 29`. The adaptive logic is working in code, not just the spec.

**S6b-11 ("Whom Blog & Business"): FIXED.** Cluster 0 is now "Social Media & Blog." The "whom" stop word was added. Quality assessment now has a "Bad" category for function/archaic words.

**S6b-12 (multi-signal not working): FIXED.** The diagnostic section confirms: Titles 969 phrases, Body 44,315 phrases, Headings 1,047 phrases, Total 49,316. Body text is contributing 90% of all input phrases. The multi-signal extraction is decisively active.

**S6b-13 (descriptions not shown): FIXED.** Each cluster now shows its generated description and description words.

**S6b-14 (negative validation not shown): FIXED.** Each cluster shows "Specific (validation): YES."

**S6b-15 (alternatives not shown): FIXED.** Each cluster shows 3 alternatives.

**S6b-16 (smart connector): UNCHANGED.** All 4 labels still use "&". Expected for this dataset — no compound noun pairs. Verify on Backlinko.

**S6b-18 (accuracy claim): FIXED.** Updated to "~75% good, ~15% acceptable, ~10% vague (single-site test; varies by content style)." Honest and appropriately qualified.

---

## NEW ISSUES

**S6b-19: "Social Media & People" and "Social Media & Blog" are near-duplicate labels**

Priority: Fix before launch
Found in: Copyblogger E2E test (Cluster 0 and Cluster 3)

Cluster 3 is "Social Media & People." Cluster 0 is "Social Media & Blog." Both share "Social Media" as the primary bigram. A customer looking at their cluster dashboard sees two clusters that sound like the same topic. The deduplication step (6b-k) checks for exact duplicates, not near-duplicates. These pass dedup because the qualifiers differ ("People" vs "Blog"), but the primary term is identical.

The negative validation (6b-j) checks whether a label's words appear in other clusters' titles. "Social Media" appears in Cluster 3's titles (selected bigram) but likely also appears in Cluster 0's body text (which is why the multi-signal extraction surfaced it). The validation might pass because the check looks at title word presence, not label overlap between clusters.

Fix: After deduplication, add a near-duplicate check: if two labels share the same primary bigram (the first 2 words), force the second label to use its top alternative. Cluster 0's alternatives are "Chris Garrett, Teaching Sells, Locked Mortal" — none are great, but "Chris Garrett" at least differentiates. Better yet: when the primary bigram matches another cluster's label, fall back to the top unigram pair that doesn't overlap. Cluster 0's top unigrams are "business" and "people" — "Business & People" (the old label) was actually more differentiating.

---

**S6b-20: Body text dominance (90% of phrases) is drowning out title and heading signals**

Priority: Fix before launch
Found in: Copyblogger E2E test (Multi-Signal Diagnostic)

Body contributes 44,315 phrases vs titles 969 and headings 1,047. Even with 3x title weighting and 2x heading weighting, the effective ratios are: titles 2,907 (969×3), headings 2,094 (1,047×2), body 44,315 (1x). Body phrases are 90% of the weighted input. The title signal (designed to be the primary signal at 3x) is overwhelmed.

This explains why the labels changed dramatically from the title-only version. "Sales Letter & SEO" (driven by title bigrams) became "Keyword Research & Online" (driven by body text). The title bigram "sales letter" (TF-IDF 0.1158, freq=2) was the clear winner in title-only mode, but body phrases diluted it.

The problem: body text from the first 200 words of each post produces ~300 phrases per post (200 words → ~180 content words → ~180 unigrams + ~170 bigrams). For a 24-post cluster, that's ~7,200 body phrases vs ~160 title phrases (24 titles × ~7 phrases each). Even with 3x title weighting, body phrases are 7,200 / (160×3 + 7,200) = 94% of the pool.

Fix: Cap body phrases per post. Instead of using all phrases from 200 words, use the top 10 unigrams and top 5 bigrams per post (ranked by raw frequency in that post's text). This gives ~360 body phrases per 24-post cluster instead of ~7,200 — making body ~43% of the weighted pool instead of 94%. Titles at 3x would then be ~33%, headings at 2x would be ~24%. This restores the intended hierarchy: titles > headings > body.

Alternative: increase title weight from 3x to 10x. But this is a blunt fix that would make body text nearly irrelevant.

---

**S6b-21: "Keyword Research & Online" is a worse label than the title-only "Sales Letter & SEO"**

Priority: Consequence of S6b-20 — resolved by fixing body phrase capping
Found in: Copyblogger E2E test (Cluster 2)

Cluster 2's sample titles: "Does the SEO Industry Have a Branding Problem?", "The Death of the Long Copy Sales Letter", "Why Linking to Other Blogs is Critical", "Is the New SEO Book Sales Letter Working?" These posts are about SEO and copywriting fundamentals. The title-only label "Sales Letter & SEO" correctly captures the dominant topics. The multi-signal label "Keyword Research & Online" captures a topic from one post's body text ("How to Do Keyword Research") and a generic qualifier ("Online") that adds no specificity.

"Online" as a qualifier is essentially noise — it's like labeling a cluster "Marketing & Digital." It tells the customer nothing they didn't already know. The word "online" probably appears in the body text of most posts (everything on Copyblogger is about online content), giving it high TF but low IDF within this cluster.

After fixing S6b-20 (cap body phrases), the title signal would reassert itself and "Sales Letter & SEO" or similar would return.

---

**S6b-22: "Article Writing & Content" replaced "Content Promotion & Blogging" — the body signal changed the best label**

Priority: Investigate — may be S6b-20 consequence
Found in: Copyblogger E2E test (Cluster 1)

The title-only top bigram was "content promotion" (TF-IDF 0.0713, freq=3). The new label is "Article Writing & Content" — "article writing" is not in the title bigram top 5. It came from body text. Looking at the sample titles ("Copyblogger - Content marketing tools", "The True Power of the Blog", "The Most Powerful Blogging Technique"), the cluster is about blogging and content creation. "Content Promotion & Blogging" was a better label than "Article Writing & Content" — "article writing" is a synonym but less specific to the SEO/content marketing domain.

This is the same body-dominance issue (S6b-20). Body text contains generic writing vocabulary ("article," "writing," "paragraph") that's topically related but less precise than the title vocabulary ("content promotion," "blogging").

---

**S6b-23: Alternative labels include garbage: "Full Color," "Locked Mortal," "Chris Garrett"**

Priority: Fix before first paid customer
Found in: Copyblogger E2E test (Cluster 1 and Cluster 0 alternatives)

Cluster 1 alternatives: "Original Headline, Content Promotion, Full Color." "Full Color" is meaningless as a cluster topic label — it's probably from body text mentioning "full color" in a design context.

Cluster 0 alternatives: "Chris Garrett, Teaching Sells, Locked Mortal." "Chris Garrett" is an author name, not a topic. "Teaching Sells" is a product name. "Locked Mortal" is from "I'm Locked in Mortal Combat with Chris Garrett" — a title fragment.

These alternatives would be shown to customers in the dashboard as "other possible names for this cluster" and offered to Claude backfill as suggestions. "Full Color" and "Locked Mortal" as cluster name suggestions would undermine the product's credibility.

Fix: Validate alternative labels the same way primary labels are validated. Apply negative validation to alternatives. Filter alternatives that contain proper nouns (detected as words not in a common word list), single-word labels, and labels with words in `_STOP_WORDS`. If an alternative fails validation, skip it and try the next candidate.

---

**S6b-24: Descriptions are generic and sometimes redundant with the label**

Priority: Low — improve after launch
Found in: Copyblogger E2E test

Cluster 1: Label "Article Writing & Content", Description "Posts covering post, headline, and people." The word "post" is a near-synonym of "article" (already in the label). "People" is not a topic descriptor. The description doesn't add value beyond the label.

Cluster 3: Label "Social Media & People", Description "Posts covering marketing, time, and ads." "Marketing" is relevant but "time" and "ads" are generic body text vocabulary.

Cluster 2: Label "Keyword Research & Online", Description "Posts covering people, marketing, and seo." The description words ("people, marketing, seo") are more descriptive than the label itself. If the description says "seo" and "marketing," the label should reflect those topics, not "Online."

The description generation picks top TF-IDF unigrams not in the label. When the label is driven by body text (post-S6b-20), the description words come from the remaining pool which may include more specific title-derived words. This creates the ironic situation where the description is better than the label.

Fix (post-launch): After S6b-20 is fixed (body phrase capping), descriptions would naturally improve because the label would capture the most specific terms from titles, and the description would add genuine supplementary topics from body/headings.

---

**S6b-25: The quality assessment rates all 4 labels "good" but two are questionable**

Priority: Fix test
Found in: Copyblogger E2E test

"Social Media & Blog" (Cluster 0) and "Keyword Research & Online" (Cluster 2) are rated "good." But "Social Media & Blog" is a near-duplicate of Cluster 3's label, and "Keyword Research & Online" doesn't match the cluster's actual content (SEO + copywriting). The quality assessment checks for function words (good — "whom" would be caught) but doesn't check for near-duplicate labels or label-content mismatch.

Add to quality assessment: (1) "Near-duplicate" flag when two labels share the same primary bigram, (2) "Mismatch" flag when the label's top bigram doesn't appear in the cluster's title bigram top 5 (indicating body text overrode titles).

---

## SUMMARY

### Fix Before Launch (2 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-19 | Near-duplicate labels ("Social Media & People" / "Social Media & Blog") — add primary-bigram dedup | 30 min |
| S6b-20 | Body text 90% of phrases drowns title/heading signals — cap body phrases per post | 30 min |

### Fix Before First Paid Customer (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6b-23 | Alternative labels include garbage ("Full Color," "Locked Mortal") — validate alternatives | 30 min |

### Fix Test (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6b-25 | Quality assessment doesn't catch near-duplicate or label-content mismatch | 20 min |

### Low Priority (2 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-21 | "Keyword Research & Online" worse than title-only label — resolved by S6b-20 | — |
| S6b-22 | "Article Writing & Content" replaced better title-only label — resolved by S6b-20 | — |
| S6b-24 | Descriptions generic — resolved by S6b-20 | — |

### Previously Fixed (6 items)

S6b-10 (adaptive threshold), S6b-11 ("Whom" stop word), S6b-12 (multi-signal confirmed working), S6b-13 (descriptions shown), S6b-14 (validation shown), S6b-15 (alternatives shown).

### The honest assessment

The jump from 79 to 84 reflects that every test gap has been closed — the multi-signal extraction is confirmed working with 44K+ body phrases, descriptions are generated, validation is shown, alternatives are visible, and the adaptive threshold is applied. The architecture is no longer theoretical.

The remaining 16 points come from one core issue: body text dominance (S6b-20). At 90% of the phrase pool, body text overrides the carefully-designed 3x title weighting, producing labels that are less specific than the title-only version. This single issue cascades into near-duplicate labels (S6b-19), content-mismatched labels (S6b-21, S6b-22), generic descriptions (S6b-24), and garbage alternatives (S6b-23).

The fix is straightforward: cap body phrases to top-N per post instead of all phrases from 200 words. After that fix, the title signal would reassert dominance, body/headings would provide supplementary vocabulary for creative-title clusters, and the labels would be both specific (from titles) and topic-aware (from body). That would push the rating to 90+.

The real validation remains Backlinko with real embeddings — where you'll see compound nouns ("Link Building," "Email Marketing"), site stops catching "seo," and the multi-signal extraction proving its value on clusters where titles use creative headlines but body text and H2s contain the actual topic keywords.

THOUGHTS (ALL IMPLEMENTED):

**All issues S6b-26 through S6b-28 are fixed.** See below for status.

## S6b-26 through S6b-28 — STATUS

**S6b-26 (label bigram doesn't match highest title bigram): FIXED.** Added signal-source diagnostic to E2E test showing title/body/heading contribution per label bigram. Also added proper noun/single-title bigram filtering to primary bigram selection: bigrams where ALL words appear in only 1 title are skipped (catches "Teaching Sells", "Chris Garrett" without blocking legitimate multi-title bigrams like "Content Promotion", "Landing Page").

**S6b-27 ("Teaching Sells" product name): FIXED.** The proper noun heuristic in `_tfidf_label` now skips bigrams where every word appears in only 1 cluster title. "Teaching Sells" (from a single title "Teaching Sells is Live") is skipped. Cluster 0 now gets "Business Blog & People" — both "business" and "blog" appear in multiple titles.

**S6b-28 (description noise words): FIXED.** Description word selection now requires min 2 cluster title appearances (`_cluster_title_word_freq >= 2`). "Muse" (1 title), "naked" (1 title), "fear" (1 title) filtered out. Descriptions now show only words that represent genuine cluster themes: "Posts covering blogging and copywriting."

**S6b-23 tighten ("Obedience School", "Post Dead"): FIXED.** Alternative validation `_is_valid_alt` now requires at least one word to appear in >= 2 cluster titles. Single-title fragments are rejected.

---

## NEW ISSUES

**S6b-26: Cluster 2's label "Keyword Research & SEO" doesn't match its highest-scoring bigram "sales letter"**

Priority: Investigate
Found in: Copyblogger E2E test (Cluster 2)

The top bigram table for Cluster 2 shows "sales letter" at TF-IDF 0.1158 (freq=2), "seo book" at 0.1158 (freq=2), and "landing page" at 0.1072 (freq=2). But the label is "Keyword Research & SEO." "Keyword research" doesn't appear in the top 5 bigrams at all.

This means "keyword research" came from body text or headings, not titles. With the capped body phrases, the body signal should be supplementary (30% of pool), not primary. If a body-derived bigram is outscoring a title-derived bigram with 0.1158 TF-IDF and freq=2, something in the scoring is still favoring body phrases in this cluster.

Possible explanation: the "How to Do Keyword Research" post (3,229 words) has "keyword research" appearing heavily in both body text and H2 headings. With heading weight 2x, a single post's headings could contribute enough "keyword research" bigrams to outweigh 2 title occurrences of "sales letter." This would be correct behavior if the heading signal is genuinely strong — but it means one post's headings can override the title consensus of multiple posts.

The label "Keyword Research & SEO" is actually decent for this cluster (which contains SEO-focused content including the keyword research guide). But it's worth understanding why the highest-scoring title bigram lost. Add a diagnostic: for the winning label bigram, show which signal sources contributed (X from titles, Y from headings, Z from body).

---

**S6b-27: "Teaching Sells & Blog" is a product name, not a topic label**

Priority: Low — Copyblogger-specific
Found in: Copyblogger E2E test (Cluster 0)

"Teaching Sells" is a product/course by Copyblogger's Brian Clark. It appears in a post title ("Teaching Sells is Live") and probably in body text of related posts. As a cluster label, it tells the customer "these posts are about the Teaching Sells product" — which is only true for 1-2 of the 24 posts. The cluster actually contains general blogging/business posts.

This happened because the near-duplicate dedup (S6b-19) forced Cluster 0 off its natural "Social Media" primary and onto the alternative "Teaching Sells." The alternative was the best available option given the constraints, but it's a proper noun product name, not a topic.

The alternative validation (`_is_valid_alt`) doesn't detect proper nouns. Adding proper noun detection is hard (requires a dictionary or NER), but a simpler heuristic would work: reject alternatives where both words are capitalized in the original title text (suggesting a proper noun phrase rather than a topic). "Teaching Sells" would be capitalized in the title; "Business People" would not.

No fix needed for launch — this is a synthetic-embedding artifact. With real embeddings, Cluster 0 wouldn't contain the same posts, and the "Social Media" collision probably wouldn't occur. But add proper noun detection to the alternatives validator before the first paid customer.

---

**S6b-28: Description noise words ("muse," "naked," "fear") leak through from individual post titles**

Priority: Low — improve after launch
Found in: Copyblogger E2E test (descriptions)

"Posts covering blogging, copywriting, and muse." "Muse" comes from a post about creative inspiration (possibly "How to Find Your Muse" or similar). "Posts covering business, people, naked, and story." "Naked" comes from "Feel Great Naked: Confidence Boosters for Getting Personal."

These words are legitimate high-TF-IDF unigrams within their clusters — they appear in titles/headings of specific posts and are rare across the corpus (high IDF). But they're not representative of the cluster's topic. They're outlier words from individual creative titles.

Fix (post-launch): Filter description words against a minimum cluster frequency. A word should appear in at least 2 posts' titles/headings within the cluster to qualify as a description word. "Muse" appearing in 1/53 posts wouldn't qualify; "blogging" appearing in 6/53 would. This prevents single-post outliers from entering descriptions.

---

## SUMMARY

### All Launch Blockers Resolved

S6b-19 (near-duplicate dedup), S6b-20 (body phrase capping), S6b-23 (alternative validation) — all fixed and verified in the E2E output.

### Investigate (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6b-26 | Cluster 2 label doesn't match highest title bigram — add signal-source diagnostic | 15 min |

### Fix Before First Paid Customer (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6b-27 | "Teaching Sells" is a product name — add proper noun detection to alternative validator | 20 min |

### Low Priority (2 items)

| # | Issue | Effort |
|---|-------|--------|
| S6b-28 | Description noise words ("muse," "naked," "fear") — add min cluster frequency filter | 20 min |
| S6b-23 | "Obedience School" and "Post Dead" alternatives still pass validation | 15 min (tighten filter) |

### Previously Fixed (12 items across 4 rounds)

S6b-01, S6b-04, S6b-05, S6b-10, S6b-11, S6b-12, S6b-13, S6b-14, S6b-15, S6b-18, S6b-19, S6b-20, S6b-21, S6b-22, S6b-23 (partial), S6b-24 (partial), S6b-25.

### The honest assessment

The 88/100 reflects a labeling system that's been through 4 rounds of iteration and now produces output that's defensible at the $149 price point. The body phrase capping (S6b-20) was the single most impactful fix — it restored the intended signal hierarchy (titles 41% > headings 29% > body 30%) and fixed four cascading issues in one change. The near-duplicate dedup (S6b-19) solved the dashboard confusion problem. The alternative validation (S6b-23) caught the worst garbage.

The remaining 12 points: one label is a product name not a topic (-3, Copyblogger-specific), the highest-scoring title bigram lost to a heading-derived bigram in one cluster (-3, needs diagnostic), description noise words from individual creative titles (-2), two garbage alternatives still pass validation (-2), and the general limitation of synthetic embeddings producing artificial cluster boundaries (-2).

After the S6b-26 diagnostic (understanding why heading-derived bigrams can override title consensus) and S6b-27 fix (proper noun detection), the rating would be 91-92. The real validation is Backlinko with real embeddings — where "Link Building" would be a compound noun (no "&"), "seo" would be caught by site stops, and the multi-signal extraction would prove its value on clusters where creative titles miss the topic but H2 headings nail it.