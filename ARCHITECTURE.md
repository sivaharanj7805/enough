# Enough — Architecture Review

> Content intelligence platform that crawls sites, generates embeddings, clusters topics, detects cannibalization, scores health, and recommends consolidation actions — with an ecosystem visualization frontend.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js 14)                        │
│  App Router · SWR · D3/Canvas · Supabase Auth · Tailwind           │
│  Port 3000                                                          │
├─────────────────────────────────────────────────────────────────────┤
│                        Backend (FastAPI)                             │
│  asyncpg · OpenAI · Anthropic · Google APIs · Stripe                │
│  Port 8000 · /v1 prefix                                            │
├─────────────────────────────────────────────────────────────────────┤
│                    PostgreSQL 16 + pgvector                          │
│  Embeddings (1536-dim) · HNSW Index · 15 migrations                 │
│  Port 5432                                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Backend Architecture

### 1.1 Application Entry (`backend/app/main.py`)

FastAPI app with lifespan context manager that initializes/closes the asyncpg connection pool. Middleware stack (outermost first):

1. **SecurityHeadersMiddleware** — X-Content-Type-Options, X-Frame-Options, etc.
2. **RequestSizeLimitMiddleware** — 10 MB max
3. **HostValidationMiddleware** — validates Host header in production
4. **CORSMiddleware** — configured origins from settings

Rate limiting via `slowapi`: 60/min default, 10/min auth, 10/min oracle, 5/min draft.

### 1.2 Configuration (`backend/app/config.py`)

Pydantic `BaseSettings` loading from environment / `.env`. Key groups:
- **Supabase**: URL, anon key, service key, JWT secret
- **Google**: OAuth client ID/secret, redirect URI
- **AI**: OpenAI API key, Anthropic API key
- **Stripe**: secret key, webhook secret, price IDs (growth/scale)
- **Security**: CORS origins, rate limits per endpoint type, session timeout (24h)
- **Monitoring**: Sentry DSN, cron secret

Production validation enforces required secrets at startup.

### 1.3 Database Layer (`backend/app/database.py`)

- **asyncpg** connection pool (min 2, max 10)
- Supabase client (public key) + admin client (service key)
- `get_db()` dependency injection for route handlers
- PostgreSQL 16 with `pgvector` extension

