# Phase 2 — Intelligence Engine Build Task

Build the complete intelligence layer for "Tended" on top of the Phase 1 foundation at `/home/ubuntu/Projects/tended/backend/`.

This phase takes raw data (posts, embeddings, GA4 metrics, GSC metrics) and produces: topic clusters, cannibalization detection, health scores, ecosystem state assignments, consolidation ranking, and the Pre-Publish Oracle.

## What Already Exists (Phase 1 — DO NOT MODIFY)

- `backend/app/` — FastAPI app with routers, services, models, dependencies
- `backend/app/services/` — wordpress.py, sitemap.py, ga4.py, gsc.py, embeddings.py, normalizer.py
- `backend/app/routers/` — auth.py, sites.py, ingestion.py, analytics.py
- `backend/app/models/schemas.py` — existing Pydantic models
- `backend/app/dependencies.py` — shared auth deps
- `backend/app/utils/` — rate_limiter.py, encryption.py
- `backend/migrations/001_initial_schema.sql` — includes clusters, post_clusters, cannibalization_pairs, post_health_scores tables

## What to Build

### 1. New Service Files

Create these in `backend/app/services/`:

#### `clustering.py` — Topic Clustering via HDBSCAN

```python
# Takes all post embeddings for a site and clusters them
# Uses HDBSCAN (from hdbscan or sklearn.cluster) on the embedding vectors
# Auto-determines optimal number of clusters (no manual config needed)
# Steps:
#   1. Fetch all embeddings from post_embeddings table for the site
#   2. Run HDBSCAN clustering (min_cluster_size=3, metric='euclidean')
#   3. Label each cluster by sending top 5 posts (by traffic) to Claude API
#      Prompt: "These are blog post titles from the same topic cluster: [titles]. 
#               Generate a short 2-4 word label for this topic cluster."
#   4. Handle outliers (HDBSCAN label -1) — flag as "unclustered"
#   5. Store results: create/update clusters table, create post_clusters assignments
#   6. Update cluster.post_count for each cluster
#
# Must handle:
#   - Sites with < 10 posts (just one cluster or skip)
#   - Dimensionality reduction via UMAP before HDBSCAN for better results
#     (1536 dims → 50 dims via UMAP, then HDBSCAN)
#   - Idempotent: re-running clears old clusters and recreates
```

#### `cannibalization.py` — Cannibalization Detection

```python
# For each cluster, detect which posts are cannibalizing each other
# Steps:
#   1. For each cluster, get all posts and their GSC query data
#   2. For each pair of posts in the cluster:
#      a. Get set of queries each post ranks for (from gsc_metrics)
#      b. Calculate Jaccard similarity: |A ∩ B| / |A ∪ B|
#      c. If overlap >= 0.30 (30%), flag as cannibalizing pair
#   3. Calculate severity score for each pair:
#      severity = overlap_percentage × position_proximity_factor × traffic_split_factor
#      
#      position_proximity_factor:
#        - Both posts positions 5-20: 1.0 (high — both competing in striking distance)
#        - Both posts positions 1-5: 0.8 (already ranking well but splitting)
#        - One post top 10, other 20-50: 0.5 (moderate)
#        - One post top 10, other 50+: 0.2 (low — not really competing)
#      
#      traffic_split_factor:
#        - 50/50 split: 1.0 (worst — totally split authority)
#        - 70/30 split: 0.7
#        - 90/10 split: 0.3
#        - 95/5 split: 0.1
#   4. Assign severity label: critical (>0.7), high (>0.5), medium (>0.3), low (<=0.3)
#   5. Store overlapping queries for each pair
#   6. Store in cannibalization_pairs table
#
# Performance: for clusters with 20+ posts, use top-N queries per post (limit 50)
#              to avoid O(n²) explosion on query comparisons
```

#### `health_scoring.py` — Post & Cluster Health Scoring

