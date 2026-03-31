-- Add chunk_overlap_confirmed and chunk_similarity columns to cannibalization_pairs.
-- These were previously added at runtime by chunk_cannibalization service,
-- but the intelligence GET endpoint references them unconditionally.
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_overlap_confirmed BOOLEAN;
ALTER TABLE cannibalization_pairs ADD COLUMN IF NOT EXISTS chunk_similarity FLOAT;
