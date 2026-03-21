-- Migration 026: Email opt-outs for CAN-SPAM/CASL compliance
--
-- Tracks emails that have unsubscribed from marketing communications.
-- Checked before sending any drip or win-back email.

CREATE TABLE IF NOT EXISTS email_optouts (
    email TEXT PRIMARY KEY,
    reason TEXT DEFAULT 'unsubscribed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_optouts_created ON email_optouts(created_at);
