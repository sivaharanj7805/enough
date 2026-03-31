-- Simple Postgres-backed job queue for crawl/pipeline tasks.
-- Replaces FastAPI BackgroundTasks which die on process restart.
-- Workers claim jobs with SELECT FOR UPDATE SKIP LOCKED.

CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL CHECK (job_type IN ('crawl', 'full_pipeline', 'incremental_pipeline', 'analytics_sync', 'embeddings')),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    payload JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_queue_pending ON job_queue(status, created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_job_queue_site ON job_queue(site_id, status);
