# Contributing to Tended

## Setup

```bash
git clone https://github.com/blossummico123/tended.git
cd tended

# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env  # Fill in your keys

# Frontend
cd ../frontend
npm ci
cp .env.example .env.local
```

Or use Docker Compose for the full stack:
```bash
cp .env.example .env
docker-compose up
```

## Running Tests

```bash
make test-backend    # pytest with coverage
make test-frontend   # vitest
make test            # both
```

## Linting / Formatting

```bash
make lint-backend    # ruff check
make lint-frontend   # eslint
make format          # ruff format + prettier
```

## PR Process

1. Branch off `main`: `git checkout -b feature/your-feature`
2. Make changes + tests
3. Run `make lint test` — must pass
4. Open a PR against `main`
5. PRs require one approval before merge

## Coding Standards

**Python:**
- Type hints on all public functions
- `logger.exception()` instead of `traceback.print_exc()`
- Never use bare `except: pass` — at minimum log the error
- Follow ruff rules (E, F, W, I, UP, B)

**TypeScript:**
- No `any` types — use proper interfaces
- `useEffect` cleanup for all subscriptions, timers, and D3 event listeners
- `aria-label` on all interactive SVG elements

**SQL:**
- Every new table needs `created_at TIMESTAMPTZ DEFAULT NOW()`
- Every new query path needs a covering index
- No raw string interpolation in queries — use parameterized queries

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
feat: add weekly email digest
fix: correct UMAP min_dist for tight niches
security: enforce CRON_SECRET in production
test: add health scoring unit tests
```
