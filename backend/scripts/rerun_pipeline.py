"""Re-run the intelligence pipeline on Close.com with all 50 fixes applied.

Skips crawl + embeddings (already in DB). Re-runs everything from readability onward.
"""

import asyncio
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/rerun_pipeline.log"),
    ],
)
logger = logging.getLogger(__name__)

SITE_ID = "32296e5d-7924-4d9f-92b8-7f774c634fad"
USER_ID = "11111111-1111-1111-1111-111111111111"


async def main():
    from uuid import UUID
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    db_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(db_url)

    site_id = UUID(SITE_ID)
    start = time.time()

    # Verify data exists
    post_count = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id = $1", site_id)
    emb_count = await conn.fetchval(
        "SELECT count(*) FROM post_embeddings pe JOIN posts p ON pe.post_id = p.id WHERE p.site_id = $1",
        site_id,
    )
    logger.info("=== Close.com Re-run Pipeline (50 fixes applied) ===")
    logger.info("Posts: %d, Embeddings: %d", post_count, emb_count)

    # Step 1: Readability (free, pure math + language detection)
    logger.info("--- Step 1: Readability Scoring ---")
    t = time.time()
    from app.services.readability import ReadabilityScorer
    scorer = ReadabilityScorer()
    scored = await scorer.score_site(conn, site_id)
    logger.info("Readability: %d posts scored (%.1fs)", scored, time.time() - t)

    # Step 2: PageRank (free, networkx)
    logger.info("--- Step 2: PageRank ---")
    t = time.time()
    from app.services.pagerank import InternalPageRank
    pr = InternalPageRank()
    ranked = await pr.compute_for_site(conn, site_id)
    logger.info("PageRank: %d posts ranked (%.1fs)", ranked, time.time() - t)

    # Step 3: Clustering (with recursive sub-clustering + adaptive UMAP)
    logger.info("--- Step 3: Clustering ---")
    t = time.time()
    # Clear old clusters first
    await conn.execute("DELETE FROM post_clusters WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", site_id)
    await conn.execute("DELETE FROM clusters WHERE site_id = $1", site_id)
    from app.services.clustering import TopicClusterer
    clusterer = TopicClusterer()
    cluster_result = await clusterer.cluster_site(conn, site_id)
    logger.info("Clustering: %s (%.1fs)", cluster_result, time.time() - t)

    # Step 4: Advanced Clustering (c-TF-IDF + hierarchy)
    logger.info("--- Step 4: Advanced Clustering ---")
    t = time.time()
    from app.services.advanced_clustering import AdvancedClusteringService
    adv = AdvancedClusteringService()
    adv_result = await adv.enrich_clusters(conn, site_id)
    logger.info("Advanced Clustering: %s (%.1fs)", adv_result, time.time() - t)

    # Step 5: Health Scoring (with fixes: honest labels, quality bonus, industry benchmarks)
    logger.info("--- Step 5: Health Scoring ---")
    t = time.time()
    # Clear old scores
    await conn.execute("DELETE FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id)
    from app.services.health_scoring import HealthScorer
    hs = HealthScorer()
    health_result = await hs.score_site(conn, site_id)
    logger.info("Health Scoring: %d posts scored (%.1fs)", health_result, time.time() - t)

    # Step 6: Cannibalization (higher thresholds + pruning to 200)
    logger.info("--- Step 6: Cannibalization Detection ---")
    t = time.time()
    # Clear old pairs
    await conn.execute("""
        DELETE FROM cannibalization_pairs
        WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, site_id)
    from app.services.cannibalization import CannibalizationDetector
    cd = CannibalizationDetector()
    cann_result = await cd.detect_for_site(conn, site_id, max_pairs=200)
    logger.info("Cannibalization: %d pairs (%.1fs)", cann_result, time.time() - t)

    # Step 7: Intent Classification (already done — skip if exists)
    intent_count = await conn.fetchval(
        "SELECT count(*) FROM posts WHERE site_id = $1 AND content_intent IS NOT NULL", site_id,
    )
    if intent_count < post_count * 0.8:
        logger.info("--- Step 7: Intent Classification ---")
        t = time.time()
        from app.services.intent_classifier import IntentClassifier
        ic = IntentClassifier()
        intent_result = await ic.classify_site(conn, site_id)
        logger.info("Intent: %s (%.1fs)", intent_result, time.time() - t)
    else:
        logger.info("--- Step 7: Intent — already classified (%d/%d), skipping ---", intent_count, post_count)

    # Step 8: Problem Detection (with FP fixes, proxy decay, severity weights)
    logger.info("--- Step 8: Problem Detection ---")
    t = time.time()
    # Clear old problems
    await conn.execute("DELETE FROM content_problems WHERE site_id = $1", site_id)
    from app.services.problem_detection import ProblemDetector
    pd = ProblemDetector()
    prob_result = await pd.detect_all(conn, site_id)
    logger.info("Problems: %s (%.1fs)", prob_result, time.time() - t)

    # Step 9: Link Suggestions (with cross-cluster prioritization + placement)
    logger.info("--- Step 9: Link Suggestions ---")
    t = time.time()
    await conn.execute("""
        DELETE FROM link_suggestions
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, site_id)
    from app.services.link_suggestions import LinkSuggestionEngine
    lse = LinkSuggestionEngine()
    suggestions = await lse.generate_suggestions(conn, site_id)
    # Store suggestions
    for s in suggestions:
        await conn.execute("""
            INSERT INTO link_suggestions (source_post_id, target_post_id, similarity, suggested_anchor_text, reason, priority)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
        """, s.source_post_id, s.target_post_id, s.similarity, s.suggested_anchor_text, s.reason, s.priority)
    logger.info("Link Suggestions: %d (%.1fs)", len(suggestions), time.time() - t)

    # Step 10: AI Recommendations (crash-resilient, smart truncation)
    logger.info("--- Step 10: AI Recommendations ---")
    t = time.time()
    from app.services.recommendations import RecommendationEngine
    re = RecommendationEngine()
    rec_result = await re.generate_for_site(conn, site_id)
    logger.info("Recommendations: %s (%.1fs)", rec_result, time.time() - t)

    total_time = time.time() - start
    logger.info("=== PIPELINE COMPLETE === Total time: %.1fs (%.1f min)", total_time, total_time / 60)

    # Summary stats
    cluster_count = await conn.fetchval("SELECT count(*) FROM clusters WHERE site_id = $1", site_id)
    cann_count = await conn.fetchval(
        "SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)",
        site_id,
    )
    prob_count = await conn.fetchval("SELECT count(*) FROM content_problems WHERE site_id = $1", site_id)
    rec_count = await conn.fetchval(
        "SELECT count(*) FROM recommendations WHERE site_id = $1", site_id,
    )
    health_avg = await conn.fetchval(
        "SELECT avg(composite_score) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)",
        site_id,
    )

    logger.info("=== FINAL STATS ===")
    logger.info("Posts: %d", post_count)
    logger.info("Clusters: %d", cluster_count)
    logger.info("Cannibalization pairs: %d", cann_count)
    logger.info("Problems: %d", prob_count)
    logger.info("Recommendations: %d", rec_count)
    logger.info("Avg health score: %.1f", health_avg or 0)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
