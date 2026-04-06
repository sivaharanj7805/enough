-- LLM API cost tracking: logs token usage per service call.
-- Enables cost visibility across pipeline steps and user-triggered features.

CREATE TABLE IF NOT EXISTS llm_cost_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_cost_site ON llm_cost_log(site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_cost_service ON llm_cost_log(service, created_at DESC);
