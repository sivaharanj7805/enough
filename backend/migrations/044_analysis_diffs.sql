-- Analysis diffs: before/after comparison when pipeline re-runs.
CREATE TABLE IF NOT EXISTS analysis_diffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    score_before NUMERIC(5,2),
    score_after NUMERIC(5,2),
    score_delta NUMERIC(5,2),
    factor_changes JSONB DEFAULT '[]',
    improvements JSONB DEFAULT '[]',
    new_issues JSONB DEFAULT '[]',
    degradations JSONB DEFAULT '[]',
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analysis_diffs_site ON analysis_diffs(site_id, analyzed_at DESC);
