# Phase 1 — Foundation Build Task

Build the complete foundation for "Tended" — a Content Ecosystem Intelligence Platform. This is the data layer that everything else depends on.

## Tech Stack
- **Backend:** Python + FastAPI
- **Database:** Supabase (PostgreSQL + pgvector) — use `supabase-py` client OR direct `asyncpg`/`psycopg2` with connection string
- **Auth:** Supabase Auth (email/password + Google OAuth for GA4/GSC)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dimensions)
- **Environment:** All secrets via `.env` file

## What to Build

### 1. Project Structure
```
tended/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Settings from .env
│   │   ├── database.py          # Supabase/DB connection
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py       # Pydantic models
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # Auth endpoints
│   │   │   ├── sites.py         # Site management
│   │   │   ├── ingestion.py     # Content ingestion triggers
│   │   │   └── analytics.py     # Analytics data endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── wordpress.py     # WordPress API connector
│   │   │   ├── sitemap.py       # Universal sitemap crawler
│   │   │   ├── ga4.py           # Google Analytics 4 connector
│   │   │   ├── gsc.py           # Google Search Console connector
│   │   │   ├── embeddings.py    # OpenAI embedding pipeline
│   │   │   └── normalizer.py    # Content normalization layer
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── rate_limiter.py  # Rate limiting + backoff
│   ├── migrations/
│   │   └── 001_initial_schema.sql
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── README.md
└── .gitignore
```

### 2. Database Schema (migrations/001_initial_schema.sql)

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (managed by Supabase Auth, but we need a profiles table)
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'growth', 'scale', 'enterprise')),
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sites
CREATE TABLE sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    cms_type TEXT CHECK (cms_type IN ('wordpress', 'sitemap', 'hubspot', 'webflow', 'ghost', 'other')),
    wordpress_url TEXT,           -- For WP: base REST API URL
    wordpress_app_password TEXT,  -- Encrypted
    sitemap_url TEXT,             -- For universal crawler
    ga4_property_id TEXT,
    gsc_site_url TEXT,
    google_refresh_token TEXT,    -- Encrypted, for GA4+GSC OAuth
    last_crawl_at TIMESTAMPTZ,
    last_analytics_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Posts (normalized from any CMS)
CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    slug TEXT,
    title TEXT NOT NULL,
    body_text TEXT,               -- Plain text extracted
    body_html TEXT,               -- Original HTML
    publish_date TIMESTAMPTZ,
    modified_date TIMESTAMPTZ,
    content_hash TEXT,            -- SHA256 of body_text for change detection
    cms_categories TEXT[],
    cms_tags TEXT[],
    word_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, url)
);

-- Internal links between posts
CREATE TABLE internal_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    target_url TEXT NOT NULL,
    target_post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
    anchor_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Embeddings (pgvector)
CREATE TABLE post_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE UNIQUE,
    embedding vector(1536),       -- text-embedding-3-small dimension
    model TEXT DEFAULT 'text-embedding-3-small',
    content_hash TEXT,            -- Hash of content that was embedded
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- GA4 analytics data (daily granularity)
CREATE TABLE ga4_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    pageviews INTEGER DEFAULT 0,
    sessions INTEGER DEFAULT 0,
    engaged_sessions INTEGER DEFAULT 0,
    avg_engagement_time_seconds FLOAT DEFAULT 0,
    bounce_rate FLOAT DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(post_id, date)
);

-- Google Search Console data (daily granularity)
CREATE TABLE gsc_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    query TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    avg_position FLOAT,
    ctr FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(post_id, date, query)
);

-- Topic clusters (populated by Phase 2, but schema needed now)
CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    label TEXT,
    ecosystem_state TEXT CHECK (ecosystem_state IN ('forest', 'swamp', 'desert', 'seedbed', 'meadow')),
    health_score FLOAT,
    post_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Post-to-cluster assignment
CREATE TABLE post_clusters (
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, cluster_id)
);

