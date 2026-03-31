#!/usr/bin/env python3
"""
Full intelligence pipeline test against close.com (SaaS CRM blog, 959 posts).
Tests the entire intelligence layer at scale.

Expected cost: ~$5-10 (embeddings + Claude API calls)
Expected runtime: ~20-40 minutes
"""

import asyncio
import asyncpg
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.services.sitemap import SitemapCrawler
from app.services.normalizer import save_normalized_posts
from app.services.embeddings import EmbeddingPipeline
from app.services.readability import ReadabilityScorer
from app.services.pagerank import InternalPageRank
from app.services.clustering import TopicClusterer
from app.services.advanced_clustering import AdvancedClusteringService
from app.services.health_scoring import HealthScorer
from app.services.cannibalization import CannibalizationDetector
from app.services.intent_classifier import IntentClassifier
from app.services.content_chunker import ContentChunkerService
from app.services.bm25_signal import compute_bm25_for_cluster
from app.services.problem_detection import ProblemDetector
from app.services.link_suggestions import LinkSuggestionEngine
from app.services.recommendations import RecommendationEngine
from app.utils.token_guard import truncate_for_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────
SITE_URL = "https://www.close.com"
SITE_NAME = "Close CRM"
SITE_DOMAIN = "close.com"
CMS_TYPE = "sitemap"
MAX_POSTS = 600  # Cap at 600 to control costs while exceeding 500

# We'll create a new site entry
USER_ID = "11111111-1111-1111-1111-111111111111"  # Dummy user
USER_EMAIL = "pipeline-test@tended.app"


