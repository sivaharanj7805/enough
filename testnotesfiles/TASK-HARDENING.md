# Hardening Pass — Take the Codebase to 10/10

This is not a new feature phase. This is a quality pass that addresses every gap identified in the audit. When complete, this codebase should be production-grade.

## 1. Test Suite

### Backend Tests (pytest + pytest-asyncio + httpx)

Create `backend/tests/` directory with:

```
backend/tests/
├── conftest.py           # Shared fixtures (test DB, test client, mock services)
├── test_health.py        # Health endpoint + DB connectivity
├── test_sites.py         # Site CRUD + ownership checks
├── test_ingestion.py     # WordPress + sitemap crawl trigger/status
├── test_analytics.py     # Post listing, analytics overview
├── test_clustering.py    # Clustering service unit tests
├── test_cannibalization.py  # Cannibalization detection unit tests
├── test_health_scoring.py   # Health scoring + ecosystem state assignment
├── test_consolidation.py    # Consolidation ranking + draft generation
├── test_oracle.py           # Oracle verdict logic
├── test_intelligence_api.py # Intelligence router endpoints
├── test_actions.py          # Ecosystem voice, calendar, redirects
├── test_retention.py        # Impact tracking, steward, billing
├── test_encryption.py       # Fernet encrypt/decrypt roundtrip
├── test_rate_limiter.py     # Rate limiter timing
└── test_auth.py             # JWT validation + dev fallback
```

**conftest.py approach:**
- Use `asyncpg` to create a test database (or use a test schema)
- Run migrations against test DB
- Create `AsyncClient` (httpx) pointed at test FastAPI app
- Mock external services: OpenAI, Claude, GA4, GSC, Stripe, Resend
- Fixture for authenticated test user (generates valid JWT or dev token)
- Cleanup: drop test data after each test

**Key test scenarios:**

**test_sites.py:**
- Create site → verify response shape
- List sites → only returns current user's sites
- Delete site → cascades (posts, metrics, clusters gone)
- Create site with WP password → verify it's encrypted in DB, not in response

**test_clustering.py:**
- Given 10 post embeddings with 2 clear groups → HDBSCAN produces 2 clusters
- Given <5 posts → single cluster fallback
- Idempotent: running twice produces same result (old clusters cleared)

**test_cannibalization.py:**
- Two posts with 50% query overlap → flagged as cannibalizing
- Two posts with 10% overlap → not flagged
- Severity scoring: both at position 10 = high, one at 3 other at 50 = low

**test_health_scoring.py:**
- Post with highest traffic in cluster → assigned "pillar" role
- Post with zero traffic → assigned "dead_weight"
- Cluster with pillar + low cannibalization → "forest" state
- Cluster with 10+ posts + high cannibalization → "swamp" state

**test_oracle.py:**
- Draft with no similar posts → high confidence, publish verdict
- Draft very similar to existing swamp cluster → low confidence, skip verdict

**test_encryption.py:**
- encrypt_value → decrypt_value roundtrip returns original
- decrypt_value with wrong key raises ValueError
- Empty string passes through unchanged

**test_auth.py:**
- Valid UUID token (dev mode) → returns user_id
- Invalid token → 401
- Missing header → 401

**test_impact_tracker.py:**
- Start tracking → baseline captured
- Check impact after traffic change → correct percentage
- 90+ days → status changes to "complete"

**test_stripe.py (mocked):**
- Checkout session creation → returns URL
- Webhook: checkout.session.completed → activates subscription
- Webhook: customer.subscription.deleted → downgrades to free
- Usage limits: free tier at 51 posts → returns False

Add to requirements.txt:
```
pytest==8.3.4
pytest-asyncio==0.24.0
httpx==0.27.0
pytest-mock==3.14.0
```

### Frontend Tests (vitest + testing-library)

Create `frontend/__tests__/` with:

```
frontend/__tests__/
├── components/
│   ├── HealthScoreCard.test.tsx
│   ├── SeverityBadge.test.tsx
│   ├── VerdictDisplay.test.tsx
│   └── PlanCard.test.tsx
├── lib/
│   ├── api.test.ts          # API client error handling
│   └── constants.test.ts    # Color/config sanity checks
└── setup.ts                 # Test setup (jsdom, mocks)
```

Add to package.json:
```json
"devDependencies": {
  "vitest": "^2.0.0",
  "@testing-library/react": "^16.0.0",
  "@testing-library/jest-dom": "^6.5.0",
  "jsdom": "^25.0.0"
}
```

Add `vitest.config.ts` and test script to package.json.

## 2. API Versioning

Add `/v1/` prefix to ALL routes in `main.py`:

```python
from fastapi import APIRouter

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
v1_router.include_router(sites.router, prefix="/sites", tags=["Sites"])
# ... etc for all routers

app.include_router(v1_router)

# Keep /health at root (no version prefix)
```

