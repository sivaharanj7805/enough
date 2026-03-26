# Enough — Product Guide

**What it is:** A content intelligence platform that finds cannibalization, decay, and dead weight in B2B SaaS blogs — and tells you exactly what to fix. The only tool that covers both traditional SEO health and AI readiness in one place.

**Who it's for:** Content marketers and SEO leads at B2B SaaS companies with 100-500 blog posts. Secondary: agencies managing 5-15 client blogs.

**What it costs:** $149/month Growth (1 site, 500 posts). $349/month Scale (3 sites, 2,000 posts, white-label). 30-day money-back guarantee. No free tier.

---

## Readiness Legend

This document describes the actual codebase as of 2026-03-23. Every feature is tagged with its real status:

| Tag | Meaning |
|-----|---------|
| **VERIFIED** | Code exists, security-audited, logic confirmed by reading the actual implementation |
| **BUILT, NOT E2E TESTED** | Code exists and compiles, but no end-to-end test has been run with real user data in production. May have edge cases. |
| **NEEDS INFRA** | Code is complete but requires infrastructure setup (hosting, DNS, Stripe price IDs, env vars) before it can run |
| **STUB** | Page or endpoint exists but shows placeholder content ("Coming Soon") or returns minimal data |
| **NOT BUILT** | Documented as a future feature — no code exists |

**Bottom line:** All backend services (47 files, 16,661 lines) are real implementations — zero stubs. All security vulnerabilities found in the March 2026 audit have been fixed and verified against the actual code. The product has never been deployed to production or tested with real paying users.

---

## Table of Contents

