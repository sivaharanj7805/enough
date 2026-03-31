-- Prospect discovery and outreach tracking

CREATE TABLE IF NOT EXISTS prospects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain TEXT NOT NULL,
    contact_email TEXT,
    contact_name TEXT,
    source TEXT DEFAULT 'manual',
    niche TEXT,
    status TEXT DEFAULT 'discovered',
    audit_score INTEGER,
    site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    contacted_at TIMESTAMPTZ,
    UNIQUE(domain)
);

CREATE TABLE IF NOT EXISTS discovery_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    niche_keyword TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'pending',
    domains_found INTEGER DEFAULT 0,
    domains_audited INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_prospects_niche ON prospects(niche);
