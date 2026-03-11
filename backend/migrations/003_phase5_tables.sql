-- Phase 5: Retention + Growth Loops
-- Weekly reports, impact tracking, Stripe billing

-- Weekly report history
CREATE TABLE report_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'failed', 'skipped')),
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Report snapshots (for week-over-week comparison)
CREATE TABLE report_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    health_score FLOAT,
    efficiency_ratio FLOAT,
    total_posts INTEGER,
    active_posts INTEGER,
    dead_posts INTEGER,
    cannibalistic_posts INTEGER,
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, snapshot_date)
);

-- Impact tracking
CREATE TABLE impact_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    pillar_url TEXT NOT NULL,
    consolidated_urls TEXT[] NOT NULL,
    baseline_traffic INTEGER DEFAULT 0,
    baseline_avg_position FLOAT,
    baseline_date DATE NOT NULL,
    latest_traffic INTEGER,
    latest_avg_position FLOAT,
    latest_check_date DATE,
    traffic_change_pct FLOAT,
    status TEXT DEFAULT 'tracking' CHECK (status IN ('tracking', 'complete')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Impact snapshots (30/60/90 day checkpoints)
CREATE TABLE impact_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracking_id UUID NOT NULL REFERENCES impact_tracking(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    traffic INTEGER DEFAULT 0,
    avg_position FLOAT,
    redirects_working INTEGER DEFAULT 0,
    milestone TEXT CHECK (milestone IN ('30d', '60d', '90d')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stripe subscription tracking (extends profiles)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'free';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMPTZ;

CREATE INDEX idx_report_history_site ON report_history(site_id);
CREATE INDEX idx_report_snapshots_site_date ON report_snapshots(site_id, snapshot_date);
CREATE INDEX idx_impact_tracking_site ON impact_tracking(site_id);
CREATE INDEX idx_impact_tracking_status ON impact_tracking(status);
CREATE INDEX idx_impact_snapshots_tracking ON impact_snapshots(tracking_id);
