-- Phase 1 Enhancements: headings, meta_description, http_status columns
-- Plus crawl_jobs.updated_at column

-- Add new columns to posts table
ALTER TABLE posts ADD COLUMN IF NOT EXISTS headings JSONB;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS meta_description TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS http_status INTEGER;

-- Add updated_at to crawl_jobs for progress tracking
ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Index for finding stale posts (re-crawl system)
CREATE INDEX IF NOT EXISTS idx_posts_content_hash ON posts(site_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_posts_http_status ON posts(http_status) WHERE http_status IS NOT NULL;

-- Index for re-embed detection (stale embeddings)
CREATE INDEX IF NOT EXISTS idx_post_embeddings_content_hash ON post_embeddings(content_hash);
