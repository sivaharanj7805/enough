# Step 6 E2E Test Results — Clustering: copyblogger.com

**Date:** 2026-03-28 17:18
**Prerequisite:** 145 posts from Step 1 crawl + synthetic embeddings
**Note:** Embeddings are synthetic (keyword-injected random vectors), not real OpenAI embeddings. Cluster quality will differ with real embeddings.

---

## 6a. UMAP Dimensionality Reduction

| Metric | Value |
|--------|-------|
| Input dimensions | 1536 |
| Output dimensions (clustering) | 15 |
| Posts processed | 145 |
| Site type (auto-detected) | diverse content (mean_sim=0.052) |
| UMAP n_components | 15 |
| UMAP n_neighbors | 15 |
| UMAP min_dist | 0.05 |
| Processing time | 14.99s |

## 6b-main. HDBSCAN Clustering

| Metric | Value |
|--------|-------|
| min_cluster_size | 7 |
| min_samples | 3 |
| **Clusters found** | **4** |
| Noise points (before reassignment) | 20 (13.8%) |
| **Avg silhouette score** | **0.473** |
| Quality retries | 0 |
| Processing time | 0.011s |

### Cluster Size Distribution

| Size Range | Count | % of Clusters |
|-----------|-------|--------------|
| 1-5 | 0 | 0% |
| 6-10 | 0 | 0% |
| 11-15 | 0 | 0% |
| 16-25 | 2 | 50% |
| 26-50 (mega) | 1 | 25% |
| 51+ | 1 | 25% |

### Per-Cluster Quality

| Cluster | Label | Posts | Silhouette |
|---------|-------|-------|-----------|
| 1 | Content Promotion & Blogging | 53 | 0.517 |
| 3 | Social Media & Marketing | 44 | 0.319 |
| 0 | Business & People | 24 | 0.500 |
| 2 | Sales Letter & Seo | 24 | 0.606 |

## 6c-main. Noise Assignment

| Metric | Value |
|--------|-------|
| Original noise points | 20 |
| Reassigned to clusters | 20 |
| Remaining unassigned | 0 |
| Processing time | 0.001s |

### Noise Reassignment Detail

**Questionable assignments (>2 std from centroid):** 4/20

| Post Title | Assigned Cluster | Distance | Cluster Mean Dist | Outlier |
|-----------|-----------------|----------|-------------------|---------|
| For Whom the Blog Tips (It Tips For Thee) | 0 | 1.053 | 0.776 +/- 0.207 |  |
| Discover the Secret Mind Control Method That Hypno | 3 | 1.111 | 0.965 +/- 0.256 |  |
| Why People Want to Know What’s In It For *You* | 0 | 1.075 | 0.776 +/- 0.207 |  |
| The Smart Way to Create a Sense of Urgency | 0 | 0.866 | 0.776 +/- 0.207 |  |
| Great Copy Ranges From the Specific to the Precise | 3 | 1.092 | 0.965 +/- 0.256 |  |
| Captivate Your Audience with a Killer Opening | 0 | 1.097 | 0.776 +/- 0.207 |  |
| Do You Have an Enemy? Here’s Why You Need to Find  | 3 | 0.941 | 0.965 +/- 0.256 |  |
| Check Out This Spam From a PR Flak | 2 | 1.076 | 0.645 +/- 0.248 |  |
| Are the New Rules of Marketing and PR Here to Stay | 3 | 0.888 | 0.965 +/- 0.256 |  |
| Here's Some Cool Copy for July 4th | 2 | 0.802 | 0.645 +/- 0.248 |  |
| Which Words Can You Live Without? | 0 | 0.973 | 0.776 +/- 0.207 |  |
| Two Techniques That Help You Embrace Brevity | 3 | 1.268 | 0.965 +/- 0.256 |  |
| Conversations with Parrots and the Dangers of a Sw | 1 | 1.005 | 0.607 +/- 0.155 | YES |
| What is a Copywriter's Most Valuable Trait? | 3 | 1.069 | 0.965 +/- 0.256 |  |
| Will You be at BlogWorld in Vegas Next Month? | 1 | 0.935 | 0.607 +/- 0.155 | YES |
| Thanks Google! | 3 | 0.815 | 0.965 +/- 0.256 |  |
| No Really… Thanks Google! | 2 | 1.226 | 0.645 +/- 0.248 | YES |
| 58 of the World's Greatest Offers | 0 | 1.313 | 0.776 +/- 0.207 | YES |
| What Does Creativity Mean to You? | 3 | 0.662 | 0.965 +/- 0.256 |  |
| What’s the Ultimate Creativity Killer? | 0 | 0.955 | 0.776 +/- 0.207 |  |

## 6d. 2D Map Positions

| Metric | Value |
|--------|-------|
| X range (post-nudge) | [-25.17, -18.27] |
| Y range (post-nudge) | [-7.99, -3.31] |
| Spread | 6.90 x 4.68 |
| UMAP 2D time | 0.30s |
| Cluster-aware nudge | 15% toward centroid |
| Avg displacement (nudge) | 0.1431 |
| Max displacement (nudge) | 0.4473 |
| Nudge time | 0.0010s |

