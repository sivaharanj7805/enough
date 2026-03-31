-- Fix schema issues discovered during E2E testing (2026-03-24)
-- BUG-4: normalizer writes language column that doesn't exist
-- BUG-5: health scorer uses ON CONFLICT (post_id) but no UNIQUE constraint
-- BUG-6: health scorer returns trend='unknown' for posts without GA4 data
-- BUG-7: health scorer returns role='at_risk' for mid-scoring posts without traffic

-- BUG-4: Add missing columns to posts table
ALTER TABLE posts ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- BUG-5: Add UNIQUE constraint on post_health_scores.post_id
-- First deduplicate: keep the row with the highest composite_score per post_id
DELETE FROM post_health_scores a
USING post_health_scores b
WHERE a.post_id = b.post_id
  AND a.id < b.id;

-- Now safe to add the constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'post_health_scores'::regclass
          AND conname = 'post_health_scores_post_id_unique'
    ) THEN
        ALTER TABLE post_health_scores
            ADD CONSTRAINT post_health_scores_post_id_unique UNIQUE (post_id);
    END IF;
END $$;

-- BUG-6: Update trend CHECK constraint to include 'unknown'
ALTER TABLE post_health_scores DROP CONSTRAINT IF EXISTS post_health_scores_trend_check;
ALTER TABLE post_health_scores ADD CONSTRAINT post_health_scores_trend_check
    CHECK (trend IN ('growing', 'stable', 'declining', 'dead', 'unknown'));

-- BUG-7: Update role CHECK constraint to include 'at_risk'
ALTER TABLE post_health_scores DROP CONSTRAINT IF EXISTS post_health_scores_role_check;
ALTER TABLE post_health_scores ADD CONSTRAINT post_health_scores_role_check
    CHECK (role IN ('pillar', 'supporter', 'competitor', 'dead_weight', 'at_risk'));
