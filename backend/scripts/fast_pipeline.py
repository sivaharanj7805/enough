"""Tier 1 Fast Pipeline — full site analysis in <60 seconds, zero Claude calls.

Usage: python scripts/fast_pipeline.py [site_id]

Each step runs in its own transaction. If a step fails, previous steps
are preserved and the pipeline logs which step failed for restart.
"""

import asyncio
import json
import logging
import os
import sys
import time
from uuid import UUID

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


async def run_step(conn, name: str, func, *args) -> tuple[bool, float, str]:
    """Run a pipeline step in a transaction with error handling.
    
    Returns (success, elapsed_seconds, result_str).
    """
    t = time.time()
    tr = conn.transaction()
    await tr.start()
    try:
        result = await func(conn, *args)
        await tr.commit()
        elapsed = time.time() - t
        result_str = str(result)
        logger.info("✅ %s: %s (%.1fs)", name, result_str, elapsed)
        return True, elapsed, result_str
    except Exception as e:
        await tr.rollback()
        elapsed = time.time() - t
        logger.error("❌ %s FAILED (%.1fs): %s", name, elapsed, e)
        import traceback
        traceback.print_exc()
        return False, elapsed, str(e)


async def step_readability(conn, site_id):
    from app.services.readability import ReadabilityScorer
    rs = ReadabilityScorer()
    return await rs.score_site(conn, site_id)


async def step_pagerank(conn, site_id):
    from app.services.pagerank import InternalPageRank
    pr = InternalPageRank()
    return await pr.compute_for_site(conn, site_id)


async def step_fast_intent(conn, site_id):
    from app.services.fast_intent import classify_site_fast
    return await classify_site_fast(conn, site_id)


async def step_clustering(conn, site_id):
    # Clear old data first (inside transaction)
    old_ids = await conn.fetch("SELECT id FROM clusters WHERE site_id = $1", site_id)
    if old_ids:
        ids = [r["id"] for r in old_ids]
        await conn.execute("DELETE FROM cannibalization_pairs WHERE cluster_id = ANY($1::uuid[])", ids)
        await conn.execute("DELETE FROM post_clusters WHERE cluster_id = ANY($1::uuid[])", ids)
        await conn.execute("DELETE FROM clusters WHERE site_id = $1", site_id)

    from app.services.clustering import TopicClusterer
    tc = TopicClusterer()
    return await tc.cluster_site(conn, site_id, skip_labeling=True)


async def step_fast_labels(conn, site_id):
    from app.services.fast_cluster_labels import label_clusters_fast
    return await label_clusters_fast(conn, site_id)


async def step_health(conn, site_id):
    await conn.execute(
        "DELETE FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)",
        site_id,
    )
    from app.services.health_scoring import HealthScorer
    hs = HealthScorer()
    return await hs.score_site(conn, site_id)


async def step_cannibalization(conn, site_id):
    await conn.execute(
        "DELETE FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)",
        site_id,
    )
    from app.services.cannibalization import CannibalizationDetector
    cd = CannibalizationDetector()
    return await cd.detect_for_site(conn, site_id, max_pairs=200)


async def step_problems(conn, site_id):
    await conn.execute("DELETE FROM content_problems WHERE site_id = $1", site_id)
    from app.services.problem_detection import ProblemDetector
    pd = ProblemDetector()
    return await pd.detect_all(conn, site_id)


async def step_recommendations(conn, site_id):
    await conn.execute("DELETE FROM recommendations WHERE site_id = $1", site_id)
    from app.services.fast_recommendations import generate_fast_recommendations
    return await generate_fast_recommendations(conn, site_id)


STEPS = [
    ("Readability", step_readability),
    ("PageRank", step_pagerank),
    ("Fast Intent", step_fast_intent),
    ("Clustering", step_clustering),
    ("Fast Labels", step_fast_labels),
    ("Health Scoring", step_health),
    ("Cannibalization", step_cannibalization),
    ("Problem Detection", step_problems),
    ("Fast Recommendations", step_recommendations),
]


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    db_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(db_url)

    try:
        site_id = UUID(sys.argv[1]) if len(sys.argv) > 1 else UUID(DEFAULT_SITE_ID)
        pipeline_start = time.time()

        post_count = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id = $1", site_id)
        emb_count = await conn.fetchval(
            "SELECT count(*) FROM post_embeddings WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)",
            site_id,
        )
        logger.info("=== TIER 1 FAST PIPELINE === Posts: %d, Embeddings: %d", post_count, emb_count)

        results = {}
        failed_step = None

        for i, (name, func) in enumerate(STEPS, 1):
            logger.info("--- Step %d: %s ---", i, name)
            success, elapsed, result_str = await run_step(conn, name, func, site_id)
            results[name] = {"success": success, "elapsed": elapsed, "result": result_str}

            if not success:
                failed_step = name
                logger.error("Pipeline stopped at step %d (%s). Previous steps preserved.", i, name)
                break

        total_time = time.time() - pipeline_start
        logger.info("=" * 60)
        if failed_step:
            logger.info("PIPELINE FAILED at '%s' in %.1fs", failed_step, total_time)
        else:
            logger.info("PIPELINE COMPLETE in %.1fs (%.1f min)", total_time, total_time / 60)
        logger.info("=" * 60)

        # Step timing summary
        logger.info("Step timing:")
        for name, r in results.items():
            status = "✅" if r["success"] else "❌"
            logger.info("  %s %s: %.1fs", status, name, r["elapsed"])

        # Final stats (only if pipeline completed)
        if not failed_step:
            stats = {
                "posts": post_count,
                "clusters": await conn.fetchval("SELECT count(*) FROM clusters WHERE site_id = $1", site_id),
                "health_scores": await conn.fetchval(
                    "SELECT count(*) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)",
                    site_id,
                ),
                "health_avg": await conn.fetchval(
                    "SELECT avg(composite_score) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)",
                    site_id,
                ),
                "cann_pairs": await conn.fetchval(
                    "SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)",
                    site_id,
                ),
                "problems": await conn.fetchval("SELECT count(*) FROM content_problems WHERE site_id = $1", site_id),
                "recommendations": await conn.fetchval("SELECT count(*) FROM recommendations WHERE site_id = $1", site_id),
            }
            logger.info("STATS:")
            for k, v in stats.items():
                logger.info("  %s: %s", k, f"{v:.1f}" if isinstance(v, float) else v)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
