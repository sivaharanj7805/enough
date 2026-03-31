# Pipeline Step 6: Topic Clustering & Map Positioning

> **Scope:** Everything that happens after Steps 2-5 (enrichment: embeddings, readability, PageRank, intent) and before Step 7 (health scoring). This step groups posts into topic clusters using UMAP + HDBSCAN, computes 2D map positions for the ecosystem visualization, labels each cluster, and optionally sub-clusters mega-clusters. No health scoring, no cannibalization, no problem detection — just topological structure discovery.

---

## Pipeline Position

After Step 2 stores embeddings in `post_embeddings` and enrichment signals on `posts` / `post_health_scores`, the full pipeline runs these sub-steps sequentially:

```
Step 1: Crawl + Normalize (done)
Steps 2-5: Embeddings + Readability + PageRank + Intent (done)
   |
Step 6a: UMAP reduction (1536 -> 15 dims) + HDBSCAN clustering        <- CPU-bound, ~5-30s
Step 6a+: UMAP reduction (1536 -> 2D) for map positions               <- CPU-bound, ~2-10s
Step 6a++: Cluster-aware 2D nudge (15% pull toward cluster centroid)   <- CPU, <0.1s
Step 6c-main: Noise assignment (orphan posts -> nearest cluster)       <- CPU, <1s
Step 6d: Rebuilding flag set (frontend shows overlay, not blank data)  <- DB write
Step 6e: Clear old cluster data (idempotent)                           <- DB deletes
Step 6f: Cluster storage + 2D position writes                         <- DB writes
Step 6g: Recursive sub-clustering (clusters > 25 posts)               <- CPU + DB
Step 6h: TF-IDF cluster labeling (zero API calls)                     <- CPU, ~0.5s
Step 6i: Claude label backfill (optional quality upgrade)              <- Anthropic API, ~$0.02
   |
Step 7: Health Scoring (next pipeline step)
```

Each sub-step is independently error-handled via `_pipeline_step()` — a failure in labeling doesn't block clustering or downstream steps.

### Step Mapping: Spec vs Code

The spec documents use Steps 1-7. The code in `ingestion.py:_run_full_pipeline` uses Steps 1-10b. This table maps between the two:

| Spec Step | Code Step | Service |
|-----------|-----------|---------|
| Step 1 | Step 1 | Crawl + Normalize |
| Step 2a | Step 2 | Embeddings |
| Step 2b | Step 3 | Readability |
| Step 2c | Step 4 | PageRank |
| Step 2d | Step 5 | Intent Classification |
| **Step 3** | **Step 6** | **Clustering (this document)** |
| Step 3h | Step 6b | TF-IDF Cluster Labels |
| (none) | Step 6c | AI Citability (runs once here, not in Step 2) |
| Step 4 | Step 7 | Health Scoring |
| Step 5 | Step 8 | Cannibalization |
| (none) | Step 8b | Chunk Confirmation (optional, $0.50) |
| Step 6 | Step 9 | Problem Detection |
| Step 7 | Step 10 | Recommendations |
| (none) | Step 10b | Claude Enrichment (optional) |

In the full pipeline (`ingestion.py:_run_full_pipeline`), Step 6 maps to:
- **Step 6:** `TopicClusterer().cluster_site(db, site_id, skip_labeling=True)` — runs 6a through 6g
- **Step 6b:** `label_clusters_fast(db, site_id)` — runs 6h (TF-IDF labels)

Claude label backfill (6i) runs separately via the intelligence router, not in the default pipeline — it's an optional quality upgrade costing ~$0.02 per site.

### Progress Reporting

Unlike the crawl step (which updates `crawl_jobs.posts_processed` every 25 URLs), the clustering step now reports progress at key checkpoints via an `on_progress` callback:

1. `"Fetched {n} embeddings"` — after DB query
2. `"UMAP + HDBSCAN complete — {n} clusters found"` — after ML finishes
3. `"Stored {n} clusters — checking for mega-clusters"` — after DB writes

In the full pipeline, these updates are written to `crawl_jobs.current_step` as `"clustering: {msg}"` using a fire-and-forget task with a **separate pool connection** (not the main pipeline connection, to avoid asyncpg concurrency errors).

---

## 6a. UMAP Dimensionality Reduction (`services/clustering.py`)

### What It Does

Reduces 1536-dimensional OpenAI embeddings down to 15 dimensions for clustering, and separately down to 2 dimensions for the ecosystem map visualization. This is necessary because HDBSCAN (density-based clustering) suffers from the "curse of dimensionality" — in 1536-dim space, all points are roughly equidistant, making density-based separation impossible.

### Why UMAP Over PCA or t-SNE

