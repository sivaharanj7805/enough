-- Tended: Content Ecosystem Intelligence Platform
-- Phase 1 Initial Schema
-- Requires: pgvector extension

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (managed by Supabase Auth, but we need a profiles table)
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'growth', 'scale', 'enterprise')),
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sites
CREATE TABLE sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    cms_type TEXT CHECK (cms_type IN ('wordpress', 'sitemap', 'hubspot', 'webflow', 'ghost', 'other')),
    wordpress_url TEXT,
    wordpress_app_password TEXT,
    sitemap_url TEXT,
    ga4_property_id TEXT,
    gsc_site_url TEXT,
    google_tokens TEXT,
    last_crawl_at TIMESTAMPTZ,
    last_analytics_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Posts (normalized from any CMS)
CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    slug TEXT,
    title TEXT NOT NULL,
    body_text TEXT,
    body_html TEXT,
    publish_date TIMESTAMPTZ,
    modified_date TIMESTAMPTZ,
    content_hash TEXT,
    cms_categories TEXT[],
    cms_tags TEXT[],
    word_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, url)
);

-- Internal links between posts
CREATE TABLE internal_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    target_url TEXT NOT NULL,
    target_post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
    anchor_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Embeddings (pgvector)
CREATE TABLE post_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE UNIQUE,
    embedding vector(1536),
    model TEXT DEFAULT 'text-embedding-3-small',
    content_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- GA4 analytics data (daily granularity)
CREATE TABLE ga4_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    pageviews INTEGER DEFAULT 0,
    sessions INTEGER DEFAULT 0,
    engaged_sessions INTEGER DEFAULT 0,
    avg_engagement_time_seconds FLOAT DEFAULT 0,
    bounce_rate FLOAT DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(post_id, date)
);

-- Google Search Console data (daily granularity)
CREATE TABLE gsc_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    query TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    avg_position FLOAT,
    ctr FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(post_id, date, query)
);

-- Topic clusters (populated by Phase 2, schema needed now)
CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    label TEXT,
    ecosystem_state TEXT CHECK (ecosystem_state IN ('forest', 'swamp', 'desert', 'seedbed', 'meadow')),
    health_score FLOAT,
    post_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Post-to-cluster assignment
CREATE TABLE post_clusters (
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, cluster_id)
);

-- Cannibalization pairs (populated by Phase 2)
CREATE TABLE cannibalization_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    post_a_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    post_b_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    overlap_score FLOAT NOT NULL,
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    overlapping_queries TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Crawl job tracking (DB-backed, survives restarts)
CREATE TABLE crawl_jobs (
    site_id UUID PRIMARY KEY REFERENCES sites(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'crawling', 'completed', 'failed')),
    posts_found INTEGER DEFAULT 0,
    posts_processed INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Health scores per post (populated by Phase 2)
CREATE TABLE post_health_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    traffic_contribution FLOAT,
    ranking_strength FLOAT,
    trend TEXT CHECK (trend IN ('growing', 'stable', 'declining')),
    internal_link_score FLOAT,
    composite_score FLOAT,
    role TEXT CHECK (role IN ('pillar', 'supporter', 'competitor', 'dead_weight')),
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Intelligence pipeline job tracking
CREATE TABLE pipeline_jobs (
    site_id UUID PRIMARY KEY REFERENCES sites(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'running', 'completed', 'failed')),
    current_step TEXT CHECK (current_step IN ('clustering', 'cannibalization', 'health_scoring', NULL)),
    steps_completed TEXT[] DEFAULT '{}',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_posts_site_id ON posts(site_id);
CREATE INDEX idx_posts_url ON posts(url);
CREATE INDEX idx_internal_links_source ON internal_links(source_post_id);
CREATE INDEX idx_internal_links_target ON internal_links(target_post_id);
CREATE INDEX idx_ga4_post_date ON ga4_metrics(post_id, date);
CREATE INDEX idx_gsc_post_date ON gsc_metrics(post_id, date);
CREATE INDEX idx_gsc_query ON gsc_metrics(query);
CREATE INDEX idx_post_embeddings_post ON post_embeddings(post_id);
CREATE INDEX idx_post_clusters_cluster ON post_clusters(cluster_id);