async def main():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        return

    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    logger.info("Connected to database")
    
    results = {}
    total_start = time.time()
    
    try:
        # ─── STEP 0: CREATE SITE ──────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 0: SETUP — Creating site entry for close.com")
        logger.info("=" * 60)
        
        # Check if site already exists
        existing = await conn.fetchrow(
            "SELECT id FROM sites WHERE domain = $1", SITE_DOMAIN
        )
        
        if existing:
            SITE_ID = existing["id"]
            post_count = await conn.fetchval(
                "SELECT count(*) FROM posts WHERE site_id = $1", SITE_ID
            )
            emb_count = await conn.fetchval("""
                SELECT count(*) FROM post_embeddings pe
                JOIN posts p ON pe.post_id = p.id WHERE p.site_id = $1
            """, SITE_ID)
            logger.info(f"Site already exists: {SITE_ID}, {post_count} posts, {emb_count} embeddings")
            
            if post_count >= 400 and emb_count >= 400:
                # Check if earlier pipeline steps are done
                cluster_count = await conn.fetchval(
                    "SELECT count(*) FROM clusters WHERE site_id = $1", SITE_ID
                )
                if cluster_count > 0:
                    logger.info(f"Pipeline partially complete ({cluster_count} clusters). Resuming from BM25.")
                    await run_pipeline_from_bm25(conn, SITE_ID, results)
                else:
                    logger.info("Sufficient posts exist. Running full pipeline.")
                    await run_pipeline(conn, SITE_ID, results)
                return
        else:
            # Create auth user first (required FK)
            user_id = uuid.UUID(USER_ID)
            await conn.execute("""
                INSERT INTO auth.users (id, email, encrypted_password, created_at, updated_at)
                VALUES ($1, $2, 'dummy', now(), now())
                ON CONFLICT (id) DO NOTHING
            """, user_id, USER_EMAIL)
            
            # Create profile
            await conn.execute("""
                INSERT INTO profiles (id, email, full_name, subscription_tier, created_at)
                VALUES ($1, $2, $3, 'growth', now())
                ON CONFLICT (id) DO NOTHING
            """, user_id, USER_EMAIL, "Pipeline Test")
            
            # Create site (columns: name, domain, cms_type, sitemap_url)
            SITE_ID = uuid.uuid4()
            await conn.execute("""
                INSERT INTO sites (id, user_id, name, domain, cms_type, sitemap_url, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, now())
            """, SITE_ID, user_id, SITE_NAME, SITE_DOMAIN, CMS_TYPE, f"{SITE_URL}/sitemap.xml")
            
            logger.info(f"Created site: {SITE_ID}")
        
        # ─── STEP 1: CRAWL ────────────────────────────────────
        logger.info("=" * 60)
        logger.info(f"STEP 1: CRAWL — Crawling close.com/blog (max {MAX_POSTS} posts)")
        logger.info("=" * 60)
        
        t = time.time()
        # Blog URLs start at index 899 in close.com's sitemap.
        # Pre-filter to only crawl /blog/ pages, avoiding 899 non-blog pages.
        import httpx as httpx_lib
        import re as re_lib
        
        logger.info("Pre-fetching sitemap to filter blog URLs only...")
        async with httpx_lib.AsyncClient(follow_redirects=True, timeout=15) as http:
            resp = await http.get(f"{SITE_URL}/sitemap.xml")
            all_sitemap_urls = re_lib.findall(r'<loc>([^<]+)</loc>', resp.text)
        
        blog_urls = [u for u in all_sitemap_urls if "/blog/" in u]
        logger.info(f"Sitemap: {len(all_sitemap_urls)} total, {len(blog_urls)} blog URLs")
        
        # Cap at MAX_POSTS
        if len(blog_urls) > MAX_POSTS:
            blog_urls = blog_urls[:MAX_POSTS]
            logger.info(f"Capped at {MAX_POSTS} blog URLs")
        
        # Use SitemapCrawler but with a high max_pages and a custom _discover_urls
        crawler = SitemapCrawler(
            sitemap_url=f"{SITE_URL}/sitemap.xml",
            domain=SITE_DOMAIN,
            max_pages=len(blog_urls) + 10,
            concurrency=10,
        )
        # Monkey-patch _discover_urls to return only blog URLs
        async def _blog_urls_only():
            return blog_urls
        crawler._discover_urls = _blog_urls_only
        
        raw_posts = await crawler.crawl()
        logger.info(f"Crawler returned {len(raw_posts)} posts")
        
        blog_posts = raw_posts  # Already filtered to /blog/
        
        # Save to DB - save_normalized_posts expects NormalizedPost objects
        saved = await save_normalized_posts(conn, SITE_ID, blog_posts)
        elapsed = time.time() - t
        
        post_count = await conn.fetchval(
            "SELECT count(*) FROM posts WHERE site_id = $1", SITE_ID
        )
        results["crawl"] = {
            "status": "OK",
            "raw": len(raw_posts),
            "blog": len(blog_posts),
            "saved": saved,
            "in_db": post_count,
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Crawl: {post_count} posts in DB in {elapsed:.1f}s")
        
        # ─── STEP 2: EMBEDDINGS ───────────────────────────────
        logger.info("=" * 60)
        logger.info("STEP 2: EMBEDDINGS — Generating OpenAI embeddings")
        logger.info("=" * 60)
        
        t = time.time()
        emb_pipeline = EmbeddingPipeline()
        embedded = await emb_pipeline.generate_for_site(conn, SITE_ID)
        elapsed = time.time() - t
        
        emb_count = await conn.fetchval("""
            SELECT count(*) FROM post_embeddings pe
            JOIN posts p ON pe.post_id = p.id
            WHERE p.site_id = $1
        """, SITE_ID)
        
        results["embeddings"] = {
            "status": "OK",
            "new": embedded,
            "total": emb_count,
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Embeddings: {emb_count} total in {elapsed:.1f}s")
        
        # ─── RUN PIPELINE ─────────────────────────────────────
        await run_pipeline(conn, SITE_ID, results)
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        total_elapsed = time.time() - total_start
        
        # ─── SUMMARY ──────────────────────────────────────────
        logger.info("\n" + "=" * 70)
        logger.info(f"PIPELINE COMPLETE — Total: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
        logger.info("=" * 70)
        
        for step, data in results.items():
            status = data.get("status", "?")
            t = data.get("time", "?")
            icon = "✅" if status == "OK" else "❌"
            # Remove status and time for display
            detail = {k: v for k, v in data.items() if k not in ("status", "time")}
            logger.info(f"  {icon} {step}: {json.dumps(detail)} [{t}]")
        
        logger.info(f"\nTotal time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
        
        await conn.close()


async def run_pipeline_from_bm25(conn, site_id, results):
    """Resume pipeline from BM25 step (steps 11-14)."""
    post_count = await conn.fetchval(
        "SELECT count(*) FROM posts WHERE site_id = $1", site_id
    )
    logger.info(f"\nResuming pipeline from BM25 for {post_count} posts")
    
    # ─── STEP 11: BM25 TRIPLE SIGNAL ─────────────────────
    logger.info("=" * 60)
    logger.info("STEP 11: BM25 TRIPLE SIGNAL")
    logger.info("=" * 60)
    t = time.time()
    try:
        cluster_ids = await conn.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id
        )
        total_bm25_pairs = 0
        for cl in cluster_ids:
            cl_size = await conn.fetchval(
                "SELECT count(*) FROM post_clusters WHERE cluster_id = $1", cl["id"]
            )
            if cl_size > 100:
                logger.warning(f"  Skipping BM25 for cluster {cl['id']} ({cl_size} posts — too large)")
                continue
            bm25_scores = await compute_bm25_for_cluster(conn, cl["id"])
            total_bm25_pairs += len(bm25_scores)
        
        elapsed = time.time() - t
        results["bm25"] = {"status": "OK", "pairs": total_bm25_pairs, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ BM25: {total_bm25_pairs} pairwise scores in {elapsed:.1f}s")
    except Exception as e:
        results["bm25"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ BM25: {e}")

    # ─── STEP 12: PROBLEM DETECTION ──────────────────────
    logger.info("=" * 60)
    logger.info("STEP 12: PROBLEM DETECTION")
    logger.info("=" * 60)
    t = time.time()
    try:
        pd = ProblemDetector()
        counts = await pd.detect_all(conn, site_id)
        elapsed = time.time() - t
        results["problems"] = {"status": "OK", "counts": counts, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ Problems: {sum(counts.values())} total in {elapsed:.1f}s")
        for ptype, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {ptype}: {cnt}")
    except Exception as e:
        results["problems"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Problems: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 13: LINK SUGGESTIONS ───────────────────────
    logger.info("=" * 60)
    logger.info("STEP 13: LINK SUGGESTIONS")
    logger.info("=" * 60)
    t = time.time()
    try:
        ls = LinkSuggestionEngine()
        suggestions = await ls.generate_suggestions(conn, site_id)
        elapsed = time.time() - t
        results["link_suggestions"] = {"status": "OK", "count": suggestions, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ Link suggestions: {suggestions} in {elapsed:.1f}s")
    except Exception as e:
        results["link_suggestions"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Link suggestions: {e}")

    # ─── STEP 14: RECOMMENDATIONS ────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 14: AI RECOMMENDATIONS (Claude)")
    logger.info("=" * 60)
    t = time.time()
    try:
        re = RecommendationEngine()
        rec_count = await re.generate_for_site(conn, site_id)
        elapsed = time.time() - t
        
        rec_dist = await conn.fetch("""
            SELECT recommendation_type, count(*) as cnt
            FROM recommendations WHERE site_id = $1
            GROUP BY recommendation_type ORDER BY cnt DESC
        """, site_id)
        
        results["recommendations"] = {
            "status": "OK",
            "count": rec_count,
            "types": {r["recommendation_type"]: r["cnt"] for r in rec_dist},
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Recommendations: {rec_count} in {elapsed:.1f}s")
        for r in rec_dist:
            logger.info(f"  {r['recommendation_type']}: {r['cnt']}")
    except Exception as e:
        results["recommendations"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Recommendations: {e}")
        import traceback; traceback.print_exc()


async def run_pipeline(conn, site_id, results):
    """Run all intelligence pipeline steps."""
    
    post_count = await conn.fetchval(
        "SELECT count(*) FROM posts WHERE site_id = $1", site_id
    )
    logger.info(f"\nRunning pipeline on {post_count} posts for site {site_id}")
    
    # ─── STEP 3: READABILITY ──────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 3: READABILITY")
    logger.info("=" * 60)
    t = time.time()
    try:
        scorer = ReadabilityScorer()
        scored = await scorer.score_site(conn, site_id)
        elapsed = time.time() - t
        results["readability"] = {"status": "OK", "scored": scored, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ Readability: {scored} posts scored in {elapsed:.1f}s")
        
        # Sample scores
        samples = await conn.fetch("""
            SELECT p.title, p.readability_score, p.grade_level
            FROM posts p WHERE p.site_id = $1 AND p.readability_score IS NOT NULL
            ORDER BY p.readability_score ASC LIMIT 5
        """, site_id)
        for s in samples:
            logger.info(f"  Flesch {s['readability_score']:.0f} Grade {s['grade_level']:.1f} — {s['title'][:50]}")
    except Exception as e:
        results["readability"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Readability: {e}")
    
    # ─── STEP 4: PAGERANK ─────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4: PAGERANK")
    logger.info("=" * 60)
    t = time.time()
    try:
        pr = InternalPageRank()
        ranked = await pr.compute_for_site(conn, site_id)
        elapsed = time.time() - t
        results["pagerank"] = {"status": "OK", "ranked": ranked, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ PageRank: {ranked} posts ranked in {elapsed:.1f}s")
        
        # Top PageRank posts
        # Check if internal_pagerank is in post_health_scores or posts
        top = await conn.fetch("""
            SELECT p.title, phs.internal_pagerank
            FROM post_health_scores phs
            JOIN posts p ON phs.post_id = p.id
            WHERE p.site_id = $1 AND phs.internal_pagerank IS NOT NULL
            ORDER BY phs.internal_pagerank DESC LIMIT 5
        """, site_id)
        for r in top:
            logger.info(f"  PR {r['internal_pagerank']:.4f} — {r['title'][:50]}")
    except Exception as e:
        results["pagerank"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ PageRank: {e}")

    # ─── STEP 5: CLUSTERING ───────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 5: CLUSTERING (UMAP + HDBSCAN + Claude)")
    logger.info("=" * 60)
    t = time.time()
    try:
        clusterer = TopicClusterer()
        cluster_count = await clusterer.cluster_site(conn, site_id)
        elapsed = time.time() - t
        
        clusters = await conn.fetch("""
            SELECT c.id, c.label, c.description,
                   (SELECT count(*) FROM post_clusters pc WHERE pc.cluster_id = c.id) as post_count
            FROM clusters c WHERE c.site_id = $1
            ORDER BY post_count DESC
        """, site_id)
        
        results["clustering"] = {
            "status": "OK", "clusters": cluster_count,
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Clustering: {cluster_count} clusters in {elapsed:.1f}s")
        for c in clusters[:10]:
            logger.info(f"  [{c['post_count']} posts] {c['label']}: {(c['description'] or '')[:80]}")
    except Exception as e:
        results["clustering"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Clustering: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 6: ADVANCED CLUSTERING ──────────────────────
    logger.info("=" * 60)
    logger.info("STEP 6: ADVANCED CLUSTERING (c-TF-IDF, hierarchy)")
    logger.info("=" * 60)
    t = time.time()
    try:
        adv = AdvancedClusteringService()
        adv_result = await adv.enrich_clusters(conn, site_id)
        elapsed = time.time() - t
        results["advanced_clustering"] = {"status": "OK", "time": f"{elapsed:.1f}s", **adv_result}
        logger.info(f"✅ Advanced clustering in {elapsed:.1f}s: {adv_result}")
    except Exception as e:
        results["advanced_clustering"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Advanced clustering: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 7: HEALTH SCORING ───────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 7: HEALTH SCORING")
    logger.info("=" * 60)
    t = time.time()
    try:
        hs = HealthScorer()
        scored = await hs.score_site(conn, site_id)
        elapsed = time.time() - t
        
        # Distribution
        dist = await conn.fetch("""
            SELECT trend, count(*) as cnt
            FROM post_health_scores phs
            JOIN posts p ON phs.post_id = p.id
            WHERE p.site_id = $1
            GROUP BY trend ORDER BY cnt DESC
        """, site_id)
        
        results["health_scoring"] = {
            "status": "OK", "scored": scored,
            "distribution": {r["trend"]: r["cnt"] for r in dist},
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Health scoring: {scored} posts in {elapsed:.1f}s")
        for d in dist:
            logger.info(f"  {d['trend']}: {d['cnt']}")
    except Exception as e:
        results["health_scoring"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Health scoring: {e}")

    # ─── STEP 8: CANNIBALIZATION ──────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 8: CANNIBALIZATION DETECTION")
    logger.info("=" * 60)
    t = time.time()
    try:
        cd = CannibalizationDetector()
        await cd.calibrate_thresholds(conn, site_id)
        pair_count = await cd.detect_for_site(conn, site_id)
        elapsed = time.time() - t
        
        # Severity distribution
        sev = await conn.fetch("""
            SELECT severity, count(*) as cnt
            FROM cannibalization_pairs cp
            JOIN posts pa ON cp.post_a_id = pa.id
            WHERE pa.site_id = $1
            GROUP BY severity ORDER BY cnt DESC
        """, site_id)
        
        results["cannibalization"] = {
            "status": "OK", "pairs": pair_count,
            "severity": {r["severity"]: r["cnt"] for r in sev},
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Cannibalization: {pair_count} pairs in {elapsed:.1f}s")
        for s in sev:
            logger.info(f"  {s['severity']}: {s['cnt']}")
        
        # Top 5 pairs
        top_pairs = await conn.fetch("""
            SELECT pa.title as title_a, pb.title as title_b, cp.cosine_similarity, cp.severity
            FROM cannibalization_pairs cp
            JOIN posts pa ON cp.post_a_id = pa.id
            JOIN posts pb ON cp.post_b_id = pb.id
            WHERE pa.site_id = $1
            ORDER BY cp.cosine_similarity DESC LIMIT 5
        """, site_id)
        for p in top_pairs:
            logger.info(f"  [{p['severity']}] cos={p['cosine_similarity']:.3f} — {p['title_a'][:30]} ↔ {p['title_b'][:30]}")
    except Exception as e:
        results["cannibalization"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Cannibalization: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 9: INTENT CLASSIFICATION ────────────────────
    logger.info("=" * 60)
    logger.info("STEP 9: INTENT CLASSIFICATION")
    logger.info("=" * 60)
    t = time.time()
    try:
        ic = IntentClassifier()
        classified = await ic.classify_site(conn, site_id)
        elapsed = time.time() - t
        
        # Intent distribution
        intent_dist = await conn.fetch("""
            SELECT content_intent as search_intent, count(*) as cnt
            FROM posts WHERE site_id = $1 AND content_intent IS NOT NULL
            GROUP BY content_intent ORDER BY cnt DESC
        """, site_id)
        
        results["intent"] = {
            "status": "OK", "classified": classified,
            "distribution": {r["search_intent"]: r["cnt"] for r in intent_dist},
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Intent: {classified} classified in {elapsed:.1f}s")
        for i in intent_dist:
            logger.info(f"  {i['search_intent']}: {i['cnt']}")
    except Exception as e:
        results["intent"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Intent: {e}")

    # ─── STEP 10: CONTENT CHUNKING + EMBEDDINGS ──────────
    logger.info("=" * 60)
    logger.info("STEP 10: CONTENT CHUNKING + CHUNK EMBEDDINGS")
    logger.info("=" * 60)
    t = time.time()
    try:
        chunker = ContentChunkerService()
        
        # Get all posts with body text
        posts_data = await conn.fetch("""
            SELECT id, body_text FROM posts
            WHERE site_id = $1 AND body_text IS NOT NULL
            ORDER BY id
        """, site_id)
        
        total_chunks = 0
        for pd in posts_data:
            chunks = await chunker.chunk_post(conn, pd["id"], site_id, pd["body_text"])
            total_chunks += chunks
        
        # Now embed the chunks
        logger.info(f"Created {total_chunks} chunks, now embedding...")
        embedded = await chunker.embed_chunks(conn, site_id)
        
        elapsed = time.time() - t
        results["chunking"] = {
            "status": "OK",
            "chunks": total_chunks,
            "embedded": embedded,
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Chunking: {total_chunks} chunks, {embedded} embedded in {elapsed:.1f}s")
    except Exception as e:
        results["chunking"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Chunking: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 11: BM25 TRIPLE SIGNAL ─────────────────────
    logger.info("=" * 60)
    logger.info("STEP 11: BM25 TRIPLE SIGNAL")
    logger.info("=" * 60)
    t = time.time()
    try:
        cluster_ids = await conn.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id
        )
        total_bm25_pairs = 0
        for cl in cluster_ids:
            # Check cluster size — skip BM25 for clusters >100 posts (O(n²) memory)
            cl_size = await conn.fetchval(
                "SELECT count(*) FROM post_clusters WHERE cluster_id = $1", cl["id"]
            )
            if cl_size > 100:
                logger.warning(f"  Skipping BM25 for cluster {cl['id']} ({cl_size} posts — too large)")
                continue
            bm25_scores = await compute_bm25_for_cluster(conn, cl["id"])
            total_bm25_pairs += len(bm25_scores)
        
        elapsed = time.time() - t
        results["bm25"] = {"status": "OK", "pairs": total_bm25_pairs, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ BM25: {total_bm25_pairs} pairwise scores in {elapsed:.1f}s")
    except Exception as e:
        results["bm25"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ BM25: {e}")

    # ─── STEP 12: PROBLEM DETECTION ──────────────────────
    logger.info("=" * 60)
    logger.info("STEP 12: PROBLEM DETECTION")
    logger.info("=" * 60)
    t = time.time()
    try:
        pd = ProblemDetector()
        counts = await pd.detect_all(conn, site_id)
        elapsed = time.time() - t
        results["problems"] = {"status": "OK", "counts": counts, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ Problems: {sum(counts.values())} total in {elapsed:.1f}s")
        for ptype, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {ptype}: {cnt}")
    except Exception as e:
        results["problems"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Problems: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 13: LINK SUGGESTIONS ───────────────────────
    logger.info("=" * 60)
    logger.info("STEP 13: LINK SUGGESTIONS")
    logger.info("=" * 60)
    t = time.time()
    try:
        ls = LinkSuggestionEngine()
        suggestions = await ls.generate_suggestions(conn, site_id)
        elapsed = time.time() - t
        results["link_suggestions"] = {"status": "OK", "count": suggestions, "time": f"{elapsed:.1f}s"}
        logger.info(f"✅ Link suggestions: {suggestions} in {elapsed:.1f}s")
    except Exception as e:
        results["link_suggestions"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Link suggestions: {e}")

    # ─── STEP 14: RECOMMENDATIONS ────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 14: AI RECOMMENDATIONS (Claude)")
    logger.info("=" * 60)
    t = time.time()
    try:
        re = RecommendationEngine()
        rec_count = await re.generate_for_site(conn, site_id)
        elapsed = time.time() - t
        
        # Type distribution
        rec_dist = await conn.fetch("""
            SELECT recommendation_type, count(*) as cnt
            FROM recommendations WHERE site_id = $1
            GROUP BY recommendation_type ORDER BY cnt DESC
        """, site_id)
        
        results["recommendations"] = {
            "status": "OK",
            "count": rec_count,
            "types": {r["recommendation_type"]: r["cnt"] for r in rec_dist},
            "time": f"{elapsed:.1f}s",
        }
        logger.info(f"✅ Recommendations: {rec_count} in {elapsed:.1f}s")
        for r in rec_dist:
            logger.info(f"  {r['recommendation_type']}: {r['cnt']}")
    except Exception as e:
        results["recommendations"] = {"status": "FAIL", "error": str(e)[:200], "time": f"{time.time()-t:.1f}s"}
        logger.error(f"❌ Recommendations: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