```python
# Calculate health scores at post level and cluster level
#
# POST-LEVEL HEALTH:
#   1. traffic_contribution: post's 90-day pageviews / cluster's total 90-day pageviews
#      Score 0-1 (what % of cluster traffic does this post drive?)
#
#   2. ranking_strength: weighted average position for post's top queries
#      Transform: position 1 → score 1.0, position 10 → 0.5, position 50+ → 0.1
#      Formula: score = max(0, 1 - (avg_position - 1) / 50)
#
#   3. trend: linear regression on daily traffic over last 90 days
#      slope > +2% per week → "growing"
#      slope between -2% and +2% → "stable"  
#      slope < -2% per week → "declining"
#
#   4. internal_link_score: (inbound_links + outbound_links) / max_links_in_cluster
#      Normalized 0-1. Posts with more internal links are better connected.
#
#   5. composite_score: weighted combination
#      = 0.35 * traffic_contribution 
#      + 0.25 * ranking_strength 
#      + 0.25 * trend_score  (growing=1.0, stable=0.5, declining=0.0)
#      + 0.15 * internal_link_score
#      Result: 0-100 scale
#
#   6. role assignment:
#      - "pillar": highest composite_score in cluster AND traffic_contribution > 0.30
#      - "supporter": composite_score > 40 AND not pillar
#      - "competitor": in a cannibalization_pair with severity >= "medium"
#      - "dead_weight": composite_score < 15 OR (zero traffic for 90 days)
#
# CLUSTER-LEVEL HEALTH:
#   Average of post composite_scores, weighted by traffic
#
# ECOSYSTEM STATE ASSIGNMENT per cluster:
#   🌲 "forest": has_pillar AND cannibalization_rate < 0.2 AND avg_health > 50
#   🪴 "swamp": cannibalization_rate > 0.5 OR (post_count > 8 AND no clear pillar)
#   🏜️ "desert": all posts declining OR avg_traffic_per_post < threshold
#   🌱 "seedbed": any post published within 30 days AND cluster size <= 3
#   🌻 "meadow": everything else (stable, modest performance)
#   
#   cannibalization_rate = cannibalizing_pairs / total_possible_pairs
#
# Store everything in post_health_scores table
# Update clusters table with health_score and ecosystem_state
```

#### `consolidation.py` — Consolidation Ranking & Plans

```python
# For each "swamp" cluster, generate a prioritized consolidation plan
#
# Steps:
#   1. Get all swamp clusters for the site
#   2. For each swamp:
#      a. Identify the pillar candidate (highest composite_score)
#      b. Identify supporting posts to merge INTO the pillar
#         (posts with high overlap with pillar, ordered by composite_score desc)
#      c. Identify dead weight to redirect or remove
#         (composite_score < 15, zero traffic)
#      d. Calculate estimated_traffic_recovery:
#         Sum of traffic from cannibalizing posts that would consolidate to pillar
#         Multiply by 0.6 (conservative — not all traffic transfers)
#      e. Calculate estimated_effort:
#         Number of posts to merge × average word count / 1000 (rough hours estimate)
#      f. Priority score = estimated_traffic_recovery / estimated_effort
#   3. Rank all consolidation opportunities by priority score
#   4. Tag the #1 opportunity as "Quick Win of the Week"
#
# Also provide a consolidation draft generator endpoint:
#   - Takes cluster_id
#   - Sends pillar post + merge candidate posts to Claude API
#   - Prompt: structured merge request (see below)
#   - Returns the AI-generated consolidated draft
#
# Claude consolidation prompt:
# """
# You are a content strategist consolidating multiple blog posts into one 
# authoritative piece. 
#
# PILLAR POST (keep this structure and voice):
# Title: {pillar_title}
# Content: {pillar_body_text}
#
# POSTS TO MERGE (extract unique insights, data, examples):
# {for each merge candidate: title + body_text}
#
# Instructions:
# 1. Keep the pillar post's structure, tone, and primary angle
# 2. Integrate unique insights, statistics, examples, and perspectives 
#    from the merge posts that aren't already in the pillar
# 3. Remove redundancy — don't repeat the same point twice
# 4. Ensure the final piece is comprehensive and authoritative
# 5. Output the complete merged post in markdown format
# """
#
# Also generate redirect map: list of {old_url → pillar_url} for each merged/removed post
```

