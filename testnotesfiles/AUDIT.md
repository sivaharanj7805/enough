# Tended — Launch Readiness Audit

**Updated:** 2026-03-25
**Purpose:** Single source of truth. What works, what's broken, what to ship, what to build.

---

## Status Summary

| Area | Done | Remaining |
|---|---|---|
| Security (SEC-1–20) | 20/20 | — |
| Ecosystem Visualization (VIZ-1–8 + PixiJS) | 9/9 | — |
| Intelligence Pipeline (PIPE-1–8) | 8/8 | — |
| Customer Outputs (OUT-1–5) | 5/5 | — |
| Frontend UX (UX-1–7) | 7/7 | — |
| GEO / AI Readiness (GEO-1–8) | 8/8 | 3 post-launch |
| Pipeline Performance (PERF-1–6) | 6/6 | — |
| E2E Bug Fixes (BUG-1–21) | 21/21 | — |
| **Data Quality Bugs (DQ-1–7)** | **0/7** | **7 ship-blocking** |
| **Credibility Bugs (CQ-1–5)** | **0/5** | **5 ship-blocking** |
| Backend Performance | 10/14 | 4 low-priority |
| Frontend Cleanup | 19/24 | 5 low-priority |
| Infrastructure | 2/8 | **6 ship-blocking** |
| Test Suite | 686+98 passing | — |
| E2E: backlinko.com | 11/11 steps | 2 DB constraint bugs fixed during run |

---

## PART 1: SHIP-BLOCKING — Before first customer

### 1. Dev Environment Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt && pip install ruff
cd frontend && npm install && cd ..
# Start Docker Desktop, then:
make lint && make test && make build
```

Fix all failures before proceeding.

### 2. Infrastructure (INFRA-1, INFRA-3–8)

| # | Item | How | Effort |
|---|---|---|---|
| **INFRA-1** | Make repo private | GitHub → Settings → Danger Zone | 5 min |
| **INFRA-3** | Production hosting | Supabase (DB + Auth), Vercel (frontend), Fly.io (backend) | 4h |
| **INFRA-4** | Configure Resend | SPF/DKIM/DMARC DNS records for `tended.app` | 30 min |
| **INFRA-5** | Configure Stripe | Create price IDs $149/$349, register webhook, test with Stripe CLI | 1h |
| **INFRA-6** | Production env vars | Set all from `backend/.env.example` (see PRD.md Section 7) | 30 min |
| **INFRA-7** | Run migrations | `python backend/migrate.py` — 29 files (001–029) | 15 min |
| **INFRA-8** | Set up Sentry | Backend + frontend projects, set `SENTRY_DSN` | 30 min |

**Reminder:** `NEXT_PUBLIC_API_URL` must omit `/v1` — the frontend appends it.

### 3. End-to-End Testing (E2E-1–5)

| # | Flow | Verify |
|---|---|---|
| **E2E-1** | Free audit | Landing → URL + email → PDF in inbox within 25 min → drip emails (day 0, 2, 5) |
| **E2E-2** | Signup → onboarding | Sign up → blog URL → pipeline → `/today` with data → tab close → resume |
| **E2E-3** | Stripe checkout | Subscribe → checkout → webhook → status update → dashboard unlocks |
| **E2E-4** | Core features | Landscape renders → cannibalization shows pairs → recommendations → Oracle verdict → consolidation draft |
| **E2E-5** | Cancellation | Cancel → email → downgrade → winback (day 7, 30, 60) → COMEBACK30 works |

### 4. Launch Activities

| # | Activity | Detail |
|---|---|---|
| **LAUNCH-1** | Run 30 real blogs | Verify across 50–500 post sites. Check clusters, cann pairs, recs, ecosystem visuals |
| **LAUNCH-2** | DM 30 founders | Personalized outreach with audit PDFs: "We found 12 cannibalization pairs on your blog" |
| **LAUNCH-3** | Take 4–6 calls | Convert to first paying customer |

---

## PART 2: GEO ROADMAP — AI Readiness for 2026

### The market context

SEO has split into two disciplines. Traditional SEO (rank in Google, get clicks) is still 90% of the market. But GEO (Generative Engine Optimization — getting cited by ChatGPT, Perplexity, Google AI Overviews, Gemini, Claude) has emerged alongside it. Google AI Overviews now appear on ~50% of searches. Organic CTR dropped 34.5% when AI Overviews are present. 60-70% of searches end with zero clicks. AI referral traffic grew 357% YoY in 2025.

Content marketers — Tended's exact customers — are watching their traffic erode. Agencies are scrambling to offer "GEO audits." New tools are launching (Frase, AuraMetrics, Geoptie, Semrush Enterprise AIO). Nobody has a unified view of traditional SEO health AND AI readiness in one place.

**Tended's 2026 pitch:** "Google AI Overviews just cut your organic traffic by 34%. Your competitors are getting cited by ChatGPT and you're not. Tended shows you exactly which posts are AI-ready, which ones are invisible to AI, and what to fix — in 25 minutes."

### What already exists (strong foundation)

The codebase has more GEO infrastructure than expected:

| Component | Status | Location |
|---|---|---|
| 4-dimension AI scoring (citability, E-E-A-T, schema, extraction) | Implemented | `ai_citability.py` (593 lines) |
| AI problem detection (low_citability, weak_eeat, missing_schema, poor_structure) | Implemented | `problem_detection.py:140-194` |
| Template recommendations for all 4 AI problem types | Implemented | `fast_recommendations.py:111-184` |
| Frontend AIReadinessCard with 4 dimension bars | Implemented | `AIReadinessCard.tsx` |
| `useAIScores()` hook + API endpoint | Implemented | `useApi.ts:149`, `intelligence.py:1430` |
| DB columns for all 4 scores + signals JSONB | Implemented | migration 018 |
| Run AI citability scan endpoint | Implemented | `intelligence.py:1363` |
| AI Readiness Score on Today view | Implemented | `today/page.tsx` |

### What to build for launch (GEO-1 through GEO-8)

These items transform the existing AI scoring from "technically present" to "the product's competitive edge." Ordered by impact.

---

#### GEO-1: Deepen AI citability scoring model
**File:** `backend/app/services/ai_citability.py`
**Effort:** 3-4 hours
**Why:** The current scoring model checks for data tables, lists, first-person language, statistics, and definitions. But the 2026 GEO research identifies specific structural requirements that drive AI citation rates.

**Add to Citability Score (lines 78-154):**
- **Question-format H2/H3 detection** (+15 pts): Count headers starting with "What", "How", "Why", "When", "Which", "Can", "Does", "Is". AI systems match natural language prompts to question-format headers. Target: ≥30% of H2s should be questions.
- **Data density scoring** (+10 pts): Count sentences containing numbers, percentages, or dollar amounts. Target: ≥1 data point per 200 words. Current code checks for "original statistics" but doesn't measure density.
- **TL;DR / answer-first structure** (+10 pts): Check if the first 200 words (not just first 100) contain a direct answer to the title's implied question. AI systems extract the first passage that directly answers a query.

**Add to Extraction Score (lines 340-421):**
- **FAQ section detection** (+15 pts): Look for `<h2>FAQ</h2>`, `<h2>Frequently Asked Questions</h2>`, or consecutive H3s with question marks followed by short answer paragraphs (≤150 words each). AI systems strongly favor content with explicit FAQ sections.
- **Standalone section test** (+10 pts): Each H2 section should make sense without context. Check that sections begin with a topic sentence (not a pronoun reference like "This" or "It" without antecedent).

---

#### GEO-2: Integrate AI readiness into health score
**File:** `backend/app/services/health_scoring.py`
**Effort:** 1-2 hours
**Why:** AI scores are computed and stored but completely separate from the composite health score. A post can score 90/100 health but 15/100 AI readiness, and the dashboard shows it as healthy. In 2026, AI readiness IS health.

**Fix:** Add an 8th factor to the composite score:

```
Current 7 factors:
  Traffic (25%) + Ranking (20%) + Engagement (15%) + Freshness (15%) +
  Depth (10%) + Internal Links (10%) + Technical SEO (5%)