-- Cannibalization pairs (populated by Phase 2)
CREATE TABLE cannibalization_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    post_a_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    post_b_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    overlap_score FLOAT NOT NULL,
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    overlapping_queries TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Health scores per post (populated by Phase 2)
CREATE TABLE post_health_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    traffic_contribution FLOAT,
    ranking_strength FLOAT,
    trend TEXT CHECK (trend IN ('growing', 'stable', 'declining')),
    internal_link_score FLOAT,
    composite_score FLOAT,
    role TEXT CHECK (role IN ('pillar', 'supporter', 'competitor', 'dead_weight')),
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_posts_site_id ON posts(site_id);
CREATE INDEX idx_posts_url ON posts(url);
CREATE INDEX idx_internal_links_source ON internal_links(source_post_id);
CREATE INDEX idx_internal_links_target ON internal_links(target_post_id);
CREATE INDEX idx_ga4_post_date ON ga4_metrics(post_id, date);
CREATE INDEX idx_gsc_post_date ON gsc_metrics(post_id, date);
CREATE INDEX idx_gsc_query ON gsc_metrics(query);
CREATE INDEX idx_post_embeddings_post ON post_embeddings(post_id);
CREATE INDEX idx_post_clusters_cluster ON post_clusters(cluster_id);
```

### 3. Content Ingestion — WordPress API Connector (`services/wordpress.py`)

- Accept WordPress site URL + application password
- Fetch all published posts via WP REST API (`/wp-json/wp/v2/posts?per_page=100&page=X`)
- Pagination handling (follow `X-WP-TotalPages` header)
- Extract: title, content (HTML), slug, date, modified, categories (resolve IDs to names), tags (resolve IDs to names)
- Extract internal links from HTML body (parse `<a href>` tags, filter to same domain)
- Normalize output to standard schema

### 4. Content Ingestion — Universal Sitemap Crawler (`services/sitemap.py`)

- Accept any sitemap URL (XML sitemap standard)
- Handle sitemap index files (sitemaps of sitemaps)
- Fetch each URL listed in sitemap
- Use Mozilla Readability.js equivalent in Python (use `readability-lxml` or `trafilatura` package)
- Extract: title, main content (text + HTML), internal links from HTML
- Handle rate limiting (configurable delay between requests, default 1 second)
- Respect robots.txt

### 5. Content Normalization (`services/normalizer.py`)

Both WordPress and sitemap paths output the same normalized schema:
```python
class NormalizedPost:
    url: str
    slug: str | None
    title: str
    body_text: str        # Plain text
    body_html: str        # Original HTML
    publish_date: datetime | None
    modified_date: datetime | None
    internal_links: list[InternalLink]  # [{target_url, anchor_text}]
    cms_categories: list[str]
    cms_tags: list[str]
    word_count: int
    content_hash: str     # SHA256 of body_text
```

### 6. Analytics — GA4 Connector (`services/ga4.py`)

- Google OAuth 2.0 flow (authorization code → access token + refresh token)
- Store encrypted refresh token per site
- Use `google-analytics-data` Python client library
- Fetch per-URL metrics for last 90 days (daily granularity):
  - Pageviews, sessions, engaged sessions, avg engagement time, bounce rate
- Dimension: `pagePath` — match to stored post URLs
- Handle API rate limits (exponential backoff)
- Incremental sync: only fetch dates since last sync

### 7. Analytics — Google Search Console Connector (`services/gsc.py`)

- Shares OAuth with GA4 (same Google account)
- Use `google-api-python-client` for Search Console API
- Fetch per-URL search data for last 90 days (daily granularity):
  - Queries, impressions, clicks, CTR, average position
- Dimensions: `page` + `query` + `date`
- Handle API rate limits (exponential backoff)
- Row limit handling (GSC returns max 25,000 rows per request — paginate)
- Incremental sync

### 8. Embedding Pipeline (`services/embeddings.py`)

- Accept batch of posts
- For each post: check if content_hash matches existing embedding
- If content changed or no embedding exists: generate new embedding
- Use OpenAI `text-embedding-3-small` (1536 dimensions)
- Batch API calls (max 2048 tokens per text, truncate if needed)
- Store in `post_embeddings` table via pgvector
- Handle rate limits on OpenAI API

### 9. API Endpoints

**Auth:**
- `POST /auth/register` — create account
- `POST /auth/login` — sign in
- `GET /auth/google/callback` — Google OAuth callback for GA4/GSC

**Sites:**
- `POST /sites` — add a new site (WordPress or sitemap)
- `GET /sites` — list user's sites
- `GET /sites/{id}` — get site details
- `DELETE /sites/{id}` — remove site

**Ingestion:**
- `POST /sites/{id}/crawl` — trigger content crawl (WordPress or sitemap)
- `GET /sites/{id}/crawl/status` — check crawl progress
- `POST /sites/{id}/sync-analytics` — trigger GA4 + GSC sync
- `POST /sites/{id}/generate-embeddings` — trigger embedding generation

**Data:**
- `GET /sites/{id}/posts` — list all posts with health data
- `GET /sites/{id}/posts/{post_id}` — single post with full metrics
- `GET /sites/{id}/analytics/overview` — aggregated analytics

### 10. Configuration

`.env.example`:
```
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
DATABASE_URL=postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres

# Google OAuth (for GA4 + GSC)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# OpenAI
OPENAI_API_KEY=

# App
SECRET_KEY=your-secret-key
CORS_ORIGINS=http://localhost:3000
```

## Requirements

- Clean, well-documented code with docstrings
- Type hints everywhere
- Proper error handling (don't swallow exceptions)
- Logging (use Python `logging` module)
- All async where possible (FastAPI is async-native)
- Tests are NOT required for this phase — focus on working code
- Use `httpx` for async HTTP requests
- Use `beautifulsoup4` for HTML parsing
- Use `trafilatura` for content extraction in sitemap crawler

## Important Notes

- This is the DATA LAYER. No frontend. No visualization. Just APIs and data processing.
- Every service should be independently testable via API endpoints.
- The schema includes Phase 2 tables (clusters, cannibalization_pairs, health_scores) — create them now so the schema is complete, but don't populate them yet.
- Use proper connection pooling for database operations.
- All timestamps in UTC.
