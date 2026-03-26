-- Page type classification for content-type-aware scoring
-- Values: blog (default), product, documentation, landing, glossary, index

ALTER TABLE posts ADD COLUMN IF NOT EXISTS page_type TEXT DEFAULT 'blog';