| Method | Preserves | Speed | Why Not |
|--------|-----------|-------|---------|
| **PCA** | Global variance | Fastest | Loses local neighborhood structure — similar posts may not cluster correctly |
| **t-SNE** | Local structure | Very slow | Non-parametric (can't reuse the model), bad at preserving global relationships between clusters |
| **UMAP** | Local + global | Fast | Best balance: similar posts stay close, different topics stay far apart. Parameterized for reproducibility |

### Step 1: Fetch Embeddings

```sql
SELECT p.id AS post_id, p.title, p.url, p.word_count,
       pe.embedding::text AS embedding_text
FROM post_embeddings pe
JOIN posts p ON p.id = pe.post_id
WHERE p.site_id = $1
ORDER BY p.id
```

The `embedding::text` cast converts pgvector's binary format to `[0.123,0.456,...]` text, which is parsed by `_parse_pgvector()` into a Python `list[float]`. These are stacked into a `numpy.float32` array of shape `(n_posts, 1536)`.

### Small Site Shortcut (< 15 posts)

If fewer than 15 posts exist, UMAP/HDBSCAN are skipped entirely:
- All posts assigned to a single cluster (label `0`)
- 2D positions computed as a simple circular layout (evenly spaced around a circle of radius 2.0)
- This avoids UMAP failing on tiny datasets where `n_neighbors` would exceed the sample count
- Sites with 5-15 posts get unstable HDBSCAN results (`min_cluster_size=2` on 10 points in 15D produces random clusters). Clustering adds value starting around 20 posts where mental load exceeds what a person can hold.

### Adaptive Similarity Analysis

Before running UMAP, the algorithm samples up to 100 posts and computes the **mean pairwise cosine similarity** to characterize the site's content diversity:

```python
from sklearn.metrics.pairwise import cosine_similarity as cos_sim
sample_size = min(100, n_posts)
sample_indices = np.random.choice(n_posts, sample_size, replace=False)
sample = embeddings[sample_indices]
sim_matrix = cos_sim(sample)
np.fill_diagonal(sim_matrix, 0)
mean_sim = sim_matrix.mean()
```

This is the critical calibration step that makes clustering work across different site archetypes:

| Mean Similarity | Site Type | UMAP Strategy |
|----------------|-----------|---------------|
| **> 0.70** | Tight niche (e.g., all posts about SEO) | `min_dist=0.25`, `n_neighbors=5` — **INCREASE** spread so UMAP pushes similar points apart, making subtle differences visible to HDBSCAN |
| **0.50-0.70** | Moderate focus (e.g., digital marketing blog) | `min_dist=0.1` — balanced |
| **< 0.50** | Diverse content (e.g., general lifestyle blog) | `min_dist=0.05` — compact clusters, let HDBSCAN find tight structure |

**Why this matters:** Without this calibration, a tight-niche SEO blog would collapse into 1-2 mega-clusters because all posts are already similar. Increasing `min_dist` forces UMAP to spread the similar points out, revealing sub-topic structure that HDBSCAN can then find.

### UMAP Parameters for Clustering

```python
reducer_cluster = umap.UMAP(
    n_components=max(2, min(15, n_posts - 2)),  # 15 dims or less if tiny site
    n_neighbors=min(15, n_posts - 1),            # Default 15, reduced for small sites
    min_dist=<adaptive>,                          # 0.05, 0.1, or 0.25 based on mean similarity
    metric="cosine",                              # Matches embedding space geometry
    random_state=42,                              # Reproducibility
)
reduced = reducer_cluster.fit_transform(embeddings)  # Shape: (n_posts, 15)
```

| Parameter | Value | Research Basis |
|-----------|-------|---------------|
| `n_components` | 15 (capped at `n_posts - 2`) | Research consensus: "no less than 15 dimensions" for HDBSCAN on high-dim embeddings. Range 5-20 optimal. |
| `n_neighbors` | 15 (capped at `n_posts - 1`) | Controls local vs global structure. 15 is standard; reduced to 5 for tight niches to find micro-clusters |
| `min_dist` | Adaptive (0.05-0.25) | Auto-calibrated per site based on mean pairwise similarity |
| `metric` | `"cosine"` | OpenAI embeddings are L2-normalized, so cosine distance is the natural metric |
| `random_state` | 42 | Ensures deterministic results across re-runs |

### CPU Offloading

UMAP is CPU-bound (involves nearest-neighbor graph construction and spectral embedding). It runs inside `asyncio.to_thread()` to avoid blocking the async event loop:

```python
labels, positions_2d = await asyncio.to_thread(
    self._run_clustering_and_2d, embeddings, n_posts,
)
```

This means the FastAPI server stays responsive to other requests while clustering runs in a thread pool.

---

## 6b-main. HDBSCAN Clustering

### What It Does

HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise) groups the 15-dimensional UMAP-reduced embeddings into topic clusters. Unlike k-means, it:
- **Doesn't require specifying `k`** — discovers the natural number of clusters
- **Handles non-spherical clusters** — topics can have irregular shapes
- **Identifies noise points** — posts that don't fit any cluster are labeled `-1` (noise) rather than being forced into a bad cluster

### Adaptive Parameters

The `min_cluster_size` parameter controls how many posts are needed to form a cluster. It's adaptive based on site size:

| Post Count | `min_cluster_size` | `min_samples` | Rationale |
|------------|-------------------|---------------|-----------|
| **< 20** | `max(2, n // 5)` | 1 | Very small sites — allow 2-post clusters |
| **20-99** | `max(3, n // 10)` | 2 | Medium sites — clusters need 3+ posts |
| **100-499** | `max(5, n // 20)` | 3 | Large sites — clusters need 5+ posts |
| **500-999** | 12 | 3 | Big sites — fixed reasonable minimum |
| **1000+** | 20 | 5 | Mega sites — capped at 20 to avoid collapsing into 3 mega-clusters |

**Note:** Sites with < 15 posts never reach HDBSCAN — they get the single-cluster shortcut.

**Why the cap at 20:** Without a cap, `min_cluster_size` would keep growing with post count (e.g., `n // 20 = 50` for a 1000-post site), forcing HDBSCAN to only find clusters of 50+ posts — which collapses a diverse 1000-post blog into just 3-5 mega-clusters. The cap at 20 lets it discover dozens of meaningful sub-topics.

### HDBSCAN Configuration

```python
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=min_cluster_size,
    min_samples=min_samples,
    metric="euclidean",              # UMAP output is Euclidean
    cluster_selection_method="eom",  # Excess of Mass — preserves cluster hierarchy
)
labels = clusterer.fit_predict(reduced)
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `metric` | `"euclidean"` | UMAP output is already in Euclidean space (UMAP transforms cosine -> Euclidean) |
| `cluster_selection_method` | `"eom"` (Excess of Mass) | Default HDBSCAN method. Balances between splitting and merging clusters. Alternative `"leaf"` would produce more fine-grained clusters |
| `min_samples` | Decoupled from `min_cluster_size` | Set lower to be less conservative about noise. A high `min_samples` would mark too many edge posts as noise |

### Silhouette Quality Gate with Retry

After clustering, the algorithm evaluates quality using the **silhouette score** — a metric from -1 to 1 measuring how similar a point is to its own cluster versus the nearest other cluster:

```python
from sklearn.metrics import silhouette_samples, silhouette_score

mask = labels != -1  # Exclude noise
avg_silhouette = float(silhouette_score(reduced[mask], labels[mask]))
```

| Silhouette Score | Interpretation |
|-----------------|----------------|
| **> 0.5** | Excellent — clearly separated clusters |
| **0.25-0.5** | Good — reasonable structure |
| **0.1-0.25** | Weak — overlapping clusters |
| **< 0.1** | Poor — clusters are barely distinguishable |

**Retry logic:** If `avg_silhouette < 0.1` and we haven't retried yet (max 2 retries), bump `min_cluster_size += 1` and retry HDBSCAN. This forces slightly larger clusters, which often produces better-separated groups:

```python
if avg_silhouette < 0.1 and retry_count < 2:
    retry_count += 1
    min_cluster_size += 1
    continue  # Re-run HDBSCAN with larger min_cluster_size
```

Per-cluster silhouette scores are also computed and stored on the `clusters` table (migration 028) for downstream quality assessment:

```python
for cl in set(labels[mask]):
    cl_scores = per_sample[labels[mask] == cl]
    self._cluster_silhouettes[int(cl)] = float(np.mean(cl_scores))
```

---

## 6c-main. Noise Point Assignment

### What It Does

HDBSCAN marks posts that don't belong to any dense region as "noise" (label `-1`). Rather than leaving them unclustered (which breaks downstream analysis that assumes every post has a cluster), each noise point is assigned to the **nearest cluster centroid** by Euclidean distance:

```python
from sklearn.metrics.pairwise import euclidean_distances

# Compute centroid of each cluster
centroids = np.array([
    reduced[labels == c].mean(axis=0)
    for c in unique_clusters
])

# For each noise point, find nearest centroid
noise_indices = np.where(noise_mask)[0]
noise_reduced = reduced[noise_indices]
dists = euclidean_distances(noise_reduced, centroids)
nearest = np.argmin(dists, axis=1)

for i, idx in enumerate(noise_indices):
    labels[idx] = unique_clusters[nearest[i]]
