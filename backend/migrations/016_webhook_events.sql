-- Idempotency table for Stripe webhook events.
-- Prevents duplicate processing when Stripe retries a webhook.

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-cleanup: drop events older than 30 days (Stripe retries for max 3 days)
CREATE INDEX IF NOT EXISTS idx_webhook_events_processed_at ON webhook_events (processed_at);