Update frontend `api.ts` to use `/v1/` prefix in all API paths.

## 3. API Rate Limiting

Install `slowapi` and add rate limiting:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Rate limits:
- Oracle endpoint: 10/minute (Claude API calls are expensive)
- Consolidation draft: 5/minute
- Narrative generation: 5/minute
- All other endpoints: 60/minute
- Stripe webhook: no limit (it's Stripe calling us)

Add `slowapi==0.1.9` to requirements.txt.

## 4. Migration Runner

Create `backend/migrate.py`:

```python
"""Run database migrations in order against Supabase."""
import asyncio
import asyncpg
import os
import glob

async def run_migrations():
    db_url = os.environ.get("DATABASE_URL")
    conn = await asyncpg.connect(db_url)
    
    # Create migrations tracking table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # Get already-applied migrations
    applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM _migrations")}
    
    # Run pending migrations in order
    migration_files = sorted(glob.glob("migrations/*.sql"))
    for filepath in migration_files:
        filename = os.path.basename(filepath)
        if filename in applied:
            print(f"  ✅ {filename} (already applied)")
            continue
        
        print(f"  🔄 Applying {filename}...")
        sql = open(filepath).read()
        await conn.execute(sql)
        await conn.execute("INSERT INTO _migrations (filename) VALUES ($1)", filename)
        print(f"  ✅ {filename} applied")
    
    await conn.close()
    print("Migrations complete.")

if __name__ == "__main__":
    asyncio.run(run_migrations())
```

## 5. Background Task Retry Logic

Create `backend/app/utils/task_retry.py`:

```python
"""Retry wrapper for background tasks."""
import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

async def with_retry(
    func: Callable,
    *args: Any,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    task_name: str = "task",
    **kwargs: Any,
) -> Any:
    """Execute an async function with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                logger.error("%s failed after %d attempts: %s", task_name, max_retries, e)
                raise
            wait = backoff_base ** attempt
            logger.warning(
                "%s attempt %d/%d failed: %s — retrying in %.1fs",
                task_name, attempt, max_retries, e, wait,
            )
            await asyncio.sleep(wait)
```

Apply to all background tasks in intelligence.py, actions.py, retention.py:
```python
background_tasks.add_task(with_retry, _run_full_pipeline, site_id, task_name="intelligence_pipeline")
```

## 6. Batch Queries in steward.py

Rewrite steward.py to use `ANY($1::uuid[])` pattern instead of per-site loops.
Should go from ~70 queries (10 sites) to ~10 queries total.

## 7. Token Guard for Claude API Calls

Create `backend/app/utils/token_guard.py`:

```python
"""Token counting and truncation for Claude API calls."""

def estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ≈ 4 chars for English)."""
    return len(text) // 4

def truncate_for_context(
    texts: list[str],
    max_total_tokens: int = 150000,  # Leave headroom in Claude's 200k context
    per_text_max: int = 20000,
) -> list[str]:
    """Truncate a list of texts to fit within token budget."""
    result = []
    remaining = max_total_tokens
    for text in texts:
        tokens = estimate_tokens(text)
        if tokens > per_text_max:
            # Truncate individual text
            char_limit = per_text_max * 4
            text = text[:char_limit] + "\n\n[... truncated for length]"
            tokens = per_text_max
        if tokens > remaining:
            break
        result.append(text)
        remaining -= tokens
    return result
```

Apply in consolidation.py before sending posts to Claude for draft generation.
Apply in oracle.py before sending similar posts context.

## 8. Landing Page Landscape Mockup

Create a static SVG landscape illustration for the landing page hero section.
This should be an inline SVG in the hero component showing:
- A stylized terrain with 4-5 regions
- Green forest region with tall trees
- Murky swamp region with tangled vines
- Tan desert region with stumps
- Small bright seedbed with sprouts
- Soft meadow area

This is the "screenshot factor" — what makes people share and ask "what is that?"

Update `frontend/src/app/page.tsx` hero section to include this SVG illustration.

## 9. CORS Production Config

Update `backend/app/main.py` CORS to read from config:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Ensure `.env.example` has:
```
CORS_ORIGINS=http://localhost:3000,https://tended.app
```

## When Complete

1. Run `cd backend && python -m pytest tests/ -v` — all tests pass
2. Run `cd frontend && npm run build` — zero errors
3. Run `cd frontend && npx vitest run` — all tests pass  
4. All Python files compile clean
5. Commit: "quality: hardening pass — tests, API versioning, rate limiting, retry logic, migration runner, token guards, landing mockup"
6. Run: openclaw system event --text "Done: Hardening pass complete — 50+ tests, API v1 versioning, rate limiting, retry logic, migration runner, token guards, landing page mockup. Codebase is 10/10." --mode now