```

This runs inside `_run_clustering_and_2d` (the threaded function), so by the time `cluster_site` receives labels, all noise has already been reassigned. The `unclustered_indices` list in `cluster_site` will be empty unless HDBSCAN found zero clusters.

### Why Assign Noise Instead of Leaving It

1. **Ecosystem visualization requires cluster membership** — the landscape map colors and groups posts by cluster. Unclustered posts would be orphans with no territory.
2. **Cannibalization detection requires clusters** — it compares posts within the same cluster for overlap. Unclustered posts would be invisible to cannibalization detection.
3. **Health scoring aggregates by cluster** — ecosystem states (forest/swamp/desert) are assigned per cluster. Unclustered posts can't get an ecosystem state.

### Fallback: "Unclustered" Meta-Cluster

An "Unclustered" meta-cluster is created **only when HDBSCAN found zero clusters** (all posts were noise on every retry). This is gated by `if unclustered_indices and not cluster_groups:` — it does not fire in the normal case where noise was reassigned to real clusters.

---

## 6d. 2D Map Positions (Ecosystem Visualization)

### What It Does

Runs a **second, separate UMAP reduction** from the original 1536-dim embeddings down to exactly 2 dimensions. These (x, y) coordinates become the map positions for the ecosystem landscape visualization — the signature feature of the product.

### Why a Separate UMAP Run (Not Just First 2 Dims of the 15D)

Taking the first 2 of 15 UMAP dimensions would produce terrible 2D layout because:
- UMAP dimensions are not ordered by importance (unlike PCA)
- The first 2 dims of a 15D UMAP capture just a slice of the structure
- A dedicated 2D UMAP with `min_dist=0.3` optimizes specifically for visual clarity

### Parameters

```python
reducer_2d = umap.UMAP(
    n_components=2,
    n_neighbors=n_neighbors,    # Same as clustering (5 or 15)
    min_dist=0.3,               # Spread out for visual clarity
    metric="cosine",
    random_state=42,
)
positions_2d = reducer_2d.fit_transform(embeddings)  # Shape: (n_posts, 2)
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `n_components` | 2 | Exactly 2D for map rendering |
| `min_dist` | 0.3 | Higher than clustering UMAP — spreads points out for visual clarity so posts don't overlap on the canvas |
| `metric` | `"cosine"` | Consistent with clustering |
| `random_state` | 42 | Same seed — ensures 2D layout is consistent across re-runs |

### Cluster-Aware 2D Nudge

After UMAP 2D and before returning positions, each post is nudged **15% toward its cluster's 2D centroid**. This reduces inter-cluster overlap on the ecosystem map without destroying the topological structure:

```python
unique_labels = set(labels)
unique_labels.discard(-1)
if unique_labels:
    centroids_2d = {
        c: positions_2d[labels == c].mean(axis=0) for c in unique_labels
    }
    for i, lbl in enumerate(labels):
        if lbl in centroids_2d:
            positions_2d[i] += 0.15 * (centroids_2d[lbl] - positions_2d[i])
```

**Why this is needed:** The 2D UMAP runs on raw embeddings, independent of clustering results. Without the nudge, two posts in different clusters can overlap on the 2D map, and the frontend's convex hull territory polygons would intersect. The 15% nudge pulls posts inward toward their cluster center of mass, tightening cluster territories while preserving relative positions within each cluster.

**Edge cases:**
- Single cluster: all posts nudge toward the same centroid — harmless but a no-op (centroid is the mean of all points).
- Zero clusters (all noise, labels all `-1`): `unique_labels` is empty after `discard(-1)`, guard prevents any iteration. Positions unchanged.

### Storage

Positions are stored on the `posts` table using a single batch `unnest()` UPDATE instead of N individual UPDATEs:

```python
pos_x = [float(positions_2d[idx, 0]) for idx in range(len(post_ids))]
pos_y = [float(positions_2d[idx, 1]) for idx in range(len(post_ids))]
await db.execute(
    """
    UPDATE posts SET x_pos = d.x, y_pos = d.y
    FROM (SELECT unnest($1::uuid[]) AS id, unnest($2::float8[]) AS x, unnest($3::float8[]) AS y) d
    WHERE posts.id = d.id
    """,
    post_ids, pos_x, pos_y,
)
```

| Column | Type | Source |
|--------|------|--------|
| `posts.x_pos` | FLOAT | UMAP 2D x-coordinate (nudged) |
| `posts.y_pos` | FLOAT | UMAP 2D y-coordinate (nudged) |

These coordinates are consumed by the frontend's `EcosystemCanvas.tsx` to render posts as creatures/plants/trees on the landscape map, with cluster territory polygons drawn around groups.

---

## 6e. Rebuilding Status Flag

### What It Does

Before clearing old cluster data, the system sets `crawl_jobs.current_step = 'rebuilding'`. This tells the frontend to show an amber "Refreshing your data..." overlay instead of empty tables during the rebuild window.

```python
await db.execute(
    """UPDATE crawl_jobs SET current_step='rebuilding', updated_at=NOW()
       WHERE site_id=$1""",
    site_id,
)
```

### Frontend Handling

`PipelineProgress.tsx` checks for the `'rebuilding'` state before rendering the normal progress stages:

```tsx
if (status.current_step === 'rebuilding') {
  return (
    <div className="rounded-xl border border-[#f59e0b]/20 bg-[#f59e0b]/5 px-4 py-3 card-in">
      <Loader2 size={14} className="animate-spin text-[#f59e0b]" />
      <span className="text-sm font-medium text-[#f59e0b]">Refreshing data</span>
      <p className="text-xs text-[#94a3b8] mt-1">{copy.rebuilding}</p>
    </div>
  );
}
```

The `PipelineStatus.current_step` type in `lib/types.ts` includes `'rebuilding' | string` to accommodate this and future sub-step strings like `'clustering: Found 12 clusters'`.

### Why This Exists

`_clear_old_clusters()` deletes cannibalization_pairs, post_health_scores, post_clusters, and clusters before storing new ones. During the 60-120 second rebuild window, the dashboard would show empty data without this flag. A customer looking at their dashboard during a weekly re-crawl would see their scores and recommendations vanish then gradually repopulate. The overlay prevents this.

---

## 6f. Cluster Storage (Idempotent)

### Clear Old Data First

Before storing new clusters, all existing cluster data for the site is wiped — making re-clustering fully idempotent:

```python
async def _clear_old_clusters(self, db, site_id):
    old_cluster_ids = [r["id"] for r in await db.fetch(
        "SELECT id FROM clusters WHERE site_id = $1", site_id
    )]
    if old_cluster_ids:
        await db.execute("DELETE FROM cannibalization_pairs WHERE cluster_id = ANY($1::uuid[])", ids)
        await db.execute("DELETE FROM post_health_scores WHERE post_id IN (SELECT ...)")
        await db.execute("DELETE FROM post_clusters WHERE cluster_id = ANY($1::uuid[])", ids)
        await db.execute("DELETE FROM clusters WHERE site_id = $1", site_id)
```

**Cascade order:**
1. `cannibalization_pairs` (FK -> `clusters.id`) — must go first
2. `post_health_scores` (FK -> `posts.id` via `post_clusters`) — must go before post_clusters
3. `post_clusters` (FK -> `clusters.id`) — junction table
4. `clusters` — parent table

