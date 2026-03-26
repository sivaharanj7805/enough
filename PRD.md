# Enough — Product Requirements Document

**Version:** 1.0
**Date:** 2026-03-22
**Author:** Generated from codebase audit + founder input
**Status:** Draft — pending founder review
**Audience:** Solo founder (primary), Claude Code sessions (working context), future hires/contractors (reference)

---

## Table of Contents

1. [Vision & Problem](#1-vision--problem)
2. [Target Users](#2-target-users)
3. [Competitive Landscape](#3-competitive-landscape)
4. [Product Specification](#4-product-specification)
5. [User Journeys](#5-user-journeys)
6. [Pricing & Tier Specification](#6-pricing--tier-specification)
7. [Technical Architecture](#7-technical-architecture)
8. [Lead Generation & GTM Infrastructure](#8-lead-generation--gtm-infrastructure)
9. [90-Day Roadmap](#9-90-day-roadmap)
10. [Success Metrics & KPIs](#10-success-metrics--kpis)
11. [Open Questions & Decisions Needed](#11-open-questions--decisions-needed)
12. [Known Issues & Technical Debt](#12-known-issues--technical-debt)

---

## 1. Vision & Problem

### 1.1 One-line

Content intelligence platform that finds cannibalization, decay, and dead weight in your blog — and tells you exactly what to fix.

### 1.2 The problem

B2B SaaS companies with 100-500 blog posts have a hidden problem: their content is fighting itself. Posts written 2 years apart target the same keywords. Google picks one; the rest cannibalize each other. Meanwhile, old posts decay silently — losing rankings, leaking traffic, dragging down the domain.

Content teams know this happens. They don't have the tools to find it at scale. The current workflow is:

1. Export 500 URLs from Ahrefs/Semrush into a spreadsheet
2. Manually compare titles, keywords, and traffic for overlaps
3. Spend 2-4 weeks building a consolidation plan
4. Pay an agency $2K-5K for a content audit that's outdated the day it's delivered

This costs $2K-5K per audit, takes weeks, and produces a static PDF that's stale immediately.

### 1.3 The solution

Enough does this in 25 minutes for $7 in API costs:

1. Crawl every post on the blog
2. Generate 1,536-dimension embeddings for each post
3. Cluster posts by topic similarity (UMAP + HDBSCAN)
4. Detect cannibalization with auto-calibrated thresholds (cosine similarity + GSC query overlap)
5. Score health across 6 factors (traffic, ranking, engagement, freshness, depth, technical SEO)
6. Generate specific, actionable recommendations (not "improve this post" but "merge posts A and B, redirect A → B, here's the new meta description")

The output is a living, visual ecosystem map — not a spreadsheet. Clusters appear as terrain (forests for healthy topics, swamps for cannibalized ones, deserts for dead content). Individual posts are trees. The user sees their blog as a map and immediately understands what's healthy, what's dying, and what's fighting.

### 1.4 Core differentiators

| Differentiator | What it means |
|---|---|
| **Auto-calibrated thresholds** | Cannibalization detection adapts per site. A niche blog with tightly related content uses different similarity thresholds than a general blog. 85th/92nd/97th percentile calibration, not fixed numbers. |
| **Chunk-level detection** | Finds overlap within sections of posts, not just whole-post similarity. Two posts can be 40% similar overall but have one section that's 95% duplicated. |
| **Specific actionable output** | Writes the meta description, names the redirect URL, tells you which sections to merge, generates the actual consolidated draft (Scale tier). |
| **RAG-enhanced recommendations** | Recommendations are grounded in the user's own top-performing content. "Expand to ~2,400 words — your top 3 posts in this cluster average 2,387." |
| **Ecosystem visualization** | The landscape map is the screenshot that stops the scroll. No other SEO tool looks like this. |
| **Tiered AI strategy** | ~85-90% of work handled without API calls (TF-IDF labels, regex intent classification, template recommendations). API calls only for the hard 10-15%. |

---

## 2. Target Users

### 2.1 Primary persona: "Content Sarah"

**Role:** Content Marketing Manager or SEO Lead at a B2B SaaS company (50-500 employees)
**Blog size:** 100-500 published posts, 2-5 years of accumulated content
**Budget:** Already paying $129-$149/month for Ahrefs or Semrush
**Pain:** Knows the blog has cannibalization and decay problems. Has been asked by her VP to "clean up the blog." Doesn't have the time or tools to audit 300+ posts manually. Has gotten quotes from agencies: $3K-5K for a one-time audit.
**Behavior:** Checks Ahrefs weekly. Publishes 2-4 posts/month. Occasionally updates old posts when someone flags a ranking drop. Has never done a systematic content consolidation.
**Conversion trigger:** Seeing specific cannibalization pairs in her own blog with similarity scores and traffic data. "Oh shit, these two posts are 87% similar and they're splitting my traffic."

### 2.2 Secondary persona: "Agency Alex"

**Role:** SEO consultant or agency owner managing 5-15 client blogs
**Blog sizes:** Varies, 50-2,000 posts per client
**Budget:** Charges clients $2K-5K per content audit. Enough at $349/month for 3 sites is a fraction of one client engagement.
**Pain:** Producing content audits manually takes 2-4 weeks per client. Wants to scale the audit practice without hiring more analysts.
**Behavior:** Runs audits quarterly per client. Delivers PDF reports. Needs white-label output.
**Conversion trigger:** Enough produces in 25 minutes what takes 2 weeks. The PDF report is ready to rebrand and deliver.

### 2.3 Who we are NOT targeting

- **Solo bloggers with <50 posts:** Not enough content for cannibalization to be a real problem. Won't pay $149/month.
- **Enterprise teams with 10,000+ pages:** Need Salesforce-level onboarding, SSO, custom integrations, SLAs. Can't serve as a solo founder.
- **E-commerce sites:** Product pages have different patterns than blog content. The clustering and health scoring models are tuned for editorial content.

---

## 3. Competitive Landscape

### 3.1 Direct competitors

| Competitor | Price | Overlap | Enough's advantage |
|---|---|---|---|
| **MarketMuse** | $270-$545+/mo | Content intelligence, topic modeling, content briefs | MarketMuse tells you "write about X." Enough tells you "merge these two posts, here's the redirect URL, here's the new meta description." Plus the ecosystem visualization. |
| **Entail AI** | $200+/mo | Topical authority graphs | Entail shows abstract network diagrams. Enough shows a living ecosystem with terrain, trees, and health scores. |
| **Surfer SEO Content Audit** | $129-$219/mo (bundled) | Monitors positions, suggests refreshes | Growing threat — massive distribution. But Surfer audits individual pages. Enough audits the relationship between pages (cannibalization, clustering, consolidation). |

### 3.2 Indirect competitors

| Competitor | Price | Overlap | Why they're not the same |
|---|---|---|---|
| **Ahrefs** | $129/mo | Has cannibalization detection as a buried feature | Finds the problem but doesn't generate merge plans, redirect maps, or rewritten meta descriptions. |
| **Semrush** | $139/mo | Content Audit tool | Same as Ahrefs. Identifies issues but doesn't tell you specifically what to do. |
| **Manual agency audit** | $2K-5K one-time | Full content audit | Static PDF, outdated immediately. Enough is a living dashboard that updates weekly. |

### 3.3 Positioning statement

For content marketers at B2B SaaS companies who need to find and fix cannibalization, decay, and dead weight in their blog, Enough is a content ecosystem intelligence platform that analyzes your entire blog in 25 minutes, finds every post competing against another, and tells you exactly what to merge, redirect, and rewrite — unlike Ahrefs and Semrush which identify problems but leave you to figure out the fix, or agencies that charge $5K for a static audit that's outdated tomorrow.

---

## 4. Product Specification

This section documents every feature area: what it does, its current implementation state, and the acceptance criteria for "done." Features are grouped by user-facing area, not by code architecture.

### 4.1 Landing Page & Lead Generation

**Purpose:** Convert visitors to free audit requests (lead gen) or paid signups.

**Current state:** Built. 320+ lines. Hero with audit CTA, social proof bar, problem statement, pricing section, FAQ accordion.

**What exists:**
- URL + email form → triggers `POST /v1/audit-report/pdf` (unauthenticated)
- Success state: "Check your inbox in 20-25 minutes"
- Trust badges: "Read-only," "30-day money-back," "Your data stays private"
- Social proof bar: "958 posts analyzed on Close.com, 200 cannibalization pairs, 1,247 blogs analyzed"
- Pricing section with Growth/Scale cards and monthly/annual toggle
- FAQ accordion (5 items, inline strings)
- Secondary CTA: "Subscribe & Start Fixing" → /signup

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Stale pricing | Critical | Shows $99/$249. Correct: $149/$349. |
| Fabricated social proof | High | "1,247 blogs analyzed" — zero users exist. Remove or replace with Close.com case study only. |
| Inline strings | Medium | FAQ items, problem statements, pricing features all inline. Should be in `lib/copy.ts`. |
| API URL fragility | High | Uses `${NEXT_PUBLIC_API_URL}/v1/...` directly instead of `apiFetch`. |
| Annual pricing math | Medium | Annual prices ($990/$2490) need updating when monthly prices change to $149/$349. |

**Acceptance criteria for "done":**
- [ ] Pricing shows $149/mo Growth, $349/mo Scale
- [ ] Annual pricing: Growth $1,490/yr ($124.17/mo equiv), Scale $3,490/yr ($290.83/mo equiv)
- [ ] Social proof shows only verifiable data (Close.com case study)
- [ ] All user-facing strings moved to `lib/copy.ts`
- [ ] Audit form uses `apiFetch` or `apiUrl()` helper
- [ ] Hero headline tested: current version is good but long

---

### 4.2 Free Audit Report (Lead Magnet)

**Purpose:** Give prospects a taste of the value. Shows problems but not fixes. Drives email drip → paid conversion.

**Current state:** Backend fully built (`audit_report.py`, 630+ lines). Frontend form exists on landing page.

**Flow:**
1. Visitor enters URL + email on landing page
2. Backend checks if domain already exists in DB → if yes, generates PDF from cached data
3. If new domain → creates anonymous site (`user_id = NULL`), triggers crawl of first 50 posts
4. Runs abbreviated pipeline: crawl → embed → cluster → health score → cannibalization → problems
5. Generates PDF report with: health score, cluster count, cannibalization pair count, top 5 problems, AI readiness score
6. Emails PDF to the provided address via Resend
7. Enrolls email in 3-email drip sequence (day 0, day 2, day 5)

**What the PDF shows:**
- Overall health score (0-100)
- Number of topic clusters found
- Number of cannibalization pairs (shows count, not details)
- Top 5 content problems (shows type and severity, not specific fixes)
- AI citability score
- "Subscribe to see the full analysis" CTA

**What the PDF does NOT show (paywalled):**
- Which specific posts are cannibalizing each other
- The specific recommendations and how to fix them
- The ecosystem map visualization
- Consolidation plans and redirect maps
- The Oracle pre-publish checker

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| No authentication on endpoint | Critical | SEC-2 in AUDIT.md. Unauthenticated. Can exhaust API quotas. |
| ILIKE wildcard injection | High | SEC-6. `f"%{domain}%"` matches arbitrary rows. |
| Stale pricing in drip emails | Critical | BE-3. Drip emails hardcode $99/month. |
| No rate limiting per domain | High | Same domain can be re-audited infinitely. |
| Bare except swallows pipeline errors | High | SEC-10. Silent failure. |

**Acceptance criteria for "done":**
- [ ] Rate limited: 3 audits per email per day, 6 per IP per minute, 1 per domain per 24h
- [ ] CAPTCHA or honeypot on the form (hCaptcha preferred — free for small sites)
- [ ] Domain lookup uses exact match, not ILIKE wildcard
- [ ] Drip emails show correct pricing ($149/mo)
- [ ] Pipeline errors logged with `logger.exception()`
- [ ] Total anonymous site cap: 10,000 (configurable). After cap, return "high demand" message.

---

### 4.3 Authentication & Onboarding

**Purpose:** Get user from signup to seeing their first results as fast as possible.

**Current state:** Auth is built (Supabase Auth + Google OAuth + magic links). Onboarding page exists (170+ lines).

**Auth methods:**
- Email/password signup via Supabase
- Google OAuth
- Magic links (email OTP)
- Demo mode (env var bypass for testing)

**Onboarding flow (current):**
1. User signs up → redirected to `/onboarding`
2. Enter blog URL, select CMS type (sitemap/WordPress), optionally name the site and add URL patterns
3. Click "Analyze" → backend creates site, triggers crawl
4. Poll `GET /sites/{id}/crawl/status` with exponential backoff (5s → 30s, max 25min)
5. UI shows pipeline stages with educational text (crawling → embedding → health scoring → clustering → recommendations)
6. Shows early findings as they arrive (posts sampled, clusters found, cann pairs, thin content)
7. On completion → redirect to `/today`

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Middleware doesn't protect routes | Critical | FE-1. Auth middleware matcher covers `/dashboard/*` but routes are `/today`, `/landscape`, etc. |
| Poll loop has no abort on unmount | High | FE-7. If user navigates away, loop continues in background for up to 25 minutes. |
| No paywall redirect for onboarding | Medium | User can complete onboarding without paying. Currently, dashboard layout redirects to `/billing` if unpaid, but onboarding itself is unprotected. Is this intentional? (See Open Questions.) |
| JWT fallback accepts any UUID | Critical | SEC-4. If `SUPABASE_JWT_SECRET` not set, any UUID is a valid auth token. |

**Acceptance criteria for "done":**
- [ ] Middleware updated to match actual dashboard routes
- [ ] Poll loop uses AbortController, cleans up on unmount
- [ ] JWT fallback removed or gated behind `environment == "development"`
- [ ] Pipeline progress shows real-time stage transitions (current implementation works)
- [ ] Error state shows actionable message ("Check that your blog has a sitemap.xml")
- [ ] Happy path: URL → first results visible in <30 minutes including pipeline runtime

**Decision needed:** Should onboarding require payment first? Current flow: signup → onboarding → pipeline runs → paywall at dashboard. Alternative: signup → paywall → onboarding → pipeline. The current flow lets the pipeline run before payment, meaning free audit + no conversion = wasted API spend (~$7). But it also means the user sees value before paying, which likely increases conversion. See Open Questions.

---

### 4.4 Dashboard Layout & Navigation

**Purpose:** Container for all authenticated views. Enforces auth + paywall. Provides sidebar navigation and Oracle FAB.

**Current state:** Built (`layout.tsx`, 97 lines). Sidebar, Header, paywall redirect, Oracle floating action button.

**Components:**
- `Sidebar` — navigation links to all dashboard pages
- `Header` — site selector, user menu
- `OraclePanel` — slide-in panel triggered by FAB
- Paywall: redirects to `/billing` if subscription tier is not `growth` or `scale`
- Only `/billing` is accessible without a paid subscription

**Dashboard pages (22 total):**

| Route | Page | Purpose | Status |
|---|---|---|---|
| `/today` | Today | Daily command center: health score, priority actions, ROI, changes since last visit | Built (1,202 lines) |
| `/landscape` | Landscape | Ecosystem visualization (D3/Canvas) | Built but **broken** — renderers deleted |
| `/dashboard` | Dashboard | Redirects to `/today` | Built (redirect only) |
| `/clusters` | Clusters | List of topic clusters with health scores | Built |
| `/clusters/[clusterId]` | Cluster Detail | Posts in cluster, narrative, health breakdown | Built |
| `/posts` | Posts | Content library with search/filter/sort | Built |
| `/posts/[postId]` | Post Detail | Single post: problems, recommendations, health | Built |
| `/actions` | Actions | Recommendation feed with type/priority/status filters | Built but **compile error** (duplicate import) |
| `/issues` | Issues | Content problems grouped by type/severity | Built |
| `/cannibalization` | Cannibalization | Pairs with similarity scores, network graph | Built |
| `/consolidation` | Consolidation | Plans with merge groups, drafts, redirect maps | Built |
| `/consolidation/[clusterId]` | Consolidation Detail | Specific cluster's consolidation plan | Built |
| `/oracle` | Oracle | Pre-publish conflict checker (full page) | Built |
| `/overview` | Overview | Analytics KPIs and trend charts | Built but shows **synthetic/fake data** |
| `/billing` | Billing | Stripe subscription management, cancel flow | Built but **wrong prices** |
| `/impact` | Impact | Track consolidation impact | Built |
| `/impact/[trackingId]` | Impact Detail | Specific tracking item's before/after metrics | Built |
| `/explore` | Explore | Tabbed explorer (clusters, posts, landscape, cann, recs, consolidation) | Built |
| `/briefs` | Briefs | Content brief generation | Built |
| `/calendar` | Calendar | Publishing calendar | Built |
| `/competitors` | Competitors | Competitor comparison | Built |
| `/settings` | Settings | Site settings, Google integration | Built |
| `/profile` | Profile | User profile | Built |
| `/wrapped` | Content Wrapped | Weekly summary shareable card | Built |

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| ErrorBoundary not wired | Critical | FE-4. Any render error crashes the entire layout. |
| Actions page won't compile | Critical | FE-5. Duplicate `useSite` import. |
| Oracle FAB missing `aria-label` | Low | FE-24. Has `title` but not `aria-label`. |

**Acceptance criteria for "done":**
- [ ] `<ErrorBoundary>` wraps `{children}` in dashboard layout
- [ ] Actions page compiles (remove duplicate import)
- [ ] All 22 pages load without errors
- [ ] Paywall redirect works (unpaid user → `/billing`)
- [ ] Oracle FAB has `aria-label="Ask Oracle anything"`

---

### 4.5 Today View (Daily Command Center)

**Purpose:** The page users see every day. Shows health score, top priority actions, ROI, and changes since last visit. Replaces the old `/dashboard` page.

**Current state:** Fully built (1,202 lines). Most feature-complete page in the app.

**Components:**
- `SetupChecklist` — shown to new users before first pipeline run
- `PipelineProgress` — shown during active pipeline run
- Animated health score counter (0-100, ease-out quad easing)
- Health score ring with color coding (green/blue/yellow/red)
- Factor breakdown bars (traffic, ranking, engagement, freshness, depth, technical)
- `SinceLastVisitCard` — "Since your last visit: 3 new issues, 2 ranking changes"
- `ProgressCard` — "You've completed 7 recommendations — health improved +4 points"
- `ROICard` — completed actions count, estimated traffic recovery, estimated value, health score change
- `ContentGapCard` — top GSC query with no matching post, one-click "Generate Brief"
- Priority action cards — top 5 recommendations sorted by priority, with expand/collapse, copy-to-clipboard for meta descriptions
- Re-analyze button — triggers pipeline re-run
- AI readiness score card (citability, E-E-A-T, schema, extraction)
- Trend indicators (7d and 30d changes)

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Inline strings | Medium | `getScoreLabel`, confidence levels, "TOP PRIORITY" — should be in `copy.ts`. |
| `daysSinceAnalysis` hardcoded | Low | Always shows 3 or 14 days, not the actual date. |
| `handleGenerateBrief` silently fails | High | API error caught with no user feedback. |
| `CopyButton` catch block empty | Low | Clipboard API failure gives no feedback. |

**Acceptance criteria for "done":**
- [ ] All user-facing strings in `copy.ts`
- [ ] `daysSinceAnalysis` reads `analyzed_at` from the health API response
- [ ] Brief generation failure shows toast/error message
- [ ] Copy failure shows fallback text selection or toast
- [ ] Pipeline re-run button shows progress and disables during run
- [ ] Factor breakdown bars are clickable (link to relevant detail page)

---

### 4.6 Ecosystem Visualization (Landscape)

**Purpose:** The core differentiator. A nature-themed map where topic clusters are terrain zones and individual posts are trees. This is the "screenshot that stops the scroll."

**Current state:** BROKEN. All 6 renderers were deleted in commit `c0a296b`. The canvas runs an empty `requestAnimationFrame` loop. What remains is colored ellipses with health badges — which is the data layer without the visual layer.

**What was built (and needs to be restored from commits `2a559e1` / `43fe5ea`):**

| Component | Purpose | Status |
|---|---|---|
| `EcosystemCanvas.tsx` | Main canvas orchestrator, force simulation, pan/zoom | Exists but shows only ellipses |
| `RegionRenderer.tsx` | Cluster territory polygons with biome colors | Exists but renderers are comment stubs |
| `EcosystemOverlay.tsx` | Overlay canvas for animated layers | Exists but runs empty animation loop |
| `VegetationRenderer` | Trees for posts (oak=pillar, birch=supporter, thorn=competitor, stump=dead weight) | **Deleted** |
| `GrassRenderer` | Background terrain texture per biome | **Deleted** |
| `RiverRenderer` | Internal link flow visualization between clusters | **Deleted** |
| `AnimalRenderer` | Creature icons for post roles (Bloomling, Rustmite, Fogling) | **Deleted** |
| `WeatherRenderer` | Weather overlays per cluster state | **Deleted** |
| `TerrainFeatureRenderer` | Mountains, valleys, paths | **Deleted** |

**What also exists (supporting components):**
| Component | Purpose | Status |
|---|---|---|
| `CreatureLegend.tsx` | Interactive legend explaining creature types | Exists |
| `OnboardingTour.tsx` | First-time user walkthrough of the landscape | Exists |
| `LandscapeTooltip.tsx` | Hover tooltip showing post/cluster details | Exists |
| `Minimap.tsx` | Overview minimap for large ecosystems | Exists |
| `LegendPanel.tsx` | Expanded legend panel | Exists |
| `TimelineSlider.tsx` | Historical view slider | Exists |
| `ContentPlannerOverlay.tsx` | Plan new content from the map | Exists |
| `EcosystemNarrative.tsx` | AI-generated narrative per cluster | Exists |

**V1 scope (launch):**
Restore the renderers that were already working. No new features. Specifically:
- Terrain textures (Forest=green, Meadow=yellow-green, Seedbed=light green, Swamp=brown, Desert=grey)
- Tree sprites for posts (size=traffic, height=word count, color=health, role=shape)
- Creature icons for post roles
- Health score badges on clusters
- Hover → tooltip with post title, URL, health, role
- Click → zoom to post, show recommendations

**NOT in V1:**
- Weather overlays, seasons, quests, achievements, competitor overlays
- Animated river flows (could restore if the code is straightforward)
- Sound effects (`useEcosystemSounds` hook exists but should stay disabled)

**Acceptance criteria for "done":**
- [ ] All 5 terrain biomes render with distinct visual textures
- [ ] Posts appear as tree sprites with size reflecting traffic volume
- [ ] Pillar, supporter, competitor, dead weight roles visually distinguishable
- [ ] Cluster health badges visible without hover
- [ ] Hover shows tooltip with: post title, URL, health score, role, word count
- [ ] Click zooms to post and shows action panel
- [ ] Pan and zoom works smoothly (trackpad and mouse)
- [ ] Minimap updates during navigation
- [ ] Performance: 60fps with 500 posts rendered
- [ ] First-time users see OnboardingTour
- [ ] Canvas animation loop is efficient (no work when idle)
- [ ] `ecosystem-preview.png` in repo can be used as reference for visual quality target

---

### 4.7 Intelligence Pipeline

**Purpose:** The backend engine that does all the analysis. Triggered on first crawl and on scheduled re-analysis.

**Current state:** Fully built and battle-tested on Close.com (958 posts, 22 clusters, 200 cann pairs, 724 recommendations, ~$7-8 cost, 20-25 min runtime).

**Pipeline stages (in order):**

| Stage | Service | API calls | Purpose |
|---|---|---|---|
| 1. Crawl | `sitemap.py` or `wordpress.py` | HTTP | Fetch sitemap.xml, download HTML, extract text via trafilatura |
| 2. Normalize | `normalizer.py` | None | Unified post representation, URL normalization, deduplication |
| 3. Embed | `embeddings.py` | OpenAI | text-embedding-3-small, 1536-dim, batches of 100, content-hash skip |
| 4. Weight | `weighted_embeddings.py` | None | Title 3x, headings 2x, first paragraph 1.5x, body 1x |
| 5. Cluster | `clustering.py` | Anthropic | UMAP + HDBSCAN, adaptive params, recursive sub-clustering |
| 6. Label | `fast_cluster_labels.py` | None | TF-IDF labeling (zero API calls) |
| 7. Intent | `fast_intent.py` + `claude_intent.py` | Anthropic (~10%) | Classify: informational/transactional/commercial/navigational |
| 8. Health | `health_scoring.py` | None | 6-factor composite: traffic, ranking, engagement, freshness, depth, technical |
| 9. Cannibalization | `cannibalization.py` | None | Cosine similarity + GSC query overlap, auto-calibrated thresholds |
| 10. Chunk cann | `chunk_cannibalization.py` | OpenAI | Section-level overlap confirmation |
| 11. Problems | `problem_detection.py` | None | Decay, thin, SEO, orphan, readability, velocity, AI readiness |
| 12. Recommendations | `fast_recommendations.py` + `recommendations.py` | Anthropic (~10%) | Template-based (~90%) + AI (~10%) |
| 13. PageRank | `pagerank.py` | None | Internal link graph authority via NetworkX |
| 14. AI citability | `ai_citability.py` | None | 4-dimension scoring |
| 15. Readability | `readability.py` | None | Flesch Reading Ease + Kincaid Grade Level |
| 16. Ecosystem visuals | `ecosystem_visuals.py` | None | Terrain, weather, creatures for visualization |
| 17. Ecosystem voice | `ecosystem_voice.py` | Anthropic | Nature-metaphor narrative summaries |

**Tiered AI strategy:**
~85-90% of work is done without API calls. API calls only when the free tier can't handle it:

| Task | Free tier | API tier |
|---|---|---|
| Intent classification | Regex/keywords (~85% accuracy) | Claude (~10% of posts) |
| Cluster labels | TF-IDF | Claude (fallback) |
| Recommendations | Templates (~90% coverage) | Claude (~10%) |
| Embeddings | Content-hash skip for unchanged | OpenAI (batch 100) |

**Cost model:**
- OpenAI embeddings: ~$0.02 per 100 posts (text-embedding-3-small)
- Anthropic calls: ~$2-5 per 500-post site (cluster labels, recommendations, oracle)
- Total per full pipeline run: ~$7-8 for a 1,000-post site

**Performance:**
- 958 posts: 20-25 minutes end-to-end
- Rate limiting: token-bucket for external API calls (configurable RPS)
- Content-hash change detection: re-analysis skips unchanged posts

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Pipeline lock is process-local | Critical | BE-1. Race condition with multiple workers. |
| N+1 queries in clustering, pagerank, problem detection | High | BE-4, BE-5, BE-6. Per-row updates/inserts in loops. |
| Two independent pipeline implementations | Medium | BE-20. `ingestion.py` and `intelligence.py` have different step ordering. |
| Class-level mutable state | Critical | BE-2. `ProblemDetector._first_detected_map` shared across requests. |
| Connection held across API calls | High | BE-10. Pool starvation during GA4/GSC sync. |
| TOCTOU on crawl start | High | BE-11. Double pipeline start possible. |

**Acceptance criteria for "done":**
- [ ] Pipeline lock is database-level (`pipeline_jobs` table with `status = 'running'` check)
- [ ] N+1 queries replaced with batch operations (`executemany` or VALUES CTE)
- [ ] Single pipeline orchestrator (consolidate the two implementations)
- [ ] `ProblemDetector._first_detected_map` is an instance attribute, not class attribute
- [ ] DB connections acquired only around writes, not held during API calls
- [ ] Pipeline idempotent: re-running produces the same results
- [ ] Pipeline resumable: if it crashes at step 8, re-run picks up from step 8

---

### 4.8 Cannibalization Detection

**Purpose:** Find pairs of posts competing for the same keywords. The highest-value insight for content teams.

**Current state:** Fully built. Two-signal approach.

**How it works:**
1. **Embedding cosine similarity** — auto-calibrated per site using distribution percentiles:
   - 85th percentile → low severity
   - 92nd percentile → medium severity
   - 97th percentile → high/critical severity
2. **GSC query overlap** — 3+ shared Google Search Console queries triggers detection
3. **Chunk-level confirmation** — section-level embeddings confirm exactly which parts overlap

**Performance optimization:** Clusters with 20+ posts use HNSW index pre-filtering (top-10 nearest neighbors) instead of O(n^2) pair scan.

**Filters:** Skips same-content-hash pairs (redirect issues), cross-language pairs.

**Frontend:** Cannibalization page shows pairs sorted by severity, with similarity scores, shared queries, and a network graph visualization (`NetworkGraph.tsx` using D3 force simulation).

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Missing unique constraint | Medium | BE-15. `ON CONFLICT (post_a_id, post_b_id)` has no backing constraint — inserts duplicates. |
| Unbounded query | High | BE-7. All pairs returned with no pagination. |

---

### 4.9 Oracle (Pre-Publish Checker)

**Purpose:** Before publishing a new post, check if it will cannibalize existing content.

**Current state:** Fully built. Backend service (`oracle.py`) + frontend panel (`OraclePanel.tsx`) + full page (`oracle/page.tsx`) + persistent FAB in dashboard layout.

**How it works:**
1. User enters draft text and/or target keyword
2. Backend generates embedding for the draft
3. Cosine similarity search against all existing post embeddings (HNSW index)
4. GSC keyword check for the target keyword
5. Claude generates a verdict: "safe to publish" / "potential conflict with [post X]" / "high risk — consider merging with [post Y]"
6. Returns similar posts with similarity scores and specific recommendations

**Rate limits:** 10/minute per user.

**Frontend:** Two access points:
- Full page at `/oracle` with input form and results display
- Slide-in panel via FAB button (available on all dashboard pages)

---

### 4.10 Recommendations & Actions

**Purpose:** Specific, actionable items the user can execute to improve their content. Not "improve this post" — more like "merge posts A and B, redirect A → B, use this meta description, expand to 2,400 words."

**Current state:** Fully built. Backend generates recommendations. Frontend displays them with filters, copy-to-clipboard, and status tracking.

**Recommendation types:**
- Merge/consolidate overlapping posts
- Update stale content (with specific refresh suggestions)
- Add internal links (with specific source → target pairs)
- Fix SEO issues (with the corrected meta description, title, etc.)
- Remove/redirect dead weight posts
- Add schema markup
- Improve readability

**Each recommendation includes:**
- Type, priority (critical/high/medium/low), effort estimate
- Specific before/after content (e.g., "Change meta description from X to Y")
- Affected post(s) with URLs
- Status tracking: pending → in_progress → completed → dismissed
- Impact estimate: expected traffic recovery

**Frontend features:**
- Filter by type, priority, status
- Copy meta descriptions / titles to clipboard
- Mark as completed / dismissed
- View per-post recommendations on post detail page
- Today view shows top 5 by priority

---

### 4.11 Consolidation Planning & Execution

**Purpose:** For swamp clusters with cannibalization, generate a specific merge plan with drafts and redirect maps.

**Current state:** Fully built. Backend (`consolidation.py`) generates plans. Frontend has list view and detail view.

**What a consolidation plan includes:**
- Target post (the one that survives)
- Source posts (the ones to merge into target)
- Content sections to merge (specific headings/paragraphs from each source)
- Redirect map (source URL → target URL for each merged post)
- Merged draft (Scale tier only — Claude writes the actual consolidated post)
- Quick win banner for obvious merges

**Frontend components:**
- `PlanCard.tsx` — overview of each consolidation plan
- `DraftViewer.tsx` — side-by-side view of the merged draft
- `RedirectMap.tsx` — visual redirect chain
- `QuickWinBanner.tsx` — highlights easy-win consolidations

---

### 4.12 Content Problems & Issues

**Purpose:** Systematic detection of content health issues across the entire blog.

**Current state:** Fully built.

**Problem categories:**
| Category | Signals |
|---|---|
| Content decay | Click decline >30%, position drop >5, stale >365 days |
| Thin content | <300 words, below cluster average, high bounce |
| SEO issues | Missing meta, title length, no headings/links/images |
| Orphan content | Zero internal inbound links |
| Readability | Flesch score <40 (too complex) |
| Publishing velocity | Slowdown detection |
| AI readiness | Citability, E-E-A-T, schema, extraction scores |

**Frontend:** Issues page shows problems grouped by type and severity with post links.

---

### 4.13 Analytics & Overview

**Purpose:** Traffic, ranking, and engagement trends from GA4 and GSC data.

**Current state:** Built but the overview page shows **synthetic/fake data** generated with `Math.random()`, presented as real analytics without a disclaimer.

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Fake data displayed as real | Medium | FE-11. `Math.random()` in `useMemo` creates SSR hydration mismatch. Charts show fabricated trends. |
| No disclaimer | Medium | User sees "Traffic Trend" chart with random data and assumes it's real. |

**Acceptance criteria for "done":**
- [ ] Overview page shows real GA4/GSC data when connected
- [ ] Shows clear "Connect Google Analytics to see real data" state when GA4 not connected
- [ ] No `Math.random()` in any chart data
- [ ] SSR-safe rendering (no hydration mismatches)

---

### 4.14 Impact Tracking

**Purpose:** After completing a recommendation (e.g., merging two posts), track whether it actually improved traffic, rankings, and engagement.

**Current state:** Built. Backend service (`impact_tracking.py`, `impact_tracker.py`) + frontend components (`ImpactCard`, `ImpactTimeline`, `ShareableCard`, `TrafficChangeChart`).

**How it works:**
1. User marks a recommendation as completed
2. System snapshots current traffic/ranking metrics for affected posts
3. Over the next 30/60/90 days, compares against the snapshot
4. Shows before/after traffic, ranking position, engagement metrics
5. `ShareableCard` generates a visual card the user can share (proof of ROI)

---

### 4.15 Billing & Subscriptions

**Purpose:** Stripe-powered subscription management.

**Current state:** Built. Backend (`stripe_service.py`) handles checkout, portal, webhooks. Frontend has upgrade, manage, and cancel flows.

**Backend features:**
- Checkout session creation
- Customer portal redirect
- Webhook handling (subscription.created, updated, deleted, payment_failed)
- Winback email sequence (day 7, 14, 30 after cancellation)

**Frontend features:**
- Plan cards with features and pricing
- Usage meter (posts analyzed / limit)
- Invoice history
- Cancel flow with retention offers (downgrade, pause, feedback)
- Upgrade/downgrade between tiers

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Wrong prices everywhere | Critical | Shows $99/$249. Must be $149/$349. |
| Feature lists disagree | High | Landing page and billing page show different features per tier. |
| `success_url`/`cancel_url` not validated | Critical | SEC-3. Open redirect via Stripe checkout. |
| `price_id` no allowlist | High | SEC-11. Arbitrary Stripe price subscription. |
| Checkout errors not shown to user | High | FE-8. `console.error` only. |
| Retention offer references wrong price | Medium | Says "downgrade to Growth at $99/mo." |
| Two `PLANS` constants | Low | Landing page and billing page have independent copies. |
| Stale pricing in winback emails | Critical | BE-3. Hardcodes $99/month. |

**Acceptance criteria for "done":**
- [ ] Single source of truth for plan data (`lib/plans.ts` or equivalent)
- [ ] All prices updated: Growth $149/mo, Scale $349/mo
- [ ] Annual: Growth $1,490/yr, Scale $3,490/yr
- [ ] `success_url` and `cancel_url` validated against `settings.frontend_url`
- [ ] `price_id` validated against known IDs from settings
- [ ] Checkout/portal errors shown to user via toast
- [ ] Retention offer prices corrected
- [ ] Winback email prices corrected
- [ ] Drip email prices corrected

---

### 4.16 Email & Notifications

**Purpose:** Transactional email (drip sequence, weekly digest, winback) via Resend.

**Current state:** Backend services built (`drip_sequence.py`, `weekly_report.py`, `stripe_service.py` winback). Frontend unsubscribe page exists.

**Email types:**
| Email | Trigger | Purpose |
|---|---|---|
| Drip 1 (day 0) | Free audit request | PDF attachment + key findings |
| Drip 2 (day 2) | Cron | "Here's what you're missing" — paywalled insights |
| Drip 3 (day 5) | Cron | Urgency + discount code |
| Weekly digest | Cron (weekly) | Health changes, new problems, completed actions |
| Winback day 7 | 7 days after cancel | "We miss you" + 30% discount |
| Winback day 14 | 14 days after cancel | Feature highlights |
| Winback day 30 | 30 days after cancel | Last chance offer |

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| Drip email prices wrong | Critical | BE-3. $99/month hardcoded. |
| Winback prices wrong | Critical | $99 and $69 (COMEBACK30) hardcoded. |
| `_send_email_1` no error handling | High | BE-14. Network error = 500 to caller. |
| Unsubscribe fires immediately | Medium | FE-12. No confirmation step. |
| `email` param no validation | Medium | SEC-14. Raw string stored in DB. |
| Opt-out check is N+1 | Medium | BE-19. One query per drip row. |
| Duplicate send risk | Low | BE-23. Race between `schedule_drip` and cron. |

---

### 4.17 Google Integration (GA4 & GSC)

**Purpose:** Pull Google Analytics 4 and Google Search Console data to enrich health scoring, detect decay, and identify cannibalization via query overlap.

**Current state:** Built. Backend OAuth flow (`google_auth.py`, `google_integration.py`), GA4 sync (`ga4.py`, `ga4_sync.py`), GSC sync (`gsc.py`, `gsc_sync.py`). Frontend settings page has "Connect Google" button.

**Data pulled:**
- **GA4:** Daily pageviews, sessions, avg engagement time, conversions, bounce rate per post
- **GSC:** Daily query, impressions, clicks, avg position, CTR per post per query

**Issues to fix:**
| Issue | Severity | Detail |
|---|---|---|
| OAuth callback has no auth | Critical | SEC-1. Token injection vulnerability. |
| No ownership check on token storage | High | SEC-8. `UPDATE sites SET google_tokens WHERE id = $2` — no `AND user_id`. |
| Raw exception in 500 response | High | SEC-9. Leaks internal error details. |
| Connection held during API sync | High | BE-10. Pool starvation. |

---

### 4.18 PDF Reports

**Purpose:** Generate downloadable/emailable PDF audit reports. Free (lead gen) and paid (full detail) variants.

**Current state:** Built (`pdf_report.py`, `audit_report.py`).

**Free report:** Health score, cluster count, cann pair count, top 5 problems (type only, not fixes).
**Paid report:** Everything above plus specific pairs, recommendations, consolidation plans, full health breakdown.
**Scale tier:** White-label option (client's branding instead of Enough branding).

---

### 4.19 Content Briefs

**Purpose:** Generate a content brief for a new topic based on the site's existing content ecosystem.

**Current state:** Backend service built (`content_briefs.py`). Frontend page exists at `/briefs`.

**How it works:**
1. User enters a topic or selects a content gap from the Today view
2. Backend analyzes existing coverage, identifies gaps, checks for potential cannibalization
3. Generates a brief with: target keyword, suggested title, outline, word count target, internal linking suggestions, differentiation points vs. existing content

**Tier limits:** Growth: 5 briefs/month. Scale: unlimited.

---

### 4.20 Additional Features

**Content Wrapped (`/wrapped`):** Weekly summary card showing actions taken, health changes, content published. Shareable to social media (LinkedIn-optimized).

**Competitors (`/competitors`):** Compare your ecosystem health against a competitor domain. Backend (`competitor_compare.py`) exists. This is post-launch — the comparison only works if the competitor's blog has been crawled.

**Calendar (`/calendar`):** Publishing calendar view (`calendar_restraint.py`). Shows when posts were published and suggests optimal publishing cadence.

**Explore (`/explore`):** Tabbed explorer combining clusters, posts, landscape, cannibalization, recommendations, and consolidation views into one searchable interface.

---

## 5. User Journeys

### 5.1 Journey A: Visitor → Free Audit → Paid Subscriber

```
1. Visitor lands on enough.app (source: organic, Indie Hackers, r/SEO, cold DM)
2. Reads hero: "See your content health score... in your inbox in 25 minutes. Free."
3. Enters blog URL + email → clicks "Get Your Free Audit"
4. Backend: creates anonymous site, crawls 50 posts, runs abbreviated pipeline
5. Visitor sees: "Check your inbox in 20-25 minutes"
6. 20-25 minutes later: PDF arrives in email
7. PDF shows: Health Score 43/100, 12 cannibalization pairs, 5 critical problems
8. PDF does NOT show: which specific posts, what to do about them
9. CTA in PDF: "See the full analysis — subscribe to Enough"

10. Day 0 — Drip email 1: "Your blog has 12 posts fighting each other. Here's what you're missing."
11. Day 2 — Drip email 2: "Post A and Post B are 87% similar. Here's exactly how to fix it. (Subscribe to see all 12 pairs.)"
12. Day 5 — Drip email 3: "Last chance: your cannibalization pairs are actively costing you traffic."

13. User clicks → signup → pays $149/month (30-day money-back guarantee)
14. → Onboarding flow (Journey B begins)
```

**Conversion metrics to track:** Landing page → audit request rate, audit request → email open rate, email open → click rate, click → signup rate, signup → paid rate.

### 5.2 Journey B: New Subscriber → First "Wow" Moment

```
1. Signup complete → redirected to /onboarding
2. URL already pre-filled if they did the free audit (same domain)
3. Select CMS type (auto-detected if possible) → click "Analyze"
4. Watch pipeline progress:
   - 🕷️ "Crawling posts..." (education: "We're downloading every page...")
   - 🧠 "Understanding content..." (education: "Each post gets a 1,536-dimension fingerprint...")
   - 🔬 "Scoring health..." (education: "We score on 6 factors...")
   - 🗂️ "Clustering topics..." (education: "Posts grouped by similarity...")
   - ✦ "Building recommendations..." (education: "Prioritizing what to fix first...")
5. Early findings appear during pipeline: "42 posts found... 6 clusters detected... 8 cann pairs..."
6. Pipeline complete → redirect to /landscape (the "wow" moment)

7. ★ THE WOW MOMENT ★
   User sees their blog as a living ecosystem map:
   - Green forests (healthy clusters)
   - Brown swamps (cannibalized clusters)
   - Grey deserts (dead content)
   - Trees representing each post (size = traffic, health = color)
   - Health score badge on each cluster

8. User clicks a sick tree in a swamp → tooltip shows:
   "How to Set Up OAuth — 87% similar to 'OAuth Integration Guide'"
   "Recommendation: Merge these posts. Click to see the consolidation plan."

9. User navigates to /today → sees priority action card:
   "Merge 'How to Set Up OAuth' and 'OAuth Integration Guide' — 87% similar, splitting 450 visits/month"
   [Copy meta description] [View consolidation plan] [Mark as done]

10. User copies the meta description, opens their CMS, pastes it → marks as done
11. → Impact tracking begins. Day 30 email: "Your merged post gained +120 visits/month."
```

**Key metric:** Time from signup to first "wow" moment = pipeline runtime (20-25 min). This is irreducible (API calls take time). The education text during the wait is critical to prevent abandonment.

### 5.3 Journey C: Returning User → Daily Check-in

```
1. User opens enough.app → lands on /today (daily command center)
2. Sees: "Since your last visit: 2 new issues, 1 ranking change, 1 recommendation completed"
3. Sees: Health score 52/100 (+2 from last week)
4. Sees: ROI card — "4 actions completed, +340 visits/mo recovered, $680/mo estimated value"
5. Sees: Top priority action — "Update 'API Best Practices' (stale 400 days, ranking dropped from #4 to #12)"
6. Expands the action card → sees specific refresh suggestions with copy buttons
7. Takes action in their CMS
8. Returns to Enough → marks as done
9. Health score updates on next re-analysis (weekly for Growth, daily for Scale)
10. Visits /landscape to see how the ecosystem has changed
```

**Key metric:** DAU/MAU ratio. Target: >30% (user opens Enough at least 2x/week).

---

## 6. Pricing & Tier Specification

### 6.1 Tier comparison (AUTHORITATIVE — all other sources must match this)

| | Growth | Scale | Enterprise |
|---|---|---|---|
| **Monthly price** | $149/mo | $349/mo | Custom ($600+/mo) |
| **Annual price** | $1,490/yr ($124.17/mo) | $3,490/yr ($290.83/mo) | Custom |
| **Sites** | 1 | 3 | Unlimited |
| **Posts** | 500 | 2,000 | Unlimited |
| **Intelligence pipeline** | Full | Full | Full |
| **Re-analysis cadence** | Weekly | Daily | Daily |
| **Weekly email digest** | Yes | Yes | Yes |
| **Oracle (pre-publish checker)** | Yes | Yes | Yes |
| **GSC & GA4 integration** | Yes | Yes | Yes |
| **RAG-enhanced recommendations** | Yes | Yes | Yes |
| **Impact tracking** | Yes | Yes | Yes |
| **PDF reports** | Yes | Yes | Yes |
| **Content briefs** | 5/month | Unlimited | Unlimited |
| **Consolidation drafts** | No | Yes (Claude writes the merged post) | Yes |
| **White-label reports** | No | Yes | Yes |
| **Priority pipeline** | No | Yes (runs first in queue) | Yes |
| **API access** | No | Yes | Yes |
| **Dedicated support** | No | No | Yes |
| **Custom integrations** | No | No | Yes |
| **SLA** | No | No | Yes |

### 6.2 Free tier

There is no free tier. The free audit report (URL + email → crawl 50 posts → PDF) is the lead magnet, not a tier. It shows problems but not fixes.

### 6.3 Money-back guarantee

30-day money-back guarantee instead of a free trial. Every pipeline run costs $1-3 in API spend, so free trials attract tire-kickers who consume resources without converting.

### 6.4 Places where pricing appears (must all be updated)

| Location | Current price | File |
|---|---|---|
| Landing page | $99/$249 | `frontend/src/app/page.tsx:54-89` |
| Billing page | $99/$249 | `frontend/src/app/(dashboard)/billing/page.tsx:48-81` |
| Retention offer (downgrade) | $99 | `frontend/src/app/(dashboard)/billing/page.tsx:103` |
| Drip email 1 | $99 | `backend/app/services/drip_sequence.py:351` |
| Winback email | $99 + $69 (COMEBACK30) | `backend/app/services/stripe_service.py:583` |
| Stripe dashboard | (must match) | External: stripe.com |

---

## 7. Technical Architecture

### 7.1 Stack

```
Frontend:  Next.js 14 (App Router) + React 18 + Tailwind + SWR + D3/Canvas + Supabase Auth
Backend:   FastAPI + asyncpg + Pydantic + slowapi
Database:  PostgreSQL 16 + pgvector (1536-dim HNSW index)
AI:        OpenAI (embeddings) + Anthropic Claude (labels, recs, oracle, drafts)
Payments:  Stripe (checkout, portal, webhooks)
Auth:      Supabase Auth (JWT + Google OAuth + magic links)
Email:     Resend (transactional email)
Infra:     Docker Compose (postgres + backend + frontend)
Monitoring: Sentry (frontend + backend)
```

### 7.2 Codebase size

| Area | Lines | Files |
|---|---|---|
| Backend Python | ~38,000 | 78 files |
| Frontend TypeScript | ~22,000 | 120 files |
| Migrations SQL | ~2,000 | 27 files |
| **Total** | **~62,000** | **225 files** |

### 7.3 Key architecture decisions

| Decision | Rationale |
|---|---|
| asyncpg over SQLAlchemy | Raw performance for embedding operations; no ORM overhead |
| pgvector in-database | Single database simplicity; avoids separate vector DB |
| BackgroundTasks over Celery | Simpler deployment; pipeline jobs tracked in DB for resilience |
| SWR over React Query | Lighter weight; stale-while-revalidate fits dashboard patterns |
| Tiered AI (free → API) | ~85-90% without API calls; significant cost savings |
| Canvas over SVG | Performance at 1000+ posts rendered simultaneously |
| Supabase over custom auth | Reduced auth surface; built-in RLS for multi-tenancy |

### 7.4 External services

| Service | Usage | Cost model |
|---|---|---|
| Supabase | Auth, database hosting (production) | Free tier sufficient for early users |
| OpenAI | text-embedding-3-small | ~$0.02 per 100 posts |
| Anthropic | Claude Sonnet — labels, recs, oracle, drafts | ~$2-5 per pipeline run |
| Stripe | Billing | 2.9% + $0.30 per transaction |
| Resend | Email | Free tier: 100 emails/day |
| Sentry | Error monitoring | Free tier: 5K errors/month |

### 7.5 Database schema (core tables)

```
profiles           → User profiles (linked to Supabase auth.users)
sites              → CMS sites (1 per Growth, 3 per Scale)
posts              → Normalized content (title, url, body_text, content_hash, x_pos, y_pos)
post_embeddings    → pgvector 1536-dim vectors
internal_links     → Post-to-post link graph
clusters           → Topic groups with ecosystem_state
post_clusters      → Many-to-many post↔cluster
cannibalization_pairs → Overlapping content pairs
post_health_scores → 6-factor composite scores
content_problems   → Detected issues
recommendations    → Actionable items with status tracking
ga4_metrics        → Daily GA4 data per post
gsc_metrics        → Daily GSC data per post per query
crawl_jobs         → Crawl state tracking
pipeline_jobs      → Pipeline execution log
email_optouts      → Unsubscribed emails
audit_drip_emails  → Drip sequence state
winback_emails     → Cancellation winback state
```

Full schema details in `ARCHITECTURE.md`. 27 sequential SQL migration files in `backend/migrations/`.

---

## 8. Lead Generation & GTM Infrastructure

### 8.1 Infrastructure already built

| Component | Status | Notes |
|---|---|---|
| Landing page with audit CTA | Built | Needs pricing fix |
| Free audit endpoint | Built | Needs security hardening (SEC-2) |
| PDF report generator | Built | Works |
| 3-email drip sequence | Built | Needs pricing fix |
| Winback email sequence | Built | Needs pricing fix |
| Unsubscribe page | Built | Needs confirmation step |
| Stripe checkout | Built | Needs URL validation |
| Stripe webhook handler | Built | Works |

### 8.2 Go-to-market plan

**Phase 1 — Validation (weeks 1-4):**
- Run 30 blogs through the pipeline
- DM each founder/content lead with one specific finding: "Your posts [A] and [B] are 87% similar and splitting your traffic"
- Take 4-6 calls. Share screen. Ask "would you pay $149/month for this?"
- Their reaction tells you everything

**Phase 2 — Content-led launch (weeks 4-8):**
- Post the Close.com analysis on r/SEO, Indie Hackers, Twitter, LinkedIn
- One "I analyzed [famous blog]" post per week for 10 weeks
- Build in public on Indie Hackers (23.1% conversion rate vs Product Hunt's 3.1%)

**Phase 3 — Product Hunt + outbound (weeks 8-12):**
- Product Hunt launch
- Free audit funnel live
- 5 cold DMs per day with specific findings
- Agency partnership outreach (Scale tier)

**Budget:** $0 for first 3 months except API costs (~$7-8 per pipeline run).

---

## 9. 90-Day Roadmap

### Phase 1: Stabilize (Weeks 1-2)

**Goal:** Fix critical bugs, get the dev environment working, make the product deployable.

| # | Task | Severity | Effort |
|---|---|---|---|
| 1 | Fix dev environment (Python venv, install deps, ruff, Docker) | Blocker | 2h |
| 2 | Fix 5 security criticals (SEC-1 through SEC-5) | Critical | 1d |
| 3 | Fix pricing everywhere (landing, billing, drip, winback, retention) | Critical | 2h |
| 4 | Fix actions page compile error (duplicate import) | Critical | 5min |
| 5 | Wire ErrorBoundary into dashboard layout | Critical | 15min |
| 6 | Fix auth middleware to match actual routes | Critical | 30min |
| 7 | Fix pipeline race condition (database-level lock) | Critical | 2h |
| 8 | Fix `ProblemDetector` class-level state | Critical | 15min |
| 9 | Fix N+1 queries (clustering, pagerank, problem detection) | High | 4h |
| 10 | Fix unbounded queries (add pagination) | High | 2h |
| 11 | Fix Google OAuth callback (auth + ownership check) | Critical | 1h |
| 12 | Fix overview page (remove fake data, show real or "connect GA4" state) | Medium | 1h |
| 13 | Remove fabricated social proof from landing page | High | 15min |

**Exit criteria:** `make lint && make test && make build` all pass. No critical security vulnerabilities. Product deploys to staging.

### Phase 2: Restore & Validate (Weeks 3-6)

**Goal:** Restore the landscape visualization, deploy to production, validate with 30 real blogs.

| # | Task | Effort |
|---|---|---|
| 14 | Restore landscape renderers from git history | 2-3d |
| 15 | End-to-end test: signup → pay → crawl → see results | 1d |
| 16 | Deploy to production (Supabase + Vercel/Fly.io + managed Postgres) | 1d |
| 17 | Configure Resend (SPF/DKIM/DMARC for enough.app domain) | 2h |
| 18 | Run 30 blogs through the pipeline (validation batch) | 3d |
| 19 | DM 30 founders/content leads with specific findings | 1w |
| 20 | Take 4-6 calls, gather feedback | 1w |
| 21 | Fix remaining high-severity AUDIT.md items | 2d |

**Exit criteria:** Landscape visualization works. 30 blogs analyzed. 4+ user calls completed. First paying customer (or clear signal to pivot).

### Phase 3: Launch (Weeks 7-12)

**Goal:** Public launch. Content marketing. First 10 paying customers.

| # | Task | Effort |
|---|---|---|
| 22 | Write Close.com case study blog post | 1d |
| 23 | Post to r/SEO, Indie Hackers, Twitter, LinkedIn | 1d |
| 24 | Enable free audit funnel on landing page | 1d |
| 25 | Build-in-public posts on Indie Hackers (weekly) | Ongoing |
| 26 | Product Hunt launch | 1d |
| 27 | 5 cold DMs per day with specific findings | Ongoing |
| 28 | Agency partnership outreach (Scale tier) | Ongoing |
| 29 | Fix medium-severity AUDIT.md items based on user feedback | Ongoing |
| 30 | Make repo private | 5min |

**Exit criteria:** 10 paying customers. $1,490+ MRR. Positive unit economics (LTV > CAC).

---

## 10. Success Metrics & KPIs

### 10.1 Product metrics

| Metric | Target | How measured |
|---|---|---|
| Free audit → signup | >5% | Drip email click → signup tracking |
| Signup → paid | >30% | Stripe webhook + Supabase auth |
| 30-day retention | >60% | Monthly active subscription rate |
| DAU/MAU | >30% | Frontend analytics (page views per user) |
| Time to first "wow" | <30 min | Pipeline completion time |
| Pipeline success rate | >95% | `pipeline_jobs` completion rate |
| NPS | >40 | Post-onboarding survey (add later) |

### 10.2 Business metrics

| Metric | 90-day target |
|---|---|
| MRR | $1,490+ (10 Growth customers) |
| Paying customers | 10+ |
| Churn rate | <10% monthly |
| CAC | <$50 (organic/content-led) |
| Pipeline cost per run | <$10 |
| Support tickets per customer | <2/month |

### 10.3 Technical metrics

| Metric | Target |
|---|---|
| Pipeline runtime (500 posts) | <25 minutes |
| API response time (p95) | <500ms |
| Landscape render (500 posts) | 60fps |
| Uptime | >99.5% |
| Error rate | <1% of requests |

---

## 11. Open Questions & Decisions Needed

### Q1: Should onboarding require payment first?

**Current:** Signup → onboarding → pipeline runs → paywall at dashboard.
**Alternative:** Signup → paywall → onboarding → pipeline runs.

**Trade-off:** Current flow lets users see value before paying (higher conversion). But if they don't convert, you've spent ~$7 in API costs for nothing. At 30% signup→paid conversion, 70% of pipeline runs are wasted = ~$5 per non-converting user.

**Recommendation:** Keep current flow but add a cost cap. Track the ratio of "pipeline completed but never paid" users. If it exceeds 80%, switch to payment-first.

### Q2: Multi-seat / team support?

The codebase has no multi-user support. Each account is single-seat. Is this intentional for V1? Agency Alex might want to invite a client to view their report.

**Recommendation:** Single-seat for V1. Add "share read-only link" for Scale tier in Phase 3 if agencies request it.

### Q3: Re-analysis trigger — cron only or manual too?

The Today view has a "Re-analyze" button. The `steward.py` service exists for scheduled re-analysis. How should these interact?

**Recommendation:** Both. Manual re-analyze button triggers immediately. Cron runs weekly (Growth) or daily (Scale) automatically. Manual trigger resets the cron timer.

### Q4: Demo mode — keep or remove?

`demo/page.tsx` exists. `AuthProvider` has a demo mode bypass. Useful for sales calls but a security surface.

**Recommendation:** Keep but gate behind a specific env var (`DEMO_SITE_ID`). Demo mode should show a pre-loaded site with real data, not bypass auth entirely.

### Q5: Enterprise tier — build now or later?

The PRD lists Enterprise ($600+/mo) but no infrastructure exists for custom pricing, SSO, or SLAs.

**Recommendation:** Don't build. Add a "Contact us" button on the pricing page. If someone clicks it, manually negotiate. Build Enterprise infrastructure only after 3+ Enterprise inquiries.

### Q6: Content Wrapped — is this a launch feature?

`/wrapped` exists. It generates a weekly shareable card (LinkedIn-optimized). This is a growth hack (users share → their network sees Enough branding).

**Recommendation:** Keep for launch. Low effort (already built), high potential virality. Just needs correct data (currently may use placeholder data).

### Q7: What is the single source of truth for plan limits?

Currently, plan limits (500 posts, 1 site for Growth; 2,000 posts, 3 sites for Scale) are enforced in multiple places with no shared constant. Should limits be:
- Hardcoded in frontend and backend separately?
- Stored in Stripe metadata and read at runtime?
- Defined in a shared config file?

**Recommendation:** Define in `backend/app/config.py` as settings. Frontend reads from a `/v1/plans` endpoint that returns the limits. Single source of truth in the backend.

---

## 12. Known Issues & Technical Debt

See `AUDIT.md` for the complete list of 65 issues with exact file paths, line numbers, and fix instructions.

**Summary:**

| Severity | Count | Key items |
|---|---|---|
| Critical | 15 | Security vulnerabilities (auth bypass, open redirects, API cost abuse), broken landscape, wrong pricing, compile error |
| High | 20 | N+1 queries, unbounded queries, race conditions, missing indexes, silent error swallowing |
| Medium | 18 | Bare excepts, fake data, inline strings, timer leaks, missing validation |
| Low | 12 | Duplicate constants, missing aria-labels, hardcoded heuristics |

**Priority order for fixing:**
1. Security criticals (SEC-1 through SEC-5)
2. Dev environment setup
3. Compilation blockers (FE-5)
4. Auth middleware (FE-1)
5. Pricing (FE-2, BE-3)
6. Landscape restoration (FE-3)
7. ErrorBoundary (FE-4)
8. N+1 queries (BE-4 through BE-6)
9. Everything else by severity

---

## Appendix A: File Reference

**Key files for any Claude Code session:**

| File | Purpose |
|---|---|
| `CLAUDE.md` | Root config — loaded every session |
| `backend/CLAUDE.md` | Backend-specific context |
| `frontend/CLAUDE.md` | Frontend-specific context |
| `ARCHITECTURE.md` | Full technical architecture |
| `ECOSYSTEM-BIBLE.md` | Visualization spec and gamification vision |
| `PRD.md` | This document — product requirements |
| `AUDIT.md` | 65 issues with file paths and fix instructions |
| `.claude/settings.json` | Hooks, permissions, LSP toggle |

**When starting a new Claude Code session, load this PRD for product context and AUDIT.md for known issues.**

---

## Appendix B: Data Inconsistencies Found During Audit

These inconsistencies exist in the current codebase and must be resolved:

| Item | Location A | Location B | Discrepancy |
|---|---|---|---|
| Growth monthly price | Landing page: $99 | Founder says: $149 | Landing page wrong |
| Scale monthly price | Landing page: $249 | Founder says: $349 | Landing page wrong |
| Scale sites limit | Billing page: "Up to 10 sites" | Founder says: 3 sites | Billing page wrong |
| Scale posts limit | Billing page: "Up to 5,000 posts" | Founder says: 2,000 posts | Billing page wrong |
| Growth features | Landing page: 10 features | Billing page: 7 features | Different feature lists |
| Blogs analyzed | Landing page: "1,247 blogs analyzed" | Founder says: 0 users | Fabricated |
| Drip email price | Backend: "$99/month" | Founder says: $149 | Backend wrong |
| Winback discount | Backend: "$69/month (COMEBACK30)" | Should be: 30% off $149 = $104.30 | Backend wrong |
| Retention offer | Billing page: "downgrade to Growth at $99/mo" | Should be: $149/mo | Frontend wrong |

**All locations must be updated to match Section 6 (Pricing & Tier Specification) of this PRD.** Section 6 is the single source of truth for pricing.
