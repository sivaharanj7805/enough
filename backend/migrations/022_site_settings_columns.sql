-- Add site settings columns for recrawl schedule and notification preferences
ALTER TABLE sites ADD COLUMN IF NOT EXISTS recrawl_schedule TEXT DEFAULT 'manual'
    CHECK (recrawl_schedule IN ('manual', 'weekly', 'monthly'));

ALTER TABLE sites ADD COLUMN IF NOT EXISTS digest_frequency TEXT DEFAULT 'weekly'
    CHECK (digest_frequency IN ('weekly', 'biweekly', 'monthly', 'off'));
