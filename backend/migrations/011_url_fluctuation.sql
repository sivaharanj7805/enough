-- 011: SERP URL fluctuation tracking for active cannibalization detection
-- Tracks which URL GSC reports for each query over time.
-- If the URL changes ≥3 times in 30 days → Google literally can't decide
-- which page to rank → active cannibalization (strongest signal).

CREATE TABLE IF NOT EXISTS gsc_query_urls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    url TEXT NOT NULL,
    position REAL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    recorded_date DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(site_id, query, recorded_date)
);
CREATE INDEX IF NOT EXISTS idx_gsc_query_urls_site_query
    ON gsc_query_urls(site_id, query);
CREATE INDEX IF NOT EXISTS idx_gsc_query_urls_date
    ON gsc_query_urls(site_id, recorded_date);

-- Detected URL fluctuations (active cannibalization)
CREATE TABLE IF NOT EXISTS url_fluctuations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    urls_involved TEXT[] NOT NULL,          -- Array of distinct URLs
    fluctuation_count INTEGER NOT NULL,     -- Number of URL changes in window
    window_days INTEGER NOT NULL DEFAULT 30,
    avg_position REAL,
    total_impressions INTEGER DEFAULT 0,
    severity TEXT NOT NULL DEFAULT 'medium', -- critical/high/medium
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, query)
);
CREATE INDEX IF NOT EXISTS idx_url_fluctuations_site ON url_fluctuations(site_id);

COMMENT ON TABLE gsc_query_urls IS 'Daily snapshot of which URL ranks for each query in GSC';
COMMENT ON TABLE url_fluctuations IS 'Queries where Google alternates between ranking different URLs';
