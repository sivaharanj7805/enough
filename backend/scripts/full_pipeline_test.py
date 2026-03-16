"""Full intelligence pipeline test against real data in Supabase.

Runs every intelligence service end-to-end:
1. Readability scoring
2. Internal PageRank
3. Clustering (UMAP + HDBSCAN + Claude labeling)
4. Advanced clustering (c-TF-IDF, hierarchy, bridge posts, outlier reduction)
5. Health scoring (7-factor model)
6. Cannibalization detection (cosine + auto-calibration)
7. Intent classification (Claude)
8. Content chunking + chunk embeddings
9. BM25 signal
10. Problem detection (8 types)
11. Link suggestions
12. AI recommendations (5 generators via Claude)
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

# Must set env before importing services
os.environ.setdefault('OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
os.environ.setdefault('ANTHROPIC_API_KEY', os.environ.get('ANTHROPIC_API_KEY', ''))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('pipeline')

SITE_ID = uuid.UUID('e990b073-db4d-4ebc-a933-0c78b21ff558')
DB_URL = os.environ['DATABASE_URL']


async def run_pipeline():
    conn = await asyncpg.connect(DB_URL, ssl='require')
    
    post_count = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id = $1", SITE_ID)
    emb_count = await conn.fetchval(
        "SELECT count(*) FROM post_embeddings pe JOIN posts p ON pe.post_id = p.id WHERE p.site_id = $1",
        SITE_ID
    )
    logger.info(f"Site: {SITE_ID}")
    logger.info(f"Posts: {post_count}, Embeddings: {emb_count}")
    
    if post_count == 0:
        logger.error("No posts found! Run smoke test first.")
        await conn.close()
        return
    
    results = {}
    total_start = time.time()
    
    # ─── STEP 1: READABILITY ───────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: READABILITY SCORING")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.readability import ReadabilityScorer
        scorer = ReadabilityScorer()
        scored = await scorer.score_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['readability'] = {'status': 'OK', 'scored': scored, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Readability: {scored} posts scored in {elapsed:.1f}s")
        
        # Show results
        rows = await conn.fetch("""
            SELECT title, readability_score, grade_level, word_count
            FROM posts WHERE site_id = $1 AND readability_score IS NOT NULL
            ORDER BY readability_score ASC LIMIT 5
        """, SITE_ID)
        for r in rows:
            logger.info(f"  Flesch {r['readability_score']:.1f} | Grade {r['grade_level']:.1f} | {r['word_count']}w | {r['title'][:50]}")
    except Exception as e:
        results['readability'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Readability: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 2: INTERNAL PAGERANK ────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 2: INTERNAL PAGERANK")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.pagerank import InternalPageRank
        pr = InternalPageRank()
        ranked = await pr.compute_for_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['pagerank'] = {'status': 'OK', 'ranked': ranked, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ PageRank: {ranked} posts ranked in {elapsed:.1f}s")
        
        rows = await conn.fetch("""
            SELECT p.title, phs.internal_pagerank 
            FROM posts p JOIN post_health_scores phs ON p.id = phs.post_id
            WHERE p.site_id = $1 AND phs.internal_pagerank IS NOT NULL
            ORDER BY phs.internal_pagerank DESC LIMIT 5
        """, SITE_ID)
        for r in rows:
            logger.info(f"  PR {r['internal_pagerank']:.4f} | {r['title'][:60]}")
    except Exception as e:
        results['pagerank'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ PageRank: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 3: CLUSTERING ───────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 3: TOPIC CLUSTERING (UMAP + HDBSCAN + Claude)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.clustering import TopicClusterer
        clusterer = TopicClusterer()
        n_clusters = await clusterer.cluster_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['clustering'] = {'status': 'OK', 'clusters': n_clusters, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Clustering: {n_clusters} clusters in {elapsed:.1f}s")
        
        clusters = await conn.fetch("""
            SELECT c.id, c.label, c.description, 
                   (SELECT count(*) FROM post_clusters pc WHERE pc.cluster_id = c.id) as post_count
            FROM clusters c WHERE c.site_id = $1
            ORDER BY post_count DESC
        """, SITE_ID)
        for c in clusters:
            logger.info(f"  [{c['post_count']} posts] {c['label']}: {(c['description'] or '')[:60]}")
            # Show posts in cluster
            cposts = await conn.fetch("""
                SELECT p.title, p.word_count FROM posts p
                JOIN post_clusters pc ON p.id = pc.post_id
                WHERE pc.cluster_id = $1
                ORDER BY p.word_count DESC
            """, c['id'])
            for cp in cposts:
                logger.info(f"    → {cp['title'][:55]} ({cp['word_count']}w)")
        
        # Show 2D positions
        positioned = await conn.fetchval(
            "SELECT count(*) FROM posts WHERE site_id = $1 AND x_pos IS NOT NULL", SITE_ID
        )
        logger.info(f"  2D positions assigned: {positioned}/{post_count}")
    except Exception as e:
        results['clustering'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Clustering: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 4: ADVANCED CLUSTERING ──────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4: ADVANCED CLUSTERING (c-TF-IDF, hierarchy, bridges)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.advanced_clustering import AdvancedClusteringService
        adv = AdvancedClusteringService()
        adv_result = await adv.enrich_clusters(conn, SITE_ID)
        elapsed = time.time() - t
        results['advanced_clustering'] = {'status': 'OK', 'result': str(adv_result)[:200], 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Advanced clustering in {elapsed:.1f}s")
        logger.info(f"  Result: {adv_result}")
    except Exception as e:
        results['advanced_clustering'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Advanced clustering: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 5: HEALTH SCORING ───────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 5: HEALTH SCORING (7-factor model)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.health_scoring import HealthScorer
        hs = HealthScorer()
        scored = await hs.score_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['health_scoring'] = {'status': 'OK', 'scored': scored, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Health scoring: {scored} posts scored in {elapsed:.1f}s")
        
        rows = await conn.fetch("""
            SELECT p.title, phs.composite_score, phs.role, phs.trend,
                   phs.freshness_score, phs.content_depth_score, phs.internal_link_score, phs.technical_seo_score
            FROM posts p JOIN post_health_scores phs ON p.id = phs.post_id
            WHERE p.site_id = $1
            ORDER BY phs.composite_score DESC
        """, SITE_ID)
        for r in rows:
            logger.info(f"  {r['composite_score']:.0f}/100 [{r['trend']}] [{r['role']}] {r['title'][:45]}")
            logger.info(f"    Fresh:{r['freshness_score']:.0f} Depth:{r['content_depth_score']:.0f} Links:{r['internal_link_score']:.0f} TechSEO:{r['technical_seo_score']:.0f}")
    except Exception as e:
        results['health_scoring'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Health scoring: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 6: CANNIBALIZATION ──────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 6: CANNIBALIZATION DETECTION")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.cannibalization import CannibalizationDetector
        cd = CannibalizationDetector()
        
        # Auto-calibrate thresholds
        thresholds = await cd.calibrate_thresholds(conn, SITE_ID)
        logger.info(f"  Auto-calibrated thresholds: {thresholds}")
        
        # Detect
        pairs = await cd.detect_for_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['cannibalization'] = {'status': 'OK', 'pairs': pairs, 'thresholds': thresholds, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Cannibalization: {pairs} pairs found in {elapsed:.1f}s")
        
        cpairs = await conn.fetch("""
            SELECT p1.title as title_a, p2.title as title_b, 
                   cp.cosine_similarity, cp.overlap_score, cp.severity, cp.overlapping_queries
            FROM cannibalization_pairs cp
            JOIN posts p1 ON cp.post_a_id = p1.id
            JOIN posts p2 ON cp.post_b_id = p2.id
            WHERE p1.site_id = $1
            ORDER BY cp.cosine_similarity DESC
        """, SITE_ID)
        for cp in cpairs:
            logger.info(f"  [{cp['severity']}] {cp['cosine_similarity']:.3f} — {cp['title_a'][:35]} ↔ {cp['title_b'][:35]}")
    except Exception as e:
        results['cannibalization'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Cannibalization: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 7: INTENT CLASSIFICATION ────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 7: INTENT CLASSIFICATION (Claude)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.intent_classifier import IntentClassifier
        ic = IntentClassifier()
        classified = await ic.classify_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['intent'] = {'status': 'OK', 'classified': classified, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Intent classification: {classified} posts classified in {elapsed:.1f}s")
        
        rows = await conn.fetch("""
            SELECT title, content_intent FROM posts 
            WHERE site_id = $1 AND content_intent IS NOT NULL
            ORDER BY title
        """, SITE_ID)
        for r in rows:
            logger.info(f"  [{r['content_intent']}] {r['title'][:60]}")
    except Exception as e:
        results['intent'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Intent classification: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 8: CONTENT CHUNKING ─────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 8: CONTENT CHUNKING + CHUNK EMBEDDINGS")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.content_chunker import ContentChunkerService
        chunker = ContentChunkerService()
        total_chunks = 0
        posts_data = await conn.fetch(
            "SELECT id, title, body_text FROM posts WHERE site_id = $1", SITE_ID
        )
        for pd in posts_data:
            if pd['body_text'] and len(pd['body_text']) > 100:
                chunks = await chunker.chunk_post(conn, pd['id'], SITE_ID, pd['body_text'])
                total_chunks += chunks
        elapsed = time.time() - t
        results['chunking'] = {'status': 'OK', 'chunks': total_chunks, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Chunking: {total_chunks} chunks created in {elapsed:.1f}s")
        
        chunk_count = await conn.fetchval(
            "SELECT count(*) FROM content_chunks cc JOIN posts p ON cc.post_id = p.id WHERE p.site_id = $1",
            SITE_ID
        )
        
        # Now embed the chunks
        logger.info("Embedding chunks...")
        try:
            embedded = await chunker.embed_chunks(conn, SITE_ID)
            logger.info(f"  ✅ {embedded} chunk embeddings generated")
        except Exception as embed_err:
            logger.error(f"  ❌ Chunk embedding failed: {embed_err}")
            import traceback; traceback.print_exc()
        
        chunk_emb_count = await conn.fetchval("""
            SELECT count(*) FROM chunk_embeddings ce 
            JOIN content_chunks cc ON ce.chunk_id = cc.id
            JOIN posts p ON cc.post_id = p.id WHERE p.site_id = $1
        """, SITE_ID)
        logger.info(f"  Chunks in DB: {chunk_count}, Chunk embeddings: {chunk_emb_count}")
    except Exception as e:
        results['chunking'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Chunking: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 8b: BM25 TRIPLE-SIGNAL ───────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 8b: BM25 + TRIPLE-SIGNAL CLASSIFICATION")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.bm25_signal import compute_bm25_for_cluster, classify_triple_signal
        
        # Get all clusters for this site
        cluster_ids = await conn.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", SITE_ID
        )
        
        total_bm25_pairs = 0
        for cl in cluster_ids:
            bm25_scores = await compute_bm25_for_cluster(conn, cl['id'])
            total_bm25_pairs += len(bm25_scores)
            
            # Show top BM25 pairs per cluster
            sorted_pairs = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            for (a, b), score in sorted_pairs:
                ta = await conn.fetchval("SELECT title FROM posts WHERE id = $1", a)
                tb = await conn.fetchval("SELECT title FROM posts WHERE id = $1", b)
                logger.info(f"  BM25 {score:.3f} — {(ta or '')[:35]} ↔ {(tb or '')[:35]}")
        
        elapsed = time.time() - t
        results['bm25'] = {'status': 'OK', 'pairs': total_bm25_pairs, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ BM25: {total_bm25_pairs} pairwise scores in {elapsed:.1f}s")
    except Exception as e:
        results['bm25'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ BM25: {e}")
        import traceback; traceback.print_exc()

    # ─── STEP 9: PROBLEM DETECTION ────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 9: PROBLEM DETECTION (8 types)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.problem_detection import ProblemDetector
        pd = ProblemDetector()
        problems = await pd.detect_all(conn, SITE_ID)
        elapsed = time.time() - t
        results['problems'] = {'status': 'OK', 'counts': problems, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Problems detected in {elapsed:.1f}s: {problems}")
        
        prob_rows = await conn.fetch("""
            SELECT cp.problem_type, cp.severity, p.title, cp.details
            FROM content_problems cp
            JOIN posts p ON cp.post_id = p.id
            WHERE p.site_id = $1
            ORDER BY 
                CASE cp.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                cp.problem_type
        """, SITE_ID)
        for pr in prob_rows:
            details = json.loads(pr['details']) if pr['details'] else {}
            detail_str = json.dumps(details)[:80]
            logger.info(f"  [{pr['severity']}] {pr['problem_type']}: {pr['title'][:40]} — {detail_str}")
    except Exception as e:
        results['problems'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Problem detection: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 10: LINK SUGGESTIONS ────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 10: AUTOMATED LINK SUGGESTIONS")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.link_suggestions import LinkSuggestionEngine
        lse = LinkSuggestionEngine()
        suggestions = await lse.generate_suggestions(conn, SITE_ID)
        elapsed = time.time() - t
        results['link_suggestions'] = {'status': 'OK', 'count': len(suggestions), 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Link suggestions: {len(suggestions)} in {elapsed:.1f}s")
        
        for s in suggestions[:10]:
            logger.info(f"  [{s.priority}] {s.source_title[:30]} → {s.target_title[:30]} (sim:{s.similarity:.2f}) anchor:'{s.suggested_anchor_text[:30]}'")
    except Exception as e:
        results['link_suggestions'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Link suggestions: {e}")
        import traceback; traceback.print_exc()
    
    # ─── STEP 11: AI RECOMMENDATIONS (Claude) ─────────────────
    logger.info("=" * 60)
    logger.info("STEP 11: AI RECOMMENDATIONS (5 generators via Claude)")
    logger.info("=" * 60)
    try:
        t = time.time()
        from app.services.recommendations import RecommendationEngine
        re = RecommendationEngine()
        rec_counts = await re.generate_for_site(conn, SITE_ID)
        elapsed = time.time() - t
        results['recommendations'] = {'status': 'OK', 'counts': rec_counts, 'time': f'{elapsed:.1f}s'}
        logger.info(f"✅ Recommendations generated in {elapsed:.1f}s: {rec_counts}")
        
        recs = await conn.fetch("""
            SELECT r.recommendation_type, r.priority, r.title, r.summary,
                   r.specific_actions, r.ai_generated_content, r.estimated_effort_hours, r.estimated_impact,
                   p.title as post_title
            FROM recommendations r
            JOIN posts p ON r.post_id = p.id
            WHERE r.site_id = $1
            ORDER BY 
                CASE r.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END
        """, SITE_ID)
        for rec in recs:
            actions = json.loads(rec['specific_actions']) if rec['specific_actions'] else []
            ai = json.loads(rec['ai_generated_content']) if rec['ai_generated_content'] else {}
            action_str = "; ".join(str(a)[:50] for a in actions[:3]) if actions else "no actions"
            confidence = ai.get('confidence', 'N/A')
            logger.info(f"  [{rec['priority']}] {rec['recommendation_type']}: {rec['post_title'][:50]}")
            logger.info(f"    Impact: {rec['estimated_impact']} | Effort: {rec['estimated_effort_hours']}h | Confidence: {confidence}")
            logger.info(f"    Summary: {(rec['summary'] or '')[:100]}")
            logger.info(f"    Actions: {action_str}")
    except Exception as e:
        results['recommendations'] = {'status': 'FAIL', 'error': str(e)[:200]}
        logger.error(f"❌ Recommendations: {e}")
        import traceback; traceback.print_exc()
    
    # ─── FINAL SUMMARY ────────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("")
    logger.info("=" * 60)
    logger.info("FULL PIPELINE RESULTS")
    logger.info("=" * 60)
    for step, data in results.items():
        status = data['status']
        icon = "✅" if status == "OK" else "❌"
        extra = {k: v for k, v in data.items() if k not in ('status', 'error')}
        logger.info(f"  {icon} {step}: {extra}")
        if status == "FAIL":
            logger.info(f"     Error: {data.get('error', 'unknown')[:100]}")
    
    logger.info(f"\nTotal pipeline time: {total_elapsed:.1f}s")
    logger.info(f"Site ID: {SITE_ID}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run_pipeline())