#### `oracle.py` — Pre-Publish Oracle

```python
# Before publishing new content, analyze against existing ecosystem
#
# Input: draft_text OR target_keyword (at least one required)
# 
# Steps:
#   1. If draft_text provided: generate embedding via OpenAI
#   2. Find top 10 most similar existing posts via cosine similarity in pgvector
#      SELECT p.*, pe.embedding <=> $1 AS distance 
#      FROM post_embeddings pe JOIN posts p ON p.id = pe.post_id
#      WHERE p.site_id = $2
#      ORDER BY pe.embedding <=> $1 LIMIT 10
#   3. If target_keyword provided: check GSC data for existing posts ranking for it
#      SELECT DISTINCT p.* FROM gsc_metrics g JOIN posts p ON p.id = g.post_id
#      WHERE p.site_id = $1 AND g.query ILIKE '%keyword%'
#   4. Analyze overlap:
#      - How many existing posts cover this topic? (cosine distance < 0.3 = very similar)
#      - Which cluster would this fall into?
#      - Is that cluster a swamp already?
#      - What's the strongest existing post on this topic?
#   5. Generate verdict via Claude API:
#      - Send: draft/keyword + top similar posts + cluster state
#      - Ask Claude to assess: should they publish, update existing, or skip?
#   6. Return structured verdict:
#      {
#        "confidence": "high" | "medium" | "low",
#        "verdict": "publish" | "update_existing" | "skip",
#        "reasoning": "...",  // Claude's analysis
#        "similar_posts": [...],  // top matches with similarity scores
#        "cluster_state": "forest" | "swamp" | etc,
#        "recommendation": "..."  // specific action recommendation
#      }
#
# Confidence mapping:
#   high (publish): no similar posts within cosine distance 0.3, cluster is not swamp
#   medium (update): some overlap exists, but cluster could use refreshing
#   low (skip): heavy overlap, cluster is swamp, existing post already ranks well
```

### 2. New Router File

Create `backend/app/routers/intelligence.py`:

```python
# New endpoints for Phase 2 intelligence features
# Prefix: /sites/{site_id}/intelligence/

# POST /sites/{site_id}/intelligence/cluster
#   Trigger topic clustering for the site (background task)
#   Returns: TaskTriggerResponse

# GET /sites/{site_id}/intelligence/clusters
#   List all clusters with their ecosystem state, health score, post count
#   Returns: list of ClusterResponse

# GET /sites/{site_id}/intelligence/clusters/{cluster_id}
#   Detailed cluster view: all posts with roles, health scores
#   Returns: ClusterDetailResponse

# POST /sites/{site_id}/intelligence/detect-cannibalization
#   Trigger cannibalization detection (background task, requires clusters exist)
#   Returns: TaskTriggerResponse

# GET /sites/{site_id}/intelligence/cannibalization
#   List all cannibalization pairs, grouped by cluster, sorted by severity
#   Returns: list of CannibalizationPairResponse

# POST /sites/{site_id}/intelligence/score-health
#   Trigger health scoring (background task, requires clusters + cannibalization)
#   Returns: TaskTriggerResponse

# GET /sites/{site_id}/intelligence/health
#   Site-wide health dashboard data
#   Returns: SiteHealthResponse {
#     content_health_score: float,
#     total_posts: int,
#     active_posts: int,
#     passive_posts: int,
#     cannibalistic_posts: int,
#     dead_posts: int,
#     content_efficiency_ratio: float,
#     clusters: list[ClusterSummary],
#     trends: { "30d": float, "60d": float, "90d": float }
#   }

# GET /sites/{site_id}/intelligence/consolidation
#   Ranked list of consolidation opportunities
#   Returns: list of ConsolidationPlanResponse

# GET /sites/{site_id}/intelligence/consolidation/{cluster_id}
#   Detailed consolidation plan for a specific cluster
#   Returns: ConsolidationDetailResponse

# POST /sites/{site_id}/intelligence/consolidation/{cluster_id}/draft
#   Generate AI consolidation draft (calls Claude API)
#   Returns: { "draft_markdown": str, "redirect_map": list[{old_url, new_url}] }

# POST /sites/{site_id}/intelligence/oracle
#   Pre-publish oracle check
#   Body: { "draft_text": str | None, "target_keyword": str | None }
#   Returns: OracleVerdictResponse

# POST /sites/{site_id}/intelligence/run-all
#   Run the full intelligence pipeline: cluster → detect cannibalization → score health
#   Background task that runs all three in sequence
#   Returns: TaskTriggerResponse
```

