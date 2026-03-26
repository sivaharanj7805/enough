-- Track step-level progress for the pipeline
-- Allows the UI to show "Step 7/12: Health Scoring" instead of just "analyzing"

ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS current_step TEXT;
ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS steps_completed INTEGER DEFAULT 0;
ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS total_steps INTEGER DEFAULT 12;
