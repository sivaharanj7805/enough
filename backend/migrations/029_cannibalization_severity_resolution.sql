-- Add severity_score and resolution columns to cannibalization_pairs
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS severity_score FLOAT;
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS resolution TEXT;

-- Index for sorting by severity_score
CREATE INDEX IF NOT EXISTS idx_cann_pairs_severity_score
    ON cannibalization_pairs (severity_score DESC NULLS LAST);