New 8 factors (rebalanced):
  Traffic (20%) + Ranking (18%) + Engagement (12%) + Freshness (12%) +
  Depth (10%) + Internal Links (8%) + Technical SEO (5%) +
  AI Readiness (15%)
```

AI Readiness factor = average of the 4 normalized AI scores (citability, E-E-A-T, schema, extraction). Pull from `post_health_scores.ai_citability_score` etc. If not scored yet (NULL), exclude from average rather than scoring 0.

---

#### GEO-3: Add GEO-specific recommendations
**Files:** `backend/app/services/fast_recommendations.py`, `backend/app/services/recommendations.py`
**Effort:** 2-3 hours
**Why:** The existing AI recommendation templates are good but generic. The 2026 GEO framework has specific, actionable patterns.

**New recommendation templates to add:**

| Problem | Recommendation | Specific action |
|---|---|---|
| No FAQ section | `add_faq_section` | "Add an FAQ section with 3-5 questions matching these top GSC queries for this cluster: [list]. Each answer should be 40-100 words, directly answering the question." |
| H2s not questions | `reformat_headers_geo` | "Reformat {n} H2 headers as questions: change '{current_h2}' to '{suggested_question}'. AI systems match prompts to question headers." |
| No TL;DR | `add_answer_first` | "Add a TL;DR in the first 200 words that directly answers: '{title_as_question}'. AI systems extract the first direct answer they find." |
| Low data density | `increase_data_density` | "This post has {n} data points in {word_count} words ({ratio}/200 words). Target: 1 data point per 200 words. Add specific statistics, percentages, or measurements from {suggested_sources}." |
| Missing FAQPage schema | `add_faq_schema` | "Your FAQ section exists but has no FAQPage JSON-LD. Add structured data so AI systems can directly extract Q&A pairs." |
| No "last updated" date | `add_freshness_signal` | "Add a visible 'Last updated: {date}' timestamp. AI systems favor content with recent modification dates." |

**For Claude-powered recommendations (recommendations.py):** Add GEO context to the Claude prompt: "Also consider AI citability: this post has an AI readiness score of {score}/100. The following GEO signals are weak: {weak_signals}. Suggest specific improvements to make this content citable by ChatGPT, Perplexity, and Google AI Overviews."

---

#### GEO-4: GEO section in free audit PDF
**File:** `backend/app/services/pdf_report.py`
**Effort:** 2-3 hours
**Why:** The free audit PDF is the first impression and the conversion hook. An AI Readiness grade is the scariest, most urgent finding you can show a prospect in 2026. "Your blog's AI Readiness score is 23/100. Here's why ChatGPT doesn't cite you."

**Add after the existing health score section:**
- **AI Readiness Score** — large number (0-100) with color coding, same visual treatment as health score
- **4-dimension breakdown** — spider/radar chart (you already have `SpiderChart` from reportlab) showing citability, E-E-A-T, schema, extraction
- **Top 3 AI issues** — "67% of your posts have no schema markup", "Only 12% of H2 headers are question-format", "Average data density: 0.3 per 200 words (target: 1.0)"
- **CTA reframe** — "Subscribe to see exactly which posts to fix and get AI-ready recommendations for each one"

**Update drip email subjects to include AI angle:**
- Email 1: "Your blog's AI Readiness is {score}/100 — here's why ChatGPT skips you"
- Email 2: "{domain}: {n} posts are invisible to AI. Here's the one fix that changes everything."

---

#### GEO-5: Content brief GEO requirements
**File:** `backend/app/services/content_briefs.py`
**Effort:** 1-2 hours
**Why:** When generating new content briefs, the GEO structure requirements should be baked in — not left for the user to figure out.

**Add to the Claude brief generation prompt:**
```
Structure requirements for AI citability:
- First 200 words: directly answer the primary query (TL;DR first)
- H2 headers: phrase as questions matching how users prompt AI
- Data density: include at least 1 specific statistic per 200 words
- FAQ section: add 3-5 Q&A pairs covering related searches
- Schema: specify Article + FAQPage JSON-LD structure
- Sources: cite at least 2 credible external sources
```

**Add to the brief output:**
- Suggested FAQ questions (pulled from GSC query data for the cluster)
- Target data density (word count / expected data points)
- Schema markup template (pre-filled Article JSON-LD)

---

#### GEO-6: Reframe content decay as AI citation decay
**Files:** `backend/app/services/problem_detection.py`, `frontend/src/lib/copy.ts`
**Effort:** 1 hour
**Why:** This is a messaging change more than a code change. The same decay detection becomes more urgent when framed through the AI lens.

**In problem descriptions and recommendation copy:**
- Old: "This post hasn't been updated in 8 months and is losing rankings."
- New: "This post hasn't been updated in 8 months. It's not just losing Google rankings — AI systems are actively replacing it with newer sources. Posts older than 6 months are 3x less likely to be cited by ChatGPT."

**Add freshness urgency tiers to decay detection:**
- 6-12 months stale: "AI citation risk — update recommended"
- 12+ months stale: "AI invisible — AI systems have likely stopped citing this content"

---

#### GEO-7: AI Readiness on landing page
**File:** `frontend/src/app/page.tsx`
**Effort:** 30 min
**Why:** The landing page pitch needs the AI angle to be relevant in 2026.

**Changes:**
- Add to hero subheadline or feature list: "See your AI Readiness score — find out why ChatGPT doesn't cite your content"
- Add to the "How it works" section: a 4th step — "4. Get your AI Readiness score and fix what's making you invisible to AI"
- Update the free audit CTA: "Get Your Free Audit + AI Readiness Score"
- Add a new section or FAQ item addressing the GEO shift: "Google AI Overviews now appear on 50% of searches. Is your content ready?"

---

#### GEO-8: GEO problem types in detection
**File:** `backend/app/services/problem_detection.py`
**Effort:** 2 hours
**Why:** The current problem detection flags 4 AI issues (`low_ai_citability`, `weak_eeat`, `missing_schema`, `poor_ai_structure`). Adding granular GEO-specific problem types makes the Issues page actionable.

**New problem types:**

| Problem type | Detection | Severity |
|---|---|---|
| `geo_no_faq_section` | Post has no FAQ-structured section (no consecutive Q&A H3s, no "FAQ" heading) | medium |
| `geo_no_question_headers` | <30% of H2s are question-format | medium |
| `geo_low_data_density` | <0.5 data points per 200 words | medium |
| `geo_no_answer_first` | First 200 words don't contain a direct answer (no declarative sentence matching the title query) | medium |
| `geo_missing_faq_schema` | Has FAQ-like content but no FAQPage JSON-LD | high |
| `geo_no_freshness_date` | No visible "last updated" or `<time>` element | low |

---

### Post-launch features (Scale tier / post-validation)

These are high-value differentiators but should not delay launch.

---

#### GEO-9: AI Citation Monitoring (Scale tier)
**New service:** `backend/app/services/ai_citation_monitor.py`
**Effort:** 2-3 weeks
**Why:** The hottest metric in the industry: "How often does ChatGPT/Perplexity/Gemini cite MY content?" Semrush, AuraMetrics, Conductor, Frase all building versions.

**How it works:**
1. Take the user's top keyword clusters (already have them)
2. For each cluster, generate 3-5 natural language prompts matching how users would ask AI about that topic
3. Query AI platforms via API (OpenAI, Perplexity API) with those prompts
4. Parse responses for citations/mentions of the user's domain
5. Track "AI Share of Voice" over time
6. Report: "For queries about [cluster topic], ChatGPT cited your content 2 out of 10 times. Your competitor [domain] was cited 6 out of 10 times."

**Frequency:** Weekly per cluster (to keep API costs reasonable)
**Pricing:** Scale tier only ($349/mo) — this is the upsell from Growth

---

#### GEO-10: AI Share of Voice Dashboard
**New page:** `frontend/src/app/(dashboard)/ai-visibility/page.tsx`
**Effort:** 1-2 weeks (after GEO-9 backend)
**Why:** Visual dashboard showing AI citation trends over time, per-cluster breakdown, competitor comparison.

**Components:**
- Overall AI Share of Voice score (% of tracked prompts where your domain is cited)
- Per-cluster citation rate chart
- Competitor comparison (if competitor domain crawled)
- Trend over time (weekly data points)
- "Most cited posts" and "Never cited posts" lists

---

#### GEO-11: GEO-optimized content briefs
**Enhancement to:** `backend/app/services/content_briefs.py`
**Effort:** 3-4 hours (after GEO-5)
**Why:** Go beyond structural requirements — generate briefs that are specifically designed to be cited by AI.

**Enhancements:**
- Auto-generate FAQ questions from GSC query data + AI prompt patterns
- Include "citation-ready statements" — pre-written factual claims the author should verify and include
- Suggest internal linking patterns that build topical authority (AI systems cite domains with depth)
- Include competitor gap analysis: "ChatGPT currently cites [competitor URL] for this topic. Here's what their content has that yours doesn't."

---

### What NOT to build

| Feature | Why skip |
|---|---|
| MCP server integration (Ahrefs/Semrush) | Infrastructure for AI agent workflows, not for your users |
| Multi-platform SEO (TikTok, YouTube, Reddit) | Real but outside Tended's content blog scope |
| Full agentic commerce optimization | Enterprise e-commerce, not content marketing |
| Keyword rank tracking | Ahrefs/Semrush do this better; don't compete on their turf |

---

## PART 3: PIPELINE PERFORMANCE AUDIT

**Updated:** 2026-03-24
**Context:** E2E test on anthropic.com (375 posts). Pipeline took 20+ minutes. Recommendations step alone took 15+ minutes and hadn't finished when we stopped watching.

### What happens today (375-post site, no GA4/GSC)

| Step | Duration | Claude API calls | What it does |
|------|----------|-----------------|--------------|
| Clustering | ~2 min | 15-20 | UMAP+HDBSCAN (fast), then 1 Claude call per cluster for label+description |
| Cannibalization | ~10s | 0 | pgvector cosine similarity + SQL. No API calls. |
| Health Scoring | ~5s | 0 | 8-factor scoring, pure SQL. |
| Problem Detection | ~5s | 0 | Decay/thin/SEO/orphan detection, pure SQL. |
| **Recommendations** | **15-20 min** | **200-250** | **1 Claude call per detected problem, fully sequential** |
| Auto-enrichment | ~30s | up to 10 | RAG context + Claude for top 10 recs |
| **Total** | **~20 min** | **~240-280** | |

### Why recommendations is the bottleneck

The recommendation engine (`recommendations.py:141`) loops through every detected problem and makes a Claude API call for each one:

```python
for i, problem in enumerate(remaining):   # 250 problems, one at a time
    rec = await self._generate_recommendation(db, site_id, problem)  # 1 Claude call each
