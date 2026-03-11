-- Phase 4: Action Layer tables

-- Cluster narratives (ecosystem voice)
CREATE TABLE cluster_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE UNIQUE,
    narrative_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Content calendar recommendations
CREATE TABLE cluster_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE UNIQUE,
    recommendation_type TEXT NOT NULL CHECK (recommendation_type IN ('pause', 'maintain', 'revive', 'grow')),
    recommendation_text TEXT NOT NULL,
    suggested_keywords TEXT[],
    pause_months INTEGER,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Redirect push log
CREATE TABLE redirect_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    old_url TEXT NOT NULL,
    new_url TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'pushed', 'verified', 'failed')),
    pushed_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, old_url)
);

CREATE INDEX idx_cluster_narratives_cluster ON cluster_narratives(cluster_id);
CREATE INDEX idx_cluster_recommendations_cluster ON cluster_recommendations(cluster_id);
CREATE INDEX idx_redirect_log_site ON redirect_log(site_id);