This means **every re-cluster wipes health scores and cannibalization data too**, which forces downstream steps to re-run. In the full pipeline this is fine (they run sequentially), but a standalone re-cluster via the intelligence router endpoint also wipes these.

### Store Clusters

For each cluster group:

```sql
INSERT INTO clusters (site_id, label, description, post_count, silhouette_score)
VALUES ($1, $2, $3, $4, $5)
RETURNING id
```

Then assign posts:

```sql
INSERT INTO post_clusters (post_id, cluster_id)
VALUES ($1, $2)
ON CONFLICT (post_id, cluster_id) DO NOTHING
```

### `clusters` Table Schema (After All Migrations)

| Column | Type | Source | Migration |
|--------|------|--------|-----------|
| `id` | UUID | `gen_random_uuid()` | 001 |
| `site_id` | UUID | FK -> `sites(id)` CASCADE | 001 |
| `label` | TEXT | TF-IDF or Claude-generated | 001 |
| `description` | TEXT | Claude-generated (or empty in fast mode) | 005 |
| `ecosystem_state` | TEXT | `forest`/`swamp`/`desert`/`seedbed`/`meadow` — set later by health scoring | 001 |
| `health_score` | FLOAT | Set later by health scoring | 001 |
| `post_count` | INTEGER | Count of assigned posts | 001 |
| `parent_cluster_id` | UUID | FK -> `clusters(id)` CASCADE — for sub-clusters | 012 |
| `quality_score` | FLOAT | General quality metric | 012 |
| `silhouette_score` | FLOAT | Per-cluster silhouette from HDBSCAN | 028 |
| `created_at` | TIMESTAMPTZ | | 001 |
| `updated_at` | TIMESTAMPTZ | | 001 |

**CHECK constraint on `ecosystem_state`:** Only allows `'forest'`, `'swamp'`, `'desert'`, `'seedbed'`, `'meadow'`.

### `post_clusters` Table Schema

| Column | Type | Notes | Migration |
|--------|------|-------|-----------|
| `post_id` | UUID | FK -> `posts(id)` CASCADE | 001 |
| `cluster_id` | UUID | FK -> `clusters(id)` CASCADE | 001 |
| **PRIMARY KEY** | | `(post_id, cluster_id)` | 001 |

This is a many-to-many table. A post CAN belong to multiple clusters (parent + child after sub-clustering). In practice, **each post currently belongs to exactly one cluster** — the sub-clustering code assigns posts to child clusters and removes them from the parent. The many-to-many schema exists for future flexibility (e.g., soft multi-membership). The unique index was recreated in migration 012 to support this:

```sql
ALTER TABLE post_clusters DROP CONSTRAINT IF EXISTS post_clusters_post_id_cluster_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS post_clusters_post_cluster_unique ON post_clusters(post_id, cluster_id);
```

### Database Indexes for This Step

```sql
CREATE INDEX idx_post_clusters_cluster ON post_clusters(cluster_id);  -- migration 001
```

---

## 6g. Recursive Sub-Clustering (`_recursive_subcluster`)

### What It Does

After initial clustering, any cluster with **more than 25 posts** is recursively sub-clustered into smaller topic groups. This prevents mega-clusters that hide meaningful sub-topic structure.

Example: A 60-post "SEO" cluster might be sub-clustered into "Technical SEO" (18 posts), "Link Building" (22 posts), and "Local SEO" (20 posts).

### Algorithm

```
For each cluster with > MAX_CLUSTER_SIZE (25) posts:
  1. Run UMAP (1536 -> min(10, n-2) dims) with tighter params
  2. Run HDBSCAN with min_cluster_size = max(3, n//10)
  3. If only 0-1 sub-clusters found -> stop (can't split further)
  4. For each sub-cluster:
     a. Create new cluster row with parent_cluster_id = current cluster
     b. Store child_id in dict (sub_label -> cluster_id) for noise assignment
     c. Assign posts to sub-cluster via post_clusters
     d. If sub-cluster still > 25 posts -> recurse (up to max_depth=3)
  5. Assign noise posts to nearest child centroid (using stored dict)
  6. Remove all posts from parent cluster (they now belong to leaves only)
  7. Set parent post_count = 0 so queries don't double-count
```

### Sub-Clustering Parameters

Sub-clustering uses tighter UMAP parameters than the top-level clustering because it's operating within a niche (posts already known to be similar):

```python
reducer = umap.UMAP(
    n_components=min(10, max(2, n - 2)),  # Fewer dims (max 10 vs 15)
    n_neighbors=min(10, max(1, n - 1)),   # Smaller neighborhood
    min_dist=0.05,                         # Tight — separate similar content
    metric="cosine",
    random_state=42 + depth,               # Different seed per depth for variety
)
```

| Parameter | Sub-clustering Value | Top-level Value | Why Different |
|-----------|---------------------|-----------------|---------------|
| `n_components` | max 10 | 15 | Fewer posts need fewer dimensions |
| `n_neighbors` | max 10 | 15 | Smaller neighborhood for finer resolution |
| `min_dist` | 0.05 | 0.05-0.25 (adaptive) | Always tight — find subtle differences |
| `random_state` | `42 + depth` | 42 | Vary seed per depth to avoid degenerate symmetries |

### Child Cluster ID Tracking

During sub-cluster creation, child IDs are stored in a dict keyed by HDBSCAN label. This is used later for noise assignment:

```python
child_ids_by_label: dict[int, UUID] = {}
for sub_label in unique_labels:
    child_id = await db.fetchval("INSERT INTO clusters ... RETURNING id", ...)
    child_ids_by_label[sub_label] = child_id
```

This replaces a previous approach that looked up child IDs via `ORDER BY cluster_id DESC LIMIT 1` on `post_clusters`, which was fragile if a post was in a prior cluster from a previous run.

### Post Reassignment After Sub-Clustering

After sub-clusters are created:
1. **Noise posts** (HDBSCAN label `-1`) are assigned to the nearest child cluster by Euclidean distance from their embedding to child centroids, using the `child_ids_by_label` dict
2. **ALL posts are removed from the parent cluster:** `DELETE FROM post_clusters WHERE cluster_id = $parent_id`
3. **Parent post_count is set to 0:** So that queries filtering on `post_count > 0` skip parent clusters

This means the parent cluster becomes a **container-only node** — it has no directly assigned posts, only child clusters. The frontend and API queries filter parent clusters out:

```sql
-- List clusters (intelligence router)
SELECT * FROM clusters
WHERE site_id = $1
AND id NOT IN (
    SELECT parent_cluster_id FROM clusters
    WHERE parent_cluster_id IS NOT NULL AND site_id = $1
)
ORDER BY post_count DESC
```

### Depth Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| `max_depth` | 3 | Maximum recursion depth |
| `max_cluster_size` | 25 | Trigger threshold for sub-clustering |

At max depth 3, the deepest possible cluster hierarchy is:
```
Site
  +-- Top-level cluster (> 25 posts, post_count=0 after split)
       +-- Sub-cluster depth 1 (> 25 posts, post_count=0 after split)
            +-- Sub-cluster depth 2 (> 25 posts, post_count=0 after split)
                 +-- Sub-cluster depth 3 (leaf -- any size, no further splitting)
```

