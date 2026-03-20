-- Add AI citability / readiness columns to post_health_scores
-- Used by ai_citability service, audit_report router, intelligence router, problem_detection

ALTER TABLE post_health_scores
    ADD COLUMN IF NOT EXISTS ai_citability_score FLOAT,
    ADD COLUMN IF NOT EXISTS eeat_score FLOAT,
    ADD COLUMN IF NOT EXISTS schema_score FLOAT,
    ADD COLUMN IF NOT EXISTS extraction_score FLOAT,
    ADD COLUMN IF NOT EXISTS ai_signals JSONB DEFAULT '{}';
