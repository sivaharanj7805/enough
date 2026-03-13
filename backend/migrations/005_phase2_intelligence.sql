-- Phase 2: Intelligence Engine — full schema additions
-- Adds: 2D positions, cluster descriptions, content problems, recommendations

-- ═══════════════════════════════════════════════
-- 2.4: Post 2D positions for visualization map
-- ═══════════════════════════════════════════════
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS x_pos FLOAT,
    ADD COLUMN IF NOT EXISTS y_pos FLOAT;

-- ═══════════════════════════════════════════════
-- 2.3: Cluster descriptions
-- ═══════════════════════════════════════════════
ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS description TEXT;

-- ═══════════════════════════════════════════════
-- 2.5-2.7: Enhanced health scoring
-- ═══════════════════════════════════════════════
-- Add new health factor columns to post_health_scores
ALTER TABLE post_health_scores
    ADD COLUMN IF NOT EXISTS engagement_score FLOAT,
    ADD COLUMN IF NOT EXISTS freshness_score FLOAT,
    ADD COLUMN IF NOT EXISTS content_depth_score FLOAT,
    ADD COLUMN IF NOT EXISTS technical_seo_score FLOAT;

-- Add Dead trend category
ALTER TABLE post_health_scores
    DROP CONSTRAINT IF EXISTS post_health_scores_trend_check;
ALTER TABLE post_health_scores
    ADD CONSTRAINT post_health_scores_trend_check
    CHECK (trend IN ('growing', 'stable', 'declining', 'dead'));

-- ═══════════════════════════════════════════════
-- 2.8: Enhanced cannibalization (cosine similarity)
-- ═══════════════════════════════════════════════
ALTER TABLE cannibalization_pairs
    ADD COLUMN IF NOT EXISTS cosine_similarity FLOAT,
    ADD COLUMN IF NOT EXISTS stronger_post_id UUID REFERENCES posts(id) ON DELETE SET NULL;

-- ═══════════════════════════════════════════════
-- 2.9: Content decay detection
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS content_problems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    problem_type TEXT NOT NULL CHECK (problem_type IN (
        'decay_mild', 'decay_moderate', 'decay_severe',
        'thin_content', 'thin_below_cluster_avg', 'thin_high_bounce',
        'seo_missing_meta', 'seo_title_length', 'seo_no_headings',
        'seo_no_internal_links', 'seo_no_images',
        'orphan',
        'cannibalization'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    details JSONB DEFAULT '{}',
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    UNIQUE(post_id, problem_type)
);

CREATE INDEX IF NOT EXISTS idx_content_problems_post ON content_problems(post_id);
CREATE INDEX IF NOT EXISTS idx_content_problems_site ON content_problems(site_id);
CREATE INDEX IF NOT EXISTS idx_content_problems_type ON content_problems(problem_type);
CREATE INDEX IF NOT EXISTS idx_content_problems_severity ON content_problems(severity);

-- ═══════════════════════════════════════════════
-- 2.13: AI Recommendations
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    problem_id UUID REFERENCES content_problems(id) ON DELETE SET NULL,
    recommendation_type TEXT NOT NULL CHECK (recommendation_type IN (
        'merge', 'refresh', 'optimize', 'delete', 'expand', 'interlink', 'growth'
    )),
    priority TEXT NOT NULL CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    estimated_effort_hours FLOAT,
    estimated_impact TEXT CHECK (estimated_impact IN ('high', 'medium', 'low')),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    specific_actions JSONB NOT NULL DEFAULT '[]',
    ai_generated_content JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'dismissed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_post ON recommendations(post_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_site ON recommendations(site_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_type ON recommendations(recommendation_type);
CREATE INDEX IF NOT EXISTS idx_recommendations_priority ON recommendations(priority);
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations(status);

-- ═══════════════════════════════════════════════
-- Pipeline jobs: add new steps
-- ═══════════════════════════════════════════════
ALTER TABLE pipeline_jobs
    DROP CONSTRAINT IF EXISTS pipeline_jobs_current_step_check;
ALTER TABLE pipeline_jobs
    ADD CONSTRAINT pipeline_jobs_current_step_check
    CHECK (current_step IN (
        'clustering', 'positions_2d', 'cannibalization', 'health_scoring',
        'problem_detection', 'recommendations', NULL
    ));

-- ═══════════════════════════════════════════════
-- pgvector HNSW index for cosine similarity search
-- ═══════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_post_embeddings_hnsw
    ON post_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
