-- Migration 027: Add missing indexes and constraints
-- Addresses: BE-12 (email_optouts), BE-13 (winback_emails), BE-15 (cannibalization_pairs)

-- BE-12: email_optouts lookup in drip sequence cron
-- Called per-row in process_pending_drips loop; without index = full table scan per check
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_optouts_email
  ON email_optouts(email);

-- BE-13: winback_emails cron queries filter by cancelled_at range + day_X_sent_at IS NULL
-- Runs daily; without index = full table scan on every cron tick
CREATE INDEX IF NOT EXISTS idx_winback_emails_cancelled_at
  ON winback_emails(cancelled_at);

-- BE-15: cannibalization_pairs upsert deduplication
-- ON CONFLICT (post_a_id, post_b_id) requires a unique constraint to work correctly
-- Without this, the upsert silently inserts duplicate pairs
CREATE UNIQUE INDEX IF NOT EXISTS idx_cann_pairs_unique
  ON cannibalization_pairs(post_a_id, post_b_id);
