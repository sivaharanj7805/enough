# Intelligence Pipeline — Canonical Step Reference

> **This is the single source of truth for pipeline step numbering.** All docs, test scripts, and code comments use this numbering. There is no separate "spec numbering" — only this.

## Pipeline Steps

```
Step 1    Crawl + Normalize         → Sitemap discovery, HTML fetch, content extraction
Steps 2-5 Enrichment                → Embeddings (2), Readability (3), PageRank (4), Intent (5)
Step 6    Clustering                 → UMAP dimensionality reduction + HDBSCAN topic clustering
Step 6b   TF-IDF Cluster Labels     → Zero-cost cluster naming from title term frequency
Step 6c   AI Citability Scoring     → E-E-A-T, schema, extraction structure scoring
Step 7    Health Scoring             → Composite score (10 weighted factors) + roles + ecosystem states
Step 8    Cannibalization Detection  → Embedding similarity → overlapping content pairs
Step 8b   Chunk Confirmation         → Claude validates top pairs at chunk level (optional, ~$0.50)
Step 8c   Role Patch                 → Fixes roles that depend on cannibalization data
Step 9    Problem Detection          → Decay, thin content, SEO issues, orphans, readability, velocity, AI readiness
Step 10   Recommendations            → Template-matched action items with priority + effort estimates
Step 10b  Claude Enrichment          → AI-enriches top 10 recommendations (optional, ~$0.10)
```

## File Map

| Step | Pipeline Doc | Test Results | Test Script |
|------|-------------|-------------|-------------|
| 1 | `PIPELINE-STEP1-INGESTION.md` | `STEP1-TEST-RESULTS.md` | `test_step1_e2e.py` |
| 2-5 | `PIPELINE-STEPS2-5-ENRICHMENT.md` | `STEPS2-5-TEST-RESULTS.md` | `test_steps2_5_e2e.py` |
| 6 | `PIPELINE-STEP6-CLUSTERING.md` | `STEP6-TEST-RESULTS.md` | `test_step6_e2e.py` |
| 6b | `PIPELINE-STEP6B-TFIDF-LABELS.md` | `STEP6B-TEST-RESULTS.md` | `test_step6b_e2e.py` |
| 6c | `PIPELINE-STEP6c-AI-CITABILITY.md` | `STEP6c-TEST-RESULTS.md` | `test_step6c_e2e.py` |
| 7 | `PIPELINE-STEP7-HEALTH-SCORING.md` | `STEP7-TEST-RESULTS.md` | `test_step7_e2e.py` |
| 8 | `PIPELINE-STEP8-CANNIBALIZATION.md` | `STEP8-TEST-RESULTS.md` | `test_step8_e2e.py` |
| 8b | `PIPELINE-STEP8B-CHUNK-CONFIRMATION.md` | `STEP8B-TEST-RESULTS.md` | `test_step8b_e2e.py` |
| 8c | (no separate doc — covered in Step 8) | — | — |
| 9 | `PIPELINE-STEP9-PROBLEM-DETECTION.md` | `STEP9-TEST-RESULTS.md` | `test_step9_e2e.py` |
| 10 | `PIPELINE-STEP10-RECOMMENDATIONS.md` | `STEP10-TEST-RESULTS.md` | `test_step10_e2e.py` |
| 10b | `PIPELINE-STEP10B-CLAUDE-ENRICHMENT.md` | — | `test_step10b_e2e.py` |

## Code Reference

Pipeline orchestration: `backend/app/routers/ingestion.py:_run_full_pipeline`

Each step is called via `_pipeline_step(pool, site_id, step_name, status, lambda)` which:
- Acquires a DB connection from the pool
- Updates `crawl_jobs.current_step`
- Runs the step function
- Handles errors (non-fatal — logs and continues)

## Deprecated Numbering

An older "spec numbering" (Steps 1-7) existed in early docs. It has been fully replaced:

| Old Spec # | Current Code # | What |
|-----------|---------------|------|
| Spec 1 | Step 1 | Crawl |
| Spec 2 | Steps 2-5 | Enrichment (was bundled as one step) |
| Spec 3 | Step 6 | Clustering |
| Spec 4 | Step 7 | Health Scoring |
| Spec 5 | Step 8 | Cannibalization |
| Spec 6 | Step 9 | Problem Detection |
| Spec 7 | Step 10 | Recommendations |

**Do not use spec numbering.** If you see "Spec Step X" in old code comments, it refers to the mapping above.


