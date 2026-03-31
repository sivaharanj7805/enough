-- Preserve previous crawl results during new crawl runs.
-- Before this, starting a new crawl erased completed_at and posts_processed,
-- making previous crawl data unrecoverable mid-crawl.

ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS prev_completed_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS prev_posts_processed INTEGER;
