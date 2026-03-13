-- 006: Add metadata JSONB column to sites for per-site configuration
-- Stores auto-calibrated cosine thresholds, data availability flags, etc.

ALTER TABLE sites ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Add data_sources column to track what data is available per site
-- Values: 'crawl_only', 'crawl_gsc', 'crawl_ga4', 'full'
ALTER TABLE sites ADD COLUMN IF NOT EXISTS data_sources TEXT DEFAULT 'crawl_only';

COMMENT ON COLUMN sites.metadata IS 'Per-site configuration: calibrated cosine thresholds, feature flags, etc.';
COMMENT ON COLUMN sites.data_sources IS 'Available data sources: crawl_only, crawl_gsc, crawl_ga4, full';
