# Pipeline Step 7: Health Scoring

**Code location:** `backend/app/services/health_scoring.py`
**Pipeline position:** Spec Step 4 = Code Step 7 (runs after AI citability at Code Step 6c)
**Post-cannibalization patch:** Code Step 8c (runs after cannibalization at Code Step 8)
**Trigger:** `POST /v1/{site_id}/intelligence/score-health` or full pipeline via ingestion router
**Class:** `HealthScorer` with two public methods: `score_site()` and `patch_roles_after_cannibalization()`

---

## 1. Pipeline Position

```
Code Step 6c: AI Citability        (populates ai_citability_score, eeat_score, schema_score, extraction_score)
Code Step 7:  Health Scoring       (this step — computes composite, assigns roles + ecosystem states)
Code Step 8:  Cannibalization      (detects keyword overlap pairs)
Code Step 8c: Role Patch           (patch_roles_after_cannibalization — fixes competitor roles + ecosystem states)
Code Step 9:  Problem Detection
Code Step 10: Recommendations
```

Health scoring depends on AI citability scores existing in `post_health_scores`. If >50% of posts in a cluster lack AI citability scores, a warning is logged.

---

## 2. Data Availability Detection

`score_site()` queries `ga4_metrics` and `gsc_metrics` counts for the site to determine mode:

| Condition | Mode | Label |
|-----------|------|-------|
| GA4 present + GSC present | `full` | All 8 factors at original weights |
| GA4 only or GSC only | `partial` | Missing factors zeroed, remaining rescaled to sum to 1.0 |
| Neither GA4 nor GSC | `crawl-only` | 6 crawl-derived factors at hand-tuned weights |

Mode is passed as `has_ga4` / `has_gsc` booleans to `_score_cluster()` and recorded in health history as `scoring_mode`.

---

## 3. Content Profile Detection

Before scoring, the site's median word count and stddev are computed from posts with `word_count > 50`:

```sql
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY word_count) AS median_wc,
       stddev(word_count) AS stddev_wc
FROM posts WHERE site_id = $1 AND word_count > 50
```

**Short-form detection:** `median_wc < 600 AND stddev_wc < 400`

When `is_short_form = True`:
- Content depth uses a gentler absolute curve (200w=40, 500w=70, 1000+=100 instead of the long-form 2500w=100)
- Relative vs absolute blend shifts to 35/65 (favoring cluster-relative) instead of 50/50
- Quality bonus cap raised to 25 points (vs 15 for long-form)

---

## 4. Weight Distribution

### Full-data mode (GA4 + GSC)

| Factor | Weight |
|--------|--------|
| traffic_trend | 20% |
| ranking | 18% |
| ai_readiness | 15% |
| engagement | 12% |
| freshness | 12% |
| content_depth | 10% |
| internal_links | 8% |
| technical_seo | 5% |
| **Total** | **100%** |

### Partial mode (one of GA4/GSC missing)

Missing factors are zeroed. Remaining factors are rescaled proportionally so weights sum to 1.0. For example, with GSC missing (ranking = 0), the remaining 82% is scaled by `1.0 / 0.82`.

### Crawl-only mode (no GA4, no GSC)

| Factor | Weight |
|--------|--------|
| ai_readiness | 28% |
| content_depth | 20% |
| content_richness | 20% |
| freshness | 15% |
| internal_links | 10% |
| technical_seo | 7% |
| traffic_trend | 0% |
| ranking | 0% |
| engagement | 0% |
| **Total** | **100%** |

Implemented in `compute_dynamic_weights(has_ga4, has_gsc)` which returns a `dict[str, float]`.

---

## 5. Factor Scoring Functions

### Factor 1: Traffic Trend (`_compute_trend`)

Compares 30-day pageviews (recent vs previous 30d). Returns `(trend_label, score)`.

| Condition | Label | Score |
|-----------|-------|-------|
| total_60d < 5 AND all zero | `unknown` | 30.0 |
| total_60d < 5 | `dead` | 0.0 |
| prev = 0, recent > 0 | `growing` | 100.0 |
| prev = 0, recent = 0, total >= 5 | `stable` | 30.0 |
| >15% increase | `growing` | 75-100 (scaled by magnitude) |
| >15% decrease | `declining` | 0-25 (scaled by magnitude) |
| -15% to +15% | `stable` | 50.0 |

