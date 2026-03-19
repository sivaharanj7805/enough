-- Migration 015: Add terms acceptance tracking for GDPR compliance
-- Also ensures CASCADE deletes work properly for account deletion

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ;
