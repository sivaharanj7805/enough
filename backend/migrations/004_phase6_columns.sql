-- Phase 6: Living Ecosystem — add columns for ecosystem visual computations

-- Add status_code tracking to internal_links (for boulder/broken link detection)
ALTER TABLE internal_links ADD COLUMN IF NOT EXISTS status_code INT;

-- Add bounce_rate and avg_session_duration to ga4_metrics (for fox/deer animal detection)
ALTER TABLE ga4_metrics ADD COLUMN IF NOT EXISTS bounce_rate FLOAT;
ALTER TABLE ga4_metrics ADD COLUMN IF NOT EXISTS avg_session_duration FLOAT;