In practice, most sites only need 1 level of sub-clustering. Depth 2+ only activates on very large, single-niche sites (e.g., 500+ posts all about "digital marketing").

---

## 6h. TF-IDF Cluster Labeling (`services/fast_cluster_labels.py`)

### What It Does

Generates human-readable topic labels for each cluster using TF-IDF on bigram phrases extracted from post titles. **Zero API calls** — pure Python text analysis.

Examples of labels produced:
- "Link Building" (not "Seo For & Step")
- "Email Marketing" (not "Email & Guide")
- "Ecommerce SEO" (not "Store & Optimization")

### Why TF-IDF Over Simple Word Frequency

Simple word frequency produces garbage labels because the most common words are site-wide vocabulary, not topic-specific. On an SEO blog:
- Most frequent word in every cluster: "SEO" — useless as a differentiating label
- Second most frequent: "content", "marketing" — also useless

TF-IDF (Term Frequency x Inverse Document Frequency) down-weights words that appear across many clusters and up-weights words unique to each cluster.

### Algorithm

**Step 1: Site-wide stop word detection (`_compute_site_stops`)**

Words appearing in >= 30% of all post titles are classified as site-level vocabulary and excluded from labels:

```python
def _compute_site_stops(all_titles, top_n=12) -> frozenset:
    doc_freq = Counter()
    for t in all_titles:
        words = set(_WORD_RE.findall(stripped)) - _STOP_WORDS - _FORMAT_WORDS
        doc_freq.update(words)
    threshold = len(all_titles) * 0.3
    return frozenset(w for w, count in doc_freq.items() if count >= threshold)
```

For Backlinko (SEO blog), this catches: `"seo"`, `"search"`, `"content"`, `"marketing"`, `"google"`.

**Step 2: Format marker stripping (`_strip_format`)**

Before extracting topic words, article format markers are stripped from titles:

```python
_FORMAT_MARKERS = [
    "the definitive guide", "a complete guide", "the ultimate guide",
    "step by step guide", "everything you need to know", ...
]
```

Also strips leading patterns: `"How to"`, `"What Is"`, `"N Best/Top..."` and trailing year/site names.

Example: `"The Definitive Guide to Link Building in 2024 - Backlinko"` -> `"link building"`

**Phrase extraction (`_extract_phrases`)**

From each cleaned title, extracts:
- **Unigrams:** Individual meaningful words (excluding stop words and format words)
- **Bigrams:** Consecutive pairs of content words

**Step 4: TF-IDF scoring (`_tfidf_label`)**

Separate scoring for bigrams and unigrams:
- **TF** (term frequency): count in cluster titles / total phrases in cluster
- **IDF** (inverse document frequency): `log(total_titles / (1 + document_frequency))`

Bigrams are preferred over unigrams because they produce more readable labels ("Link Building" > "Link" or "Building").

**Step 5: Label construction**

Priority order:
1. Best bigram (must appear >= 2 times in cluster titles) -> e.g., "Link Building"
2. If a qualifying unigram exists that's not already in the bigram -> append: "Link Building & Outreach"
3. If no bigram qualifies -> use top 2 unigrams: "Outreach & Prospecting"
4. Fallback -> most common unigram, or "General Content"

### Batch Query Optimization

All cluster-title mappings are fetched in a single query instead of N+1 per-cluster queries:

```python
cluster_ids = [c["id"] for c in clusters]
titles_by_cluster: dict[UUID, list[str]] = {cid: [] for cid in cluster_ids}
rows = await db.fetch(
    """
    SELECT pc.cluster_id, p.title
    FROM posts p
    JOIN post_clusters pc ON pc.post_id = p.id
    WHERE pc.cluster_id = ANY($1::uuid[])
    """,
    cluster_ids,
)
for row in rows:
    titles_by_cluster[row["cluster_id"]].append(row["title"] or "")
```

### Word Filtering Layers

Three layers of noise removal:

| Layer | Examples | Purpose |
|-------|----------|---------|
| **`_STOP_WORDS`** (100+) | the, a, how, what, get, make, like | Standard English stop words |
| **`_FORMAT_WORDS`** (40+) | guide, definitive, checklist, template, tips, tricks | Article format descriptors |
| **Site stops** (auto-detected) | seo, content, marketing (for an SEO blog) | Site-specific vocabulary that appears in 30%+ of titles |

### Storage

Labels are written directly to existing cluster rows:

```python
await db.execute(
    "UPDATE clusters SET label = $1 WHERE id = $2",
    label, cluster["id"],
)
```

### Accuracy

For a typical content marketing blog (Backlinko, Copyblogger):
- **Good labels (~70%):** "Link Building", "Email Marketing", "YouTube SEO", "Keyword Research"
- **Acceptable labels (~20%):** "Blog Traffic & Growth", "Conversion & Landing"
- **Vague labels (~10%):** "Strategy & Tactics", "General Content"

The 10% vague labels are where the optional Claude backfill adds value.

---

## 6i. Claude Label Backfill (`services/fast_cluster_labels.py:backfill_claude_labels`)

### What It Does

Optional quality upgrade that relabels all clusters using Claude API. Runs after TF-IDF labels as a separate pipeline step — TF-IDF labels serve as fallback if Claude fails for any cluster.

### When It Runs

- **NOT in the default full pipeline** — the full pipeline only runs `skip_labeling=True` + TF-IDF
- **Triggered via intelligence router:** `POST /{site_id}/intelligence/cluster` runs `TopicClusterer` with `skip_labeling=False`, which calls Claude for each cluster
- **Can be run as a standalone backfill** via `backfill_claude_labels(db, site_id)`

### Claude API Call

For each cluster (excluding parent clusters that have children):

```python
prompt = (
    f"These are {len(titles)} blog post titles from {site_domain}, "
    f"all in the same topic cluster.\n\n"
    f"Titles:\n" + "\n".join(f"- {t}" for t in titles[:15])
    + "\n\nWhat topic do these posts share? Respond with ONLY a 2-4 word topic label."
)
response = await client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=20,
    messages=[{"role": "user", "content": prompt}],
)
```

| Parameter | Value |
|-----------|-------|
| **Model** | `claude-sonnet-4-20250514` |
| **Max tokens** | 20 (just a label) |
| **Input** | Up to 15 post titles from the cluster |
| **Output** | 2-4 word topic label |
| **Rate limit** | 10 req/sec (self-imposed) |

### Label + Description (Full Mode)

When `skip_labeling=False`, the `_label_and_describe_cluster` method in `TopicClusterer` makes a richer call:

```python
prompt = (
    f"These {len(titles)} blog posts are grouped in the same topic cluster:\n"
    f"{titles_text}\n\n"
    f"Respond with exactly three lines:\n"
    f"Line 1: A specific 2-5 word topic label\n"
    f"Line 2: A one-sentence description of what this cluster covers\n"
    f"Line 3: 3-5 sub-themes separated by commas"
)
response = await self.anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=200,
    messages=[{"role": "user", "content": prompt}],
)
```

