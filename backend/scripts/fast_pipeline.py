"""Tier 1 Fast Pipeline — full site analysis in <60 seconds, zero Claude calls.

Usage: python scripts/fast_pipeline.py [site_id]
"""

import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/fast_pipeline.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_SITE_ID = "32296e5d-7924-4d9f-92b8-7f774c634fad"


async def main():
    from uuid import UUID
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    db_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(db_url)

    site_id = UUID(sys.argv[1]) if len(sys.argv) > 1 else UUID(DEFAULT_SITE_ID)
    pipeline_start = time.time()

    post_count = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id = $1", site_id)
    emb_count = await conn.fetchval("SELECT count(*) FROM post_embeddings WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id)
    logger.info("=== TIER 1 FAST PIPELINE === Posts: %d, Embeddings: %d", post_count, emb_count)

    # Step 1: Readability (pure compute)
    logger.info("--- Step 1: Readability ---")
    t = time.time()
    from app.services.readability import ReadabilityScorer
    rs = ReadabilityScorer()
    scored = await rs.score_site(conn, site_id)
    logger.info("✅ Readability: %d posts (%.1fs)", scored, time.time() - t)

    # Step 2: PageRank (pure compute)
    logger.info("--- Step 2: PageRank ---")
    t = time.time()
    from app.services.pagerank import InternalPageRank
    pr = InternalPageRank()
    ranked = await pr.compute_for_site(conn, site_id)
    logger.info("✅ PageRank: %d posts (%.1fs)", ranked, time.time() - t)

    # Step 3: Intent Classification (pattern-based, no Claude)
    logger.info("--- Step 3: Fast Intent ---")
    t = time.time()
    from app.services.fast_intent import classify_site_fast
    classified = await classify_site_fast(conn, site_id)
    logger.info("✅ Intent: %d posts (%.1fs)", classified, time.time() - t)

    # Step 4: Clustering (UMAP + HDBSCAN, local ML)
    logger.info("--- Step 4: Clustering ---")
    t = time.time()
    # Clear old cluster data
    await conn.execute("""
        DELETE FROM post_clusters WHERE cluster_id IN (
            SELECT id FROM clusters WHERE site_id = $1
        )
    """, site_id)
    await conn.execute("DELETE FROM clusters WHERE site_id = $1", site_id)
    
    from app.services.clustering import TopicClusterer
    tc = TopicClusterer()
    cluster_result = await tc.cluster_site(conn, site_id, skip_labeling=True)
    logger.info("✅ Clustering: %s (%.1fs)", cluster_result, time.time() - t)

    # Step 5: Fast Cluster Labels (TF-IDF, no Claude)
    logger.info("--- Step 5: Fast Labels ---")
    t = time.time()
    from app.services.fast_cluster_labels import label_clusters_fast
    labeled = await label_clusters_fast(conn, site_id)
    logger.info("✅ Labels: %d clusters (%.1fs)", labeled, time.time() - t)

    # Step 6: Health Scoring (pure compute)
    logger.info("--- Step 6: Health Scoring ---")
    t = time.time()
    await conn.execute("DELETE FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id)
    from app.services.health_scoring import HealthScorer
    hs = HealthScorer()
    health_result = await hs.score_site(conn, site_id)
    logger.info("✅ Health: %d scored (%.1fs)", health_result, time.time() - t)

    # Step 7: Cannibalization (pgvector HNSW)
    logger.info("--- Step 7: Cannibalization ---")
    t = time.time()
    await conn.execute("""
        DELETE FROM cannibalization_pairs
        WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, site_id)
    from app.services.cannibalization import CannibalizationDetector
    cd = CannibalizationDetector()
    cann_result = await cd.detect_for_site(conn, site_id, max_pairs=200)
    logger.info("✅ Cannibalization: %d pairs (%.1fs)", cann_result, time.time() - t)

    # Step 8: Problem Detection (pure compute)
    logger.info("--- Step 8: Problem Detection ---")
    t = time.time()
    await conn.execute("DELETE FROM content_problems WHERE site_id = $1", site_id)
    from app.services.problem_detection import ProblemDetector
    pd = ProblemDetector()
    prob_result = await pd.detect_all(conn, site_id)
    logger.info("✅ Problems: %s (%.1fs)", prob_result, time.time() - t)

    # Step 9: Fast Recommendations (template-based, no Claude)
    logger.info("--- Step 9: Fast Recommendations ---")
    t = time.time()
    from app.services.fast_recommendations import generate_fast_recommendations
    rec_count = await generate_fast_recommendations(conn, site_id)
    logger.info("✅ Recommendations: %d generated (%.1fs)", rec_count, time.time() - t)

    total_time = time.time() - pipeline_start
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1fs (%.1f min)", total_time, total_time / 60)
    logger.info("=" * 60)

    # Final stats
    stats = {
        "posts": post_count,
        "clusters": await conn.fetchval("SELECT count(*) FROM clusters WHERE site_id = $1", site_id),
        "health_scores": await conn.fetchval("SELECT count(*) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id),
        "health_avg": await conn.fetchval("SELECT avg(composite_score) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id),
        "cann_pairs": await conn.fetchval("SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id),
        "problems": await conn.fetchval("SELECT count(*) FROM content_problems WHERE site_id = $1", site_id),
        "recommendations": await conn.fetchval("SELECT count(*) FROM recommendations WHERE site_id = $1", site_id),
    }

    logger.info("STATS:")
    for k, v in stats.items():
        if isinstance(v, float):
            logger.info("  %s: %.1f", k, v)
        else:
            logger.info("  %s: %s", k, v)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