1. [How a visitor becomes a customer](#1-how-a-visitor-becomes-a-customer)
2. [Authentication and accounts](#2-authentication-and-accounts)
3. [Onboarding — first 25 minutes](#3-onboarding--first-25-minutes)
4. [The intelligence pipeline — what happens behind the scenes](#4-the-intelligence-pipeline--what-happens-behind-the-scenes)
5. [The dashboard — what users see every day](#5-the-dashboard--what-users-see-every-day)
6. [The ecosystem visualization — the core differentiator](#6-the-ecosystem-visualization--the-core-differentiator)
7. [Taking action — recommendations, consolidation, and the Oracle](#7-taking-action--recommendations-consolidation-and-the-oracle)
8. [AI readiness and GEO scoring](#8-ai-readiness-and-geo-scoring)
9. [Google integrations — GA4 and Search Console](#9-google-integrations--ga4-and-search-console)
10. [Email system — drip, weekly digest, winback](#10-email-system--drip-weekly-digest-winback)
11. [PDF reports — free audit and paid reports](#11-pdf-reports--free-audit-and-paid-reports)
12. [Billing and subscriptions](#12-billing-and-subscriptions)
13. [Background jobs and automated maintenance](#13-background-jobs-and-automated-maintenance)
14. [Architecture and technology](#14-architecture-and-technology)
15. [Data model — what's stored and where](#15-data-model--whats-stored-and-where)
16. [Security model](#16-security-model)
17. [What doesn't exist yet](#17-what-doesnt-exist-yet)

---

## 1. How a visitor becomes a customer

> Status: **BUILT, NOT E2E TESTED.** All code exists. Backend generates PDFs, sends emails via Resend, runs the abbreviated pipeline. Never tested end-to-end with a real email landing in a real inbox from production infrastructure.

### The free audit funnel

A visitor lands on `enough.app`. The landing page has a single form: **blog URL + email address**. They click "Get Free Audit + AI Score."

**What happens behind the scenes:**
1. The frontend POSTs to `/v1/sites/audit-report/pdf` with the URL and email
2. The backend extracts the domain, checks if this domain has been analyzed before
3. **If new domain:** Creates an anonymous site (no user account needed, `user_id = NULL`), crawls the first 50 posts, runs an abbreviated pipeline (crawl → embed → cluster → health → cannibalization → problems → AI citability), generates a PDF, and emails it. Returns HTTP 202 — the frontend shows "Check your inbox in 20-25 minutes."
4. **If already analyzed:** Generates the PDF immediately from cached data and returns it as a download (HTTP 200)
5. Either way, the email is enrolled in a 3-email drip sequence

**Rate limits:** 3 audits per email per day, 6 per IP per minute.

### The drip sequence

Three emails designed to convert the free audit lead into a paying customer:

| Email | When | Subject | Content |
|-------|------|---------|---------|
| 1 | Immediately (day 0) | "Your blog is fighting itself — here's the proof" | PDF attached. Key findings: health score, cann pair count, top problems. CTA: subscribe to see the full analysis. |
| 2 | Day 2 | "{domain}: this one fix could recover {traffic} visits/mo" | Shows one specific recommendation with difficulty badge and estimated traffic impact. Paywalled details. |
| 3 | Day 5 | "Your blog is still fighting itself" | Urgency. Score colored by severity. $149/month CTA with 30-day money-back guarantee. |

All user data in emails is HTML-escaped to prevent injection. Unsubscribe links point to `/unsubscribe?email=...`.

---

## 2. Authentication and accounts

> Status: **VERIFIED.** JWT validation, HMAC-signed OAuth state, UUID fallback gated behind `environment != "production"`, Supabase integration — all confirmed by reading `dependencies.py`, `auth.py`, `google_integration.py`. **NEEDS INFRA** for production (Supabase project, Google OAuth credentials, env vars).

### Sign up options

Users create accounts via Supabase Auth. Three methods:

1. **Email + password** — Password requires 8+ characters, uppercase, lowercase, and a number. Frontend shows a strength meter.
2. **Google OAuth** — Uses Supabase's Google provider. One-click signup.
3. **Magic link** — User enters email, receives a login link. No password needed.

After signup, the user is redirected to `/onboarding`.

### Sign in options

Same three methods. Login page has a left panel showing Close.com case study stats (958 posts analyzed, 200+ cann pairs detected) as social proof.

If a session expires, the frontend middleware redirects to `/login?redirectTo={current_path}` and returns the user to where they were after login.

### Session management

- Supabase manages JWT tokens with automatic refresh
- The backend validates JWTs using the Supabase JWT secret (HS256 algorithm, expiry verified)
- A UUID-based dev fallback exists but is gated behind `environment != "production"` — it cannot fire in production
- Frontend stores the Supabase session in cookies (set by `@supabase/ssr`)
- A manual token fallback stores tokens in localStorage for edge cases (demo mode)

### Demo mode

Setting `NEXT_PUBLIC_DEMO_MODE=true` bypasses Supabase entirely and uses a hardcoded test user. This is for development only.

### Account deletion

Users can delete their account via `DELETE /v1/auth/account`. This removes all sites, posts, clusters, recommendations, and pipeline data. Irreversible.

### What doesn't exist

- **Teams / collaboration** — Enough is single-user per account. There are no team invitations, shared workspaces, roles, or permissions. Each account owns its sites independently.
- **SSO / SAML** — Enterprise auth is not implemented.
- **Multi-user per site** — A site belongs to one user. There's no way to share a site's dashboard with colleagues.

---

## 3. Onboarding — first 25 minutes

> Status: **BUILT, NOT E2E TESTED.** Frontend form, pipeline polling, progress display, resume-on-return — all code exists. Pipeline runs 17 stages sequentially. **Known issue:** pipeline marks "completed" even if individual stages fail silently (errors are logged but execution continues). A user could see partial/missing data and not know why.

After signup and payment, the user lands on `/onboarding`. Here's what happens:

### Step 1: Enter your blog

The user provides:
- **Blog URL** (required) — validated as a proper URL
- **CMS type** — WordPress (REST API) or Sitemap (universal XML sitemap crawler)
- **Site name** (optional)
- **Sitemap URL** (optional, auto-discovered if not provided)
- **URL patterns** (optional) — filter to specific paths like `/blog/`, `/resources/`

They click "Analyze."

### Step 2: Pipeline runs (20-25 minutes)

The frontend polls `/v1/sites/{id}/crawl/status` with exponential backoff (5s → 30s). The UI shows a progress stepper with educational content at each stage:

| Stage | What the user sees | What happens behind the scenes |
|-------|-------------------|-------------------------------|
| Crawling | "Reading every post on your blog..." | Sitemap/WordPress crawler fetches all URLs, extracts text via trafilatura, parses metadata, headings, internal links |
| Embedding | "Understanding your content's meaning..." | OpenAI text-embedding-3-small generates 1536-dimension vectors for each post |
| Health Scoring | "Calculating content health across 8 factors..." | 8-factor composite score (traffic, ranking, engagement, freshness, depth, links, technical SEO, AI readiness) |
| Clustering | "Discovering your topic ecosystem..." | UMAP dimensionality reduction + HDBSCAN density clustering groups posts by topic similarity |
| Recommendations | "Building your action plan..." | Template-based (90%) + Claude-powered (10%) specific recommendations |

Early findings trickle in as the pipeline progresses — the user sees post count, cluster count, cann pair count update in real time.

Early findings trickle in as stages complete — after 50+ posts are processed, the UI shows live counts: "3 topic clusters | 12 overlap pairs | 5 thin content." This keeps users engaged during the 20-minute wait.

### Step 3: Resume on return

If the user closes the tab during the pipeline, the onboarding page checks for existing sites with active pipelines on mount and resumes polling automatically. No work is lost.

### Step 4: Done

On completion, the user clicks "View Dashboard" and lands on `/today`.

---

## 4. The intelligence pipeline — what happens behind the scenes

> Status: **VERIFIED.** All 17 stages are real implementations reading from and writing to the database. Algorithms (UMAP, HDBSCAN, cosine similarity, PageRank) are correctly implemented. Has been tested against Close.com (958 posts, 22 clusters, 200 cann pairs). **Not tested** in production infrastructure or with diverse blog types at scale.

This is the core engine. 17 stages, fully automated, ~$7 in API costs per 1,000-post site.

### Stage 1: Crawl
- **Sitemap crawler** (`sitemap.py`, 469 lines): Discovers URLs from `sitemap.xml`, `sitemap_index.xml`, or RSS/Atom feeds. Crawls each URL with trafilatura for body text extraction, BeautifulSoup for metadata, headings, internal links. Concurrent (10 parallel requests). Handles redirects, retries, timeouts.
- **WordPress crawler** (`wordpress.py`, 225 lines): Uses WP REST API (`/wp-json/wp/v2/posts`) with pagination. Resolves categories and tags. Extracts body HTML, featured images, dates.
- **Output:** List of `NormalizedPost` objects with: URL, title, body_text, body_html, publish_date, modified_date, word_count, headings, cms_categories, cms_tags.

### Stage 2: Normalize
- Strips site names from titles ("My Post | My Blog" → "My Post")
- Deduplicates by URL (normalized: lowercased, trailing slash stripped)
- Filters navigation links that appear on 80%+ of pages
- Resolves internal link targets to post IDs
- Stores in `posts` and `internal_links` tables

### Stage 3: Embed
- **Model:** OpenAI `text-embedding-3-small` (1536 dimensions)
- **Input:** Title prepended to body text (`f"{title}\n\n{body}"`) with smart truncation (preserves intro + headings + conclusion)
- **Change detection:** Content hash comparison — unchanged posts skip re-embedding
- **Batching:** 100 texts per API call
- **Storage:** pgvector column in `post_embeddings` table with HNSW index for fast similarity search

### Stage 4: Readability
- Computes Flesch Reading Ease and Flesch-Kincaid Grade Level
- Pure Python implementation (no external dependencies)
- Flags posts with readability score below industry threshold (SaaS: Flesch < 35)

### Stage 5: PageRank
- Builds internal link graph using NetworkX
- Computes PageRank scores showing how link authority flows through the site
- Identifies hub pages (high inbound) and orphan pages (zero inbound)

### Stage 6: Intent Classification
- **Fast tier (~85% of posts):** Regex/keyword patterns classify as informational, transactional, commercial, or navigational based on title, URL slug, and word count
- **Claude tier (~10% of ambiguous posts):** Claude Sonnet classifies posts where keyword signals are weak or contradictory
- Detects intent mismatches between post content and ranking queries

### Stage 7: Cluster
- **UMAP** reduces 1536-dimension embeddings to 15 dimensions (for clustering) and 2 dimensions (for visualization)
- **HDBSCAN** performs density-based clustering with adaptive parameters
- Recursive sub-clustering for mega-clusters (50+ posts)
- **Cluster labeling:** TF-IDF extracts distinguishing terms (zero API calls). Claude fallback for ambiguous labels.
- Silhouette score computed and stored for quality assessment
- **Output:** Topic clusters like "SEO Strategy," "Content Marketing," "Product Updates"

### Stage 8: Health Scoring
Eight factors, dynamically weighted based on available data:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Traffic trend | 20% | Growing, stable, declining, or dead (GA4 pageviews) |
| Ranking positions | 18% | Average position for top GSC queries |
| Engagement | 12% | Bounce rate, time on page (GA4) |
| Freshness | 12% | Months since last update |
| Content depth | 10% | Word count vs cluster average |
| Internal links | 8% | Inbound link count normalized to site max |
| Technical SEO | 5% | Meta description, title length, headings, images |
| AI Readiness | 15% | Average of citability + E-E-A-T + schema + extraction scores |

If GA4/GSC data isn't connected, weights redistribute proportionally to crawl-only factors.

**Role assignment** based on composite score + traffic:
- **Pillar** (score ≥ 70, high traffic): Hub posts that anchor a topic
- **Supporter** (score 40-70): Complementary posts building topical depth
- **Competitor** (cannibalizing): Posts fighting each other for the same keywords
- **Dead weight** (score < 30): Posts dragging down the domain

**Ecosystem state** per cluster:
- **Forest** 🌲 (score ≥ 65): Thriving topic with strong pillars
- **Meadow** 🌻 (score 50-65): Healthy but room to grow
- **Seedbed** 🌱 (score 35-50): New or emerging topic area
- **Swamp** 🪴 (active cannibalization): Posts fighting each other
- **Desert** 🏜️ (score < 35): Abandoned or neglected topic

### Stage 9: Cannibalization Detection
Two-signal approach with auto-calibration:
1. **Embedding cosine similarity** — posts in the same cluster compared pairwise. Thresholds auto-calibrated per site using 85th/92nd/97th percentiles with floors at 0.30/0.40/0.50.
2. **GSC query overlap** — 3+ shared Google Search Console queries triggers detection regardless of embedding similarity.
3. **HNSW optimization** — clusters with 20+ posts use pgvector's HNSW index for top-10 nearest neighbor pre-filtering instead of O(n²) comparison.
4. **Severity scoring** — 0-100 composite of cosine similarity + intent match + query overlap ratio.
5. **Resolution recommendation** — redirect (≥0.95 similarity), merge (≥0.85), differentiate (different intents), or monitor.

### Stage 10: Chunk-level Cannibalization
Confirms post-level pairs by checking H2/H3 section overlap. Uses OpenAI embeddings on individual sections. A post can be 40% similar overall but have one section that's 95% duplicated.

### Stage 11: Problem Detection
Thirteen problem types detected across the site:

| Category | Problem types | Signals |
|----------|--------------|---------|
| Content decay | `decay_severe`, `decay_moderate`, `decay_mild` | Click decline >30%, position drop >5, stale >365 days |
| Thin content | `thin_content`, `thin_below_cluster_avg` | <300 words, below cluster average |
| SEO issues | `seo_missing_meta`, `seo_title_length`, `seo_no_headings`, `seo_no_internal_links`, `seo_no_images` | Missing meta, title >60 chars, no H2s, no links, no images |
| Orphan | `orphan` | Zero internal inbound links |
| Readability | `readability_too_complex` | Flesch score < 35 (SaaS threshold) |
| Velocity | `velocity_decline` | Publishing rate slowdown |
| AI readiness | `low_ai_citability`, `weak_eeat`, `missing_schema`, `poor_ai_structure` | AI scores below thresholds |
| GEO-specific | `geo_no_faq_section`, `geo_no_question_headers`, `geo_low_data_density`, `geo_no_answer_first`, `geo_missing_faq_schema`, `geo_no_freshness_date` | Missing FAQ, question headers, data density, answer-first, schema |

### Stage 12: Recommendations
Two tiers:

**Tier 1 — Template-based (90% of recommendations, zero API calls):**
Every detected problem maps to a recommendation template with specific, actionable steps. Examples:
- "Expand thin content: {title}" with word count target, competitor analysis suggestions
- "Fix orphan page: {title}" with specific posts to link from
- "Add FAQ section for AI citation: {title}" with suggested questions from GSC data
- "Restructure for AI extraction: {title}" with TL;DR instructions

**Tier 2 — Claude-powered (10%, for complex cases):**
Claude Sonnet generates recommendations with RAG context from the user's own blog. The prompt includes their top-performing posts as benchmarks, cluster statistics, and specific content excerpts. Generates merge plans, rewrite suggestions, and differentiation strategies.

### Stage 13: AI Citability Scoring
Four dimensions scored 0-100 each:
- **Citability:** Data tables, numbered lists, first-person experience, original statistics, definitions, entity density, external citations, question-format headers, data density, answer-first structure
- **E-E-A-T:** Author byline, credentials, visible dates, author schema, credible external links, contact page
- **Schema:** JSON-LD presence, high-value types (Article, FAQPage, HowTo), field completeness
- **Extraction:** Direct answer in first 200 words, H2s with concise answers, FAQ sections, standalone sections, structured lists

### Stage 14: Ecosystem Visuals
Computes the visual metadata for the landscape map:
- **Rivers** between clusters representing internal link flows (width = link count, color = quality)
- **Grass** around cluster edges (fresh/maintained/overgrown/dead based on content age)
- **Weather** per cluster (sunny/cloudy/rain/storm/fog based on traffic trends)
- **Animals** (birds = low CTR, foxes = high bounce, deer = steady engagement, bees = active interlinking, vultures = decaying content)
- **Terrain features** (boulders = broken links, mushrooms = near-duplicates, erosion = thin content)

### Stage 15: Ecosystem Voice
Claude generates nature-metaphor narratives per cluster. Example: "This forest of 12 posts is thriving — your pillar on 'Content Strategy' anchors the topic. But two swamp posts are cannibalizing each other. Clear the undergrowth."

### Stage 16-17: Additional Processing
- Content gap detection from GSC queries with high impressions but low CTR
- Position monitoring alerts for ranking changes
- Impact baseline recording for recommendations about to be acted on

---

## 5. The dashboard — what users see every day

> Status: **BUILT, NOT E2E TESTED.** All 22+ pages compile, render, and fetch from real backend endpoints. All SWR hooks map to real API routes (verified by cross-referencing `useApi.ts` against router files). No frontend page tests exist — zero Playwright/Cypress coverage. Empty states exist for most pages but edge cases (null scores, missing clusters) may show "NaN" or blank cards.

### Today View (`/today`) — 1,211 lines
The daily command center. Shows:

- **Health score** — animated counter (0-100) with color ring and 7-day/30-day trend indicators
- **Factor breakdown** — 8 bars showing each scoring factor's contribution
- **Since Last Visit** card — "3 new issues, 2 ranking changes since Tuesday"
- **Progress** card — "You've completed 7 recommendations — health improved +4 points"
- **ROI** card — completed actions count, estimated traffic recovery, estimated dollar value
- **Content Gap** card — top GSC query without a matching post, one-click "Generate Brief"
- **Priority actions** — top 5 recommendations sorted by impact, expandable with specific instructions and copy-to-clipboard for meta descriptions
- **AI Readiness** card — overall score + 4 dimension bars + % AI-ready posts
- **Re-analyze button** — triggers pipeline re-run

### Overview (`/overview`) — 748 lines
Analytics dashboard with two modes:

**With GA4/GSC connected:** Traffic trend (90 days), post health distribution, publishing velocity, cluster performance comparison, CTR trend

**Without GA4/GSC (crawl-only):** Health score radar chart, content age distribution, content depth distribution, cluster health scores, cluster size distribution, publishing velocity, content structure stats (avg/median word count)

### Clusters (`/clusters`) — 177 lines list + 446 lines detail
- **List:** All clusters with health scores, post counts, ecosystem states
- **Detail:** Posts in cluster, ecosystem narrative, health breakdown, cannibalization pairs within cluster, recommendations for this cluster, bridge posts connecting to other clusters

### Posts (`/posts`) — 518 lines list + 551 lines detail
- **List:** All posts with search, filter by role (pillar/supporter/competitor/dead_weight), sort by health score. Paginated (50 per page).
- **Detail:** Health score with factor breakdown, problems detected, recommendations, cannibalization pairs involving this post, internal link graph, word count, readability score

### Issues (`/issues`) — 358 lines
Content problems grouped by type (decay, thin, SEO, orphan, readability, AI). Filterable by severity (critical/high/medium/low). Each issue links to the affected post and its recommendation.

### Impact Tracking (`/impact`) — 192 lines list + 267 lines detail
After completing a recommendation (e.g., merging two posts), the system:
1. Snapshots current traffic, ranking, and engagement metrics
2. Monitors for 30/60/90 days
3. Shows before/after comparison with delta percentages
4. Generates a shareable "Impact Card" proving ROI

---

## 6. The ecosystem visualization — the core differentiator

> Status: **BUILT, NOT E2E TESTED.** PixiJS v8 migration completed — dynamic import confirmed, WebGL rendering confirmed (not D3/SVG). D3 used only for force layout math. **Has never been tested with real user data from a production pipeline.** If `pixi.js` fails to load (network error, browser without WebGL), the component crashes with no fallback UI. Old Canvas overlay renderer files still exist in the codebase but are no longer imported.

### The landscape map (`/landscape`) — 499 lines

The single feature that makes Enough visually different from every other SEO tool. Instead of spreadsheets and bar charts, users see their blog as a **living ecosystem**.

**Technology:** PixiJS v8 (WebGL, GPU-accelerated) with D3.js force simulation for layout.

**What users see:**
- Each **cluster** is a terrain zone — green forests for healthy topics, brown swamps for cannibalized areas, grey deserts for neglected content
- Each **post** is a tree — oaks for pillars (tall, full canopy), birches for supporters (smaller), thorny vines for competitors (tangled), stumps for dead weight (grey, lifeless), seedlings for new posts
- **Creatures** animate near posts: Bloomlings (🌸 green, bobbing) near healthy pillars, Rustmites (🦀 orange, wiggling) near decaying posts, Foglings (👻 translucent, floating) near orphaned posts
- **Rivers** flow between clusters showing internal link pathways (width = link count, color = quality: sparkling blue → clear → murky → toxic green)
- **Weather** reflects traffic trends: sunny for growing clusters, rain for declining, storm for severe decay, fog for stagnant
- **Grass** around cluster edges shows content freshness (green = recent, yellow = aging, brown = stale, grey = dead)
- **Terrain features**: red mushrooms near near-duplicate content, boulders where broken links exist, erosion stains for thin content

**Interactions:**
- Pan and zoom (trackpad and mouse, GPU-accelerated transforms)
- Hover any tree for tooltip (title, URL, health score, role, traffic)
- Click a tree to select it and show detail panel
- Click a cluster region to zoom into it
- Click a creature to see the specific recommendation it represents
- Minimap in corner for navigation on large ecosystems
- Toggle to Data View for a structured grid of cluster cards

**Data View** (alternative to the map):
- Cards for each cluster showing: SVG health score ring, role distribution mini bar chart (pillar/supporter/competitor/dead_weight), ecosystem state badge with icon, clustering confidence badge

---

## 7. Taking action — recommendations, consolidation, and the Oracle

> Status: **VERIFIED** for template recommendations (fast_recommendations.py — tested logic). **BUILT, NOT E2E TESTED** for Claude-powered recommendations and Oracle (requires Anthropic API key + real content to test). Consolidation draft generation requires Scale tier and Claude API — code exists, never tested with real merge.

### Actions page (`/actions`) — 838 lines
The recommendation feed. Every recommendation has:
- **Type:** merge, refresh, expand, consolidate, optimize, interlink, growth, improve_ai_citability, add_faq_section, reformat_headers_geo, etc.
- **Priority:** critical, high, medium, low
- **Effort estimate:** hours
- **Status tracking:** pending → in_progress → completed → dismissed
- **Specific actions:** Not "improve this post" but "merge posts A and B, redirect A → B, use this meta description: [copy-to-clipboard]"
- **Copy-to-clipboard** for meta descriptions, title tags
- **Push to WordPress** button (if WordPress site) — pushes redirect or meta description changes via WP REST API

### Consolidation (`/consolidation`) — 133 lines list + 174 lines detail
For swamp clusters with cannibalization:
- **Plan** identifies pillar post (keeps), merge candidates (absorb), dead weight (redirect and forget)
- **Traffic recovery estimate** (35% of cannibal traffic, realistic)
- **Effort estimate** (hours based on total word count)
- **Priority score** = recovery / effort
- **Quick win badge** on the highest-priority plan
- **AI-generated draft** (Scale tier) — Claude writes a consolidated post merging unique insights from all source posts. Includes source annotations (`<!-- Integrated from: "Post Title" -->`), word count summary, SEO metadata (title tag + meta description), HTML export alongside markdown.
- **Redirect map** in htaccess, WordPress Redirection CSV, or plain CSV format

### Oracle (`/oracle`) — 323 lines + slide-in panel
The pre-publish conflict checker. Before publishing a new post, a user pastes their draft text and/or target keyword. The Oracle:

1. Generates an embedding for the draft
2. Finds the 20 most similar existing posts via pgvector HNSW index
3. Checks GSC for existing posts ranking for the target keyword
4. Sends everything to Claude with cluster context and cannibalization data
5. Returns a verdict: **"safe to publish"**, **"potential conflict with [post X]"**, or **"high risk — merge with [post Y]"**

Available as a full page at `/oracle` and as a slide-in panel via the floating action button (available on every dashboard page for paid users).

### Content Briefs (`/briefs`) — 623 lines
Generates writer-ready content briefs combining RAG context + Claude:
- Suggested titles (2 options with keyword placement)
- Target keyword + 5 secondary keywords from GSC
- Word count target based on cluster average
- Full outline with H2 sections, specific bullet points per section, estimated word counts
- Questions to answer (for FAQ sections)
- Topics to avoid (prevents cannibalization with existing content)
- Internal linking plan (specific posts to link to/from with anchor text)
- GEO requirements: TL;DR first, question headers, data density target, schema types, FAQ questions
- Difficulty level and opening hook suggestion

---

## 8. AI readiness and GEO scoring

> Status: **VERIFIED.** All 4 scoring dimensions implemented in `ai_citability.py` (746 lines). All 6 GEO problem types exist in `generate_ai_problems()`. 8th health factor (15% weight) confirmed in `health_scoring.py`. GEO recommendation templates confirmed in `fast_recommendations.py`. **Known scoring bugs fixed:** standalone section zero-guard, answer-first flexibility, severity score cap. AI Readiness section exists in PDF report with spider chart.

### The 2026 landscape

Google AI Overviews now appear on ~50% of searches. Organic CTR drops 34.5% when AI Overviews are present. Content marketers need to optimize not just for Google rankings but for AI citation.

### What Enough measures

Every post gets scored on 4 AI dimensions (0-100 each):

**Citability** — Will an AI quote this content?
- Data tables, numbered lists, first-person experience language
- Original statistics with specific numbers
- Definition paragraphs ("X is...")
- Entity density (proper nouns per 1000 words)
- Credible external citations
- Question-format H2/H3 headers (target: 30%+)
- Data density (target: 1 data point per 200 words)
- Answer-first structure (first 200 words directly answer the query)

**E-E-A-T** — Does this look trustworthy?
- Author byline with name visible
- Author bio with credentials (CEO, PhD, years of experience)
- Visible publication/update date (`<time>` element)
- Author schema markup (JSON-LD)
- Links to credible sources (.gov, .edu, peer-reviewed journals)
- Contact/about page link

**Schema** — Is the content machine-readable?
- JSON-LD presence (any structured data)
- High-value types: Article, FAQPage, HowTo, TechArticle
- Article field completeness (headline, datePublished, author, image, dateModified)
- Multiple schema types

**Extraction** — Can AI systems pull out answers?
- Direct answer in first 200 words
- H2 sections start with concise 1-2 sentence answers
- FAQ section with explicit heading + Q&A pairs
- Standalone sections (don't start with "This" or "It" without context)
- Structured lists under headings

### AI Readiness as a health factor

AI Readiness is the 8th factor in the composite health score, weighted at 15%. A post can score 90/100 on traditional metrics but 15/100 on AI readiness — and the dashboard shows this clearly.

### GEO-specific recommendations

When AI issues are detected, the system generates specific recommendations:
- "Add FAQ section for AI citation" with suggested questions from GSC data
- "Reformat H2 headers as questions" with specific before/after examples
- "Add data points for AI citation" with density targets
- "Add TL;DR for AI extraction" with structure guidance
- "Add FAQPage schema markup" when FAQ content exists without structured data
- "Add visible update date" for freshness signals

### The free audit hook

The AI Readiness grade is prominently featured in the free audit PDF and drip emails: "Your blog's AI Readiness score is 23/100. Here's why ChatGPT doesn't cite you." This is the scariest, most urgent finding a content marketer can receive in 2026.

---

## 9. Google integrations — GA4 and Search Console

> Status: **BUILT, NEEDS INFRA.** OAuth flow, token encryption, GSC/GA4 sync services — all code exists. Google OAuth state is HMAC-signed (verified). **Requires:** Google Cloud project with OAuth credentials, authorized redirect URIs, and the `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI` env vars configured. Never tested with a real Google account in production.

### Connecting Google

From Settings (`/settings`), users click "Connect Google" which initiates an OAuth2 flow:
1. User authorizes Enough to read their GA4 and GSC data (read-only)
2. OAuth tokens are encrypted with Fernet (AES-128-CBC) and stored in the database
3. Token refresh happens automatically when expired

### Google Search Console data
- Daily query data: queries, impressions, clicks, average position, CTR
- Synced incrementally (only new dates)
- Used for: cannibalization detection (query overlap), ranking trend analysis, content gap identification, position monitoring alerts

### Google Analytics 4 data
- Daily per-URL metrics: pageviews, sessions, engaged sessions, avg engagement time, bounce rate, conversions
- Used for: traffic trend scoring, engagement scoring, decay detection, ROI calculation

### Settings page integration hub

The Settings page (`/settings`) has three tabs:

**Integrations tab:**
- Connect/disconnect Google account (OAuth flow)
- Google Search Console: browse verified sites, select site URL, trigger 90-day sync
- Google Analytics 4: browse properties, select property ID, trigger 90-day sync
- Status badges showing connection state and last sync time

**Intelligence upgrades** (one-click triggers from Settings):
- Quick Scan (30 seconds, no re-crawl) — fast health check
- Incremental Refresh — re-analyze without full recrawl
- Confirm Chunk Overlap (5 min) — section-level cannibalization verification
- Claude Intent Classification (2 min) — AI-powered intent analysis for ambiguous posts
- AI Readiness Scan (1-3 min) — compute citability, E-E-A-T, schema, extraction scores

**Site Settings tab:** CMS type, re-crawl schedule (manual/weekly/monthly)
**Notifications tab:** Email digest frequency (weekly/biweekly/monthly/off)

### What changes with Google connected
- Health scoring gets 3 additional factors (traffic, ranking, engagement) — scores become much more accurate
- Cannibalization detection gains the query overlap signal (the strongest signal)
- Decay detection gains click/impression decline analysis
- Overview page shows real traffic and CTR charts instead of crawl-only metrics
- Content gaps identified from high-impression/low-CTR queries

---

## 10. Email system — drip, weekly digest, winback

> Status: **BUILT, NEEDS INFRA.** All email templates exist with correct pricing, HTML-escaped user data, and functional unsubscribe links. **Requires:** Resend API key, SPF/DKIM/DMARC configured on `enough.app` domain. HTML injection vulnerabilities fixed (html.escape applied). Never tested with real email delivery.

### Drip sequence (leads)
3 emails for free audit leads (described in Section 1). Sent via Resend. Processed by cron every 30 minutes.

### Weekly digest (customers)
Every Monday, paying customers receive a personalized email per site:
- Health score delta (this week vs last)
- Post breakdown changes (new active, newly dead)
- New cannibalization threats detected
- Top recommendation ("do this one thing this week")
- Quick win consolidation opportunity
- CTA: "View your full dashboard →"

Sent via Resend. Weekly cron.

### Winback sequence (churned)
After cancellation, 3 win-back emails:

| Email | When | Content |
|-------|------|---------|
| Day 7 | 7 days after cancel | "Your content health has gone unchecked for a week" — urgency about unmonitored cannibalization |
| Day 30 | 30 days after cancel | "A lot can change in a month" — Google algorithm updates, competitor changes, decay |
| Day 60 | 60 days after cancel | "Final offer: 30% off for 3 months" — COMEBACK30 coupon code ($104.30/mo instead of $149) |

The COMEBACK30 coupon is auto-created in Stripe at app startup. 30% off, 3-month duration, one redemption per customer.

### Unsubscribe
CAN-SPAM compliant. `/unsubscribe` page lets users opt out by email. Optouts are checked before every email send.

---

## 11. PDF reports — free audit and paid reports

> Status: **VERIFIED.** PDF generation tested in unit tests. Bar chart, spider chart, cover page, executive summary, AI readiness section, quick wins, pricing CTA — all confirmed in `pdf_report.py` (693 lines). Spider chart data coerced to float (crash bug fixed). **Known edge case:** if audit data has None values in unexpected fields, some sections may render as "---" instead of crashing (graceful degradation).

Generated with ReportLab. Professional multi-page PDF with:

- **Cover page** — domain name, date, health score as a large colored number
- **Executive summary** — 2 sentences summarizing the scariest finding
- **Issue breakdown bar chart** — cannibalization, thin, orphan, duplicate, decay counts
- **AI Readiness section** — score, 4-dimension spider/radar chart, top 3 GEO issues ("67% of posts have no schema," etc.)
- **Top 3 Quick Wins** — specific actionable items
- **Top 5 Posts Needing Attention** — table with scores and issues
- **CTA** — "$149/month. 30-day money-back guarantee."

Scale tier customers get **white-label reports** — custom brand name and logo rendered on the PDF.

---

## 12. Billing and subscriptions

> Status: **VERIFIED** for code logic. Stripe redirect URLs validated via `urlparse()` (not `startswith()`). Webhook idempotency uses atomic `INSERT ON CONFLICT` (no race condition). COMEBACK30 coupon auto-created at startup. **NEEDS INFRA:** Stripe price IDs (`STRIPE_PRICE_GROWTH`, `STRIPE_PRICE_SCALE`), webhook endpoint registered, Stripe CLI tested. `validate_production()` now checks both price IDs at startup. Pricing consistent at $149/$349 across all 7 code locations (verified, zero stale `$99`/`$249` instances).

### Plans

| Feature | Growth ($149/mo) | Scale ($349/mo) |
|---------|-----------------|-----------------|
| Sites | 1 | 3 |
| Posts | 500 | 2,000 |
| Consolidation drafts | 5/month | Unlimited |
| Oracle pre-publish checker | Yes | Yes |
| White-label reports | No | Yes |
| Annual pricing | $1,490/yr ($124.17/mo) | $3,490/yr ($290.83/mo) |

### Stripe integration

- **Checkout:** Creates Stripe checkout session with validated redirect URLs (parsed by hostname, not just prefix). Returns checkout URL for frontend redirect.
- **Webhooks:** Handles `checkout.session.completed`, `subscription.updated`, `subscription.deleted`, `subscription.paused`, `payment_failed` with atomic idempotency (INSERT ON CONFLICT).
- **Grace period:** 7 days after payment failure before lockout. User gets a payment failure email with deadline.
- **Customer portal:** Redirect to Stripe's hosted portal for payment method management and invoice history.

### Paywall

The dashboard layout checks subscription status. Unpaid users are hard-redirected to `/billing` — no soft wall, no teaser content. Only `/billing` is accessible without a paid subscription.

---

## 13. Background jobs and automated maintenance

> Status: **BUILT, NEEDS INFRA.** All 6 cron endpoints exist and are protected by HMAC-verified `X-Cron-Secret`. Stale job cleanup timeout increased to 6 hours (was 2). Anonymous site deletion checks for active pipelines. **Requires:** External cron scheduler (e.g., Fly.io scheduled machines, Railway cron, or simple curl cron job) to call these endpoints on schedule.

Six cron endpoints, all protected by `X-Cron-Secret` header with constant-time HMAC comparison:

| Endpoint | Frequency | What it does |
|----------|-----------|-------------|
| `/cron/daily-refresh` | Daily | Syncs GA4 + GSC data for all sites with Google connected. Updates analytics. |
| `/cron/weekly-recrawl` | Weekly | Re-crawls all sites. Detects new/updated/deleted posts via content hash comparison. |
| `/cron/monthly-reembed` | Monthly | Re-generates embeddings for posts whose content changed since last embedding. |
| `/cron/process-drips` | Every 30 min | Sends pending drip emails (day 2 and day 5 follow-ups for audit leads). |
| `/cron/winback-emails` | Daily | Processes win-back email sequence for cancelled subscribers. |
| `/cron/weekly-digest` | Weekly (Monday) | Sends personalized weekly ecosystem health reports to all paying users. |

### Stale job cleanup
Automatically marks pipeline/crawl jobs as failed if they haven't updated in 6 hours. Cleans up anonymous sites older than 30 days (with safety check for active pipelines).

---

## 14. Architecture and technology

> Status: **VERIFIED.** All technology choices confirmed by reading `package.json`, `requirements.txt`, `main.py`, `database.py`. SSL is now conditional (production only — fixed from hardcoded `ssl="require"`). CI runs lint + test + type check + build on every push.

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, SWR for data fetching |
| Visualization | PixiJS v8 (WebGL), D3.js (force layout math) |
| Backend | Python 3.12, FastAPI, asyncpg (async PostgreSQL), Pydantic |
| Database | PostgreSQL 16 with pgvector extension (HNSW indexes for similarity search) |
| Auth | Supabase Auth (JWT, Google OAuth, magic links) |
| AI | OpenAI text-embedding-3-small (embeddings), Claude Sonnet 4 (recommendations, Oracle, labels, narratives) |
| Payments | Stripe (checkout, webhooks, customer portal, coupons) |
| Email | Resend (transactional emails) |
| Monitoring | Sentry (error tracking, both frontend and backend) |
| CI/CD | GitHub Actions (lint, test, type check, build) |
| Infrastructure | Docker Compose (dev), Supabase + Vercel + Fly.io (production) |

### API structure

All endpoints under `/v1`. 13 routers, 131 total endpoints. 88% require authentication. Rate limiting: 60/minute global, stricter limits on auth (5-10/min), crawl (5/min), pipeline (3/min), Oracle (10/min), consolidation draft (5/min).

### Security

- JWT validation with HS256, expiry enforcement
- HMAC-signed OAuth state (prevents token hijacking)
- SSRF protection on URL inputs (blocks private IP ranges)
- Fernet encryption for stored Google/WordPress tokens
- Security headers: HSTS, CSP, X-Frame-Options, XSS-Protection, Referrer-Policy, Permissions-Policy
- Request size limit (10MB)
- Host header validation
- Parameterized SQL queries throughout (zero SQL injection vectors)
- HTML escaping on all user data in email templates

---

## 15. Data model — what's stored and where

### Core tables

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `profiles` | User accounts | email, subscription_status, stripe_customer_id |
| `sites` | Analyzed blogs | domain, cms_type, google_tokens (encrypted), metadata |
| `posts` | Individual blog posts | url, title, body_text, body_html, word_count, publish_date, content_hash |
| `post_embeddings` | 1536-dim vectors | embedding (pgvector), content_hash |
| `clusters` | Topic groups | label, ecosystem_state, health_score, silhouette_score |
| `post_clusters` | Post → cluster mapping | post_id, cluster_id (many-to-many) |
| `post_health_scores` | Per-post health | composite_score, role, trend, 8 factor scores, 4 AI scores |
| `cannibalization_pairs` | Competing posts | overlap_score, severity, resolution, severity_score |
| `content_problems` | Detected issues | problem_type, severity, first_detected_at |
| `recommendations` | Action items | type, priority, status, specific_actions |
| `internal_links` | Post-to-post links | source_post_id, target_post_id, anchor_text |

### Analytics tables

| Table | Purpose |
|-------|---------|
| `ga4_metrics` | Daily GA4 data per post (pageviews, sessions, bounce rate) |
| `gsc_metrics` | Daily GSC data per post per query (impressions, clicks, position) |
| `health_score_history` | Weekly health score snapshots for trend analysis |
| `report_snapshots` | Week-over-week comparison data for weekly digest |

### Content intelligence tables

| Table | Purpose |
|-------|---------|
| `content_briefs` | Generated content outlines |
| `content_gaps` | GSC queries without matching posts |
| `consolidation plans` | Merge plans for swamp clusters (computed, not stored) |
| `redirect_log` | Redirects pushed to WordPress |
| `impact_tracking` | Before/after metrics for completed recommendations |

### 29 sequential migrations

Managed by a custom migration runner (`migrate.py`) with a `schema_migrations` tracking table. Each migration runs in a transaction. Applied in alphabetical order, tracked by filename.

---

## 16. Security model

> Status: **VERIFIED.** Every security claim in this section has been confirmed by reading the actual code in the March 2026 audit. HMAC-signed OAuth state — confirmed (`google_integration.py:54-64`). Stripe URL validation via urlparse — confirmed (`stripe_service.py:89-96`). UUID fallback gated to non-production — confirmed (`dependencies.py:58`). Webhook idempotency atomic — confirmed (`stripe_service.py:174`). HTML escaping in emails — confirmed (`drip_sequence.py`, `weekly_report.py`). All parameterized SQL — confirmed (zero string interpolation in queries).

### Authentication chain
1. Frontend Next.js middleware checks for Supabase cookie or Authorization header on all 19 dashboard routes
2. Backend FastAPI dependency `get_current_user_id` validates JWT (HS256, expiry checked)
3. Site ownership verified via `get_verified_site` (SELECT WHERE site_id = $1 AND user_id = $2)
4. Subscription tier checked via `SubscriptionGuard` for premium features (Oracle, consolidation drafts)

### Data isolation
- Every database query filters by `site_id` AND `user_id` — no cross-site or cross-user data access
- Google tokens encrypted at rest with Fernet (AES-128-CBC)
- WordPress passwords encrypted at rest
- Production validation enforces all secrets at startup — app won't start if misconfigured

### What's validated in production startup
SECRET_KEY, SUPABASE_URL, SUPABASE_JWT_SECRET, CRON_SECRET, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_GROWTH, STRIPE_PRICE_SCALE, RESEND_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, FRONTEND_URL — all required. App crashes on startup if any are missing.

---

## 17. What doesn't exist yet

> These are honest gaps — not planned for launch, documented so future sessions don't re-discover them.

### Not built (deliberate scope decisions)

| Feature | Status | Notes |
|---------|--------|-------|
| **Team collaboration** | Not built | Single-user accounts only. No invites, roles, shared dashboards. |
| **AI citation monitoring** | Not built | Planned for Scale tier. Query ChatGPT/Perplexity with cluster topics, track citation frequency. |
| **AI Share of Voice dashboard** | Not built | Planned post-launch. Your brand vs competitors across AI platforms. |
| **Competitor crawling** | **STUB** | `competitors/page.tsx` shows "Coming Soon." Backend `competitor_compare.py` exists but only compares internal cluster data — does not actually crawl competitor domains. |
| **MCP server integrations** | Not built | Not planned. |
| **Multi-platform SEO** | Not built | TikTok, YouTube, Reddit SEO out of scope. |
| **SSO / SAML** | Not built | Enterprise auth not needed for target market. |
| **Keyword rank tracking** | Not built | Ahrefs/Semrush do this better. Enough focuses on relationships, not individual keywords. |
| **Content editor** | Not built | Users edit content in their CMS, not in Enough. |
| **Automated content changes** | Limited | Can push meta descriptions and redirects to WordPress. Cannot edit post body content. |

### Built but minimal

| Feature | Status |
|---------|--------|
| **Calendar** (`/calendar`) | Basic publishing cadence recommendations per cluster. Not a full editorial calendar. |
| **Content Wrapped** (`/wrapped`) | Spotify Wrapped-style annual review. Stats + narrative slides. |
| **Profile** (`/profile`) | Shows steward stats (swamps cleared, deserts revived). Export as text. |
| **Gamification** | Login streaks, ecosystem forecasts. Lightweight engagement hooks. |
