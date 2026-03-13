-- 008: Stickiness Features — Historical tracking, alerts, impact tracking,
-- content briefs, keyword opportunity scoring

-- 1. Historical snapshots (weekly health score tracking)
CREATE TABLE IF NOT EXISTS health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    composite_score FLOAT,
    trend TEXT,
    role TEXT,
    traffic_30d INTEGER DEFAULT 0,
    avg_position FLOAT,
    problems_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(post_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_site_date ON health_snapshots(site_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_post ON health_snapshots(post_id);

-- Site-level snapshots
CREATE TABLE IF NOT EXISTS site_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    avg_health_score FLOAT,
    total_posts INTEGER DEFAULT 0,
    total_problems INTEGER DEFAULT 0,
    pillar_count INTEGER DEFAULT 0,
    dead_weight_count INTEGER DEFAULT 0,
    publishing_velocity FLOAT DEFAULT 0.0,
    cannibalization_pairs INTEGER DEFAULT 0,
    content_gaps_count INTEGER DEFAULT 0,
    serp_opportunities_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, snapshot_date)
);

-- Cluster-level snapshots
CREATE TABLE IF NOT EXISTS cluster_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    topical_authority_score FLOAT,
    post_count INTEGER DEFAULT 0,
    avg_health_score FLOAT,
    ecosystem_state TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(cluster_id, snapshot_date)
);

-- 2. Smart alerts
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
    alert_type TEXT NOT NULL,
    -- ranking_drop, new_cannibalization, health_decline, velocity_decline,
    -- new_problem, recommendation_impact, pillar_at_risk
    severity TEXT NOT NULL DEFAULT 'info',  -- critical, warning, info
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    is_read BOOLEAN DEFAULT FALSE,
    is_emailed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_site ON alerts(site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts(site_id, is_read) WHERE NOT is_read;

-- 3. Impact tracking
CREATE TABLE IF NOT EXISTS recommendation_impacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    completed_at TIMESTAMPTZ NOT NULL,
    -- Snapshot at time of completion
    health_score_before FLOAT,
    traffic_before INTEGER,
    position_before FLOAT,
    problems_before INTEGER,
    -- Latest measured values (updated weekly)
    health_score_after FLOAT,
    traffic_after INTEGER,
    position_after FLOAT,
    problems_after INTEGER,
    -- Computed impact
    health_change FLOAT,
    traffic_change_pct FLOAT,
    position_change FLOAT,
    last_measured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_impacts_site ON recommendation_impacts(site_id);

-- 4. Content briefs
CREATE TABLE IF NOT EXISTS content_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,  -- content_gap, growth_recommendation, manual
    source_id UUID,  -- content_gap.id or recommendation.id
    target_keyword TEXT NOT NULL,
    secondary_keywords TEXT[] DEFAULT '{}',
    suggested_titles TEXT[] DEFAULT '{}',
    recommended_word_count INTEGER DEFAULT 1500,
    outline JSONB DEFAULT '[]',  -- [{level: "h2", text: "...", bullets: [...]}]
    questions_to_answer TEXT[] DEFAULT '{}',
    internal_link_targets UUID[] DEFAULT '{}',
    competitor_insights TEXT,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, assigned, writing, published
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_briefs_site ON content_briefs(site_id);

-- 5. Keyword opportunities
CREATE TABLE IF NOT EXISTS keyword_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    estimated_volume INTEGER,  -- from GSC impressions as proxy
    current_position FLOAT,
    opportunity_score FLOAT NOT NULL,  -- 0-100, higher = better opportunity
    difficulty_estimate TEXT DEFAULT 'unknown',  -- low, medium, high, very_high
    action TEXT,  -- optimize_existing, create_new, expand_content
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, query)
);
CREATE INDEX IF NOT EXISTS idx_kw_opps_site ON keyword_opportunities(site_id, opportunity_score DESC);

COMMENT ON TABLE health_snapshots IS 'Weekly per-post health score snapshots for trend tracking';
COMMENT ON TABLE site_snapshots IS 'Weekly site-level metric snapshots';
COMMENT ON TABLE alerts IS 'Smart alerts for ranking drops, new problems, etc.';
COMMENT ON TABLE recommendation_impacts IS 'Before/after tracking when recommendations are completed';
COMMENT ON TABLE content_briefs IS 'Full content briefs for new posts (replaces MarketMuse)';
COMMENT ON TABLE keyword_opportunities IS 'Keyword opportunities scored by volume × position proximity';
