-- 007: Intelligence Layer V2 — 8 new features
-- Internal PageRank, Topical Authority, Intent Classification,
-- Content Gap, Readability, Content Velocity, SERP Opportunities, Weighted Embeddings

-- 1. Internal PageRank score on post_health_scores
ALTER TABLE post_health_scores
    ADD COLUMN IF NOT EXISTS internal_pagerank FLOAT DEFAULT 0.0;

-- 2. Topical Authority on clusters
ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS topical_authority_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS keyword_coverage_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS link_density_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS authority_gaps TEXT[];  -- missing subtopics

-- 3. Search Intent on posts
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS content_intent TEXT;  -- informational, transactional, commercial, navigational
    
-- 4. Content gaps table
CREATE TABLE IF NOT EXISTS content_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    avg_position FLOAT,
    closest_cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    similarity_to_cluster FLOAT,
    gap_type TEXT NOT NULL DEFAULT 'missing',  -- missing, weak, intent_mismatch
    brief TEXT,  -- AI-generated content brief
    status TEXT NOT NULL DEFAULT 'open',  -- open, planned, published, dismissed
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, query)
);
CREATE INDEX IF NOT EXISTS idx_content_gaps_site ON content_gaps(site_id);

-- 5. Readability on posts
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS readability_score FLOAT,      -- Flesch Reading Ease (0-100)
    ADD COLUMN IF NOT EXISTS grade_level FLOAT;             -- Flesch-Kincaid Grade Level

-- 6. Content velocity on sites
ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS publishing_velocity FLOAT DEFAULT 0.0,       -- posts/week (30d rolling)
    ADD COLUMN IF NOT EXISTS velocity_trend TEXT DEFAULT 'stable',         -- growing, stable, declining
    ADD COLUMN IF NOT EXISTS velocity_updated_at TIMESTAMPTZ;

-- 7. SERP feature opportunities
CREATE TABLE IF NOT EXISTS serp_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    current_position FLOAT,
    opportunity_type TEXT NOT NULL,  -- featured_snippet, paa, definition_box
    has_required_format BOOLEAN DEFAULT FALSE,
    recommendation TEXT,
    estimated_impact TEXT DEFAULT 'medium',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(post_id, query, opportunity_type)
);
CREATE INDEX IF NOT EXISTS idx_serp_opps_site ON serp_opportunities(site_id);
CREATE INDEX IF NOT EXISTS idx_serp_opps_post ON serp_opportunities(post_id);

-- 8. Weighted embedding flag
ALTER TABLE post_embeddings
    ADD COLUMN IF NOT EXISTS embedding_strategy TEXT DEFAULT 'body_only';
    -- 'body_only' = current, 'weighted' = title×3 + headings×2 + first_para×1.5 + body

COMMENT ON COLUMN posts.content_intent IS 'Search intent: informational, transactional, commercial, navigational';
COMMENT ON COLUMN posts.readability_score IS 'Flesch Reading Ease score (0-100, higher = easier)';
COMMENT ON COLUMN posts.grade_level IS 'Flesch-Kincaid Grade Level (US school grades)';
COMMENT ON COLUMN clusters.topical_authority_score IS 'Composite authority score for this topic cluster (0-100)';
COMMENT ON COLUMN sites.publishing_velocity IS 'Posts per week, 30-day rolling average';