### 3. New Pydantic Models

Add to `backend/app/models/schemas.py`:

```python
# ClusterResponse — id, site_id, label, ecosystem_state, health_score, post_count
# ClusterDetailResponse — extends ClusterResponse with list of posts (with roles, health)
# ClusterSummary — lightweight: id, label, ecosystem_state, post_count

# CannibalizationPairResponse — post_a (title, url), post_b (title, url), 
#   overlap_score, severity, overlapping_queries

# PostHealthResponse — post_id, title, url, composite_score, role, trend,
#   traffic_contribution, ranking_strength, internal_link_score

# SiteHealthResponse — content_health_score, total_posts, active_posts, 
#   passive_posts, cannibalistic_posts, dead_posts, content_efficiency_ratio,
#   clusters list, 30/60/90 day trends

# ConsolidationPlanResponse — cluster_id, cluster_label, priority_score,
#   pillar_post (title, url), merge_candidates count, dead_weight count,
#   estimated_traffic_recovery, estimated_effort, is_quick_win

# ConsolidationDetailResponse — extends above with full lists of:
#   pillar_post, merge_candidates (with titles/urls/scores), 
#   dead_weight (with titles/urls), redirect_map [{old_url, new_url}]

# OracleVerdictResponse — confidence, verdict, reasoning, similar_posts list,
#   cluster_state, recommendation

# ConsolidationDraftResponse — draft_markdown, redirect_map
```

### 4. Update requirements.txt

Add these dependencies:
```
hdbscan==0.8.40
umap-learn==0.5.7
scikit-learn==1.6.1
numpy==2.2.2
anthropic==0.42.0
```

### 5. Register the New Router

In `backend/app/main.py`, add:
```python
from app.routers import intelligence
app.include_router(intelligence.router, prefix="/sites", tags=["Intelligence"])
```

### 6. Configuration

Add to `backend/app/config.py`:
```python
# Anthropic (Claude API for consolidation drafts, oracle, cluster labels)
anthropic_api_key: str = ""
```

Add to `backend/.env.example`:
```
# Anthropic (Claude API)
ANTHROPIC_API_KEY=
```

## Quality Requirements

- All code async where possible
- Type hints everywhere
- Proper error handling with logging
- Docstrings on all classes and public methods
- Claude API calls should use the `anthropic` Python SDK (AsyncAnthropic)
- Use Claude model `claude-sonnet-4-20250514` for all Claude API calls
- Rate limit Claude API calls (max 5/second)
- All background tasks should log start/completion/failure
- The intelligence pipeline should be idempotent — re-running produces correct results

## Important Notes

- DO NOT modify any existing Phase 1 files except to add imports/router registration in main.py
- DO NOT modify existing schemas — only ADD new models to schemas.py
- The clusters, post_clusters, cannibalization_pairs, and post_health_scores tables already exist in the migration
- Test that all Python files compile clean when finished
- When finished, commit with message "feat: Phase 2 intelligence engine — clustering, cannibalization, health scoring, consolidation, oracle"
- Then run: openclaw system event --text "Done: Phase 2 intelligence engine complete — HDBSCAN clustering, cannibalization detection, health scoring, ecosystem states, consolidation plans, pre-publish oracle." --mode now