### Factor 2: Ranking (`_ranking_score`)

Exponential decay from GSC average position:

```python
score = 100.0 * (1.0 - (avg_position - 1.0) / 49.0) ** 1.5
```

Position 1 = 100, Position 3 ~ 80, Position 10 ~ 35, Position 50+ = 0. Default `avg_position = 100.0` when no GSC data.

### Factor 3: Engagement (`_engagement_score`)

From GA4 bounce rate and avg engagement time:

```python
bounce_score = (1.0 - bounce_rate) * 100.0   # 0% bounce = 100
time_score = (avg_time / 300.0) * 100.0       # 300s+ = 100
score = 0.4 * bounce_score + 0.6 * time_score
```

Default: `bounce_rate = 0.5`, `avg_time = 60.0` when no GA4 data.

### Factor 4: Freshness (`_freshness_score`)

Continuous exponential decay with content-type-aware half-life:

- **Time-sensitive** (year in title/URL, "best", "top", "ranking", "pricing", "review"): half-life 6 months, floor 10
- **Evergreen** (all other content): half-life 12 months, floor 30
- **No date known:** returns 35.0 (slightly above evergreen floor)
- **Updated within 0.5 months:** returns 100.0

```python
raw = 100.0 * 0.5 ** (months_old / half_life)
return max(evergreen_floor, raw)
```

Time-sensitivity detected by `_is_time_sensitive(title, url)` which checks for `20[12]\d` regex and keyword matches.

### Factor 5: Content Depth (`_content_depth_score`)

Blends absolute and relative (vs cluster average) word count scores.

**Cluster average:** Uses actual cluster average for clusters with >= 3 posts. For clusters < 3 posts, defaults to 1000 (industry average).

**Absolute scale (long-form):** `min(100, word_count / 2500 * 100)` for >= 100 words.

**Absolute scale (short-form):** Gentler curve: 200w=40, 500w=70, 1000+=100.

**Relative scale:** Piecewise linear based on ratio to cluster average:
- 0.3x = 5, 0.5x = 20, 1.0x = 50, 1.5x = 80, 2.0x = 95, 2.0x+ = 100

**Blend:** 50/50 absolute/relative for long-form, 35/65 for short-form.

**Quality bonus** (`_content_quality_bonus`): 0-15 points (0-25 for short-form) for lists, stats/data, code blocks, tables, external links, images.

### Factor 6: Internal Links

Normalized to max inbound in cluster:

```python
link_score = min(100.0, (inbound / max(max_inbound, 1)) * 100.0)
```

Stored as `internal_link_score / 100.0` in the DB (0.0-1.0 range).

### Factor 7: Technical SEO (`_technical_seo_score`)

8 checks at 12.5 points each:

1. Has meta description (> 10 chars)
2. Title length 30-60 chars (partial credit for 20-70)
3. Has H2+ headings
4. Has outbound internal links
5. Has inbound internal links
6. Has Open Graph tags (from `eeat_metadata.has_og_tags`, fallback to body_html)
7. Has structured data / JSON-LD (from `eeat_metadata.has_jsonld` or `schema_types`)
8. Has canonical tag (from `eeat_metadata.has_canonical`)

OG, JSON-LD, and canonical are read from `eeat_metadata` (populated during crawl from `<head>` tags), not from `body_html` which only contains article content.

### Factor 8: Predicted Engagement (`_predicted_engagement_score`)

Crawl-only proxy for GA4 engagement. Checks for:

| Signal | Points |
|--------|--------|
| Images (`<img`, `<picture`, `<figure>`, `data-src`) | 20 |
| Lists (`<li`) | 15 |
| Readability 60-80 Flesch | 20 (40-60 or 80-90: 10) |
| 5+ headings | 15 (3+: 10) |
| Table of contents + 6+ headings | 10 |
| Code blocks (`<pre`, `<code`) | 10 |

Max raw = 90. Normalized: `score * 100/90` to fill 0-100 range.

### Factor 9: Content Structure (`_content_structure_score`)

Crawl-only richness signal. Checks for:

| Signal | Points |
|--------|--------|
| Heading density >= 1.5 per 500w | 25 (>= 0.8: 15, >= 0.4: 8) |
| 10+ list items | 20 (5+: 12, 2+: 5) |
| 5+ images | 20 (2+: 12, 1+: 5) |
| Tables | 15 |
| 5+ external links | 15 (2+: 8) |
| Blockquotes | 5 |