```

- **No parallelism.** Each call waits for the previous one to finish.
- **Rate limiter set to 3 req/s** (`RateLimiter(requests_per_second=3)`) — adds 83+ seconds of pure `asyncio.sleep`.
- **Network latency** of 1-3s per call makes the real throughput ~1 req/s.
- For 250 problems: **250 × (1-3s network + 0.33s rate limit) = 5-12 minutes minimum.**

The clustering step has the same pattern: 1 Claude call per cluster for labels, sequential, 3 req/s.

### Four fixes, with quality impact analysis

---

#### Fix 1: Wire in `fast_recommendations.py` (already built, not connected)

**What it does:** Generates recommendations from 22 deterministic templates instead of Claude. Covers thin content, SEO issues, decay, orphans, AI citability, E-E-A-T, schema, GEO problems — every problem type the detector can flag.

**Time saved:** Eliminates ~200 Claude API calls → **saves 10-15 minutes.**

**Quality impact — templates are equal or better than Claude for routine problems:**

Templates use the post's **actual data** — exact word count, exact title length, exact cluster average, exact AI scores — and produce specific, actionable output. Claude gets these numbers in its prompt but often falls back to safe, generic phrasing instead of using them.

**Side-by-side comparison for every problem type:**

**Thin content (post has 340 words, cluster average is 1,247):**
- Claude: *"Consider expanding this post with more detailed information, examples, and relevant data points to improve its depth and search visibility."*
- Template: *"This post has 340 words, which is below the 1,500-word threshold for technical content. Expand to at least 1,247 words to match cluster average. → Add 907+ words of substantive content."*
- **Template wins.** Exact numbers, exact target, exact gap. Claude gave no numbers despite having them in the prompt.

**SEO title too long (title is 78 characters):**
- Claude: *"The title could be shortened to improve display in search results. Consider focusing on the primary keyword."*
- Template: *"Title is 78 characters (recommended: 50-60). Titles over 60 characters get truncated in Google search results. → Shorten from 78 to under 60 characters. Front-load the primary keyword in the first 40 characters."*
- **Template wins.** Exact character count, exact threshold, specific technique.

**Missing meta description:**
- Claude: *"Adding a meta description would help improve click-through rates from search results."*
- Template: *"This post has no meta description. Google will auto-generate one from page content, which is often suboptimal for CTR. → Write a 150-160 character meta description. Include the primary keyword naturally. Add a compelling reason to click."*
- **Template wins.** Character range, specific structure, actionable steps.

**Content decay (post is 14 months old):**
- Claude: *"This content may benefit from an update to maintain its relevance and rankings."*
- Template: *"This post hasn't been updated in over 12 months and is losing rankings. In 2026, stale content faces a double penalty: Google ranks it lower AND AI systems stop citing it entirely. → Update all statistics to current year. Add a visible 'Last updated' timestamp. Refresh the introduction with a TL;DR answer. Add an FAQ section with 3-5 current questions."*
- **Template wins.** Specific timeframe, AI-era framing, 6 concrete actions vs 0.

**Low AI citability (score: 18/100):**
- Claude: *"This post could be improved for AI readability by adding more structured content."*
- Template: *"AI Citability Score: 18/100. This post lacks the signals AI systems use when selecting content to cite. → Add at least one data table. Include first-person experience language ('In our testing...'). Add 2-3 original statistics with specific numbers. Start key H2 sections with a definition paragraph."*
- **Template wins.** Exact score, 5 specific structural changes.

**Orphan page (no inbound links):**
- Claude: *"Consider adding internal links to this page from related content."*
- Template: *"This post has no internal links pointing to it. Orphan pages are nearly invisible to search engines and get minimal crawl budget. → Add links from at least 3 related posts. Link from your highest-traffic posts in the same cluster. Use descriptive anchor text (not 'click here')."*
- **Template wins.** Explains why it matters, 3 specific actions.

**Where Claude is genuinely better (and where we keep it):**
- **Growth recommendations** — "Here's a new content angle for your pillar post on Python frameworks: cover the FastAPI vs Django performance comparison, which your competitors rank for but you don't." This requires creativity, awareness of the competitive landscape, and strategic thinking that templates can't do.
- **Consolidation advice** — "Merge posts A and B because they target the same long-tail keyword and post A has better backlinks while post B has more depth." This requires reasoning about two pieces of content simultaneously.
- **On-demand deep analysis** — When a user clicks "Get AI Analysis" on a specific recommendation, Claude reads the full post body and gives nuanced advice like "your third section repeats the intro" or "the comparison table is missing the pricing column your competitors include."

**The pattern:** Templates beat Claude for problems with a known shape (thin, decay, SEO, schema, structure). Claude beats templates for problems that need creative strategy (growth, consolidation, deep rewrites). The fix keeps Claude exactly where it adds value and removes it where it doesn't.

| Aspect | Claude (current) | Fast templates | Verdict |
|--------|-----------------|----------------|---------|
| Action specificity | Generic phrasing, often ignores numbers in prompt | Plugs in exact word counts, character counts, scores, gaps | **Templates better** |
| Consistency | Varies per call — sometimes great, sometimes vague | Identical quality every time, deterministic | **Templates better** |
| Hallucination risk | Occasionally invents statistics or misquotes the post | Zero — only uses real data from the database | **Templates better** |
| Context awareness | Can reference post body text | Uses post metadata (word count, cluster avg, scores) | **Tie** |
| Deep personalization | Can say "your third paragraph repeats the intro" | Cannot read body text | **Claude better** — but only used in on-demand enrichment |
| Creative strategy | Can suggest new content angles, competitive gaps | Cannot generate novel ideas | **Claude better** — kept for growth recs |
| Speed | 1-3s per recommendation | <1ms per recommendation | **Templates: 10,000x faster** |
| Cost | ~$0.003/call × 250 = **$0.75/site** | $0 | **Templates: free** |

**Recommendation:** Use fast templates for Tier 1 (all standard problem types). Reserve Claude for Tier 2: growth recommendations (5 calls), and on-demand enrichment when user clicks "Get AI Analysis" on a specific rec. This is what `on_demand_enrichment.py` already does. The architecture was designed for this two-tier model; it just wasn't wired in.

**What users lose:** Nothing. The default recommendations get more specific, more consistent, and arrive 10,000x faster. Users who want Claude-level depth on a specific rec still get it — they just click a button instead of waiting 20 minutes for the pipeline to generate 250 mediocre versions.

---

#### Fix 2: Wire in `fast_cluster_labels.py` (already built, not connected)

**What it does:** Labels clusters using TF-IDF instead of Claude. Extracts the top distinguishing terms from each cluster's post titles.

**Time saved:** Eliminates 15-20 Claude API calls → **saves ~30-60 seconds.**

**Quality impact:**

| Aspect | Claude labels | TF-IDF labels | Verdict |
|--------|-------------|---------------|---------|
| Readability | "Python Web Frameworks & Performance" | "Python & Frameworks (Performance)" | **Claude wins** — more natural phrasing |
| Accuracy | Usually correct, occasionally hallucinates | Always reflects actual post titles | **Tie** — both accurate |
| Description | Generates a 1-2 sentence cluster description | No description (label only) | **Claude wins** — descriptions are useful |

**Recommendation:** Use TF-IDF for fast initial labels during the pipeline. The `skip_labeling=True` parameter already exists in `cluster_site()`. Then run Claude labeling as an optional enrichment step (async, non-blocking) after the pipeline completes.

**What users lose:** Cluster descriptions during initial load. Labels are slightly less polished ("Python & Frameworks" vs "Python Web Frameworks & Best Practices"). Descriptions can be backfilled asynchronously.

---

#### Fix 3: Increase rate limiter from 3 to 10 req/s

**What it does:** Reduces artificial throttling. Anthropic's API allows 50+ req/s on paid plans. The current 3 req/s adds 0.33s of forced sleep between every call.

**Time saved:** For any remaining Claude calls (growth recs, auto-enrichment): reduces wait from 0.33s to 0.1s per call → **saves ~30s.**

**Quality impact:** None. Same calls, same responses. Just less sleeping between them.

**Risk:** If the API key has very low rate limits (free tier), calls might get 429'd. The rate limiter already has exponential backoff to handle this. Setting to 10 req/s is conservative for any paid Anthropic plan.

---

#### Fix 4: Parallelize remaining Claude calls with `asyncio.gather`

**What it does:** Instead of calling Claude one at a time, batch 5-10 concurrent requests.

**Time saved:** For the ~15-25 remaining Claude calls (growth recs + auto-enrichment): **3-5x faster** → saves ~20-30s.

**Quality impact:** None. Same prompts, same responses. Just sent concurrently instead of sequentially.

**Risk:** Higher burst traffic to the API. Mitigated by the rate limiter + Anthropic's built-in rate limiting returning 429s which the backoff handler retries.

---

### Combined impact: all 4 fixes

| Step | Before | After | Change |
|------|--------|-------|--------|
| Clustering | ~2 min | ~30s | TF-IDF labels, no Claude |
| Cannibalization | ~10s | ~10s | No change (already fast) |
| Health Scoring | ~5s | ~5s | No change |
| Problem Detection | ~5s | ~5s | No change |
| Recommendations | **15-20 min** | **<5s** | Fast templates (0 Claude calls) |
| Growth recs | ~20s | ~5s | 5 Claude calls, parallelized |
| Auto-enrichment | ~30s | ~10s | 10 Claude calls, parallelized, faster rate limit |
| **Total** | **~20 min** | **~1 min** | **20x faster** |

**Claude API calls per site:** 280 → ~15-25 (growth recs + auto-enrichment only)
**API cost per site:** ~$0.85 → ~$0.05

### What stays the same

- **Recommendation quality for 90% of recs:** Templates produce more specific, data-driven actions than Claude for thin/decay/SEO/orphan/AI problems (see side-by-side comparisons above)
- **On-demand deep analysis:** Users can still click "Get AI Analysis" on any recommendation to get Claude to read the full post body and give personalized advice. This feature already exists in `on_demand_enrichment.py` and is unaffected.
- **Clustering math:** UMAP dimensionality reduction + HDBSCAN density clustering is unchanged. Cluster membership, 2D positions, silhouette scores — all identical. Only the label text changes.
- **Health scores:** All 8 factors, composite scores, role assignment, ecosystem states — untouched.
- **Cannibalization detection:** pgvector cosine similarity + GSC overlap — untouched. Zero API calls before, zero after.
- **Problem detection:** All decay/thin/SEO/orphan/readability/AI problem types — untouched. Zero API calls before, zero after.
- **Growth recommendations:** Still Claude-powered (5 calls for top pillar posts). These need creative strategy that templates can't provide. Just faster now (parallel + higher rate limit).

### What gets slightly worse (and why it doesn't matter)

- **Cluster labels are less polished:** TF-IDF produces "Python & Frameworks (Performance)" instead of Claude's "Python Web Frameworks & Best Practices." Functionally equivalent — users understand what the cluster is about. Mitigated: Claude labels can be backfilled asynchronously after the pipeline completes, so by the time a user actually looks at clusters, the polished labels are already there.
- **No cluster descriptions on initial load:** Claude generates a 1-2 sentence description per cluster ("Posts about Python web frameworks, comparing Django, Flask, and FastAPI for different use cases"). TF-IDF doesn't do this. Mitigated: same async backfill. Description appears within 30-60 seconds of pipeline completion, not at the 2-minute mark instead of the 20-minute mark. Net UX improvement.
- **No body-text-aware recommendations by default:** Claude can (sometimes) reference specific passages in the post body. Templates can't. But in practice, Claude rarely does this for routine problems — it gives the same generic advice whether it reads the body or not. The body-aware analysis is preserved in on-demand enrichment where it actually matters (user is looking at a specific post and wants deep advice).

### Implementation order

1. **Wire in `fast_recommendations.py`** → biggest win, eliminates 200+ calls
2. **Pass `skip_labeling=True` + call `fast_cluster_labels.py`** → saves 15-20 calls
3. **Bump rate limiter to 10 req/s** → 1-line change
4. **Parallelize growth recs + auto-enrichment** → `asyncio.gather` wrapper

All 4 changes are additive. The code for #1 and #2 already exists and is tested. This is a wiring task, not a rewrite.

---

## PART 4: COMPLETED WORK

### Prior work (pre-E2E testing)
- Security (20/20): OAuth, JWT, Stripe validation, ILIKE fix, input validation on all endpoints
- Ecosystem Visualization (9/9): PixiJS v8 migration, all renderers
- Intelligence Pipeline (8/8): Embeddings, clustering, health, cannibalization, recommendations
- Customer Outputs (5/5): PDF, emails, drip, consolidation drafts
- Frontend UX (7/7): Fix It button, onboarding, landing page, overview metrics
- GEO Roadmap (8/8): AI citability, E-E-A-T, schema scoring, GEO recommendations

### This session (2026-03-24)
- 21 bugs found and fixed (BUG-1 through BUG-21)
- Pipeline performance: 20+ min → 2 min 14s (PERF-1 through PERF-6)
- Test suite: 118 failures → 0 failures (686 backend + 98 frontend passing)
- Frontend build: 33 pages compiling with 0 type errors
- Audit PDF: working (dub.co PDF generated)
- Migration 030 created for schema fixes
- 7 data quality bugs identified (DQ-1 through DQ-7) — not yet fixed

### Session (2026-03-25)
- E2E test: backlinko.com (149 posts, full 11-step pipeline, all passing)
- 2 DB constraint bugs fixed (GEO problem types + recommendation types in CHECK constraints)
- 1 code bug fixed (cannibalization.py heading type detection)
- 5 credibility bugs identified (CQ-1 through CQ-5) — not yet fixed
- Accuracy audit: schema finding confirmed accurate, AI citability accurate, E-E-A-T score too low, cannibalization 50%+ false positive rate in showcase pairs
- Core architectural finding: cannibalization detection uses embedding similarity alone, says "compete for same keywords" without keyword data — critical credibility risk for SEO-savvy prospects

---

## PART 5: DATA QUALITY BUGS — Pipeline produces wrong output

**Updated:** 2026-03-24
**Found by:** Post-E2E data integrity audit on dub.co (231 posts)

These aren't crashes — the pipeline runs and returns 200. But the data it produces is wrong.

### DQ-1: Posts assigned to multiple clusters (CRITICAL)

**The bug:** 192 out of 231 posts are in 2-4 clusters each. 617 total post-cluster assignments for 231 posts (2.7x overcounting). The clustering system uses parent/child sub-clustering — when a mega-cluster is split, the posts stay in the parent AND get added to children.

**Evidence:**
```
Assignments per post:
  In 1 cluster:  39 posts
  In 2 clusters: 57 posts
  In 3 clusters: 76 posts
  In 4 clusters: 59 posts
