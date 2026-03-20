-- Health score history: track site health over time for trend analysis
CREATE TABLE IF NOT EXISTS health_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    score NUMERIC(5,2) NOT NULL,
    factor_scores JSONB,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_history_site ON health_score_history(site_id, analyzed_at DESC);

-- Audit request tracking (for rate limiting public PDF audits)
CREATE TABLE IF NOT EXISTS audit_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    domain TEXT NOT NULL,
    site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_requests_email_date ON audit_requests(email, created_at);

-- Drip email sequence tracking
CREATE TABLE IF NOT EXISTS audit_drip_emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    domain TEXT NOT NULL,
    site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
    email_number INT NOT NULL,  -- 1, 2, or 3
    send_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, sent, failed
    sent_at TIMESTAMPTZ,
    error TEXT,
    score INT,
    rec_count INT,
    blog_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(email, site_id, email_number)
);

CREATE INDEX IF NOT EXISTS idx_drip_pending ON audit_drip_emails(status, send_at) WHERE status = 'pending';

-- Win-back email tracking for cancelled subscriptions
CREATE TABLE IF NOT EXISTS winback_emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    cancelled_at TIMESTAMPTZ NOT NULL,
    day_7_sent_at TIMESTAMPTZ,
    day_30_sent_at TIMESTAMPTZ,
    day_60_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_winback_user ON winback_emails(user_id);

-- Grace period for payment failures (7-day window before lockout)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMPTZ;