Max = 100.

### Factor 10: AI Readiness

Average of 4 dimensions from `post_health_scores` (populated by AI Citability at Code Step 6c):

```python
ai_readiness = mean(ai_citability_score, eeat_score, schema_score, extraction_score)
```

Default 40.0 (neutral) when AI citability has not run for a post.

---

## 6. Content Richness (Merged Factor)

In crawl-only mode, `content_richness` replaces the separate `predicted_engagement` and `content_structure` factors:

```python
content_richness = (predicted_engagement + content_structure) / 2.0
```

**Rationale:** Predicted engagement and content structure both measure structural HTML signals (images, lists, headings, code blocks). They had r=0.59-0.61 correlation with `technical_seo`, causing triple-counting. Merging them into a single 20% factor eliminates redundancy while preserving the signal.

In full-data and partial modes, `content_richness` weight is 0 (engagement comes from GA4).

---

## 7. Composite Score + Clamping

```python
composite = sum(weight[factor] * factor_score for all factors)
composite = max(10.0, min(95.0, composite))  # Clamp to 10-95
```

Z-score normalization was removed because it forced every cluster's mean to exactly 50, destroying inter-cluster variance. Raw composites with hand-tuned weights produce real spread. Clamping to 10-95 prevents extreme outliers.

---

## 8. Role Assignment

### First pass: Absolute thresholds via `_assign_role()`

**Crawl-only mode** (no traffic data):

| Condition | Role |
|-----------|------|
| `is_cannibalizing` | `competitor` |
| `composite >= 45` | `pillar` |
| `composite >= 30` | `supporter` |
| `composite >= 15` | `at_risk` |
| else | `dead_weight` |

**Full-data mode** (has traffic):

| Condition | Role |
|-----------|------|
| `composite < 15` or `recent_pv == 0` | `dead_weight` |
| `is_cannibalizing` | `competitor` |
| `traffic_contribution > 0.25` and `composite >= 40` | `pillar` |
| `composite >= 30` | `supporter` |
| else | `dead_weight` |

### Second pass: Relative override per cluster (crawl-only)

After clamping, when `not has_traffic_data and len(post_metrics) >= 3`:

1. Sort composites within the cluster
2. `pillar_cutoff = sorted_composites[int(len * 0.85)]` (85th percentile)
3. Override roles:
   - `competitor` roles are preserved (not overridden)
   - `composite >= pillar_cutoff` -> `pillar`
   - `composite >= 30` -> `supporter`
   - `composite >= 15` -> `at_risk`
   - else -> `dead_weight`

This ensures pillar = top ~15% per cluster. For a 53-post cluster, this yields ~8 pillars.

---

## 9. Ecosystem State Assignment

`_assign_ecosystem_state()` assigns one of 5 states to each cluster.

### Evaluation order (both modes):

1. **seedbed**: `has_recent` (post published within 30 days) AND `post_count <= 3`
2. Mode-specific checks (see below)
3. **meadow**: fallback for everything else

### With traffic data:

| State | Condition |
|-------|-----------|
| swamp | `cannibalization_rate > 0.5` OR (`post_count > 8` AND no pillar) |
| desert | all posts declining/dead OR `avg_traffic < 5` |
| forest | has pillar AND `cannibalization_rate < 0.2` AND `cluster_health > 50` |

### Without traffic data (crawl-only):

| State | Condition |
|-------|-----------|
| swamp | `cannibalization_rate > 0.5` |
| desert | `avg_freshness < 25` |
| forest | has pillar AND `cannibalization_rate < 0.2` AND `cluster_health > 38` |

**Forest threshold:** 50 with traffic, 38 crawl-only. The lower crawl-only threshold accounts for compressed composite score range (~28-57 vs ~10-95 with traffic).

`cannibalization_rate = cannibal_pairs_count / (post_count * (post_count - 1) / 2)`

---

## 10. Post-Cannibalization Role Patch

`patch_roles_after_cannibalization(db, site_id)` runs at Code Step 8c, after cannibalization detection at Code Step 8.

**Why it exists:** Health scoring (Code Step 7) runs before cannibalization (Code Step 8). On first pass, `cannibalization_pairs` is empty, so no posts get the `competitor` role. The patch fixes this without re-running the full scorer.

