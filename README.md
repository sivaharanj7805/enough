# Tended — Content Ecosystem Intelligence Platform

A backend system that ingests content from any CMS (WordPress, sitemap-based), connects analytics (GA4, Google Search Console), generates semantic embeddings, and provides a unified API for content intelligence.

## Phase 1: Foundation

The data layer that everything else builds on:

- **FastAPI backend** with async PostgreSQL (Supabase + pgvector)
- **WordPress connector** — REST API ingestion with category/tag resolution
- **Universal sitemap crawler** — trafilatura-based content extraction
- **GA4 connector** — per-URL pageview/engagement metrics
- **GSC connector** — per-URL search queries, clicks, impressions
- **OpenAI embedding pipeline** — text-embedding-3-small with change detection
- **Content normalization** — unified schema from any source

## Quick Start

```bash
cd backend
cp .env.example .env
# Fill in your credentials

pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/register | Create account |
| POST | /auth/login | Sign in |
| GET | /auth/google | Google OAuth redirect |
| GET | /auth/google/callback | OAuth callback |
| POST | /sites | Add a site |
| GET | /sites | List sites |
| GET | /sites/{id} | Site details |
| DELETE | /sites/{id} | Remove site |
| POST | /sites/{id}/crawl | Trigger content crawl |
| GET | /sites/{id}/crawl/status | Check crawl progress |
| POST | /sites/{id}/sync-analytics | Sync GA4 + GSC data |
| POST | /sites/{id}/generate-embeddings | Generate embeddings |
| GET | /sites/{id}/posts | List posts |
| GET | /sites/{id}/posts/{post_id} | Post with metrics |
| GET | /sites/{id}/analytics/overview | Aggregated analytics |

## Architecture

```
WordPress API / Sitemap XML
        ↓
   Content Ingestion
        ↓
   Normalization Layer → PostgreSQL (posts, internal_links)
        ↓
   Embedding Pipeline → pgvector (post_embeddings)

GA4 API / GSC API
        ↓
   Analytics Sync → PostgreSQL (ga4_metrics, gsc_metrics)
```

## License

Proprietary — All rights reserved.
