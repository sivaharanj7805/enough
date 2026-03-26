# Enough — Technical Roadmap

**Date:** 2026-03-25
**Current state:** Pipeline works for English content blogs (50-5000 posts with sitemaps). 4 sites tested (anthropic.com, dub.co, cookieandkate.com, zenhabits.net). 18 of 19 bugs fixed. PDF audit is shippable.

---

## Phase 0: Launch Blockers (before first 30 customers)

Must ship these. Without them, the first prospect who looks carefully will lose trust.

### 0.1 Health Score Confidence Label + Z-Score Normalization
**Problem:** Scores cluster 35-70 without GA4/GSC. Prospect sees "52/100" with no context.
**Fix:** Add `score_confidence` field ("full" / "crawl-only"). Display prominently: "Health: 52 (content analysis only — connect Google Search Console for complete scoring)." Apply z-score normalization within the site to spread scores across 15-85 range.
**Files:** `health_scoring.py`, `pdf_report.py`, `audit_report.py`
**Effort:** 4-5 hours

### 0.2 Fix Ecosystem State Without GA4
**Problem:** Every cluster shows "swamp" because pillar assignment requires traffic data.
**Fix:** In no-traffic mode, assign pillar to the top-scoring post per cluster (composite > 50). Rewrite ecosystem state conditions to use content quality instead of traffic. Rename states in UI to actionable labels.
**Files:** `health_scoring.py` lines 832-866, 868-911
**Effort:** 4-5 hours

### 0.3 Cannibalization False Positive Reduction
**Problem:** 45-80% of posts flagged on niche sites. Destroys trust immediately.
**Fix:** (a) Intent-aware filtering — raise threshold +0.10 when post intents differ. (b) Heading overlap confirmation — require >20% heading overlap to confirm at "flag" level. (c) Raise absolute floor from 0.35 to 0.40. (d) Add "niche density" metric to auto-adjust.
**Files:** `cannibalization.py` lines 415, 442, 52-130
**Effort:** 6-8 hours

### 0.4 Wire Ecosystem Visualization Renderers
**Problem:** Core differentiator not rendering. Renderers exist as untracked files but aren't wired into EcosystemCanvas.
**Fix:** Commit renderer files, import and call from `EcosystemCanvas.tsx` rendering loop. Verify in browser with real data.
**Files:** `frontend/src/components/landscape/` — all renderer files + `EcosystemCanvas.tsx`
**Effort:** 4-6 hours

### 0.5 Wire Chunk Cannibalization Confirmation
**Problem:** Whole-document cosine catches "similar topic" not "same query target."
**Fix:** `chunk_cannibalization.py` exists but isn't in the pipeline. Run it on top 50 pairs. Downgrade pairs where no chunk pair exceeds 0.88 similarity.
**Files:** `ingestion.py`, `chunk_cannibalization.py`
**Effort:** 4-5 hours

**Phase 0 total: ~24-29 hours**

---

## Phase 1: First Month Post-Launch

### 1.1 Crawl-Only Proxy Signals for Traffic/Engagement
**Problem:** 50% of health score weight is zeroed without GA4/GSC.
**Fix:** Add 3 proxy signals: (a) predicted_engagement from structural signals (images, lists, readability, TOC), (b) content_structure score (heading density, list count), (c) authority_signals (external backlinks via Bing API). Rebalance weights to include these.
**Effort:** 12-16 hours
**Dependencies:** Bing Webmaster API key (free)

### 1.2 Page Type Auto-Classifier
**Problem:** E-commerce product pages and docs pages scored as blog posts.
**Fix:** Add `page_type` column. Classify from URL patterns + HTML signals (schema Product, code blocks, price elements). Adjust thin content thresholds and depth scoring per type.
**Effort:** 6-8 hours

### 1.3 GEO-5 Scoring + Action Templates
**Problem:** AI Readiness is the differentiator but could go deeper.
**Fix:** Add quote-worthiness detector, comparison table extractability, standalone section test. Generate pre-filled JSON-LD templates in recommendations.
**Effort:** 8-10 hours

