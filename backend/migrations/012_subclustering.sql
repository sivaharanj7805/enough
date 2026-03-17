-- Migration 012: Sub-clustering support
-- Adds parent_cluster_id for hierarchical clusters

ALTER TABLE clusters ADD COLUMN IF NOT EXISTS parent_cluster_id UUID REFERENCES clusters(id) ON DELETE CASCADE;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS quality_score FLOAT;

-- Allow same post in multiple clusters (parent + child)
-- post_clusters may need to allow duplicates
ALTER TABLE post_clusters DROP CONSTRAINT IF EXISTS post_clusters_post_id_cluster_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS post_clusters_post_cluster_unique ON post_clusters(post_id, cluster_id);
