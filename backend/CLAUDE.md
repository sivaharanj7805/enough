# Backend — FastAPI + asyncpg + pgvector

## Directory Map

| Directory | What's there |
|-----------|-------------|
| `app/services/` | 40+ modules — intelligence pipeline, AI calls, Stripe, email, PDF |
| `app/routers/` | 14 FastAPI routers (auth, sites, ingestion, intelligence, actions, analytics, retention, gamification…) |
| `app/models/schemas.py` | All Pydantic request/response schemas |
| `app/config.py` | BaseSettings from `.env`. `validate_production()` enforces secrets at startup |
| `app/database.py` | asyncpg pool (min 2, max 10) + Supabase clients |
| `app/middleware/` | Security headers, 10MB request limit, host validation |
| `app/utils/` | DB helpers, encryption, error handling, rate limiter, token guard, URL normalize |
| `migrations/` | 42 sequential .sql files tracked in `schema_migrations` |
| `tests/` | pytest + asyncio. Coverage target: 70% |

## Intelligence Pipeline (see `PIPELINE.md` for full reference)

```
Step 1     Crawl + Normalize
Steps 2-5  Enrichment (Embed → Readability → PageRank → Intent)
Step 6     Clustering (UMAP+HDBSCAN) → 6b TF-IDF Labels → 6c AI Citability
Step 7     Health Scoring
Step 8     Cannibalization → 8b Chunk Confirm → 8c Role Patch
Step 9     Problem Detection
Step 10    Recommendations → 10b Claude Enrichment
```

Embeddings stored in pgvector with HNSW index.

## Key Files

- `app/config.py` — every env var and production validation
- `app/models/schemas.py` — all request/response shapes
- `app/database.py` — connection pool setup
- `app/utils/encryption.py` — Google token encryption

## Secrets

Google tokens in DB are encrypted via `utils/encryption.py`. `config.py` runs `validate_production()` at startup to enforce required secrets. Never commit `.env`.

## Testing

```bash
make test-backend   # pytest -v --cov=app --cov-report=term-missing
```

CI spins up pgvector/pg16 service container via GitHub Actions on push/PR to main.