This returns both a label AND a description in one API call.

### Validation

Labels are validated before storage:
- Must be >= 3 characters
- Stripped of quotes
- Truncated to 80 chars
- On any exception -> keeps TF-IDF label (silent fallback)

### Cost

| Site Size | Clusters | API Calls | Estimated Cost |
|-----------|----------|-----------|---------------|
| 50 posts | ~5 | 5 | ~$0.005 |
| 150 posts | ~12 | 12 | ~$0.012 |
| 500 posts | ~25 | 25 | ~$0.025 |
| 1000+ posts | ~40 | 40 | ~$0.040 |

---

## API Endpoints

### Trigger Clustering

```
POST /v1/sites/{site_id}/intelligence/cluster
```

**Auth:** Supabase JWT
**Rate limit:** Default (60/min)
**Pre-flight checks:**
1. `_verify_site()` — user owns the site
2. `_try_acquire_pipeline_lock()` — no pipeline already running (checks `pipeline_jobs.status = 'running'`)

**Response:**
```json
{
  "message": "Clustering started",
  "site_id": "..."
}
```

**Background execution:** Runs `_run_clustering_safe()` which:
1. Sets pipeline status to `"running"`
2. Calls `TopicClusterer().cluster_site(conn, site_id)` (with Claude labeling — `skip_labeling=False`)
3. Sets pipeline status to `"completed"` or `"failed"`
4. Wrapped with `@with_retry(max_retries=2, base_delay=5.0)` — retries on transient failures

### List Clusters

```
GET /v1/sites/{site_id}/intelligence/clusters
```

**Auth:** Supabase JWT
**Response:** `list[ClusterResponse]`

```json
[
  {
    "id": "uuid",
    "site_id": "uuid",
    "label": "Link Building",
    "description": "Posts covering strategies for acquiring backlinks...",
    "ecosystem_state": "forest",
    "health_score": 0.72,
    "post_count": 18,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

**Key SQL:** Filters out parent clusters (only returns leaf clusters):

```sql
SELECT * FROM clusters
WHERE site_id = $1
AND id NOT IN (
    SELECT parent_cluster_id FROM clusters
    WHERE parent_cluster_id IS NOT NULL AND site_id = $1
)
ORDER BY post_count DESC
```

### Get Cluster Detail

```
GET /v1/sites/{site_id}/intelligence/clusters/{cluster_id}
```

**Auth:** Supabase JWT
**Response:** `ClusterDetailResponse` (extends `ClusterResponse` with posts)

```json
{
  "id": "uuid",
  "label": "Link Building",
  "description": "...",
  "ecosystem_state": "forest",
  "health_score": 0.72,
  "post_count": 18,
  "posts": [
    {
      "post_id": "uuid",
      "title": "The Complete Guide to Link Building",
      "url": "https://example.com/link-building",
      "composite_score": 0.85,
      "role": "pillar",
      "trend": "growing",
      "traffic_contribution": 0.12,
      "ranking_strength": 0.78,
      "internal_link_score": 0.65
    }
  ]
}
```

### Pydantic Schemas

```python
class ClusterSummary(BaseModel):
    """Lightweight cluster info for dashboard listings."""
    id: UUID
    label: str | None
    ecosystem_state: str | None
    post_count: int

class ClusterResponse(BaseModel):
    """Cluster with ecosystem state and health score."""
    id: UUID
    site_id: UUID
    label: str | None
    description: str | None = None
    ecosystem_state: str | None
    health_score: float | None
    post_count: int
    created_at: datetime
    updated_at: datetime

class ClusterDetailResponse(ClusterResponse):
    """Cluster with full post list and health details."""
    posts: list[PostHealthResponse] = []

class ClusterPosition(BaseModel):
    """Cluster position and metadata for landscape rendering."""
    id: str
    label: str
    x: float
    y: float
    post_count: int
    ecosystem_state: str
