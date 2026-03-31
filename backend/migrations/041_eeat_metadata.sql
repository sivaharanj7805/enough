-- Store E-E-A-T metadata extracted from full page HTML during crawl.
-- body_html only contains article content, but E-E-A-T signals
-- (author, schema, dates, about links) live in the page chrome.

ALTER TABLE posts ADD COLUMN IF NOT EXISTS eeat_metadata JSONB DEFAULT '{}';
