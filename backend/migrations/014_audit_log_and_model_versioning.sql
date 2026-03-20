-- Migration 014: Audit log table + embedding model version tracking

-- ── Audit Log ──
-- Tracks security-relevant actions for compliance and debugging.
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID REFERENCES sites(id) ON DELETE SET NULL,
    user_id     TEXT,
    action      TEXT NOT NULL,          -- e.g. 'site.create', 'consolidation.push', 'google.connect'
    resource_type TEXT,                  -- e.g. 'site', 'post', 'cluster'
    resource_id TEXT,                   -- UUID or identifier of the affected resource
    metadata    JSONB DEFAULT '{}',     -- Additional context (IP, request details, etc.)
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_site
    ON audit_log(site_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_user
    ON audit_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON audit_log(action, created_at DESC);

-- ── Embedding Model Version Tracking ──
-- Tracks which model generated each post's embedding.
-- Critical: embeddings from different models are NOT comparable via cosine similarity.
-- When upgrading models, filter queries by embedding_model to avoid cross-model comparisons.
ALTER TABLE post_embeddings
    ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT 'text-embedding-3-small';

-- Index moved here from 013 (column didn't exist yet in that migration)
CREATE INDEX IF NOT EXISTS idx_post_embeddings_model
    ON post_embeddings(embedding_model)
    WHERE embedding_model IS NOT NULL;

-- ── Timestamps on post_clusters ──
ALTER TABLE post_clusters
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE post_clusters
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- ── Timestamps on internal_links ──
ALTER TABLE internal_links
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- ── Per-site cannibalization config ──
-- Stores calibrated thresholds and overrides per site.
ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS cannibalization_config JSONB DEFAULT '{}';