CRITICAL — Fix Before First Cold DM
These break the product. A prospect receiving the audit PDF or opening the dashboard would see obviously wrong output.
#StepIssueEffort110aCannibalization recs still fed 373 cosine-only pairs in E2E instead of Step 8's 3 blended pairs — fix the E2E test's Step 8 substitute to use blended scoring, OR run the full production pipeline on Backlinko to confirm the real integration works30 min28bHomepage (186w) produces 12 junk chunks from blog roll H2s — add word count vs chunk count sanity check (if <300w and >5 chunks, fall back to single chunk)20 min3Full pipelineRun the complete pipeline on Backlinko with real OpenAI embeddings — this single run validates every "verify on Backlinko" item across all steps simultaneously1 hour
Total: ~2 hours

HIGH — Fix Before First Paying Customer
These don't break the product but make it look unprofessional or incomplete.
#StepIssueEffort46bTwo garbage alternative labels survive validation ("Copywriter Curse," "People & Naked") — require BOTH bigram words to appear in ≥2 cluster titles15 min56bE2E contradiction: top bigram table marks "sales letter" as selected but label is "Landing Page & Keyword" — fix the YES marker or investigate why higher-scoring bigram was skipped15 min67Homepage (186w, page_type "landing") is pillar #2 — add page_type filter so landing/index pages can't become pillars20 min710bE2E uses pre-fix Step 10 output — top 10 enrichment selection isn't representative of production. Update E2E to use fixed Step 10 output15 min
Total: ~1 hour

MEDIUM — Fix Soon After Launch
These are test gaps, documentation issues, or optimizations that don't affect what the customer sees today but will matter as you scale.
#StepIssueEffort81Spec still documents 50-char gate but code uses 100-word gate5 min91E2E doesn't show canonical URL handling diagnostic10 min101E2E doesn't show robots.txt filtering detail10 min112-5E2E is stale — shows pre-fix E-E-A-T scores (max 55 vs actual 80) and unverified intent fixes. Remove AI citability section from this E2E (it has its own at Step 6c) or re-run15 min122-5Intent misclassifications still in E2E — verify test uses updated code after S2-04 fix15 min132-5GA4/GSC sync has zero test coverage — verify URL matching, incremental sync, token refresh on Backlinko1 hour142-5Readability 2.5s for 145 posts — likely langdetect overhead, add site-level language cache20 min152-5Chunk embeddings section in wrong spec document — move to Step 8b or add note5 min166aFrontend ignores UMAP 2D positions — decide: remove dead pipeline or update frontendDecision176a74% noise rate in Cluster 1 sub-clustering — add noise-rate quality gate (>60% noise → reject split)30 min186aE2E doesn't validate idempotent re-clustering path20 min196aMany-to-many post_clusters schema but one-to-one in practice — clarify in spec5 min206b"People" qualifier less precise than "Marketing" for Cluster 3 — investigate qualifier selection path15 min216cE2E "H2 count: 0" vs "H2s with direct answer: 1/3" — clarify that Extraction counts H2+H3 while E-E-A-T counts H2 only5 min227E2E doesn't run Step 6c first — AI readiness contributes 0% variance, making test less representative15 min237Freshness ↔ internal_links correlation r=0.71 — verify it drops on Backlinko with real link graphVerify249Velocity decline count=1 in processing summary but count=0 in severity table5 min259Proxy decay sample doesn't show decay_severe examples — sort by severity tier5 min2610aSpec still describes cosine-only resolution logic in Section 10f — update to match code10 min2710aAll 373 E2E input pairs have resolution="merge" — E2E Step 8 substitute not using signal-aware resolution30 min2810bai_generated_content NULL sentinel is fragile — write marker or change filter15 min2910bNo retry on transient Claude failures — add single retry with 2s backoff20 min
Total: ~5-6 hours

LOW — Nice to Have
#StepIssueEffort301Homepage (page_type "landing") in dataset cascades through Steps 7, 8b, 9, 10 — add page_type exclusion filter to downstream analysisPost-launch316aNo site-wide stops detected on Copyblogger — verify on BacklinkoVerify326aCluster 3 label "Social Media & People" doesn't match sample titlesVerify336a4 questionable noise reassignments (>2 std from centroid)Expected346bSmart connector didn't trigger — verify compound nouns work on BacklinkoVerify358aEntity display truncation in E2E signal breakdown5 min368bUnused content_chunks/chunk_embeddings tables — drop or implementPost-launch378bskip_body mode not handled — add early return when body_html missing10 min3810aHomepage gets "expand to 2000 words" recommendationResolved by #303910bdifferentiate prompt template never live-testedVerify on Backlinko4010b800-char body excerpt may miss unique content in cann recsInvestigate if quality is low