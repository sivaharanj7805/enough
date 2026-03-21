-- Phase 7: Gamification tables (streaks, content wrapped, ecosystem forecasts)

CREATE TABLE IF NOT EXISTS user_streaks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    last_check_in DATE,
    total_check_ins INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, site_id)
);

CREATE TABLE IF NOT EXISTS content_wrapped (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, period)
);

CREATE TABLE IF NOT EXISTS ecosystem_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    forecast_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS competitor_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    competitor_domain TEXT NOT NULL,
    comparison_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_streaks_user_site ON user_streaks(user_id, site_id);
CREATE INDEX IF NOT EXISTS idx_content_wrapped_site_period ON content_wrapped(site_id, period);
CREATE INDEX IF NOT EXISTS idx_ecosystem_forecasts_site_date ON ecosystem_forecasts(site_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_competitor_comparisons_site ON competitor_comparisons(site_id);