### Territory Overlap (Convex Hull)

| Metric | Value |
|--------|-------|
| Total cluster pairs | 6 |
| Overlapping before nudge | 3 |
| Overlapping after nudge | 0 |
| Overlap reduction | 3 pair(s) |

## 6e. Sub-Clustering Results

### Parent Cluster 1 (53 posts)

**Sub-clusters found:** 2 (noise: 39)

| Sub-cluster | Posts | Sample Titles |
|------------|-------|--------------|
| 0 | 12 | Blogging Grows Up; Why Content Promotion is a Virtuous Nece |
| 1 | 41 | Copyblogger - Content marketing tools an; Why the AdWords Landing Page Fiasco Won’ |

### Parent Cluster 3 (44 posts)

**Sub-clusters found:** 2 (noise: 0)

| Sub-cluster | Posts | Sample Titles |
|------------|-------|--------------|
| 0 | 34 | 5 Steps to Pay Per Click Advertising Tha; It’s the End of AdSense as We Know It (A |
| 1 | 10 | Titles That Tell a Whole Story; The Force That Drives Social Media Traff |

## 6f. TF-IDF Cluster Labels

**Site-wide stop words detected:** (none)
**Stop word threshold:** 43 occurrences (30% of 145 titles)

### Word Frequency Analysis (Top 20)

| Word | Titles Containing | % | Stopped? |
|------|------------------|---|----------|
| blog | 11/145 | 8% |  |
| content | 10/145 | 7% |  |
| copy | 8/145 | 6% |  |
| marketing | 7/145 | 5% |  |
| writing | 7/145 | 5% |  |
| blogging | 6/145 | 4% |  |
| story | 6/145 | 4% |  |
| headlines | 6/145 | 4% |  |
| copywriting | 6/145 | 4% |  |
| bloggers | 5/145 | 3% |  |
| people | 5/145 | 3% |  |
| business | 5/145 | 3% |  |
| media | 5/145 | 3% |  |
| copyblogger | 4/145 | 3% |  |
| seo | 4/145 | 3% |  |
| words | 4/145 | 3% |  |
| click | 3/145 | 2% |  |
| landing | 3/145 | 2% |  |
| page | 3/145 | 2% |  |
| become | 3/145 | 2% |  |

| Cluster | Label | Posts | Sample Titles |
|---------|-------|-------|--------------|
| 1 | Content Promotion & Blogging | 53 | Copyblogger - Content marketing tools an; Why the AdWords Landing Page Fiasco Won’ |
| 3 | Social Media & Marketing | 44 | 5 Steps to Pay Per Click Advertising Tha; It’s the End of AdSense as We Know It (A |
| 0 | Business & People | 24 | For Whom the Blog Tips (It Tips For Thee; What’s Your Story? |
| 2 | Sales Letter & Seo | 24 | Does the SEO Industry Have a Branding Pr; I am a Shameless Attention Seeker |

## Processing Summary

| Step | Time | External API | Notes |
|------|------|-------------|-------|
| Crawl (Step 1 prerequisite) | 79.2s | None | |
| UMAP 15D reduction | 14.99s | None | CPU-bound |
| HDBSCAN clustering | 0.011s | None | 0 retries |
| Noise assignment | 0.001s | None | 20 -> 0 noise |
| UMAP 2D mapping | 0.30s | None | CPU-bound |
| Cluster-aware nudge | 0.0010s | None | 15% toward centroid |
| TF-IDF labeling | 0.032s | None | |
| Sub-clustering | 0.216s | None | 2 mega-clusters split |
| **Total Step 6** | **15.55s** | **Free** | |

## Observations

- **2 mega-cluster(s) sub-clustered** into 4 child clusters total
- **Good silhouette score (0.473)** -- clusters are well-separated
- **4 questionable noise reassignment(s)** -- assigned posts > 2 std from cluster centroid
- **No site-wide stop words detected** -- closest word 'blog' at 11/145 (8%), needs 43 (30%). Copyblogger titles are too diverse for the 150-post subset. Labels may contain site vocabulary.
- **Cluster count (4) is low** -- expected 8-15 for 145 posts. Backlinko (real embeddings) produced 11 clusters. Synthetic embeddings (mean_sim=0.052) trigger 'diverse content' mode (min_dist=0.05), which compacts clusters. Real Copyblogger content would have higher similarity and more clusters.
- **Territory overlap: 3 -> 0 pairs** (nudge reduced overlap)
- **Frontend ignores UMAP 2D coordinates** -- EcosystemCanvas.tsx uses D3 force layout with random initial positions, not posts.x_pos/y_pos. The UMAP 2D positions are stored in the DB but unused by the current renderer. Coordinate range and normalization are not a concern.
- Synthetic embeddings produce different clustering than real OpenAI embeddings -- use results as structural validation only
