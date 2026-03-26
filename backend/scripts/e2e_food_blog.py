"""End-to-end pipeline test: food blog (cookieandkate.com).

Completely different content domain from previous tests (dub.co = SaaS, anthropic.com = AI research).
This tests a recipe/lifestyle blog with high topic overlap potential.

Steps:
1. Create site record
2. Crawl via sitemap (cap at 150 posts for speed)
3. Generate embeddings (OpenAI text-embedding-3-small)
4. Run full analysis pipeline (readability, pagerank, intent, clustering, health, cannibalization, problems, recs)
5. Build audit report data
6. Generate PDF report
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

# Load env vars from .env via python-dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('e2e_food_blog')

# Target: a vegetarian food blog — very different from SaaS/AI research
DOMAIN = os.environ.get('E2E_DOMAIN', 'cookieandkate.com')
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')
MAX_PAGES = int(os.environ.get('E2E_MAX_PAGES', '150'))


async def run_e2e():
    conn = await asyncpg.connect(DB_URL)
    total_start = time.time()
    results = {}

    # ─── STEP 0: CREATE OR REUSE SITE ──────────────────────────
    logger.info("=" * 70)
    logger.info(f"E2E TEST: {DOMAIN} (food/recipe blog)")
    logger.info("=" * 70)

    existing = await conn.fetchrow(
        "SELECT id, domain FROM sites WHERE lower(domain) = lower($1)", DOMAIN
    )
    if existing:
        site_id = existing['id']
        # Clean previous data for a fresh run
        logger.info(f"Site exists: {site_id} — cleaning previous data for fresh run")
        await conn.execute("DELETE FROM recommendations WHERE site_id = $1", site_id)
        await conn.execute(
            "DELETE FROM content_problems WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id
        )
        await conn.execute(
            "DELETE FROM cannibalization_pairs WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", site_id
        )
        await conn.execute("DELETE FROM post_clusters WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", site_id)
        await conn.execute("DELETE FROM clusters WHERE site_id = $1", site_id)
        await conn.execute(
            "DELETE FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id
        )
        await conn.execute(
            "DELETE FROM post_embeddings WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id
        )
        await conn.execute("DELETE FROM posts WHERE site_id = $1", site_id)
        await conn.execute("DELETE FROM crawl_jobs WHERE site_id = $1", site_id)
    else:
        row = await conn.fetchrow(
            "INSERT INTO sites (domain, name, cms_type) VALUES ($1, $1, 'sitemap') RETURNING id",
            DOMAIN
        )
        site_id = row['id']
        logger.info(f"Created site: {site_id}")

    # ─── STEP 1: CRAWL ────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 1: SITEMAP CRAWL")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.sitemap import SitemapCrawler
        from app.services.normalizer import save_normalized_posts

        crawler = SitemapCrawler(
            sitemap_url=f"https://{DOMAIN}/sitemap.xml",
            domain=DOMAIN,
            concurrency=10,
            max_pages=MAX_PAGES,
            max_retries=3,
            timeout_seconds=30.0,
        )
        normalized_posts = await crawler.crawl()
        elapsed = time.time() - t
        logger.info(f"Crawled {len(normalized_posts)} posts in {elapsed:.1f}s")

        # Save to DB
        saved = await save_normalized_posts(conn, site_id, normalized_posts)
        results['crawl'] = {'status': 'OK', 'posts': saved, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Saved {saved} posts to DB")

        # Show sample posts
        sample = await conn.fetch(
            "SELECT title, url, word_count FROM posts WHERE site_id = $1 ORDER BY word_count DESC LIMIT 5",
            site_id
        )
        for s in sample:
            logger.info(f"  {s['word_count']:5d}w | {s['title'][:60]}")
    except Exception as e:
        results['crawl'] = {'status': 'FAIL', 'error': str(e)[:300]}
        logger.error(f"Crawl failed: {e}")
        import traceback; traceback.print_exc()
        await conn.close()
        return

    post_count = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id = $1", site_id)
    if post_count == 0:
        logger.error("No posts — aborting")
        await conn.close()
        return

    # ─── STEP 2: EMBEDDINGS ───────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 2: GENERATE EMBEDDINGS (OpenAI text-embedding-3-small)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.embeddings import EmbeddingPipeline
        ep = EmbeddingPipeline()
        embedded = await ep.generate_for_site(conn, site_id)
        elapsed = time.time() - t
        results['embeddings'] = {'status': 'OK', 'embedded': embedded, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Embedded {embedded} posts in {elapsed:.1f}s")
    except Exception as e:
        results['embeddings'] = {'status': 'FAIL', 'error': str(e)[:300]}
        logger.error(f"Embeddings failed: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 3: READABILITY ──────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 3: READABILITY SCORING")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.readability import ReadabilityScorer
        scored = await ReadabilityScorer().score_site(conn, site_id)
        elapsed = time.time() - t
        results['readability'] = {'status': 'OK', 'scored': scored, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Readability: {scored} posts scored in {elapsed:.1f}s")

        rows = await conn.fetch("""
            SELECT title, readability_score, grade_level, word_count
            FROM posts WHERE site_id = $1 AND readability_score IS NOT NULL
            ORDER BY readability_score ASC LIMIT 5
        """, site_id)
        for r in rows:
            logger.info(f"  Flesch {r['readability_score']:.1f} | Grade {r['grade_level']:.1f} | {r['word_count']}w | {r['title'][:50]}")
    except Exception as e:
        results['readability'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Readability failed: {e}")

    # ─── STEP 4: PAGERANK ─────────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 4: INTERNAL PAGERANK")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.pagerank import InternalPageRank
        ranked = await InternalPageRank().compute_for_site(conn, site_id)
        elapsed = time.time() - t
        results['pagerank'] = {'status': 'OK', 'ranked': ranked, 'time': f'{elapsed:.1f}s'}
        logger.info(f"PageRank: {ranked} posts ranked in {elapsed:.1f}s")
    except Exception as e:
        results['pagerank'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"PageRank failed: {e}")

    # ─── STEP 5: INTENT CLASSIFICATION ────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 5: INTENT CLASSIFICATION (fast TF-IDF)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.fast_intent import classify_site_fast
        classified = await classify_site_fast(conn, site_id)
        elapsed = time.time() - t
        results['intent'] = {'status': 'OK', 'classified': classified, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Intent: {classified} posts classified in {elapsed:.1f}s")
    except Exception as e:
        results['intent'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Intent failed: {e}")

    # ─── STEP 6: CLUSTERING ───────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 6: TOPIC CLUSTERING (UMAP + HDBSCAN)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.clustering import TopicClusterer
        n_clusters = await TopicClusterer().cluster_site(conn, site_id, skip_labeling=True)
        elapsed = time.time() - t
        results['clustering'] = {'status': 'OK', 'clusters': n_clusters, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Clustering: {n_clusters} clusters in {elapsed:.1f}s")

        # Label clusters with TF-IDF (fast, no Claude)
        from app.services.fast_cluster_labels import label_clusters_fast
        await label_clusters_fast(conn, site_id)
        logger.info("Cluster labels applied (TF-IDF)")

        clusters = await conn.fetch("""
            SELECT c.id, c.label, c.description,
                   (SELECT count(*) FROM post_clusters pc WHERE pc.cluster_id = c.id) as post_count
            FROM clusters c WHERE c.site_id = $1
            ORDER BY post_count DESC
        """, site_id)
        for c in clusters:
            logger.info(f"  [{c['post_count']:3d} posts] {c['label']}: {(c['description'] or '')[:60]}")
    except Exception as e:
        results['clustering'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Clustering failed: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 6c: AI CITABILITY SCORING (before health so composite includes it) ──
    logger.info("=" * 70)
    logger.info("STEP 6c: AI CITABILITY SCORING")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.ai_citability import AICitabilityService
        ai_scored = await AICitabilityService().score_site(conn, site_id)
        elapsed = time.time() - t
        results['ai_citability'] = {'status': 'OK', 'scored': ai_scored, 'time': f'{elapsed:.1f}s'}
        logger.info(f"AI Citability: {ai_scored} posts scored in {elapsed:.1f}s")
    except Exception as e:
        results['ai_citability'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"AI citability failed: {e}")

    # ─── STEP 7: HEALTH SCORING ───────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 7: HEALTH SCORING (8-factor model, includes AI readiness)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.health_scoring import HealthScorer
        scored = await HealthScorer().score_site(conn, site_id)
        elapsed = time.time() - t
        results['health'] = {'status': 'OK', 'scored': scored, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Health: {scored} posts scored in {elapsed:.1f}s")

        # Show distribution
        avg_score = await conn.fetchval("""
            SELECT AVG(composite_score) FROM post_health_scores phs
            JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1
        """, site_id)
        logger.info(f"  Average health score: {avg_score:.1f}/100")

        roles = await conn.fetch("""
            SELECT role, count(*) as cnt FROM post_health_scores phs
            JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1
            GROUP BY role ORDER BY cnt DESC
        """, site_id)
        for r in roles:
            logger.info(f"  {r['role']}: {r['cnt']} posts")

        # Worst posts
        worst = await conn.fetch("""
            SELECT p.title, phs.composite_score, phs.role
            FROM posts p JOIN post_health_scores phs ON p.id = phs.post_id
            WHERE p.site_id = $1 ORDER BY phs.composite_score ASC LIMIT 5
        """, site_id)
        logger.info("  Worst posts:")
        for w in worst:
            logger.info(f"    {w['composite_score']:.0f}/100 [{w['role']}] {w['title'][:55]}")
    except Exception as e:
        results['health'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Health scoring failed: {e}")

    # ─── STEP 8: CANNIBALIZATION ──────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 8: CANNIBALIZATION DETECTION")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.cannibalization import CannibalizationDetector
        cd = CannibalizationDetector()
        pairs = await cd.detect_for_site(conn, site_id)
        elapsed = time.time() - t
        results['cannibalization'] = {'status': 'OK', 'pairs': pairs, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Cannibalization: {pairs} pairs found in {elapsed:.1f}s")

        cpairs = await conn.fetch("""
            SELECT p1.title as title_a, p2.title as title_b,
                   cp.cosine_similarity, cp.severity
            FROM cannibalization_pairs cp
            JOIN posts p1 ON cp.post_a_id = p1.id
            JOIN posts p2 ON cp.post_b_id = p2.id
            WHERE p1.site_id = $1
            ORDER BY cp.cosine_similarity DESC LIMIT 10
        """, site_id)
        for cp in cpairs:
            logger.info(f"  [{cp['severity']}] {cp['cosine_similarity']:.3f} — {cp['title_a'][:35]} ↔ {cp['title_b'][:35]}")
    except Exception as e:
        results['cannibalization'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Cannibalization failed: {e}")

    # ─── STEP 9: PROBLEM DETECTION ────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 9: PROBLEM DETECTION (8 types)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.problem_detection import ProblemDetector
        problems = await ProblemDetector().detect_all(conn, site_id)
        elapsed = time.time() - t
        results['problems'] = {'status': 'OK', 'counts': problems, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Problems: {problems} in {elapsed:.1f}s")

        # Show by type
        prob_summary = await conn.fetch("""
            SELECT cp.problem_type, cp.severity, count(*) as cnt
            FROM content_problems cp
            JOIN posts p ON cp.post_id = p.id
            WHERE p.site_id = $1
            GROUP BY cp.problem_type, cp.severity
            ORDER BY cnt DESC
        """, site_id)
        for ps in prob_summary:
            logger.info(f"  [{ps['severity']}] {ps['problem_type']}: {ps['cnt']}")
    except Exception as e:
        results['problems'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Problem detection failed: {e}")

    # ─── STEP 10: RECOMMENDATIONS ─────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 10: AI RECOMMENDATIONS (fast rule-based)")
    logger.info("=" * 70)
    try:
        t = time.time()
        from app.services.fast_recommendations import generate_fast_recommendations
        rec_count = await generate_fast_recommendations(conn, site_id)
        elapsed = time.time() - t
        results['recommendations'] = {'status': 'OK', 'count': rec_count, 'time': f'{elapsed:.1f}s'}
        logger.info(f"Recommendations: {rec_count} generated in {elapsed:.1f}s")

        recs = await conn.fetch("""
            SELECT r.recommendation_type, r.priority, r.title, r.summary, p.title as post_title
            FROM recommendations r
            JOIN posts p ON r.post_id = p.id
            WHERE r.site_id = $1
            ORDER BY CASE r.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END
            LIMIT 10
        """, site_id)
        for rec in recs:
            logger.info(f"  [{rec['priority']}] {rec['recommendation_type']}: {rec['post_title'][:40]}")
            logger.info(f"    {(rec['summary'] or '')[:80]}")
    except Exception as e:
        results['recommendations'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"Recommendations failed: {e}")

    # ─── STEP 11: BUILD AUDIT REPORT + PDF ─────────────────────
    logger.info("=" * 70)
    logger.info("STEP 12: GENERATE AUDIT REPORT + PDF")
    logger.info("=" * 70)
    try:
        t = time.time()

        # Use the SAME audit data builder as the API — single source of truth
        from app.routers.audit_report import _build_audit_data_for_site
        site_row = await conn.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
        audit_data = await _build_audit_data_for_site(conn, site_id, dict(site_row))

        # Print audit summary
        logger.info(f"\n{'='*70}")
        logger.info(f"AUDIT REPORT SUMMARY: {DOMAIN}")
        logger.info(f"{'='*70}")
        logger.info(f"  Overall Health:     {audit_data['overall_health']}/100")
        logger.info(f"  Total Posts:        {audit_data['total_posts']}")
        logger.info(f"  Topic Clusters:     {audit_data['cluster_count']}")
        logger.info(f"  Issues Found:       {audit_data['problem_count']}")
        logger.info(f"  Recommendations:    {audit_data['rec_count']}")
        logger.info(f"  Cann. Pairs:        {audit_data['cann_pair_count']}")
        logger.info(f"  Cann. Posts:        {audit_data.get('cann_post_count', 'N/A')}")
        logger.info(f"  Orphan Posts:       {audit_data['orphan_count']}")
        logger.info(f"  Thin Content:       {audit_data['thin_content_count']}")
        logger.info(f"  Exact Duplicates:   {audit_data['exact_duplicate_count']}")
        if audit_data.get('ai_citability_score') is not None:
            logger.info(f"  AI Citability:      {audit_data['ai_citability_score']:.1f}/100")
            logger.info(f"  AI Ready:           {audit_data.get('ai_pct_ready', 0):.1f}%")
        logger.info(f"\n  Key Findings:")
        for f in audit_data.get('key_findings', []):
            logger.info(f"    - {f}")

        # Generate PDF
        from app.services.pdf_report import generate_audit_pdf
        pdf_bytes = generate_audit_pdf(audit_data)

        # Save PDF to project root
        pdf_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            f"{DOMAIN.replace('.', '-')}-audit-report.pdf"
        )
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        elapsed = time.time() - t
        results['pdf'] = {'status': 'OK', 'size_kb': len(pdf_bytes) // 1024, 'path': pdf_path, 'time': f'{elapsed:.1f}s'}
        logger.info(f"PDF generated: {len(pdf_bytes) // 1024}KB → {pdf_path}")

    except Exception as e:
        results['pdf'] = {'status': 'FAIL', 'error': str(e)[:300]}
        logger.error(f"PDF generation failed: {e}")
        import traceback; traceback.print_exc()

    # ─── FINAL SUMMARY ────────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("")
    logger.info("=" * 70)
    logger.info("E2E PIPELINE RESULTS")
    logger.info("=" * 70)
    for step, data in results.items():
        status = data['status']
        icon = "OK" if status == "OK" else "FAIL"
        extra = {k: v for k, v in data.items() if k not in ('status', 'error')}
        logger.info(f"  [{icon}] {step}: {extra}")
        if status == "FAIL":
            logger.info(f"     Error: {data.get('error', 'unknown')[:150]}")

    logger.info(f"\nTotal pipeline time: {total_elapsed:.1f}s")
    logger.info(f"Site ID: {site_id}")
    logger.info(f"Domain: {DOMAIN}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(run_e2e())
