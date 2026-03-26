-- Add readability_details column for paragraph-level readability data.
-- The readability service writes Flesch scores for the 3 hardest paragraphs
-- to help users identify which sections need simplification.

ALTER TABLE posts ADD COLUMN IF NOT EXISTS readability_details JSONB;
