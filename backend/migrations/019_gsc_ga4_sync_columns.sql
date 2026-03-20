-- Add separate sync-tracking columns for GSC and GA4.
-- Previously the code referenced last_gsc_sync / last_ga4_sync which
-- did not exist, causing runtime errors on sync completion.

ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_gsc_sync TIMESTAMPTZ;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_ga4_sync TIMESTAMPTZ;