```

**Impact:** Every downstream metric is inflated. Cluster post counts are meaningless. "Dub Link Management Platform" shows 169 posts because it's the root cluster containing all its children's posts. Health scores, cannibalization pairs, and recommendations all double/triple-count these posts.

**Root cause:** `clustering.py` sub-clustering doesn't remove posts from the parent when assigning them to children. The `post_clusters` table accumulates hierarchical assignments.

**Fix needed:** Either (a) remove parent assignments when sub-clustering creates children, or (b) filter queries to only use leaf clusters (clusters with no children), or (c) add a `is_primary` flag to `post_clusters` so each post has exactly one primary cluster.

### DQ-2: Health score factor columns are NULL for 49% of scored posts

**The bug:** 121 posts have composite scores. But only 62 have actual factor breakdowns (freshness, content_depth, technical_seo, etc). The other 59 have composite_score but ALL individual factors are NULL.

**Evidence:** The best-scored post (Steven Tey, composite 67.1) has:
```
composite_score: 67.05
role: None, trend: None
freshness_score: None, content_depth_score: None
technical_seo_score: None, engagement_score: None
internal_link_score: None
```

A post with a 67.1 health score should have factor breakdowns showing WHY it scored 67. Instead, every factor is NULL.

**Root cause:** `score_site()` (line 127-143) NULLs all factor columns before re-scoring. Then `_score_cluster()` processes each cluster and upserts scores. But posts in multiple clusters get scored multiple times. The `ON CONFLICT` keeps `GREATEST(composite_score)` but the factors from the first scoring pass get overwritten with NULLs if the second pass produces a lower composite (the CASE expression keeps the old factors, which were already NULLed).

**Impact:** The Today page health breakdown shows no factor details. The PDF can't show "why this post scored 67." Users can't understand or act on their health scores.

**Fix needed:** Don't NULL factors before re-scoring. Instead, the `ON CONFLICT` should preserve ALL columns from whichever pass had the higher composite, or score only leaf clusters (fixing DQ-1 fixes this too).

### DQ-3: 110 posts have no health score at all (48% of site)

**The bug:** 231 posts total, only 121 scored. 110 posts have post_health_scores rows (from the NULL pass) but no composite_score — they were NULLed and never re-scored because they weren't reached by any cluster's `_score_cluster` call.

**Root cause:** Same as DQ-1. The health scorer iterates ALL clusters (root + child), but the NULLing pass clears all posts. Posts that only appear in child clusters may or may not get re-scored depending on execution order.

### DQ-4: Role assignment gap — 169 out of 231 posts have no role

**The bug:** Only 62 posts have a role (competitor, at_risk, supporter, dead_weight). 59 posts have scores but NULL role. 110 posts have no score at all.

**Impact:** The ecosystem visualization assigns biome states based on role distribution. With 73% of posts missing roles, the biome assignments are based on a non-representative sample. The "swamp" and "desert" labels are computed from incomplete data.

### DQ-5: Cannibalization pairs hardcoded to max 200

**The bug:** `detect_for_site()` has `max_pairs: int = 200` default. Both test sites returned exactly 200 pairs. For dub.co with 231 posts, this means the system found more than 200 pairs but silently dropped the rest.

**Evidence:** Cosine similarity distribution of the 200 kept pairs:
```
0.95+ (near-duplicate):  4 pairs
0.90-0.95 (very high):  18 pairs
0.80-0.90 (high):      108 pairs
0.70-0.80 (moderate):   70 pairs
```

All 200 are severity "high." The pruned pairs (those above 200) would be lower severity — but we don't know if pair #201 had cosine 0.769 (actionable) or 0.400 (noise).

**Impact:** Users on sites with many similar pages will always see exactly 200 pairs regardless of actual cannibalization count. No way to know how many real issues exist.

### DQ-6: Health scores cluster in a narrow band — low discriminating power

**Evidence:**
```
Scored: 121 / 231 posts
Mean: 38.5, StdDev: 10.2
Min=18.5, P25=31.8, Median=36.3, P75=46.5, Max=67.1
```

95% of scored posts fall between 18.5 and 67.1 — a 48-point range on a 0-100 scale. The interquartile range is only 14.7 points (31.8 to 46.5). Without GA4/GSC data, the model uses only crawl-based factors (freshness, depth, technical SEO, internal links), which don't differentiate enough. The "health score" is really a "content structure score" when external data is missing.

**Impact:** Users see most posts scoring 30-45, which all map to "poor." No meaningful differentiation between a well-structured 3,000-word guide and a thin 200-word changelog entry.

### DQ-7: Ecosystem visuals return empty clusters array

**The bug:** `GET /intelligence/ecosystem-visuals` returns `clusters: []` and `links: []`. The grass, weather, terrain, and animal data are populated (keyed by cluster ID), but without cluster position data, the frontend can't place any of it on the canvas.

**Impact:** The landscape visualization — the product's core differentiator — renders an empty canvas with fog effects. No biome regions, no trees, no creatures. Users see a dark empty screen.

---

## PART 6: BACKLINKO.COM E2E TEST — Accuracy Audit (2026-03-25)

**Test site:** backlinko.com (Brian Dean's SEO blog, acquired by Semrush)
**Why this site:** SEO-savvy audience. If the report has false positives, they'll spot them instantly.
**Pipeline:** 149 posts crawled, 11 steps all passed, ~5 min total. 2 DB constraint bugs fixed mid-run (GEO problem types and recommendation types missing from CHECK constraints).

### What's accurate and genuinely impressive

**Schema finding is 100% confirmed.** Raw HTML on multiple Backlinko pages shows zero `application/ld+json`, zero `schema.org`, zero structured data markup. This is genuinely ironic — Backlinko has a schema markup generator tool AND a comprehensive schema markup guide, but their own blog posts have zero schema. If sent to the Semrush team, the schema finding alone would get their attention. Real finding that a $149/month tool should surface.

**AI Citability score of 71/100 is accurate.** Backlinko's content is data-heavy, uses numbered lists extensively, includes original research ("We analyzed 1.3 million YouTube videos"), has clear H2 structure, and provides step-by-step instructions. These are exactly the signals the citability scorer checks for.

**Extraction score of 77/100 is accurate.** Posts use strong heading hierarchy, numbered steps, clear section structure, and direct answers. Content is highly extractable by AI systems.

**"Based on content analysis — connect Google Analytics for a complete score" on cover page is excellent.** Sets expectations honestly and creates a reason to subscribe. This wasn't on previous PDFs.

**Ecosystem states are differentiated.** "Forest," "meadow," and "desert" — not all "swamp" like every other test site. Backlinko has genuinely different content types (guides, data studies, tool reviews, hub pages) so the clusters have different health profiles.

**Quick Win #3 is excellent and new.** "Add FAQPage schema markup: How to Master E-E-A-T in 2024" — specific, correct, and actionable. That post has FAQ-like content, no FAQPage schema, and adding it would directly enable rich results. Most specific quick win produced across all test sites.

**Top 5 Posts are specific and credible.** Issue labels now include GEO-specific findings: "geo low data density, geo missing faq schema, geo no question headers, No schema markup, No inbound links, Thin content, weak eeat." Someone at Semrush/Backlinko would recognize these as real issues.

### What's wrong or questionable

#### CQ-1: E-E-A-T score of 21/100 is too low (CREDIBILITY RISK — HIGH)

Backlinko posts DO have visible author attribution. The SEO Copywriting page shows "Written by Brian Dean" with a gravatar image, a link to his author page (`/blog/authors/brian-dean`), and "Last updated Apr. 15, 2025." That's author name, visible date, and author page — three of the E-E-A-T signals the scorer checks.

21/100 suggests the scorer isn't detecting these elements, possibly because the HTML structure doesn't match the patterns the scorer looks for (e.g., it might look for `<time>` elements or specific meta tags rather than the text "Last updated"). This is a calibration issue. An E-E-A-T score of 21 for one of the most authoritative SEO blogs on the internet would make the Semrush team dismiss the entire report.

**Fix needed:** Broaden E-E-A-T signal detection in `ai_citability.py` to handle more HTML patterns for author attribution and dates (text-based "Written by", "Last updated", author link patterns — not just `<time>` or `<meta>` tags).

#### CQ-2: Cannibalization false positives — 50%+ of showcase pairs are wrong (CREDIBILITY RISK — CRITICAL)

Of the 6 pairs shown in the PDF:

| Pair | Similarity | Verdict |
|------|-----------|---------|
| "SEO Copywriting" vs "17 Most Important SEO Tips" | 89% | **Borderline** — both cover on-page optimization but different intent (deep guide vs tip list) |
| "Serpstat Review" vs "Ahrefs Review" | 88% | **Wrong** — reviews of two completely different products. High embedding similarity because they share article structure (features/pricing/verdict), but they target completely different keywords |
| "How to Build Links With Content Marketing" vs "Skyscraper Method" | 88% | **Borderline** — Skyscraper is a content marketing link building method, so real overlap exists |
| "8 HTML Tags for SEO" vs "Meta Tags" | 87% | **Correct** — genuinely compete for overlapping search queries |
| "How to Create an Email Newsletter" vs "Improve Email Open Rates" | 86% | **Wrong** — different funnel stages, different search intent, different keywords |
| "SEO Case Study" vs "SEO Copywriting Guide" | 86% | **Wrong** — a case study and a how-to guide are fundamentally different content types |

**Score: 1 correct, 2 borderline, 3 wrong.** If Semrush sees "Serpstat Review vs Ahrefs Review" flagged as cannibalization, they'll dismiss the tool entirely.

**Root cause:** Cannibalization detection operates on embedding similarity alone. Embeddings capture topical similarity, not keyword competition. Two SEO tool reviews are topically similar (both discuss SEO tools with features/pricing/verdict structure) but they're not competing for the same searches. Real cannibalization requires overlapping target keywords (from GSC), overlapping ranking positions, or near-identical titles/H1s. Without GSC data, we detect "these posts are about similar topics" and call it "these posts compete for the same keywords." The report literally says "compete for the same keywords" but we have zero keyword data.

**Fix needed:** See CQ-5 below for the comprehensive fix.

#### CQ-3: 51 orphan posts (34%) seems high for Backlinko

Backlinko is known for aggressive internal linking. 51 orphans out of 149 posts is surprising. Could be accurate — older posts may have been orphaned as the site evolved under Semrush ownership — or could be a false positive from the crawler not detecting all internal links (links in navigation menus, sidebar widgets, or JavaScript-rendered elements that trafilatura doesn't capture).

**Fix needed:** Verify orphan detection by spot-checking 5 flagged pages against their actual HTML. If sidebar/nav links aren't being counted, the internal link extraction in `normalizer.py` needs broadening.

#### CQ-4: Cluster labels are cryptic for SEO content

"Analyzed & Learned (Million)" presumably groups the data study posts. "Redirects & Fix (Tags)" presumably groups technical SEO posts. But a prospect reading "Analyzed & Learned (Million)" wouldn't understand what that cluster is about. TF-IDF labels work for food blogs (where "Soup & Roasted" is obvious) but fail for SEO blogs where the vocabulary is more abstract.

Also: the PDF header says "6 topic clusters" but the table shows 8, and the actual cluster count is 21 (6 top-level + 15 sub-clusters). The count and table are inconsistent.

**Fix needed:** (a) Use Claude for cluster labeling on the showcase pairs in the PDF (TF-IDF for speed, Claude backfill for quality). (b) Fix the cluster count display to be consistent — show top-level count in the header and match the table.

#### CQ-5: Cannibalization detection doesn't understand content type (CORE ARCHITECTURAL ISSUE)

The fundamental issue: the report says "compete for the same keywords" but has zero keyword data. For an SEO-savvy audience, this distinction is immediately obvious.

**Three-tier fix for cannibalization accuracy:**

1. **With GSC data (best):** Use actual overlapping search queries + ranking positions. This is real cannibalization evidence. Already partially implemented in `cannibalization.py` (shared query detection).

2. **Without GSC data (current state) — add guardrails:**
   - **Title/H1 similarity check:** Only flag pairs where titles share 2+ meaningful keywords (not just embedding similarity). "Serpstat Review" and "Ahrefs Review" share "Review" but not the product name — different enough to skip.
   - **Content type detection:** If both posts are "review of X" where X differs, skip. If both are "how to do X" where X is the same, flag. Use the page_type_classifier or URL/title pattern matching.
   - **Intent overlap check:** If posts have different detected intents (informational vs commercial), raise the cosine threshold by +0.10 (already partially implemented but needs tuning).
   - **Raise the cosine threshold for no-GSC sites:** Current calibrated threshold is p85 (~0.66). For sites without GSC data, use p92 (~0.69) to reduce false positives at the cost of missing some true positives.

3. **Change the language:** When GSC data is absent, don't say "compete for the same keywords." Say "cover highly similar topics" or "have significant content overlap." This is honest and still actionable — the recommendation to merge or differentiate is valid even without keyword data.

### Bugs fixed during E2E run

| Bug | Location | Fix |
|-----|----------|-----|
| Headings stored as strings, not dicts | `cannibalization.py:434` | Added `isinstance(h, dict)` type check before `.get("text")` |
| `content_problems` CHECK constraint missing GEO types | DB constraint | Added `geo_no_faq_section`, `geo_no_question_headers`, `geo_low_data_density`, `geo_no_answer_first`, `geo_missing_faq_schema`, `geo_no_freshness_date` |
| `recommendations` CHECK constraint missing GEO rec types | DB constraint | Added `add_faq_section`, `reformat_headers_geo`, `increase_data_density`, `add_answer_first`, `add_faq_schema`, `add_freshness_signal`, `update` |

### Pipeline results summary

| Step | Status | Details | Time |
|------|--------|---------|------|
| Sitemap Crawl | OK | 149 posts | 156s |
| Embeddings | OK | 149 embedded (OpenAI text-embedding-3-small) | 78s |
| Readability | OK | 149 scored (Flesch range: 2.6–76.5) | 6s |
| PageRank | OK | 149 ranked | 1s |
| Intent Classification | OK | 124 informational, 23 commercial, 1 nav, 1 transactional | <1s |
| Clustering | OK | 21 clusters (6 top-level), avg silhouette 0.405 | 30s |
| AI Citability | OK | avg citability=70.9, eeat=20.9, schema=0.0, extraction=76.9 | 31s |
| Health Scoring | OK | 147 scored, avg 50.0/100 (crawl-only) | 3s |
| Cannibalization | OK | 296 pairs, 133 posts involved (after bug fix) | 3s |
| Problem Detection | OK | 768 issues: 149 missing_schema, 132 no_faq, 126 no_question_headers, 91 weak_eeat (high), 78 low_data_density, 51 orphan, etc. | 1s |
| Recommendations | OK | 870 generated (template-based) | 1s |
| PDF Generation | OK | 6-page, 12KB | 2s |
| **Total** | **11/11** | | **~316s** |

---

## MASTER TASK LIST

Everything that needs to happen, in priority order. Combines AUDIT.md items, E2E test findings (2026-03-24), and pipeline performance audit.

### PRIORITY 1 — Data quality bugs (DQ-1 through DQ-7, from Part 5)

These must be fixed before launch. The pipeline runs but produces wrong output.

| # | Bug | Impact | Fix | Effort |
|---|-----|--------|-----|--------|
| **DQ-1** | Posts in multiple clusters (2.7x overcounting) | All downstream metrics inflated | Filter to leaf clusters only, or deduplicate post_clusters | 2-3h |
| **DQ-2** | Health factor columns NULL for 49% of scored posts | Users can't see why posts scored what they did | Fix ON CONFLICT to preserve factors, or score leaf clusters only (DQ-1 fix) | 1-2h |
| **DQ-3** | 110/231 posts have no health score | 48% of content invisible to the product | Same root cause as DQ-1 — scoring only processes leaf clusters | Fixed by DQ-1 |
| **DQ-4** | 169/231 posts have no role assignment | Ecosystem states computed from 28% of data | Same root cause as DQ-1/DQ-2 | Fixed by DQ-1 |
| **DQ-5** | Cannibalization hardcoded to max 200 pairs | Users on large sites miss real issues | Make configurable per tier (Growth: 200, Scale: 500) | 30 min |
| **DQ-6** | Health scores cluster in narrow band (StdDev 10.2 on 0-100 scale) | No meaningful differentiation between good and bad content | Rebalance crawl-only weights, add floor/ceiling | 2-3h |
| **DQ-7** | Ecosystem visuals return empty clusters array | Landscape visualization renders empty canvas | Fix the endpoint to include cluster positions from post 2D coordinates | 1-2h |

### PRIORITY 1B — Credibility bugs (CQ-1 through CQ-5, from Part 6)

These produce technically "working" output that an SEO professional would immediately question. Ship-blocking for outreach to SEO-savvy prospects.

| # | Bug | Credibility Risk | Fix | Effort |
|---|-----|-----------------|-----|--------|
| **CQ-1** | E-E-A-T score 21/100 for Backlinko (should be 60+) | HIGH — dismisses entire report | Broaden E-E-A-T signal detection in `ai_citability.py` for text-based author/date patterns | 3-4h |
| **CQ-2** | 50%+ false positive cannibalization pairs in PDF showcase | CRITICAL — "Serpstat Review vs Ahrefs Review" flagged as cannibalizing | Add title keyword overlap check, content type detection, raise no-GSC threshold | 4-6h |
| **CQ-3** | 51 orphan posts (34%) may overcount due to nav/sidebar link blindness | MEDIUM — could be accurate, needs verification | Spot-check 5 flagged pages, broaden link extraction in `normalizer.py` if needed | 2h |
| **CQ-4** | Cluster labels cryptic ("Analyzed & Learned (Million)") + count inconsistency | LOW — confusing but not wrong | Use Claude backfill for PDF clusters, fix count display consistency | 1-2h |
| **CQ-5** | Report says "compete for same keywords" with zero keyword data | CRITICAL — any SEO pro sees through this | Change no-GSC language to "significant content overlap", add guardrails to cannibalization (see Part 6) | 2-3h |

### PRIORITY 2 — Infrastructure (ship-blocking)

| # | Item | Effort |
|---|------|--------|
| **INFRA-1** | Make repo private | 5 min |
| **INFRA-3** | Production hosting (Supabase + Vercel + Fly.io) | 4h |
| **INFRA-4** | Configure Resend (SPF/DKIM/DMARC) | 30 min |
| **INFRA-5** | Configure Stripe ($149/$349 prices, webhook) | 1h |
| **INFRA-6** | Production env vars | 30 min |
| **INFRA-7** | Run migrations (001–030) | 15 min |
| **INFRA-8** | Set up Sentry | 30 min |

### PRIORITY 3 — E2E testing with correct data

| # | Flow | Verify |
|---|------|--------|
| **E2E-1** | Free audit | Landing → PDF in inbox → drip emails |
| **E2E-2** | Signup → onboarding | Pipeline → `/today` with data |
| **E2E-3** | Stripe checkout | Payment → subscription active |
| **E2E-4** | Core features | Landscape renders, cann pairs real, recs actionable |
| **E2E-5** | Cancellation | Downgrade + winback emails |

### PRIORITY 4 — Launch

| # | Activity |
|---|----------|
| **LAUNCH-1** | Run 30 real blogs (diverse: SaaS, marketing, small, non-English) |
| **LAUNCH-2** | DM 30 founders with audit PDFs |
| **LAUNCH-3** | 4-6 calls → first customer |

### PRIORITY 5 — Post-launch

| # | Feature | Effort |
|---|---------|--------|
| **GEO-9** | AI Citation Monitoring | 2-3 weeks |
| **GEO-10** | AI Share of Voice Dashboard | 1-2 weeks |
| **GEO-11** | GEO-optimized content briefs | 3-4 hours |

---

### COMPLETED

| Area | Status |
|------|--------|
| Security (SEC-1–20) | 20/20 ✅ |
| Ecosystem Visualization (VIZ-1–8 + PixiJS) | 9/9 ✅ |
| Intelligence Pipeline (PIPE-1–8) | 8/8 ✅ |
| Customer Outputs (OUT-1–5) | 5/5 ✅ |
| Frontend UX (UX-1–7) | 7/7 ✅ |
| GEO Roadmap (GEO-1–8) | 8/8 ✅ |
| Pipeline Performance (PERF-1–6) | 6/6 ✅ (20 min → 2 min) |
| E2E Bug Fixes (BUG-1–21) | 21/21 ✅ |
| Test Suite | 686 backend + 98 frontend passing ✅ |
| Frontend Build | 33 pages, 0 type errors ✅ |
| Audit PDF | Working (dub.co PDF generated) ✅ |

### LOW-PRIORITY TECH DEBT

| ID | Issue | Risk |
|---|---|---|
| BE-9 | `weekly_report.py` unbounded site query | OK at <100 sites |
| BE-16 | normalizer missing transaction wrapping | Low probability |
| FE-9 | Some pages use `useSWRFetch` directly instead of `useApi.ts` | Anti-pattern |
| FE-17 | Inline user-facing strings not in `copy.ts` | Coding standard |