**What it does:**

1. Finds all post IDs in medium/high/critical cannibalization pairs
2. Sets `role = 'competitor'` for those posts (unless already `pillar`)
3. Re-evaluates ecosystem state for affected clusters only

**Pillar protection:** Posts with `role = 'pillar'` are NOT overridden to competitor.

---

## 11. Cluster-Level Health

After scoring all posts in a cluster:

- **With traffic:** Weighted average: `sum(composite * (traffic_90d / total_cluster_traffic))`
- **Without traffic:** Simple average: `sum(composite) / count`

Stored as `clusters.health_score`. Ecosystem state stored as `clusters.ecosystem_state`.

---

## 12. Score Confidence

Each post receives a `score_confidence` value:

| Mode | Value |
|------|-------|
| GA4 + GSC | `full` |
| GA4 only or GSC only | `partial` |
| Neither | `crawl_only` |

Stored in `post_health_scores.score_confidence` and returned in cluster detail API responses.

---

## 13. DB Operations + Table Schemas

### `post_health_scores` (per post)

```sql
CREATE TABLE post_health_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    traffic_contribution FLOAT,
    ranking_strength FLOAT,
    trend TEXT CHECK (trend IN ('growing', 'stable', 'declining', 'dead', 'unknown')),
    internal_link_score FLOAT,
    composite_score FLOAT,
    role TEXT CHECK (role IN ('pillar', 'supporter', 'competitor', 'dead_weight', 'at_risk')),
    engagement_score FLOAT,
    freshness_score FLOAT,
    content_depth_score FLOAT,
    technical_seo_score FLOAT,
    ai_citability_score FLOAT,
    eeat_score FLOAT,
    schema_score FLOAT,
    extraction_score FLOAT,
    ai_signals JSONB DEFAULT '{}',
    score_confidence TEXT DEFAULT 'crawl_only',
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);
-- UNIQUE constraint on post_id (for ON CONFLICT upsert)
```

### `health_score_history` (per site, per run)

```sql
CREATE TABLE health_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    score NUMERIC(5,2) NOT NULL,
    factor_scores JSONB,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_health_history_site ON health_score_history(site_id, analyzed_at DESC);
```

`factor_scores` JSONB includes: `engagement`, `freshness`, `content_depth`, `internal_links`, `technical_seo`, `ranking`, `traffic`, `ai_readiness`, and `scoring_mode`.

### `clusters` (updated fields)

```sql
health_score FLOAT,
ecosystem_state TEXT CHECK (ecosystem_state IN ('forest', 'swamp', 'desert', 'seedbed', 'meadow'))
```

### Write pattern

- Pre-scoring: NULLs existing scores ONLY for posts in leaf clusters (avoids destroying scores for posts outside leaf clusters)
- Per-post: Batch upsert via `INSERT ... ON CONFLICT (post_id) DO UPDATE`
- Per-cluster: `UPDATE clusters SET health_score, ecosystem_state`
- History: Single `INSERT INTO health_score_history` after all clusters scored

### Leaf cluster filter

All operations target leaf clusters only (clusters that are not parents):

```sql
WHERE c.id NOT IN (
    SELECT parent_cluster_id FROM clusters
    WHERE parent_cluster_id IS NOT NULL AND site_id = $1
)
```

---

## 14. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/{site_id}/intelligence/score-health` | Trigger health scoring (background task) |
| GET | `/v1/{site_id}/intelligence/health` | Site health summary (avg score, role counts, tier usage) |
| GET | `/v1/{site_id}/intelligence/health-history` | Historical scores with factor breakdown |
| GET | `/v1/{site_id}/intelligence/clusters/{cluster_id}` | Cluster detail (includes per-post scores + score_confidence) |

---

## 15. Performance

### Batch queries

7 batched CTE queries per cluster to minimize DB round trips:
1. Posts in cluster (with metadata)
2. Traffic recent 30d + previous 30d + 60d total + 90d total (4 queries)
3. Rankings (avg position, 90d)
4. Engagement (bounce rate, avg time, 90d)
5. Internal links (inbound + outbound counts)
6. Cannibalization pairs
7. AI readiness scores

### Parallel scoring

Threshold: `est_total_posts > 200` (based on total posts, not cluster count).

