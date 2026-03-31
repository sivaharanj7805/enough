# Tended — Content Ecosystem Intelligence Platform

Solo-founder SaaS. Monorepo: Python/FastAPI backend + Next.js 14 frontend + PostgreSQL/pgvector.

## Gotchas

- **API URL bug:** `NEXT_PUBLIC_API_URL` must be `http://localhost:8000` (no `/v1`). `frontend/src/lib/api.ts` appends `/v1` automatically. The backend `.env.example` has this wrong; the frontend one is correct.
- **Repo is PUBLIC with MIT license.** Treat all secrets accordingly. Never commit `.env` files.
- **20+ unreviewed PRs exist.** Do not create PRs unless explicitly asked. Do not auto-merge. Work on the current branch.
- **Landing page pricing is stale** — shows $99/$249. Correct: $149/mo Growth, $349/mo Scale. Do not change pricing without explicit instruction.
- **ErrorBoundary** exists but is NOT wired into the dashboard layout.

## Protected Files

**DO NOT delete, remove, or "clean up" any file in `frontend/src/components/landscape/` without explicit human approval.** Commit `c0a296b` previously deleted 1,600 lines of working visualization code. The ecosystem visualization is the product's core differentiator. If a landscape file looks unused — ask, don't delete.

## Commands

```bash
make dev              # docker-compose up (full stack)
make dev-backend      # uvicorn --reload :8000
make dev-frontend     # next dev :3000
make test             # pytest + vitest
make lint             # ruff check + eslint
make format           # ruff format + prettier
make build            # production docker images
make migrate          # apply pending migrations
```

## Verify Before Every Commit

```bash
make lint && make test && make build
```

Fix failures before committing. Do not skip.

## Architecture

```
frontend/          → Next.js 14 (App Router, SWR, D3/Canvas, Tailwind, Supabase Auth)
backend/           → FastAPI (asyncpg, OpenAI, Claude, Stripe, Google APIs)
backend/migrations → 27 sequential .sql files, tracked in schema_migrations
```

All API routes under `/v1`. Backend mounts 12 routers in `main.py`. For full details see `ARCHITECTURE.md`. For ecosystem visuals see `ECOSYSTEM-BIBLE.md`.

### Intelligence Pipeline (canonical numbering — see `PIPELINE.md`)

```
Step 1     Crawl + Normalize
Steps 2-5  Enrichment (Embeddings, Readability, PageRank, Intent)
Step 6     Clustering (UMAP + HDBSCAN)
 ├ 6b      TF-IDF Cluster Labels
 └ 6c      AI Citability Scoring
Step 7     Health Scoring
Step 8     Cannibalization Detection
 ├ 8b      Chunk Confirmation (optional)
 └ 8c      Role Patch
Step 9     Problem Detection
Step 10    Recommendations
 └ 10b     Claude Enrichment (optional)
```

Pipeline docs: `PIPELINE-STEP{N}-*.md`. Test results: `STEP{N}-TEST-RESULTS.md`. Test scripts: `backend/scripts/test_step{n}_e2e.py`. All use this numbering. Do not use the old "spec numbering" (Steps 1-7).

## Coding Standards

**Python:** Type hints on public functions. `logger.exception()` for errors, never `traceback.print_exc()`. Never bare `except: pass` — use `logger.warning()` at minimum. Parameterized SQL only. Ruff rules: E,F,W,I,UP,B. Line length 120. New tables need `created_at TIMESTAMPTZ DEFAULT NOW()`. New query paths need a covering index.

**TypeScript:** No `any` — use interfaces from `lib/types.ts`. All user-facing strings in `lib/copy.ts`, never inline. `useEffect` cleanup for subscriptions/timers/D3. `aria-label` on interactive elements. SWR hooks go in `lib/hooks/useApi.ts`. New pages in `app/(dashboard)/`.

**Commits:** Conventional Commits (`feat:`, `fix:`, `test:`, `security:`, `refactor:`).

## Broken Items (March 2026)

1. Landscape renderers deleted in c0a296b — restore from 2a559e1 / 43fe5ea
2. Repo is PUBLIC — must be made private
3. Landing page shows stale pricing
4. 20+ open PRs unreviewed
5. ErrorBoundary not wired into dashboard layout
6. End-to-end flow (signup → Stripe → pipeline → results) untested as integrated system

## On Compaction

Preserve: Gotchas, Protected Files warning, Broken Items, Coding Standards, Verify commands. Drop command output and conversation history first.
