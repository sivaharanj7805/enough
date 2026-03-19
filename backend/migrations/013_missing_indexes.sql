-- Migration 013: Add missing performance indexes
-- These indexes cover the most frequent query patterns that were doing full table scans.

-- Unread alerts per site (dashboard loads)
CREATE INDEX IF NOT EXISTS idx_alerts_site_unread
    ON alerts(site_id, is_read)
    WHERE is_read = false;

-- Recommendations by site + status + priority (action queue)
CREATE INDEX IF NOT EXISTS idx_recommendations_site_status
    ON recommendations(site_id, status, priority DESC);

-- Unresolved content problems per site
CREATE INDEX IF NOT EXISTS idx_content_problems_unresolved
    ON content_problems(site_id, resolved_at)
    WHERE resolved_at IS NULL;

-- Content gaps by site + status
CREATE INDEX IF NOT EXISTS idx_content_gaps_site_status
    ON content_gaps(site_id, status);

-- Cannibalization pairs ordered by severity
CREATE INDEX IF NOT EXISTS idx_cannibalization_similarity
    ON cannibalization_pairs(cosine_similarity DESC);

-- Posts by publish date (freshness queries, reporting)
CREATE INDEX IF NOT EXISTS idx_posts_site_publish
    ON posts(site_id, publish_date DESC);

-- Posts by modified date (freshness detection)
CREATE INDEX IF NOT EXISTS idx_posts_site_modified
    ON posts(site_id, modified_date DESC);

-- Competitor sites by status
CREATE INDEX IF NOT EXISTS idx_competitor_sites_status
    ON competitor_sites(site_id, status);

-- Pipeline lock check (running jobs)
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status
    ON crawl_jobs(status);

-- Email uniqueness on profiles
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email
    ON profiles(email)
    WHERE email IS NOT NULL;

-- Embedding model version index (for model migration queries)
CREATE INDEX IF NOT EXISTS idx_post_embeddings_model
    ON post_embeddings(embedding_model)
    WHERE embedding_model IS NOT NULL;
