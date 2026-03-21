-- Migration 024: Position alerts for continuous monitoring + decay duration tracking
-- Adds position_alerts table and first_detected_at to content_problems

-- Position alerts: track ranking changes, new competitors, new post issues
CREATE TABLE IF NOT EXISTS position_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,  -- position_drop, position_gain, new_competitor, new_post_detected
    keyword TEXT,
    old_position DOUBLE PRECISION,
    new_position DOUBLE PRECISION,
    details JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'new',  -- new, seen, dismissed
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_position_alerts_site_id ON position_alerts(site_id);
CREATE INDEX IF NOT EXISTS idx_position_alerts_detected_at ON position_alerts(site_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_position_alerts_status ON position_alerts(site_id, status);

-- Add first_detected_at to content_problems for decay duration tracking
ALTER TABLE content_problems
    ADD COLUMN IF NOT EXISTS first_detected_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill existing problems with their detected_at as first_detected_at
UPDATE content_problems
SET first_detected_at = detected_at
WHERE first_detected_at IS NULL;
