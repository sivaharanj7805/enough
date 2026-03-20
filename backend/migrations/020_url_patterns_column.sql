-- Add url_patterns column to sites table.
-- Used by crawl pipeline to filter which URL paths to include
-- (e.g. ["/blog/", "/resources/"]).

ALTER TABLE sites ADD COLUMN IF NOT EXISTS url_patterns TEXT[] DEFAULT '{}';
