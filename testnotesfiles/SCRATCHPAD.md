# Full Codebase Audit — Compiled Results

**Date:** 2026-03-23
**Scope:** 47 backend services (16,661 LOC), 13 routers (5,900+ LOC), 22+ frontend pages, 29 migrations, 41 backend test files (9,528 LOC), 8 frontend test files

---

## A. COMPLETE BUG LIST (Sorted by Severity)

### CRITICAL (7 bugs)

| # | File:Line | Description | Impact |
|---|-----------|-------------|--------|
| 1 | `ai_citability.py:501-507` | Missing `site_id` filter in scoring query — scores posts from ALL sites, not just the target site | Cross-site data leakage; wrong AI scores |
| 2 | `health_scoring.py:128-134` | AI scores cleared when health scores recalculated — AI readiness penalized to 0 until AI module re-runs | All posts lose AI readiness until separate re-scoring |
| 3 | `problem_detection.py:423` | Decay problem filter checks `problem_type = 'content_decay'` but actual types are `decay_severe/moderate/mild` | Duplicate decay problems created every run |
| 4 | `recrawl.py:261-274` | Stale job cleanup marks jobs as 'failed' after 2 hours — kills legitimate long-running crawls | Large site crawls aborted prematurely |
| 5 | `redirect_push.py:98-111` | WordPress fallback endpoint `/wp/v2/settings` with `tended_redirect` key doesn't exist — fails silently | Redirects never pushed if Redirection plugin missing |
| 6 | `on_demand_enrichment.py:20-22` | Global AsyncAnthropic client singleton without thread safety — race condition on concurrent requests | Resource leak, duplicate API connections |
| 7 | `impact_tracker.py:128` | Division by zero when baseline position is None — crashes position delta calculation | Impact tracking crashes for posts without GSC data |

### HIGH (12 bugs)

| # | File:Line | Description |
|---|-----------|-------------|
| 8 | `stripe_service.py:171-185` | Webhook idempotency race: check-then-insert allows duplicate processing of concurrent webhooks |
| 9 | `stripe_service.py:87-92` | Redirect URL validation uses `startswith()` — allows `http://localhost:3000.evil.com` bypass |
| 10 | `google_integration.py:49` | OAuth state is plaintext `site_id:user_id:token` — no HMAC signing (auth.py does it correctly) — allows token hijacking |
| 11 | `clustering.py:457-460` | `post_clusters` INSERT with `ON CONFLICT DO NOTHING` breaks sub-clustering hierarchy |
| 12 | `cannibalization.py:122` | JSON string construction with f-string — NaN/infinity values produce invalid JSON |
| 13 | `fast_recommendations.py:416` | Word count math: `word_count or 0` masks NULL as 0, producing incorrect `words_needed` calculation |
| 14 | `rag_context.py:472` | pgvector vector format type mismatch — `$1::vector` may fail if embedding string format is wrong |
| 15 | `consolidation.py:135` | Traffic recovery estimate multiplies by 0.6 (60%) — overly aggressive, misleads users on ROI |
| 16 | `recrawl.py:277-279` | Hard-deletes anonymous sites without checking for active pipelines — cascading data loss |
| 17 | `normalizer.py:42` | Title stripping uses `maxsplit=len(parts)-2` — when parts has 2 elements, maxsplit=0 means no stripping |
| 18 | `content_gaps.py:95-116` | Embedding similarity query compares ALL posts to a SINGLE embedding (LIMIT 1) — defeats cluster matching |
| 19 | `weekly_report.py:360` | Resend API key set as attribute — stack trace on error could leak key |

### MEDIUM (40+ bugs — top 20 shown)

| # | File:Line | Description |
|---|-----------|-------------|
| 20 | `stripe_service.py:214` | Assumes subscription always has ≥1 item — KeyError if Stripe returns empty items array |
| 21 | `health_scoring.py:823-857` | Role assignment checks `is_cannibalizing` AFTER composite score check — cannibalizing pillars mislabeled |
| 22 | `cannibalization.py:435-436` | Severity score can exceed 100 (sim_component + intent 30 + query 10 > 100 for high values) |
| 23 | `ecosystem_visuals.py:114-130` | O(N²) inter-cluster link counting — 100 clusters = 4,950 queries |
| 24 | `oracle.py:129` | pgvector format uses commas without spaces — may cause silent parsing failures |
| 25 | `drip_sequence.py:297` | Unsubscribe URL includes email in plaintext query param — leaks to proxies/analytics |
| 26 | `pdf_report.py:533-553` | Spider chart data validation missing — None values crash reportlab |
| 27 | `competitor_compare.py:81` | References `g["topic"]` but column is likely `query` — KeyError at runtime |
| 28 | `steward.py:88` | References non-existent `consolidated_urls` column — runtime crash |
| 29 | `ecosystem_voice.py:78` | Accesses `ph.role` not in SELECT clause — query fails |
| 30 | `readability.py:159` | `readability_details` computed but never stored — wasted CPU |
| 31 | `content_briefs.py:102-103` | Unsafe UUID conversion without try-except — crashes brief generation |
| 32 | `recrawl.py:150` | URL comparison done before normalization — misses HTTPS/HTTP variants |
| 33 | `normalizer.py:56-107` | Nav link filtering threshold hardcoded at 80% — unreliable for small sites |
| 34 | `on_demand_enrichment.py:191-192` | JSON parsing strips `json` token but not closing backticks — parse fails |
| 35 | `drip_sequence.py:90-97` | Email 1 retry logic never executes — status already 'sent' before cron processes |
| 36 | `content_wrapped.py:173` | `swamps_cleared` variable counts current swamps, not cleared ones — misleading metric |
| 37 | `ai_citability.py:460-474` | Standalone section ratio gives 10 pts for pages with ZERO H2 headers (1 - 0/1 = 1.0) |
| 38 | `ai_citability.py:185-188` | Answer-first requires BOTH declarative statement AND digit — definitional content penalized |
| 39 | `clustering.py:229-230` | UMAP n_components clamping: 3 posts → n_components=1 which UMAP rejects |