### 1.4 API Routers (11 routers under `/v1`)

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth` | `/auth` | Login, signup, Google OAuth, magic links, password reset |
| `sites` | `/sites` | CRUD, CMS type config |
| `ingestion` | `/sites/{id}` | Crawl, WordPress import, sitemap import |
| `intelligence` | `/sites/{id}` | Clustering, cannibalization, health scoring, recommendations |
| `analytics` | `/sites/{id}` | GA4/GSC data, calendar, overview stats |
| `actions` | `/sites/{id}` | Recommendation CRUD, tracking, impact measurement |
| `audit_report` | `/sites/{id}` | Full site audit PDF/JSON generation |
| `og_image` | `/sites/{id}` | OG image generation for sharing |
| `retention` | `/sites/{id}/retention` | User engagement & email sequences |
| `google_integration` | `/google` | OAuth callback, token exchange, GA4/GSC account listing |

### 1.5 Service Layer (15 services)

The core intelligence pipeline runs sequentially:

```
Crawl/Import → Normalize → Embed → Cluster → Health Score → Detect Problems → Recommend
```

| Service | File | External API | Purpose |
|---------|------|-------------|---------|
| **Sitemap** | `sitemap.py` | HTTP | Crawls sitemap.xml, fetches HTML, extracts text via trafilatura |
| **WordPress** | `wordpress.py` | WP REST API | Imports posts via WordPress JSON API |
| **Normalizer** | `normalizer.py` | — | Unified post representation, URL normalization, dedup |
| **Embeddings** | `embeddings.py` | OpenAI | text-embedding-3-small (1536-dim), batch processing, content-hash change detection |
| **Weighted Embeddings** | `weighted_embeddings.py` | — | Title 3×, headings 2×, first paragraph 1.5× weighting |
| **Clustering** | `clustering.py` | Anthropic | UMAP (1536→15 dims) + HDBSCAN, adaptive params, recursive sub-clustering for 50+ post clusters |
| **Fast Cluster Labels** | `fast_cluster_labels.py` | — | TF-IDF labeling (zero API calls) |
| **Health Scoring** | `health_scoring.py` | — | 6-factor composite: traffic, ranking, engagement, freshness, depth, technical SEO |
| **Cannibalization** | `cannibalization.py` | — | Cosine similarity + GSC query overlap, auto-calibrated thresholds, HNSW pre-filter |
| **Chunk Cannibalization** | `chunk_cannibalization.py` | OpenAI | Section-level overlap confirmation |
| **Content Chunker** | `content_chunker.py` | OpenAI | H2/H3 semantic chunking with per-chunk embeddings |
| **Problem Detection** | `problem_detection.py` | — | Decay, thin content, SEO issues, orphans, readability, velocity, AI readiness |
| **Recommendations** | `recommendations.py` | Anthropic | AI-powered actionable recommendations per problem |
| **Fast Recommendations** | `fast_recommendations.py` | — | Template-based recommendations (~90% coverage, zero API) |
| **Intent Classifier** | `intent_classifier.py` | Anthropic | Informational/transactional/commercial/navigational classification |
| **Fast Intent** | `fast_intent.py` | — | Keyword+URL pattern matching (~85-90% accuracy) |
| **Claude Intent** | `claude_intent.py` | Anthropic | Batch classification for ambiguous posts (~10%) |
| **Consolidation** | `consolidation.py` | Anthropic | Swamp cluster ranking, merge drafts, redirect maps |
| **Oracle** | `oracle.py` | OpenAI + Anthropic | Pre-publish analysis: embedding similarity + GSC keyword check + Claude verdict |
| **Readability** | `readability.py` | — | Flesch Reading Ease + Kincaid Grade Level |
| **PageRank** | `pagerank.py` | — | Internal link graph authority via NetworkX |
| **AI Citability** | `ai_citability.py` | — | 4-dimension scoring: citability, E-E-A-T, schema, extraction |
| **Ecosystem Voice** | `ecosystem_voice.py` | Anthropic | Nature-metaphor narrative summaries per cluster |
| **Ecosystem Visuals** | `ecosystem_visuals.py` | — | Terrain, weather, creatures, rivers for visualization |
| **Stripe** | `stripe_service.py` | Stripe | Checkout, portal, webhook handling, subscription management |

### 1.6 Tiered AI Strategy

The codebase uses a deliberate "fast-first, AI-fallback" pattern to minimize API costs:

| Task | Tier 1 (Free) | Tier 2 (API) |
|------|---------------|-------------|
| Intent classification | `fast_intent.py` (regex/keywords, ~85%) | `claude_intent.py` (ambiguous ~10%) |
| Cluster labels | `fast_cluster_labels.py` (TF-IDF) | `clustering.py` (Claude) |
| Recommendations | `fast_recommendations.py` (templates, ~90%) | `recommendations.py` (Claude) |
| Embeddings | Content-hash skip (unchanged posts) | `embeddings.py` (OpenAI, batch 100) |

### 1.7 Utilities

| Utility | Purpose |
|---------|---------|
| `rate_limiter.py` | Token-bucket rate limiter for external API calls (configurable RPS) |
| `token_guard.py` | Truncates text to safe API limits with warnings |
| `task_retry.py` | Exponential backoff retry for flaky operations |
| `error_handling.py` | Structured error responses |
| `encryption.py` | Token encryption for stored credentials |
| `url_normalize.py` | Canonical URL normalization |
| `db_helpers.py` | Common query patterns |

---

## 2. Database Schema

### 2.1 Core Tables

```sql
profiles          — User profiles (linked to Supabase auth.users)
sites             — CMS sites (wordpress/sitemap/hubspot/webflow/ghost)
posts             — Normalized content (title, url, body_text, content_hash, x_pos, y_pos)
internal_links    — Post-to-post link graph (source_post_id → target_post_id)
post_embeddings   — pgvector 1536-dim vectors (text-embedding-3-small)
```

### 2.2 Analytics Tables

```sql
ga4_metrics       — Daily: pageviews, sessions, avg_engagement_time, conversions, bounce_rate
gsc_metrics       — Daily: query, impressions, clicks, avg_position, ctr
```

### 2.3 Intelligence Tables

```sql
clusters              — Topic groups with ecosystem_state (forest/swamp/desert/seedbed/meadow)
post_clusters         — Many-to-many post↔cluster
cannibalization_pairs — Overlapping content pairs with cosine_similarity, severity, overlapping_queries
post_health_scores    — 6-factor composite scores with role assignment
content_problems      — Detected issues with type, severity, details JSON
recommendations       — Actionable items with priority, effort, status tracking
```

### 2.4 Operational Tables

```sql
crawl_jobs        — Crawl state tracking (pending/running/completed/failed)
pipeline_jobs     — Intelligence pipeline execution log
```

### 2.5 Key Indexes

- **HNSW index** on `post_embeddings.embedding` for fast cosine similarity search
- Content-hash based change detection skips re-embedding unchanged posts
- Composite indexes on `(site_id, date)` for analytics queries

---

## 3. Frontend Architecture

### 3.1 Tech Stack

- **Next.js 14** (App Router with server/client components)
- **React 18** + **Tailwind CSS** + **Lucide** icons
- **SWR 2.4** for data fetching and caching
- **Supabase JS SDK** for authentication
- **D3.js 7.9** + **Recharts** + HTML Canvas for visualization
- **Sentry** for error monitoring

### 3.2 Layout & Auth

```
Root Layout
├── AuthProvider (Supabase session, Google OAuth, magic links, demo mode)
│   └── SiteProvider (multi-site selection, localStorage persistence)
│       ├── (dashboard) Layout — protected routes
│       │   ├── Sidebar + Header
│       │   └── Page content + Oracle FAB
│       └── Public pages (login, signup, landing, terms, privacy)
```

**Auth strategies**: Supabase session (primary), Google OAuth, magic links, demo mode (env var bypass).

**Middleware** (`middleware.ts`): checks Supabase cookies OR Authorization header, redirects to `/login`.

### 3.3 Data Flow

```
Component → useApi hook → useSWRFetch → apiFetch → Backend /v1/*
                                ↓
                         SWR cache layer
                    (key = [path, token])
```

- `apiFetch()` — base URL from `NEXT_PUBLIC_API_URL`, Bearer token injection
- `useSWRFetch()` — conditional fetching (null path = skip), revalidateOnFocus: false
- All hooks accept nullable `siteId` for conditional fetching

### 3.4 Pages

| Route | Purpose |
|-------|---------|
| `/landscape` | Main ecosystem visualization (D3/Canvas) — **default dashboard** |
| `/clusters/[clusterId]` | Cluster detail with post list |
| `/posts` | Content library with search/filter |
| `/posts/[postId]` | Post detail + problems + recommendations |
| `/actions` | Recommendation feed with filters |
| `/issues` | Content problems grouped by type/severity |
| `/cannibalization` | Cannibalization pair analysis |
| `/consolidation` | Consolidation plans + execution |
| `/oracle` | Pre-publish conflict checker |
| `/overview` | Analytics KPIs and trends |
| `/impact/[trackingId]` | Track consolidation impact over time |
| `/billing` | Stripe subscription management |

### 3.5 Visualization System

The landscape view is the signature feature — a nature-themed ecosystem map:

| Component | Role |
|-----------|------|
| `EcosystemCanvas.tsx` | Main canvas orchestrator |
| `RegionRenderer.tsx` | Cluster territory polygons |
| `VegetationRenderer.tsx` | Health-based trees/flowers |
| `GrassRenderer.ts` | Background terrain texture |
| `RiverRenderer.ts` | Internal link flow visualization |
| `AnimalRenderer.ts` | Post health creatures (deer=healthy, fox=thin, owl=authoritative) |
| `WeatherRenderer.ts` | Cluster state weather (rain=decay, sun=growth) |
| `TerrainFeatureRenderer.ts` | Mountains, valleys, paths |
| `CreatureLegend.tsx` | Interactive legend |
| `OnboardingTour.tsx` | First-time user walkthrough |

### 3.6 State Management

No Redux/Zustand — uses **React Context + SWR**:
- `AuthProvider` — user session, tokens
- `SiteProvider` — selected site, site list

---

## 4. Infrastructure

### 4.1 Docker Compose

```yaml
services:
  postgres:    pgvector/pgvector:pg16, port 5432, persistent volume
  backend:     Python 3.12 slim, port 8000, non-root user, health check
  frontend:    Next.js, port 3000, depends on backend
```

### 4.2 External Services

| Service | Usage |
|---------|-------|
| **Supabase** | Auth (users, sessions), database hosting in production |
| **OpenAI** | text-embedding-3-small embeddings |
| **Anthropic** | Claude Sonnet for labeling, recommendations, oracle verdicts, drafts |
| **Google** | GA4 + GSC data via OAuth |
| **Stripe** | Subscription billing (growth/scale tiers) |
| **Resend** | Transactional email |
| **Sentry** | Error monitoring (frontend + backend) |

### 4.3 Background Tasks

Uses **FastAPI BackgroundTasks** (in-process thread pool) — no Redis/Celery queue. Pipeline jobs and crawl jobs are tracked in database tables for status visibility and restart resilience.

---

## 5. Intelligence Pipeline Deep Dive

### 5.1 Embedding Strategy

- **Model**: text-embedding-3-small (1536 dimensions)
- **Batch size**: 100 texts per API call
- **Change detection**: content_hash comparison skips unchanged posts
- **Weighted text**: title×3, headings×2, first paragraph×1.5, body×1
- **Storage**: pgvector bracket format `[x,y,z,...]` with HNSW index

### 5.2 Clustering Pipeline

```
Embeddings (1536-dim)
    ↓ UMAP (n_components=15, cosine metric)
Reduced (15-dim)
    ↓ HDBSCAN (adaptive min_cluster_size)
Cluster labels
    ↓ UMAP (n_components=2, cosine metric)
2D map positions (x_pos, y_pos on posts)
```

**Adaptive parameters**:
- Mean pairwise cosine similarity determines UMAP min_dist (tight niche → 0.25, diverse → 0.05)
- HDBSCAN min_cluster_size scales with post count (capped at 20 for 1000+ posts)
- Noise posts assigned to nearest centroid
- Mega-clusters (50+ posts) recursively sub-clustered up to depth 3
- Silhouette scores logged for quality assessment

### 5.3 Cannibalization Detection

Two-signal approach:
1. **Embedding cosine similarity** — auto-calibrated per site (85th/92nd/97th percentiles)
2. **GSC query overlap** — 3+ shared queries triggers detection

Performance optimization: clusters with 20+ posts use HNSW index pre-filtering (top-10 nearest neighbors) instead of O(n²) pair scan.

**Severity levels**: low → medium → high → critical (based on calibrated thresholds + query overlap)

**Filters**: skips same-content-hash pairs (redirect issues), cross-language pairs.

### 5.4 Health Scoring

Six-factor composite with ecosystem classification:

| Factor | Weight | Source |
|--------|--------|--------|
| Traffic | Dynamic | GA4 pageviews relative to site average |
| Ranking | Dynamic | GSC avg position (top 3 = excellent) |
| Engagement | Dynamic | GA4 engagement time + bounce rate |
| Freshness | Dynamic | Days since publish/update |
| Content Depth | Dynamic | Word count + heading structure |
| Technical SEO | Dynamic | Meta, images, links, schema |

**Ecosystem states**: forest (healthy), meadow (growing), seedbed (new), desert (declining), swamp (cannibalized/bloated)

**Post roles**: pillar, supporting, dead_weight (based on composite score percentiles)

### 5.5 Problem Detection

| Category | Signals |
|----------|---------|
| Content decay | Click decline >30%, position drop >5, stale >365 days |
| Thin content | <300 words, below cluster avg, high bounce |
| SEO issues | Missing meta, title length, no headings/links/images |
| Orphan content | Zero internal inbound links |
| Readability | Flesch score <40 (too complex) |
| Velocity | Publishing slowdown detection |
| AI readiness | Citability, E-E-A-T, schema, extraction scores |

---

## 6. Security

### 6.1 Authentication

- **Supabase Auth** with JWT validation
- Google OAuth integration
- Magic link (email OTP) support
- Session timeout: 24 hours

### 6.2 API Security

- CORS with configured origins (wildcard warning in production)
- Request size limit: 10 MB
- Host header validation
- Rate limiting per endpoint category
- Cron secret for internal endpoints
- Non-root container user

### 6.3 Data Security

- Token encryption for stored OAuth credentials
- Content-hash based deduplication (no PII in embeddings)
- Supabase Row Level Security (RLS) for multi-tenant isolation

---

## 7. Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **asyncpg over SQLAlchemy** | Raw performance for embedding operations; no ORM overhead |
| **pgvector in-database** | Avoids separate vector DB (Pinecone/Weaviate); single-database simplicity |
| **FastAPI BackgroundTasks over Celery** | Simpler deployment; pipeline jobs tracked in DB for resilience |
| **SWR over React Query** | Lighter weight; stale-while-revalidate fits dashboard refresh patterns |
| **Tiered AI (free → API)** | ~85-90% of work handled without API calls; significant cost savings |
| **Auto-calibrated thresholds** | Adapts to site niche (tight topic sites vs general blogs) |
| **UMAP + HDBSCAN over k-means** | Handles non-spherical clusters; automatic cluster count discovery |
| **Recursive sub-clustering** | Prevents mega-clusters that hide meaningful sub-topics |
| **Canvas over SVG for landscape** | Performance at scale (1000+ posts rendered simultaneously) |
| **Supabase over custom auth** | Reduces auth surface area; built-in RLS for multi-tenancy |

---

## 8. File Structure

```
enough/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + middleware + lifespan
│   │   ├── config.py               # Pydantic settings
│   │   ├── database.py             # asyncpg pool + Supabase clients
│   │   ├── dependencies.py         # DI: auth, DB, rate limits
│   │   ├── middleware/
│   │   │   └── security.py         # Security headers, size limits, host validation
│   │   ├── routers/                # 11 API routers
│   │   │   ├── auth.py
│   │   │   ├── sites.py
│   │   │   ├── ingestion.py
│   │   │   ├── intelligence.py
│   │   │   ├── analytics.py
│   │   │   ├── actions.py
│   │   │   ├── audit_report.py
│   │   │   ├── og_image.py
│   │   │   ├── retention.py
│   │   │   └── google_integration.py
│   │   ├── services/               # 24 business logic services
│   │   │   ├── embeddings.py
│   │   │   ├── clustering.py
│   │   │   ├── cannibalization.py
│   │   │   ├── health_scoring.py
│   │   │   ├── consolidation.py
│   │   │   ├── oracle.py
│   │   │   ├── problem_detection.py
│   │   │   ├── recommendations.py
│   │   │   ├── fast_*.py           # Zero-API-call alternatives
│   │   │   └── ...
│   │   └── utils/                  # 7 utility modules
│   ├── migrations/                 # 15 SQL migration files
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router pages
│   │   │   ├── layout.tsx          # Root: AuthProvider + SiteProvider
│   │   │   ├── (dashboard)/        # Protected route group
│   │   │   │   ├── landscape/      # Main ecosystem visualization
│   │   │   │   ├── clusters/
│   │   │   │   ├── posts/
│   │   │   │   ├── actions/
│   │   │   │   ├── issues/
│   │   │   │   ├── cannibalization/
│   │   │   │   ├── consolidation/
│   │   │   │   ├── oracle/
│   │   │   │   ├── overview/
│   │   │   │   └── billing/
│   │   │   └── (auth)/             # Login, signup, etc.
│   │   ├── components/
│   │   │   ├── ui/                 # Reusable: Button, Card, Modal, etc.
│   │   │   ├── landscape/          # Ecosystem canvas renderers
│   │   │   ├── consolidation/
│   │   │   ├── oracle/
│   │   │   └── impact/
│   │   ├── providers/              # AuthProvider, SiteProvider
│   │   └── lib/
│   │       ├── api.ts              # apiFetch base client
│   │       └── hooks/              # useApi, useSWRFetch, useAuth, useSite
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── ARCHITECTURE.md                 # This file
```
