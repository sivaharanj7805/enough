-- 009: Competitor Analysis — crawl competitor sites, compare coverage

-- Competitor sites to track
CREATE TABLE IF NOT EXISTS competitor_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    name TEXT,
    sitemap_url TEXT,
    last_crawled_at TIMESTAMPTZ,
    post_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, crawling, crawled, error
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_competitor_sites_site ON competitor_sites(site_id);

-- Competitor posts (crawled content)
CREATE TABLE IF NOT EXISTS competitor_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_site_id UUID NOT NULL REFERENCES competitor_sites(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    meta_description TEXT,
    word_count INTEGER DEFAULT 0,
    headings JSONB DEFAULT '[]',
    publish_date TIMESTAMPTZ,
    body_text TEXT,
    content_hash TEXT,
    crawled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(competitor_site_id, url)
);
CREATE INDEX IF NOT EXISTS idx_competitor_posts_comp ON competitor_posts(competitor_site_id);
CREATE INDEX IF NOT EXISTS idx_competitor_posts_site ON competitor_posts(site_id);

-- Competitor post embeddings
CREATE TABLE IF NOT EXISTS competitor_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_post_id UUID NOT NULL REFERENCES competitor_posts(id) ON DELETE CASCADE,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(competitor_post_id)
);
CREATE INDEX IF NOT EXISTS idx_comp_embeddings_hnsw
    ON competitor_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Competitive analysis results
CREATE TABLE IF NOT EXISTS competitive_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    competitor_site_id UUID NOT NULL REFERENCES competitor_sites(id) ON DELETE CASCADE,
    insight_type TEXT NOT NULL,
    -- topic_gap: competitor covers topic we don't
    -- content_advantage: we have better content on shared topic
    -- content_disadvantage: competitor has better content
    -- new_content: competitor published something new
    -- head_to_head: direct comparison on shared keyword
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    our_post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
    competitor_post_id UUID REFERENCES competitor_posts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    priority TEXT DEFAULT 'medium',  -- critical, high, medium, low
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_comp_insights_site ON competitive_insights(site_id);

COMMENT ON TABLE competitor_sites IS 'Competitor blogs to track and compare against';
COMMENT ON TABLE competitor_posts IS 'Crawled competitor blog posts';
COMMENT ON TABLE competitor_embeddings IS 'Embeddings for semantic comparison with our content';
COMMENT ON TABLE competitive_insights IS 'Analysis results: gaps, advantages, threats';