---

## B. SECURITY VULNERABILITY LIST

### CRITICAL (2)

| # | File:Line | Vulnerability | Exploitability |
|---|-----------|--------------|----------------|
| 1 | `google_integration.py:49` | OAuth state forgery — plaintext `site_id:user_id:token` without HMAC | Attacker crafts state to link Google account to any user. Requires redirect interception. |
| 2 | **Repository is PUBLIC** with MIT license | All source code, business logic, pricing strategy, API patterns exposed | Anyone can read, clone, and replicate the entire product |

### HIGH (3)

| # | File:Line | Vulnerability |
|---|-----------|--------------|
| 3 | `stripe_service.py:87-92` | Redirect URL validation uses `startswith()` — open redirect via domain suffix attack |
| 4 | `weekly_report.py:360` | Resend API key leak in stack traces on error |
| 5 | `AuthProvider.tsx:120-121` | JWT stored in localStorage — vulnerable to XSS token theft |

### MEDIUM (8)

| # | File:Line | Vulnerability |
|---|-----------|--------------|
| 6 | `oracle.py:164`, `rag_context.py:645` | ILIKE wildcard injection — `%` and `_` in keywords match unexpected patterns |
| 7 | `drip_sequence.py:297` | Email in unsubscribe URL query param — leaks to proxies |
| 8 | `pdf_report.py:686-693` | Incomplete HTML entity escaping — potential reportlab XML injection |
| 9 | `redirect_push.py:25` | WordPress Basic Auth over HTTP (no HTTPS validation) |
| 10 | `weekly_report.py:249-307` | HTML injection via user data in email templates (blog name, rec title) |
| 11 | `drip_sequence.py:149-169` | HTML injection — blog name/domain inserted without `html.escape()` |
| 12 | `audit_report.py:590` | Admin secret falls back to cron_secret — if both missing, endpoint unprotected |
| 13 | `config.py:117` | `validate_production()` checks `stripe_price_growth` but NOT `stripe_price_scale` |

---

## C. WHAT ACTUALLY WORKS (Production-Ready Assessment)

### Fully Production-Ready
- **Security middleware**: HSTS, CSP, X-Frame-Options, XSS-Protection, request size limit, host validation, request ID tracing
- **Auth dependency chain**: JWT validation with production guard, UUID fallback gated behind environment check
- **Pricing consistency**: $149/$349 correct across all 7 instances (landing, billing, drip, PDF, winback)
- **Frontend middleware**: All 19 dashboard routes protected, proper cookie/header check
- **Router registration**: All 13 routers registered, all frontend hooks map to real endpoints
- **ErrorBoundary**: Properly wired in dashboard layout
- **Makefile + CI**: Lint, test, build pipeline working
- **Migration runner**: Tracking table, transactional, sorted ordering
- **API URL handling**: No double `/v1` bug

### Works But Has Issues
- **47 backend services**: All real implementations (none are stubs), but 7 critical bugs and 40+ medium bugs
- **Intelligence pipeline**: Full 17-stage pipeline works but marks "completed" even when steps fail silently
- **Stripe integration**: Checkout, webhooks, winback emails work but have webhook idempotency race and redirect validation bypass
- **AI citability scoring**: 4-dimension scoring works but has 10 bugs in scoring logic and is NOT integrated into health score
- **Ecosystem visualization**: PixiJS migration done, all renderers present, but old Canvas overlay files still exist alongside
- **Email system**: Drip sequence, weekly reports, winback emails all work but have HTML injection risks
- **PDF report**: Generates professional reports but crashes on None values in audit data