When parallel: uses `asyncio.Semaphore(5)` with connection pool. Each cluster scored in a separate connection. Failures logged but don't abort other clusters.

When sequential: clusters scored one at a time on the caller's connection.

### E2E benchmark

Predicted engagement scoring: 9.5ms per post (cached readability).

---

## 16. E2E Validation Results

**Dataset:** Copyblogger, 145 posts, 4 clusters, crawl-only mode.

| Metric | Value |
|--------|-------|
| Score range | 28.6 - 56.9 |
| Mean | 40.7 |
| Stddev | 6.4 |
| Pillar | 23 (16%) |
| Supporter | 119 (82%) |
| At-risk | 3 (2%) |
| Dead weight | 0 (0%) |
| Competitor | 0 (0%) |
| Ecosystem states | All 4 clusters: forest |

---

## 17. Open Issues

**S4-02: Internal links 0 for 99% of posts.** Copyblogger's capped crawl (200 pages) does not follow internal links deeply enough. Verify on Backlinko (full crawl).

**S4-04: Freshness has no variance.** Copyblogger has 2007-era content with no `modified_date`, so all posts get the same freshness score (35.0 no-date default). Verify on Backlinko which has more recent content.

**S4-14: Concurrent scoring race condition.** Two parallel `score_site()` calls for the same site could produce inconsistent results. The leaf-cluster filter prevents the worst case (scoring non-leaf clusters), but no explicit lock exists. In practice, the pipeline runs sequentially per site.

**S4-15: Quality bonus parsing trafilatura XML body_html.** `_content_quality_bonus` searches for HTML tags (`<li`, `<table`, `<img`) in `body_html`. If trafilatura returns XML-formatted output instead of raw HTML, tag matching may undercount elements.

---

## 18. Known Limitations

**KL1: Crawl-only score compression.** Composites compress to ~28-57 range in crawl-only mode (vs ~10-95 with traffic). The relative pillar override (Section 8) and lower forest threshold (Section 9) compensate, but absolute score values are less meaningful without traffic data.

**KL2: Year regex caps at 2029.** `_is_time_sensitive` uses `20[12]\d` which matches 2010-2029. Content with years 2030+ will not be detected as time-sensitive.

**KL3: History insert failures swallowed.** The `health_score_history` insert is wrapped in a try/except that logs a warning but does not propagate the error. A DB constraint violation or connection issue silently drops the history record.

**KL4: First-run cannibalization empty.** On the first pipeline run, health scoring (Code Step 7) runs before cannibalization (Code Step 8), so `cannibalization_pairs` is empty. The post-cannibalization role patch at Code Step 8c fixes this.

**KL5: Content richness sub-scores not persisted individually.** `predicted_engagement` and `content_structure` are computed per post but only their average (`content_richness`) contributes to the composite. Neither sub-score is stored in the database.

**KL6: Uniform-quality sites show same ecosystem state for all clusters.** On sites with consistent content quality (e.g., Copyblogger), all clusters may score above the forest threshold, producing identical ecosystem states. This is correct behavior but reduces the visual differentiation in the UI.

**KL7: Role overlap between pillar and supporter ranges.** A post scoring 47.0 could be pillar in one cluster (where 85th percentile is 46) or supporter in another (where 85th percentile is 49). This is intentional — the relative threshold creates cluster-appropriate pillar counts. The absolute threshold (>=45) serves as the initial assignment; the relative override replaces it entirely (except competitor roles, which are preserved from cannibalization data).

---

## Open Issues

5 items remain, all requiring Backlinko full-crawl verification or investigation:

| # | Issue | Status |
|---|-------|--------|
| S4-02 | Internal links 0 for 99% of posts | Verify on Backlinko full crawl — likely capped-crawl artifact |
| S4-04 | Freshness has no variance on Copyblogger | Verify on Backlinko (81% updated recently — should show variance) |
| S4-14 | Concurrent scoring race on shared post_ids | Document only — leaf-cluster filter prevents it, pipeline runs sequentially per site |
| S4-15 | Quality bonus parsing trafilatura XML body_html | Investigate whether `_content_quality_bonus` HTML checks work on trafilatura output format |
| S4-29 | All clusters show same ecosystem state | Verify Backlinko produces ecosystem differentiation (KL6 — correct behavior on uniform-quality sites) |