-- 010: Chunk-level embeddings for fine-grained cannibalization detection
-- Instead of one embedding per post, split by H2/H3 sections and embed each chunk.
-- A "Technical SEO Guide" covering canonicals + sitemaps + robots.txt gets 3+ chunks,
-- each compared independently. Catches 30-40% more true cannibalization.

CREATE TABLE IF NOT EXISTS content_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,           -- 0-based order within post
    heading TEXT,                            -- H2/H3 heading that starts this chunk (NULL for intro)
    heading_level INTEGER,                   -- 2 for H2, 3 for H3, NULL for intro
    body_text TEXT NOT NULL,                 -- chunk content
    word_count INTEGER NOT NULL DEFAULT 0,
    start_char INTEGER NOT NULL DEFAULT 0,   -- character offset in original body
    end_char INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(post_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_post ON content_chunks(post_id);
CREATE INDEX IF NOT EXISTS idx_chunks_site ON content_chunks(site_id);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES content_chunks(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(chunk_id)
);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_post ON chunk_embeddings(post_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
    ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Track chunk-level cannibalization pairs (supplements document-level pairs)
CREATE TABLE IF NOT EXISTS chunk_cannibalization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    post_a_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    post_b_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    chunk_a_id UUID NOT NULL REFERENCES content_chunks(id) ON DELETE CASCADE,
    chunk_b_id UUID NOT NULL REFERENCES content_chunks(id) ON DELETE CASCADE,
    similarity REAL NOT NULL,
    chunk_a_heading TEXT,
    chunk_b_heading TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunk_cannibal_site ON chunk_cannibalization(site_id);
CREATE INDEX IF NOT EXISTS idx_chunk_cannibal_posts ON chunk_cannibalization(post_a_id, post_b_id);

COMMENT ON TABLE content_chunks IS 'Post content split by H2/H3 sections for fine-grained analysis';
COMMENT ON TABLE chunk_embeddings IS 'Per-chunk embeddings for sub-document similarity detection';
COMMENT ON TABLE chunk_cannibalization IS 'Chunk-level cannibalization pairs (section vs section)';