### Missing Entirely
- **E2E test framework**: Zero Playwright/Cypress tests
- **AI citation monitoring**: Not built (post-launch feature)
- **AI Share of Voice dashboard**: Not built (Scale tier)
- **Production deployment**: No hosting configured yet

---

## D. RECOMMENDED FIX ORDER

### Must Fix Before Any User Sees This (Security + Crashes)

1. **Make repo private** (INFRA-1) — 5 minutes
2. **Fix Google OAuth state forgery** (`google_integration.py:49`) — add HMAC signing like `auth.py` does — 30 min
3. **Fix Stripe redirect URL validation** (`stripe_service.py:87-92`) — use `urllib.parse.urlparse()` hostname comparison — 15 min
4. **Fix cross-site AI scoring** (`ai_citability.py:501-507`) — add `WHERE p.site_id = $1` filter — 5 min
5. **Fix admin endpoint fallback** (`audit_report.py:590`) — require explicit admin_secret, don't fall back — 10 min
6. **Fix SSL hardcoded in database.py** — conditionally apply based on environment — 10 min
7. **Add `stripe_price_scale` to production validation** (`config.py`) — 5 min

### Must Fix Before Charging Money (Broken Flows)

8. **Fix pipeline silent failures** (`ingestion.py`) — abort pipeline on critical step failure, report actual error — 2 hr
9. **Fix health scoring AI score clearing** (`health_scoring.py:128-134`) — preserve AI scores during recalculation — 1 hr
10. **Fix decay problem duplicate detection** (`problem_detection.py:423`) — change filter to `LIKE 'decay_%'` — 10 min
11. **Fix webhook idempotency race** (`stripe_service.py:171-185`) — use `INSERT ON CONFLICT` instead of check-then-insert — 30 min
12. **Fix stale job cleanup** (`recrawl.py:261-274`) — increase timeout to 6+ hours or add heartbeat — 30 min
13. **Fix HTML injection in emails** (`drip_sequence.py`, `weekly_report.py`) — add `html.escape()` to all user data — 1 hr
14. **Fix spider chart crash** (`pdf_report.py:533-553`) — validate/coerce values to float before rendering — 15 min

### Should Fix Before Launch (Performance + Polish)

15. **Fix ecosystem_visuals O(N²) queries** — batch inter-cluster link counting into single query — 2 hr
16. **Fix HNSW per-post queries in cannibalization** — batch into single query — 2 hr
17. **Fix weekly report sequential sends** — use `asyncio.gather()` for parallel email sends — 1 hr
18. **Fix CI format check** (`.github/workflows/ci.yml:55`) — remove `|| true` — 5 min
19. **Add rate limiting to POST /sites and POST /crawl** — prevent spam — 30 min
20. **Fix unsubscribe page styling** — use dark theme colors instead of light — 15 min

### Can Fix After Launch

21. Fix all 40+ MEDIUM bugs (see full list above)
22. Add tests for 24 untested service modules
23. Add frontend page tests
24. Add E2E test framework (Playwright)
25. Fix localStorage token storage — move to httpOnly cookies
26. Enforce session expiry using `session_max_age_seconds` config

---

## E. WHERE YOU STAND

**How close to charging $149/month?** About 1-2 days of focused security fixes away from being deployable.

The product is surprisingly complete. All 47 backend services are real implementations — not a single stub. The 17-stage intelligence pipeline (crawl → embed → cluster → health → cannibalize → recommend → AI score) works end-to-end. The frontend has 22+ functional pages, ErrorBoundary wired in, pricing consistent, no fabricated social proof. The PixiJS ecosystem visualization is built. The GEO/AI readiness scoring has 4 dimensions with 10+ signals each.

**The single biggest blocker is the repo being public.** Everything else is fixable in hours, but your entire codebase — including Stripe integration patterns, pricing logic, and competitive strategy — is currently readable by anyone with a browser. Make it private today.

**The second biggest blocker is the 7 critical bugs.** The cross-site AI scoring leak, the Google OAuth state forgery, and the pipeline silent failures are the kind of bugs that erode user trust. Fix these before any real user touches the product.

**What I'd do first:** Private the repo (5 min). Fix the 7 critical security/crash bugs (items 2-7 above, ~1 hour total). Fix the 7 broken-flow bugs (items 8-14, ~5 hours). Deploy to Supabase + Vercel + Fly.io. Run 10 real blogs through the pipeline. DM 10 founders with their audit PDFs. Take calls. Ship.

**The test coverage is your biggest long-term risk.** At ~25-35% real coverage with zero E2E tests, you're flying blind on regressions. The pipeline could break silently and you wouldn't know until a customer complains. But this is a post-launch concern — ship first, add tests as you stabilize.

**Total bugs found:** 7 CRITICAL, 12 HIGH, 40+ MEDIUM, 30+ LOW across all 47 services, 13 routers, 22 pages, and 29 migrations. 2 CRITICAL security vulnerabilities, 3 HIGH, 8 MEDIUM. Real test coverage: ~25-35%.
