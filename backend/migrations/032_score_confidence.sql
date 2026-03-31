-- Score confidence level: indicates how complete the health score is
-- 'full' = GA4 + GSC connected, all 8 factors active
-- 'partial' = one of GA4/GSC connected
-- 'crawl_only' = no external data, content analysis only

ALTER TABLE post_health_scores ADD COLUMN IF NOT EXISTS score_confidence TEXT DEFAULT 'crawl_only';