### 1.4 Canvas Performance for Large Sites
**Problem:** 50+ clusters with 5000+ posts = 10,000+ draw calls.
**Fix:** PixiJS ParticleContainer for homogeneous elements, viewport culling, sprite sheets, LOD system.
**Effort:** 6-8 hours

### 1.5 Short-Form Content Profile
**Problem:** Essay blogs (Seth Godin, zenhabits) penalized for intentionally short posts.
**Fix:** Detect site content profile from word count distribution. Adjust depth scoring curve for short-form sites.
**Effort:** 3-4 hours

---

## Phase 2: Growth Engine (Month 2-3)

### 2.1 Automated Prospect Discovery + Outreach
**Problem:** Manual DMs don't scale.
**Fix:** Google CSE to find blogs by niche keyword. Auto-run audit pipeline. Find contact emails (Hunter.io). Send 3-email drip via Resend with PDF attached.
**Effort:** 22-28 hours
**Cost:** Hunter.io $49/mo, Google CSE $5/1000 queries, ~$10/mo for 100 audits in API costs

### 2.2 Competitive AI Readiness Benchmarking
**Problem:** Scores without context. "Your AI Citability: 35/100" means nothing without comparison.
**Fix:** For top 10 posts, scrape SERP for cluster keywords, score top 3 competitor pages with same scoring functions. Show "You: 35. Competitors avg: 62. Gap: 27."
**Effort:** 8-10 hours
**Dependencies:** SerpAPI subscription ($50/5000 searches)

### 2.3 SPA Rendering via Playwright
**Problem:** React/Vue/Angular sites return empty body_text.
**Fix:** Detect JS-rendered pages, fall back to Playwright headless Chrome. Rate limit at 3 concurrent, cache rendered HTML.
**Effort:** 8-10 hours
**Dependencies:** Playwright + Chromium in Docker image (+400MB)

### 2.4 Large Site Optimizations
**Problem:** 5000+ posts take 30-60 minutes.
**Fix:** Incremental clustering (reuse assignments for unchanged posts). Parallel cluster processing with asyncio.gather. Progress reporting to UI.
**Effort:** 6-8 hours

---

## Phase 3: Future Roadmap

### 3.1 Non-English Content Support
Multilingual stop words, language-specific readability (LIX, Fernandez Huerta), skip English-only regex for non-English posts, Claude-based translation for recommendation copy.
**Effort:** 20+ hours

### 3.2 Link-Following Crawl Fallback
BFS spider from homepage when no sitemap/RSS found. Depth-limited, rate-limited.
**Effort:** 4-5 hours

### 3.3 Authenticated Content Crawling
Cookie-based auth field in sites table. Manual CSV/JSON content upload endpoint.
**Effort:** 6-8 hours

### 3.4 AI Citation Monitoring
Periodically query ChatGPT/Claude/Perplexity with cluster keywords, check if site URLs appear in citations. Ultimate proof of value.
**Effort:** 20+ hours

---

## Cost Model at Scale

| Component | 100 audits/mo | 1000 audits/mo |
|-----------|---------------|----------------|
| OpenAI embeddings | $4 | $40 |
| Claude (labels + enrichment) | $5 | $50 |
| SERP API (Phase 2) | $1 | $10 |
| Hunter.io (Phase 2) | $49 | $99 |
| Resend (email) | Free | $20 |
| Infrastructure | $50 | $200 |
| **Total marginal** | **~$110/mo** | **~$420/mo** |
| **Revenue (at 10% conversion)** | **$1,490/mo** | **$14,900/mo** |

---

## Key Files Impacted

| File | Phases |
|------|--------|
| `backend/app/services/health_scoring.py` | 0.1, 0.2, 1.1, 1.5 |
| `backend/app/services/cannibalization.py` | 0.3, 0.5 |
| `backend/app/services/problem_detection.py` | 1.2 |
| `backend/app/services/ai_citability.py` | 1.3 |
| `backend/app/services/sitemap.py` | 2.3, 3.2 |
| `backend/app/services/pdf_report.py` | 0.1 |
| `frontend/src/components/landscape/EcosystemCanvas.tsx` | 0.4, 1.4 |
| `backend/app/routers/ingestion.py` | 0.5, 2.4 |

