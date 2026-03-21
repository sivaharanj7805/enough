-- Migration 025: Support anonymous audit sites
--
-- Allows user_id to be NULL on sites table for anonymous/public audit sites.
-- These sites are created by the public PDF audit endpoint for domains
-- not yet in the database. They get a full pipeline run and the PDF
-- is emailed to the requester.
--
-- Safety: All authenticated endpoints verify ownership via
-- WHERE id = $1 AND user_id = $2, which will never match NULL user_id,
-- so anonymous sites are invisible to all authenticated users.

ALTER TABLE sites ALTER COLUMN user_id DROP NOT NULL;

-- Track pending audit pipelines to prevent abuse
-- (max 1 pending pipeline per email)
CREATE TABLE IF NOT EXISTS pending_audit_pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    domain TEXT NOT NULL,
    site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_audit_email ON pending_audit_pipelines(email, status);
CREATE INDEX IF NOT EXISTS idx_pending_audit_domain ON pending_audit_pipelines(domain);
