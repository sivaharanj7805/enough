-- Add silhouette_score column to clusters for quality assessment
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS silhouette_score FLOAT;