```

---

## Summary: Data Available After Step 6

After Step 6 completes, the database contains (in addition to Steps 1-5 data):

| Table/Column | Records | Populated By |
|-------------|---------|-------------|
| `clusters` | 1 per topic group (~5-40 depending on site size) | 3a-3f: HDBSCAN clustering |
| `clusters.label` | TF-IDF bigram labels | 3h: Fast labeling (or 3i: Claude backfill) |
| `clusters.description` | Cluster summary text | 3i: Claude (empty if fast mode) |
| `clusters.silhouette_score` | Per-cluster quality (0-1) | 3b: Silhouette analysis |
| `clusters.parent_cluster_id` | Hierarchy for sub-clustered mega-clusters | 3g: Recursive sub-clustering |
| `post_clusters` | 1 per post (many-to-many, posts in sub-clusters have 2 rows) | 3f: Cluster storage |
| `posts.x_pos` | UMAP 2D x-coordinate per post (nudged) | 3d: 2D map positioning |
| `posts.y_pos` | UMAP 2D y-coordinate per post (nudged) | 3d: 2D map positioning |

**Not yet populated (set later by downstream steps):**
- `clusters.ecosystem_state` — requires Step 7 (Health Scoring)
- `clusters.health_score` — requires Step 7 (Health Scoring)
- `post_health_scores.composite_score` / `role` / `trend` — requires Step 4
- `cannibalization_pairs` — requires Step 5
- `content_problems` — requires Step 6
- `recommendations` — requires Step 7

---

## Cost per Site

| Sub-step | External API | Estimated Cost |
|----------|-------------|---------------|
| UMAP + HDBSCAN clustering | None | Free (CPU only) |
| 2D map positions + nudge | None | Free (CPU only) |
| TF-IDF labeling | None | Free |
| Claude label backfill (optional) | Anthropic | ~$0.02 per site |
| **Total (default pipeline)** | | **Free** |
| **Total (with Claude labels)** | | **~$0.02 per site** |

---

## Performance

| Sub-step | Estimated Time (150-post site) | Estimated Time (1000-post site) | Notes |
|----------|-------------------------------|--------------------------------|-------|
| Fetch embeddings | <0.5s | ~2s | Single DB query |
| UMAP 15D reduction | 2-5s | 15-30s | CPU-bound, in thread |
| HDBSCAN clustering | <1s | 2-5s | Fast on 15D data |
| Silhouette scoring | <0.5s | 1-3s | sklearn on reduced data |
| UMAP 2D reduction | 2-5s | 15-30s | Second UMAP run |
| Cluster-aware nudge | <0.1s | <0.1s | Vectorized numpy |
| Noise assignment | <0.1s | <0.5s | Euclidean distance |
| DB writes (clusters + positions) | <1s | 1-2s | Batch unnest UPDATE |
| Recursive sub-clustering | 0s (no mega-clusters) | 5-15s | Only if clusters > 25 posts |
| TF-IDF labeling | <0.5s | ~1s | Pure Python, batch query |
| Claude label backfill (optional) | ~10-15s | ~20-30s | Parallelized API calls |
| **Total (default pipeline)** | **~5-12s** | **~40-90s** | |
| **Total (with Claude labels)** | **~15-25s** | **~60-120s** | |

---

## Unit Tests (`tests/test_clustering.py`)

### Existing Test Coverage

5 tests covering HDBSCAN behavior directly (not the full `TopicClusterer` class):

| Test | Description | Assertion |
|------|-------------|-----------|
| `test_two_clear_clusters` | Two well-separated 20-point groups (std=0.3, centers at [0,0] and [5,5]) | >= 2 clusters found |
| `test_single_cluster` | One tight 30-point group (std=0.1) | <= 2 clusters |
| `test_all_noise` | 10 points uniformly spread over [-100, 100] | >= 5 noise points |
| `test_three_clusters` | Three 15-point groups separated by 5 units | >= 3 clusters |
| `test_cluster_labels_are_integers` | Verify HDBSCAN output types | All labels are `int` |

### Test Gaps

| Missing Test | Why It Matters |
|-------------|----------------|
| `TopicClusterer.cluster_site()` integration test | Full pipeline from DB embeddings -> clusters + positions stored |
| Adaptive similarity calibration | Verify tight-niche sites get different UMAP params |
| Silhouette retry logic | Verify retry bumps min_cluster_size and retries |
| Recursive sub-clustering | Verify mega-clusters get split, parent empties |
| TF-IDF labeling (`label_clusters_fast`) | Verify site stops detected, bigram labels produced, batch query works |
| Claude label backfill | Verify labels updated, fallback on failure |
| Idempotent re-clustering | Verify old clusters + cannibalization + health scores cleared |
| Edge case: exactly 15 posts | Boundary between simple layout and full UMAP |
| Edge case: all posts identical embedding | Should produce 1 cluster |
| Cluster-aware 2D nudge | Verify posts move toward cluster centroid, no crash on single cluster |
| Rebuilding status flag | Verify `crawl_jobs.current_step` set to `'rebuilding'` before clear |
| Progress callback | Verify `on_progress` called at each checkpoint |

---

## Known Limitations (Documented, Not Fixing)

| # | Limitation | Impact | Mitigation |
|---|-----------|--------|------------|
| KL1 | UMAP is non-deterministic across library versions even with `random_state=42` | Cluster assignments may change when `umap-learn` is upgraded. Same data may produce different clusters on different machines. | Pin `umap-learn` version in requirements.txt. Clusters are re-generated on every pipeline run anyway. |
| KL2 | HDBSCAN can produce poor results on highly uniform content (all posts nearly identical) | A site with 100 posts all about "link building" may produce 1 cluster or all noise. | The adaptive similarity detection helps but can't fix fundamentally uniform content. Single-cluster result is displayed correctly. |
| KL3 | TF-IDF labels limited to English | Non-English site titles produce garbled labels (stop words are English-only). | Claude backfill would handle non-English correctly. TF-IDF is documented as English-focused. |
| KL4 | 2D positions change on every re-cluster | Users can't rely on "this post was at position X" between re-runs. | The landscape is regenerated on each re-run. No persistent position guarantees are needed for the product. |


THOUGHTS:

**Rating: 83/100**

The clustering architecture is well-designed — adaptive similarity calibration, silhouette quality gate with retry, recursive sub-clustering, cluster-aware 2D nudge, and the idempotent clear-then-rebuild pattern. The E2E validates the structural pipeline on synthetic embeddings. But there are real issues in the output and a significant frontend disconnect.

---

## WHAT'S STRONG

**Adaptive similarity calibration is the right approach.** Mean pairwise cosine of 0.052 correctly triggers "diverse content" mode (min_dist=0.05). On a tight-niche SEO blog with mean_sim > 0.70, it would increase min_dist to 0.25 to spread similar posts apart. This single calibration step is what makes clustering work across different site archetypes.

**Silhouette score of 0.473 is genuinely good** for synthetic embeddings. The per-cluster scores range from 0.319 (Cluster 3) to 0.606 (Cluster 2), all above the 0.1 retry threshold. Zero retries needed.

**Territory overlap elimination works.** 3 overlapping convex hull pairs before nudge → 0 after the 15% centroid nudge. This is exactly what the nudge is designed to do.

**Sub-clustering correctly triggers on mega-clusters.** Cluster 1 (53 posts) and Cluster 3 (44 posts) both exceed the 25-post threshold and get sub-clustered. Cluster 1 splits into 12 + 41 posts; Cluster 3 splits into 34 + 10 posts.

**TF-IDF labeling runs in 32ms** with zero API calls. Labels are readable: "Content Promotion & Blogging," "Social Media & Marketing," "Sales Letter & SEO," "Business & People."

---

## ISSUES

**S6-31: The frontend ignores UMAP 2D positions — the entire 2D positioning pipeline is dead code**

Priority: Clarify architecture decision
Found in: E2E test (Observations)

The E2E explicitly states: "Frontend ignores UMAP 2D coordinates — EcosystemCanvas.tsx uses D3 force layout with random initial positions, not posts.x_pos/y_pos. The UMAP 2D positions are stored in the DB but unused by the current renderer."

This means the second UMAP run (1536→2D), the cluster-aware nudge (15% toward centroid), the batch `unnest()` UPDATE writing x_pos/y_pos to every post, and the territory overlap analysis are all computing and storing data that nothing consumes. That's ~2-5 seconds of CPU per pipeline run and DB writes for 145 posts, all wasted.

This isn't a bug — it's an architecture decision that needs resolving. Either:
- (A) Update the frontend to use UMAP positions instead of D3 force layout. The UMAP positions are topologically meaningful (similar posts are nearby); D3 force with random init is not.
- (B) Remove the 2D UMAP pipeline and save the CPU time + DB writes. If D3 force layout works well enough for the product, the UMAP positions are unnecessary overhead.
- (C) Keep both and document why (e.g., UMAP positions are for a future "static map" feature, D3 force is for the current interactive canvas).

For launch, this doesn't block anything — the wasted compute is small. But it's confusing for anyone reading the spec, which dedicates an entire section to 2D positioning and convex hull overlap reduction for a feature the frontend doesn't use.

**S6-32: Cluster 1 sub-clustering produces 39 noise points out of 53 — 74% noise rate**

Priority: Investigate
Found in: E2E test (Section 6e)

Cluster 1 (53 posts) sub-clusters into 2 children: 12 posts + 41 posts. But HDBSCAN found 2 sub-clusters with only 14 core posts total — the remaining 39 were noise, reassigned to the nearest child centroid. A 74% noise rate in sub-clustering means HDBSCAN couldn't find meaningful density structure within this cluster.

Compare with Cluster 3: 44 posts sub-clustered into 34 + 10 with 0 noise. That's a clean split.

The 74% noise rate suggests Cluster 1's content is relatively homogeneous — HDBSCAN can't find sub-topic boundaries because most posts are equidistant in embedding space. This is expected with synthetic embeddings (random vectors don't have natural sub-topic structure), but it means the sub-clustering for this cluster is essentially "split into a small group and dump everything else in the other group."

Fix: Add a noise-rate quality gate to sub-clustering. If HDBSCAN produces > 60% noise during sub-clustering, reject the split and keep the parent cluster intact. The current behavior (reassigning 39 noise points to 2 child clusters) produces sub-clusters that aren't meaningfully different from the parent — the children are just arbitrary partitions of a homogeneous cluster.

**S6-33: No site-wide stop words detected — "blog" at 8% doesn't reach the 30% threshold**

Priority: Low — Copyblogger-specific, verify on Backlinko
Found in: E2E test (Section 6f)

The stop word threshold is 30% of 145 titles = 43 occurrences. The most common content word "blog" appears in only 11 titles (8%). This means no site-wide vocabulary is filtered, and labels may contain words like "blog" and "content" that appear across multiple clusters without being specific to any one.

On Copyblogger (diverse 2007-era titles), this is expected — the titles are genuinely diverse. On Backlinko (focused SEO blog), "seo" and "link" should appear in 30%+ of titles and get correctly stopped.

No fix needed. The 30% threshold is conservative by design. Verify on Backlinko that site-wide stops activate for "seo" and "link building."

**S6-34: Cluster 3 label "Social Media & Marketing" doesn't match the sample titles**

Priority: Low — label quality issue
Found in: E2E test (Section 6f)

Cluster 3's sample titles are "5 Steps to Pay Per Click Advertising" and "It's the End of AdSense as We Know It." These are about paid advertising and AdSense, not social media. The label "Social Media & Marketing" may be derived from other posts in the cluster that weren't shown in the sample, but the mismatch between the label and the visible sample titles would confuse a customer looking at their dashboard.

This is a TF-IDF limitation — the label reflects the highest-scoring bigrams across all 44 posts, which may be dominated by a subset of social media posts even though the cluster also contains advertising content. With real embeddings, this cluster would likely split differently (advertising vs social media might be separate clusters).

No fix needed for synthetic embeddings. Verify on Backlinko that TF-IDF labels match the visible content in each cluster.

**S6-35: The sub-clustering splits are uneven — 12/41 for Cluster 1, 34/10 for Cluster 3**

Priority: Low — expected behavior
Found in: E2E test (Section 6e)

Cluster 1 splits 12/41 (77% in one child). Cluster 3 splits 34/10 (77% in one child). In both cases, HDBSCAN found one dominant sub-cluster and one small outlier group. This is typical for density-based clustering — it finds a dense core and a secondary pocket.

With real embeddings, the splits might be more balanced (e.g., "Technical SEO" 18 / "Link Building" 22 / "Local SEO" 15 on Backlinko). The unevenness here is a synthetic embedding artifact.

No fix needed. The sub-clustering correctly identified that the content has a dominant sub-topic and a minority sub-topic. The 12-post and 10-post children are above min_cluster_size (3 for this site size), so they're legitimate clusters.

**S6-36: 4 questionable noise reassignments (> 2 standard deviations from centroid)**

Priority: Low — expected for nearest-centroid assignment
Found in: E2E test (Section 6c-main)

4 of 20 noise points are assigned to clusters where they're statistical outliers: "Conversations with Parrots" → Cluster 1 (distance 1.005, mean 0.607 ± 0.155), "Will You be at BlogWorld" → Cluster 1, "No Really… Thanks Google!" → Cluster 2, "58 of the World's Greatest Offers" → Cluster 0.

These posts are genuinely hard to cluster — creative/personal titles that don't match any topic cluster well. The nearest-centroid assignment is the least-bad option (the alternative is leaving them unclustered, which breaks downstream analysis).

No fix needed. The 4/20 outlier rate (20%) is acceptable. These posts will have low health scores and won't appear in the "most problematic" lists because they're short, old, and already flagged for multiple SEO issues.

**S6-37: The spec says post_clusters is many-to-many but the E2E doesn't show multi-cluster membership**

Priority: Low — documentation verification
Found in: Spec (Section 6f) vs E2E

The spec says "A post CAN belong to multiple clusters (parent + child after sub-clustering)." But after sub-clustering, all posts are removed from the parent cluster (`DELETE FROM post_clusters WHERE cluster_id = $parent_id`) and the parent's post_count is set to 0. So in practice, each post belongs to exactly one leaf cluster.

The many-to-many schema supports the intermediate state during sub-clustering (post in both parent and child before cleanup) but the final state is always one-to-one. The spec should clarify this: "The schema is many-to-many to support the sub-clustering process, but after sub-clustering completes, each post belongs to exactly one leaf cluster."

**S6-38: The E2E doesn't validate the idempotent re-clustering path**

Priority: Low — test gap
Found in: E2E test (missing)

The spec describes `_clear_old_clusters()` which deletes cannibalization_pairs, post_health_scores, post_clusters, and clusters before storing new ones. The E2E runs clustering once but doesn't run it twice to verify that re-clustering produces the same results and correctly clears old data.

Fix: Add a second clustering run to the E2E and verify: same cluster count, same silhouette score (within tolerance for UMAP non-determinism), old cluster IDs no longer in the database. This validates the idempotent path that runs on every weekly re-crawl.

---

## SUMMARY

### Clarify Architecture (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6-31 | Frontend ignores UMAP 2D positions — dead code or planned feature? | Decision (5 min), then either remove 2D pipeline or update frontend |

### Investigate (1 item)

| # | Issue | Effort |
|---|-------|--------|
| S6-32 | 74% noise rate in Cluster 1 sub-clustering — add noise-rate quality gate | 30 min |

### Low Priority (5 items)

| # | Issue | Effort |
|---|-------|--------|
| S6-33 | No site-wide stops on Copyblogger — verify on Backlinko | Verify |
| S6-34 | Cluster 3 label doesn't match sample titles | Verify on Backlinko |
| S6-35 | Uneven sub-clustering splits (12/41, 34/10) | Expected — synthetic |
| S6-37 | Many-to-many schema but one-to-one in practice — clarify spec | 5 min |
| S6-38 | Idempotent re-clustering path untested | 20 min |

### Not Bugs (1 item)

| # | Observation |
|---|-------------|
| S6-36 | 4 questionable noise reassignments — expected for nearest-centroid on creative titles |

### The honest assessment

83/100 reflects a well-architected clustering step with one significant architectural question (dead 2D pipeline), one real quality concern (sub-clustering noise rate), and expected synthetic-embedding limitations. The adaptive similarity calibration, silhouette quality gate, recursive sub-clustering, and territory overlap elimination are all working correctly. The TF-IDF labeling produces readable labels in 32ms with zero API cost.

The 17-point deduction: frontend doesn't use the 2D positioning pipeline (-5), sub-clustering noise rate gate missing (-4), synthetic embeddings limit all cluster quality validation (-4), test gaps on idempotent re-clustering and multi-cluster edge cases (-2), and label quality concerns that may resolve with real embeddings (-2).

Ship it. The clustering mechanics are production-ready. The Backlinko run with real OpenAI embeddings will validate cluster count (expect 8-15 vs the current 4), label quality, site-wide stop word activation, sub-clustering balance, and whether the silhouette scores improve with real semantic structure. The 2D pipeline question is a product decision, not a code bug.