"""Intelligence endpoints — clustering, cannibalization, health, consolidation, oracle."""

import logging
from typing import Annotated
from uuid import UUID

import asyncpg


# Database-level pipeline lock helper (replaces process-local set)
async def _try_acquire_pipeline_lock(db: asyncpg.Connection, site_id: UUID) -> bool:
    """Attempt to acquire a database-level lock for a site's pipeline.

    Returns True if lock acquired (no pipeline running), False if already running.
    Uses pipeline_jobs table status to prevent concurrent runs across workers.
    """
    row = await db.fetchrow(
        """SELECT id FROM pipeline_jobs
           WHERE site_id = $1 AND status = 'running'
           LIMIT 1""",
        site_id,
    )
    return row is None


async def _set_pipeline_status(site_id: UUID, status: str) -> None:
    """Update pipeline status in the database."""
    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute(
            """INSERT INTO pipeline_jobs (site_id, status, started_at)
               VALUES ($1, $2, NOW())
               ON CONFLICT (site_id) DO UPDATE SET status = $2, started_at = NOW()""",
            site_id, status,
        )

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id, require_consolidation, require_oracle, require_paid_subscription

limiter = Limiter(key_func=get_remote_address)
from datetime import UTC

from app.models.schemas import (
    AlertsListResponse,
    CannibalizationPairResponse,
    ClusterDetailResponse,
    ClusterResponse,
    ClusterSummary,
    ConsolidationDetailResponse,
    ConsolidationDraftResponse,
    ConsolidationPlanResponse,
    ContentProblemResponse,
    ContentProblemSummary,
    EcosystemVisualsResponse,
    ImpactEstimateResponse,
    OracleRequest,
    OracleVerdictResponse,
    PipelineStatusResponse,
    PositionAlertResponse,
    PostHealthResponse,
    ProblemDetectionResponse,
    RecommendationListResponse,
    RecommendationResponse,
    RecommendationStatusUpdate,
    RedirectEntry,
    ROISummaryResponse,
    SimilarPostInfo,
    SinceLastVisitResponse,
    SiteHealthResponse,
    TaskTriggerResponse,
    TopContentGapResponse,
)
from app.utils.task_retry import with_retry

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_paid_subscription)])


# ──────────────────────── Helpers ────────────────────────


async def _verify_site(site_id: UUID, user_id: str, db: asyncpg.Connection) -> None:
    """Ensure the user owns the site."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


# ──────────────── Background Task Runners ────────────────


@with_retry(max_retries=2, base_delay=5.0)
async def _run_clustering(site_id: UUID) -> None:
    """Background: run topic clustering pipeline."""
    from app.services.clustering import TopicClusterer

    logger.info("BG task: clustering started for site %s", site_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            clusterer = TopicClusterer()
            count = await clusterer.cluster_site(conn, site_id)
            logger.info("BG task: clustering complete — %d clusters for site %s", count, site_id)
        except Exception as e:
            logger.error("BG task: clustering failed for site %s: %s", site_id, e)


async def _run_clustering_safe(site_id: UUID) -> None:
    """Wrapper that clears the pipeline lock after completion."""
    try:
        await _set_pipeline_status(site_id, "running")
        await _run_clustering(site_id)
        await _set_pipeline_status(site_id, "completed")
    except Exception:
        await _set_pipeline_status(site_id, "failed")
        raise


@with_retry(max_retries=2, base_delay=5.0)
async def _run_cannibalization(site_id: UUID) -> None:
    """Background: run cannibalization detection."""
    from app.services.cannibalization import CannibalizationDetector

    logger.info("BG task: cannibalization detection started for site %s", site_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            detector = CannibalizationDetector()
            count = await detector.detect_for_site(conn, site_id)
            logger.info("BG task: cannibalization complete — %d pairs for site %s", count, site_id)
        except Exception as e:
            logger.error("BG task: cannibalization failed for site %s: %s", site_id, e)


@with_retry(max_retries=2, base_delay=5.0)
async def _run_health_scoring(site_id: UUID) -> None:
    """Background: run health scoring pipeline."""
    from app.services.health_scoring import HealthScorer

    logger.info("BG task: health scoring started for site %s", site_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            scorer = HealthScorer()
            count = await scorer.score_site(conn, site_id)
            logger.info("BG task: health scoring complete — %d posts scored for site %s", count, site_id)
        except Exception as e:
            logger.error("BG task: health scoring failed for site %s: %s", site_id, e)


async def _update_pipeline_status(
    pool, site_id: UUID, *,
    status: str | None = None,
    current_step: str | None = None,
    step_completed: str | None = None,
    error: str | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    """Update pipeline job status in DB."""
    from datetime import datetime
    async with pool.acquire() as conn:
        if started:
            await conn.execute(
                """
                INSERT INTO pipeline_jobs (site_id, status, current_step, steps_completed, started_at)
                VALUES ($1, 'running', $2, '{}', $3)
                ON CONFLICT (site_id) DO UPDATE SET
                    status = 'running',
                    current_step = $2,
                    steps_completed = '{}',
                    started_at = $3,
                    completed_at = NULL,
                    error = NULL,
                    updated_at = NOW()
                """,
                site_id, current_step, datetime.now(UTC),
            )
            return

        sets = ["updated_at = NOW()"]
        params = [site_id]
        idx = 2

        if status:
            sets.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if current_step is not None:
            sets.append(f"current_step = ${idx}")
            params.append(current_step if current_step else None)
            idx += 1
        if step_completed:
            sets.append(f"steps_completed = array_append(steps_completed, ${idx})")
            params.append(step_completed)
            idx += 1
        if error:
            sets.append(f"error = ${idx}")
            params.append(error[:500])
            idx += 1
        if completed:
            sets.append(f"completed_at = ${idx}")
            params.append(datetime.now(UTC))
            idx += 1

        await conn.execute(
            f"UPDATE pipeline_jobs SET {', '.join(sets)} WHERE site_id = $1",
            *params,
        )


async def _run_full_pipeline(site_id: UUID) -> None:
    """Background: run full intelligence pipeline in sequence with status tracking.

    Pipeline steps:
    1. Clustering (UMAP + HDBSCAN + 2D positions + labels)
    2. Cannibalization (cosine similarity + GSC overlap)
    3. Health scoring (7-factor model)
    4. Problem detection (decay, thin, SEO, orphans)
    5. Recommendations (AI-generated for all problems + growth)
    """
    from app.services.cannibalization import CannibalizationDetector
    from app.services.clustering import TopicClusterer
    from app.services.health_scoring import HealthScorer
    from app.services.problem_detection import ProblemDetector

    logger.info("BG task: full intelligence pipeline started for site %s", site_id)
    pool = await get_pool()

    await _update_pipeline_status(pool, site_id, started=True, current_step="clustering")

    try:
        # Step 1: Clustering + 2D positions
        async with pool.acquire() as conn:
            clusterer = TopicClusterer()
            clusters = await clusterer.cluster_site(conn, site_id)
            logger.info("Pipeline step 1 complete: %d clusters", clusters)

        await _update_pipeline_status(
            pool, site_id,
            current_step="cannibalization",
            step_completed="clustering",
        )

        # Step 2: Cannibalization
        async with pool.acquire() as conn:
            detector = CannibalizationDetector()
            pairs = await detector.detect_for_site(conn, site_id)
            logger.info("Pipeline step 2 complete: %d cannibalization pairs", pairs)

        await _update_pipeline_status(
            pool, site_id,
            current_step="health_scoring",
            step_completed="cannibalization",
        )

        # Step 3: Health scoring
        async with pool.acquire() as conn:
            scorer = HealthScorer()
            scored = await scorer.score_site(conn, site_id)
            logger.info("Pipeline step 3 complete: %d posts scored", scored)

        await _update_pipeline_status(
            pool, site_id,
            current_step="problem_detection",
            step_completed="health_scoring",
        )

        # Step 4: Problem detection
        async with pool.acquire() as conn:
            detector = ProblemDetector()
            problems = await detector.detect_all(conn, site_id)
            total_problems = sum(problems.values())
            logger.info("Pipeline step 4 complete: %d problems detected", total_problems)

        await _update_pipeline_status(
            pool, site_id,
            current_step="recommendations",
            step_completed="problem_detection",
        )

        # Step 5: Fast template recommendations (zero Claude calls)
        from app.services.fast_recommendations import generate_fast_recommendations
        async with pool.acquire() as conn:
            recs = await generate_fast_recommendations(conn, site_id)
            logger.info("Pipeline step 5 complete: %d recommendations generated", recs)

        await _update_pipeline_status(
            pool, site_id,
            current_step="auto_enrichment",
            step_completed="recommendations",
        )

        # Step 5b: Auto-enrich top recommendations with RAG context + Claude
        # Ensures the highest-priority recs have rich AI content without
        # requiring user to click "Get AI Analysis" manually
        try:
            from app.services.on_demand_enrichment import auto_enrich_top_recs
            enriched = await auto_enrich_top_recs(pool, site_id, limit=10)
            logger.info("Pipeline step 5b complete: %d recs auto-enriched", enriched)
        except Exception as e:
            logger.warning("Auto-enrichment failed (non-fatal): %s", e)

        await _update_pipeline_status(
            pool, site_id,
            status="completed",
            current_step=None,
            step_completed="auto_enrichment",
            completed=True,
        )
        logger.info("BG task: full pipeline complete for site %s", site_id)

    except Exception as e:
        logger.error("BG task: full pipeline failed for site %s: %s", site_id, e)
        await _update_pipeline_status(
            pool, site_id,
            status="failed",
            error=str(e),
        )


# ──────────────────────── Endpoints ────────────────────────


@router.post("/{site_id}/intelligence/cluster", response_model=TaskTriggerResponse)
async def trigger_clustering(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Trigger topic clustering for a site (background task)."""
    await _verify_site(site_id, user_id, db)
    if not await _try_acquire_pipeline_lock(db, site_id):
        raise HTTPException(status_code=429, detail="Pipeline already running for this site")
    background_tasks.add_task(_run_clustering_safe, site_id)
    return TaskTriggerResponse(message="Clustering started", site_id=site_id)


@router.post("/{site_id}/intelligence/cluster-labels", response_model=TaskTriggerResponse)
async def trigger_claude_cluster_labels(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Relabel clusters using Claude for higher-quality topic labels.

    Upgrades TF-IDF labels (e.g. "SEO and Marketing") to specific Claude labels
    (e.g. "Link Building Strategies"). Cost: ~$0.02 per site.
    """
    await _verify_site(site_id, user_id, db)

    from app.services.fast_cluster_labels import backfill_claude_labels

    labeled = await backfill_claude_labels(db, site_id)
    return TaskTriggerResponse(
        message=f"Claude cluster labeling complete: {labeled} clusters relabeled",
        site_id=site_id,
    )


@router.get("/{site_id}/intelligence/clusters", response_model=list[ClusterResponse])
async def list_clusters(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all clusters for a site with ecosystem state and health."""
    await _verify_site(site_id, user_id, db)
    rows = await db.fetch(
        """
        SELECT c.*,
               sub.center_x,
               sub.center_y
        FROM clusters c
        LEFT JOIN LATERAL (
            SELECT AVG(p.x_pos) AS center_x, AVG(p.y_pos) AS center_y
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            WHERE pc.cluster_id = c.id
        ) sub ON true
        WHERE c.site_id = $1
        AND c.id NOT IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
        ORDER BY c.post_count DESC
        """,
        site_id,
    )
    return [ClusterResponse(**dict(r)) for r in rows]


@router.get(
    "/{site_id}/intelligence/clusters/{cluster_id}",
    response_model=ClusterDetailResponse,
)
async def get_cluster_detail(
    site_id: UUID,
    cluster_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get detailed cluster view with all posts, roles, and health scores."""
    await _verify_site(site_id, user_id, db)
    cluster_row = await db.fetchrow(
        "SELECT * FROM clusters WHERE id = $1 AND site_id = $2",
        cluster_id, site_id,
    )
    if not cluster_row:
        raise HTTPException(status_code=404, detail="Cluster not found")

    post_rows = await db.fetch(
        """
        SELECT p.id AS post_id, p.title, p.url,
               ph.composite_score, ph.role, ph.trend,
               ph.traffic_contribution, ph.ranking_strength, ph.internal_link_score,
               ph.score_confidence,
               p.x_pos, p.y_pos
        FROM post_clusters pc
        JOIN posts p ON p.id = pc.post_id
        LEFT JOIN post_health_scores ph ON ph.post_id = p.id
        WHERE pc.cluster_id = $1
        ORDER BY COALESCE(ph.composite_score, 0) DESC
        """,
        cluster_id,
    )

    posts = [PostHealthResponse(**dict(r)) for r in post_rows]
    cluster_data = dict(cluster_row)
    return ClusterDetailResponse(**cluster_data, posts=posts)


@router.post(
    "/{site_id}/intelligence/detect-cannibalization",
    response_model=TaskTriggerResponse,
)
async def trigger_cannibalization(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Trigger cannibalization detection (requires clusters to exist)."""
    await _verify_site(site_id, user_id, db)
    background_tasks.add_task(_run_cannibalization, site_id)
    return TaskTriggerResponse(
        message="Cannibalization detection started", site_id=site_id,
    )


@router.get(
    "/{site_id}/intelligence/cannibalization",
    response_model=list[CannibalizationPairResponse],
)
async def list_cannibalization(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    limit: int = 200,
    offset: int = 0,
):
    """List cannibalization pairs grouped by cluster, sorted by severity (paginated)."""
    await _verify_site(site_id, user_id, db)

    # Clamp limit to a reasonable maximum
    limit = min(limit, 200)

    severity_order = "CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"
    rows = await db.fetch(
        f"""
        SELECT cp.id, cp.cluster_id, cp.overlap_score, cp.severity,
               cp.resolution, cp.stronger_post_id, cp.chunk_overlap_confirmed,
               cp.overlapping_queries,
               cp.post_a_id, pa.title AS title_a, pa.url AS url_a,
               pha.composite_score AS score_a, pha.role AS role_a,
               pha.trend AS trend_a, pha.traffic_contribution AS tc_a,
               pha.ranking_strength AS rs_a, pha.internal_link_score AS ils_a,
               cp.post_b_id, pb.title AS title_b, pb.url AS url_b,
               phb.composite_score AS score_b, phb.role AS role_b,
               phb.trend AS trend_b, phb.traffic_contribution AS tc_b,
               phb.ranking_strength AS rs_b, phb.internal_link_score AS ils_b
        FROM cannibalization_pairs cp
        JOIN clusters c ON c.id = cp.cluster_id
        JOIN posts pa ON pa.id = cp.post_a_id
        JOIN posts pb ON pb.id = cp.post_b_id
        LEFT JOIN post_health_scores pha ON pha.post_id = cp.post_a_id
        LEFT JOIN post_health_scores phb ON phb.post_id = cp.post_b_id
        WHERE c.site_id = $1
        ORDER BY {severity_order}, cp.overlap_score DESC
        LIMIT $2 OFFSET $3
        """,
        site_id, limit, offset,
    )

    results = []
    for r in rows:
        results.append(CannibalizationPairResponse(
            id=r["id"],
            cluster_id=r["cluster_id"],
            post_a=PostHealthResponse(
                post_id=r["post_a_id"], title=r["title_a"], url=r["url_a"],
                composite_score=r["score_a"], role=r["role_a"], trend=r["trend_a"],
                traffic_contribution=r["tc_a"], ranking_strength=r["rs_a"],
                internal_link_score=r["ils_a"],
            ),
            post_b=PostHealthResponse(
                post_id=r["post_b_id"], title=r["title_b"], url=r["url_b"],
                composite_score=r["score_b"], role=r["role_b"], trend=r["trend_b"],
                traffic_contribution=r["tc_b"], ranking_strength=r["rs_b"],
                internal_link_score=r["ils_b"],
            ),
            overlap_score=r["overlap_score"],
            severity=r["severity"],
            resolution=r.get("resolution"),
            stronger_post_id=r.get("stronger_post_id"),
            chunk_confirmed=r.get("chunk_overlap_confirmed"),
            overlapping_queries=r["overlapping_queries"],
        ))
    return results


@router.post(
    "/{site_id}/intelligence/score-health",
    response_model=TaskTriggerResponse,
)
async def trigger_health_scoring(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Trigger health scoring (requires clusters + cannibalization)."""
    await _verify_site(site_id, user_id, db)
    background_tasks.add_task(_run_health_scoring, site_id)
    return TaskTriggerResponse(message="Health scoring started", site_id=site_id)


@router.get("/{site_id}/intelligence/health", response_model=SiteHealthResponse)
async def get_site_health(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Site-wide health dashboard data."""
    await _verify_site(site_id, user_id, db)

    # Total posts
    total_posts = await db.fetchval(
        "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
    )

    # Posts by role
    role_counts = await db.fetch(
        """
        SELECT ph.role, COUNT(*) AS cnt
        FROM post_health_scores ph
        JOIN posts p ON p.id = ph.post_id
        WHERE p.site_id = $1
        GROUP BY ph.role
        """,
        site_id,
    )
    roles = {r["role"]: r["cnt"] for r in role_counts}

    active_posts = roles.get("pillar", 0) + roles.get("supporter", 0)
    dead_posts = roles.get("dead_weight", 0)
    # Count distinct posts involved in cannibalization pairs
    cannibalistic_posts = await db.fetchval(
        """
        SELECT COUNT(DISTINCT post_id) FROM (
            SELECT post_a_id AS post_id FROM cannibalization_pairs cp
            JOIN posts p ON p.id = cp.post_a_id WHERE p.site_id = $1
            UNION
            SELECT post_b_id FROM cannibalization_pairs cp
            JOIN posts p ON p.id = cp.post_b_id WHERE p.site_id = $1
        ) s
        """,
        site_id,
    ) or 0
    passive_posts = max(0, total_posts - active_posts - dead_posts)

    # Content health score (average composite)
    avg_health = await db.fetchval(
        """
        SELECT COALESCE(AVG(ph.composite_score), 0)
        FROM post_health_scores ph
        JOIN posts p ON p.id = ph.post_id
        WHERE p.site_id = $1
        """,
        site_id,
    )

    # Content efficiency ratio
    efficiency = active_posts / total_posts if total_posts > 0 else 0.0

    # Clusters summary
    cluster_rows = await db.fetch(
        """
        SELECT id, label, ecosystem_state, post_count
        FROM clusters WHERE site_id = $1
        AND id NOT IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
        ORDER BY post_count DESC
        """,
        site_id,
    )
    clusters = [ClusterSummary(**dict(r)) for r in cluster_rows]

    # Trends (traffic change over 30/60/90 days)
    trends = {}
    for days in [30, 60, 90]:
        traffic = await db.fetchval(
            """
            SELECT COALESCE(SUM(pageviews), 0)
            FROM ga4_metrics g
            JOIN posts p ON p.id = g.post_id
            WHERE p.site_id = $1
              AND g.date >= CURRENT_DATE - $2::int
            """,
            site_id, days,
        )
        trends[f"{days}d"] = float(traffic)

    # Data completeness: check what data sources are available
    has_ga4 = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM ga4_metrics g JOIN posts p ON p.id = g.post_id WHERE p.site_id = $1 LIMIT 1)",
        site_id,
    )
    has_gsc = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM gsc_metrics g JOIN posts p ON p.id = g.post_id WHERE p.site_id = $1 LIMIT 1)",
        site_id,
    )
    # Crawl data = 40%, GA4 = 30%, GSC = 30%
    data_completeness = 0.4 + (0.3 if has_ga4 else 0.0) + (0.3 if has_gsc else 0.0)

    # Freshness coverage — how many posts have a modified_date
    posts_with_modified = await db.fetchval(
        "SELECT COUNT(*) FROM posts WHERE site_id = $1 AND modified_date IS NOT NULL",
        site_id,
    )
    modified_date_coverage = posts_with_modified / total_posts if total_posts > 0 else 0.0

    # AI enrichment coverage — how many recs have Claude guidance
    ai_enriched_count = await db.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND specific_actions::text LIKE '%ai_enriched%'",
        site_id,
    )

    # Post limit for upsell trigger
    from app.services.stripe_service import TIER_LIMITS
    tier = await db.fetchval(
        "SELECT subscription_status FROM profiles WHERE id = $1::uuid", user_id,
    ) or "growth"
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["growth"])
    post_limit = limits.get("posts", 500)
    post_usage_pct = (total_posts / post_limit * 100) if post_limit > 0 else 0.0

    return SiteHealthResponse(
        content_health_score=float(avg_health),
        total_posts=total_posts,
        active_posts=active_posts,
        passive_posts=passive_posts,
        cannibalistic_posts=cannibalistic_posts,
        dead_posts=dead_posts,
        content_efficiency_ratio=round(efficiency * 100, 1),
        clusters=clusters,
        trends=trends,
        data_completeness=data_completeness,
        modified_date_coverage=round(modified_date_coverage, 3),
        ai_enriched_count=int(ai_enriched_count or 0),
        post_limit=post_limit,
        post_usage_pct=round(post_usage_pct, 1),
    )


@router.get("/{site_id}/intelligence/health/history")
async def get_health_history(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    limit: int = 90,
):
    """Get health score history for trend analysis.

    Returns an array of {score, factor_scores, analyzed_at} sorted newest-first.
    """
    await _verify_site(site_id, user_id, db)

    rows = await db.fetch(
        """SELECT score, factor_scores, analyzed_at
           FROM health_score_history
           WHERE site_id = $1
           ORDER BY analyzed_at DESC
           LIMIT $2""",
        site_id, min(limit, 365),
    )

    import json
    results = []
    for r in rows:
        factors = r["factor_scores"]
        if isinstance(factors, str):
            try:
                factors = json.loads(factors)
            except (json.JSONDecodeError, TypeError):
                factors = {}
        results.append({
            "score": float(r["score"]),
            "factor_scores": factors or {},
            "analyzed_at": r["analyzed_at"].isoformat() if r["analyzed_at"] else None,
        })

    return results


@router.get(
    "/{site_id}/intelligence/consolidation",
    response_model=list[ConsolidationPlanResponse],
)
async def list_consolidation_plans(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Ranked list of consolidation opportunities."""
    await _verify_site(site_id, user_id, db)

    from app.services.consolidation import ConsolidationPlanner

    planner = ConsolidationPlanner()
    plans = await planner.get_plans(db, site_id)
    return [ConsolidationPlanResponse(**p) for p in plans]


@router.get(
    "/{site_id}/intelligence/consolidation/{cluster_id}",
    response_model=ConsolidationDetailResponse,
)
async def get_consolidation_detail(
    site_id: UUID,
    cluster_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Detailed consolidation plan for a specific cluster."""
    await _verify_site(site_id, user_id, db)

    from app.services.consolidation import ConsolidationPlanner

    planner = ConsolidationPlanner()
    plan = await planner.get_plan_detail(db, cluster_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Cluster not found or no plan available")
    return ConsolidationDetailResponse(**plan)


@router.post(
    "/{site_id}/intelligence/consolidation/{cluster_id}/draft",
    response_model=ConsolidationDraftResponse,
)
@limiter.limit("5/minute")
async def generate_consolidation_draft(
    request: Request,
    site_id: UUID,
    cluster_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    _tier: None = Depends(require_consolidation),
):
    """Generate an AI-merged consolidation draft for a cluster."""
    await _verify_site(site_id, user_id, db)

    # Verify cluster belongs to site
    cluster_row = await db.fetchrow(
        "SELECT id FROM clusters WHERE id = $1 AND site_id = $2",
        cluster_id, site_id,
    )
    if not cluster_row:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from app.services.consolidation import ConsolidationPlanner

    planner = ConsolidationPlanner()
    try:
        result = await planner.generate_draft(db, cluster_id, site_id=site_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Draft generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Draft generation failed")

    return ConsolidationDraftResponse(
        draft_markdown=result["draft_markdown"],
        redirect_map=[RedirectEntry(**r) for r in result["redirect_map"]],
    )


@router.post(
    "/{site_id}/intelligence/oracle",
    response_model=OracleVerdictResponse,
)
@limiter.limit("10/minute")
async def oracle_check(
    request: Request,
    site_id: UUID,
    body: OracleRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    _tier: None = Depends(require_oracle),
):
    """Pre-publish oracle — check new content against the existing ecosystem."""
    await _verify_site(site_id, user_id, db)

    if not body.draft_text and not body.target_keyword:
        raise HTTPException(
            status_code=400,
            detail="At least one of draft_text or target_keyword is required",
        )

    from app.services.oracle import PrePublishOracle

    oracle = PrePublishOracle()
    result = await oracle.analyze(
        db, site_id,
        draft_text=body.draft_text,
        target_keyword=body.target_keyword,
    )

    return OracleVerdictResponse(
        confidence=result["confidence"],
        verdict=result["verdict"],
        reasoning=result["reasoning"],
        similar_posts=[SimilarPostInfo(**sp) for sp in result["similar_posts"]],
        cluster_state=result["cluster_state"],
        recommendation=result["recommendation"],
    )


@router.post(
    "/{site_id}/intelligence/run-all",
    response_model=TaskTriggerResponse,
)
async def run_full_pipeline(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Run full intelligence pipeline: cluster → cannibalization → health."""
    await _verify_site(site_id, user_id, db)
    background_tasks.add_task(_run_full_pipeline, site_id)
    return TaskTriggerResponse(
        message="Full intelligence pipeline started", site_id=site_id,
    )


@router.get(
    "/{site_id}/intelligence/pipeline-status",
    response_model=PipelineStatusResponse,
)
async def get_pipeline_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Check the current status of the intelligence pipeline."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        "SELECT * FROM pipeline_jobs WHERE site_id = $1", site_id,
    )
    if not row:
        return PipelineStatusResponse(site_id=site_id, status="idle")

    return PipelineStatusResponse(
        site_id=row["site_id"],
        status=row["status"],
        current_step=row["current_step"],
        steps_completed=row["steps_completed"] or [],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error=row["error"],
    )


# ──────────────── Problem Detection ────────────────


@router.post(
    "/{site_id}/intelligence/detect-problems",
    response_model=ProblemDetectionResponse,
)
async def trigger_problem_detection(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Run all problem detectors (decay, thin, SEO, orphans)."""
    await _verify_site(site_id, user_id, db)

    from app.services.problem_detection import ProblemDetector

    detector = ProblemDetector()
    counts = await detector.detect_all(db, site_id)
    return ProblemDetectionResponse(
        decay=counts.get("decay", 0),
        thin=counts.get("thin", 0),
        seo=counts.get("seo", 0),
        orphan=counts.get("orphan", 0),
        total=sum(counts.values()),
    )


@router.get(
    "/{site_id}/intelligence/problems",
    response_model=list[ContentProblemResponse],
)
async def list_problems(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    problem_type: str | None = None,
    severity: str | None = None,
    sort_by: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    """List all detected content problems for a site.

    sort_by options:
      - "severity" (default): ORDER BY severity category (critical > high > medium > low)
      - "weight": ORDER BY severity_score from weight table (highest impact first)
    """
    await _verify_site(site_id, user_id, db)

    query = """
        SELECT cp.* FROM content_problems cp
        WHERE cp.site_id = $1 AND cp.resolved_at IS NULL
    """
    params: list = [site_id]
    idx = 2

    if problem_type:
        query += f" AND cp.problem_type = ${idx}"
        params.append(problem_type)
        idx += 1
    if severity:
        query += f" AND cp.severity = ${idx}"
        params.append(severity)
        idx += 1

    if sort_by == "weight":
        # Sort by severity_score in details JSON (set by _PROBLEM_WEIGHTS during detection)
        query += " ORDER BY COALESCE((cp.details->>'severity_score')::int, 50) DESC"
    else:
        query += " ORDER BY CASE cp.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"
    query += f" LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([min(limit, 500), offset])

    rows = await db.fetch(query, *params)
    import json
    results = []
    for r in rows:
        details = r["details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (json.JSONDecodeError, TypeError):
                details = {}
        results.append(ContentProblemResponse(
            id=r["id"],
            post_id=r["post_id"],
            problem_type=r["problem_type"],
            severity=r["severity"],
            details=details,
            detected_at=r["detected_at"],
            resolved_at=r["resolved_at"],
        ))
    return results


@router.get(
    "/{site_id}/intelligence/problems/{post_id}",
    response_model=ContentProblemSummary,
)
async def get_post_problems(
    site_id: UUID,
    post_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get all problems for a specific post."""
    await _verify_site(site_id, user_id, db)

    post = await db.fetchrow(
        "SELECT id, title, url FROM posts WHERE id = $1 AND site_id = $2",
        post_id, site_id,
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    rows = await db.fetch(
        "SELECT * FROM content_problems WHERE post_id = $1 AND resolved_at IS NULL",
        post_id,
    )

    import json
    problems = []
    for r in rows:
        details = r["details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (json.JSONDecodeError, TypeError):
                details = {}
        problems.append(ContentProblemResponse(
            id=r["id"], post_id=r["post_id"],
            problem_type=r["problem_type"], severity=r["severity"],
            details=details, detected_at=r["detected_at"],
            resolved_at=r["resolved_at"],
        ))

    return ContentProblemSummary(
        post_id=post["id"], title=post["title"], url=post["url"],
        problems=problems,
    )


# ──────────────── Recommendations ────────────────


@router.post(
    "/{site_id}/intelligence/generate-recommendations",
    response_model=TaskTriggerResponse,
)
async def trigger_recommendations(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate AI recommendations for all detected problems (background)."""
    await _verify_site(site_id, user_id, db)

    async def _run_recommendations(sid: UUID) -> None:
        from app.services.fast_recommendations import generate_fast_recommendations
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await generate_fast_recommendations(conn, sid)
            logger.info("Generated %d recommendations for site %s", count, sid)

    background_tasks.add_task(_run_recommendations, site_id)
    return TaskTriggerResponse(
        message="Recommendation generation started", site_id=site_id,
    )


@router.get(
    "/{site_id}/intelligence/recommendations",
    response_model=RecommendationListResponse,
)
async def list_recommendations(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    recommendation_type: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    """List recommendations for a site with optional filters (paginated)."""
    await _verify_site(site_id, user_id, db)

    # Clamp limit to a reasonable maximum
    limit = min(limit, 200)

    query = "SELECT * FROM recommendations WHERE site_id = $1"
    params: list = [site_id]
    idx = 2

    if recommendation_type:
        query += f" AND recommendation_type = ${idx}"
        params.append(recommendation_type)
        idx += 1
    if priority:
        query += f" AND priority = ${idx}"
        params.append(priority)
        idx += 1
    if status:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1

    query += " ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, created_at DESC"
    query += f" LIMIT ${idx} OFFSET ${idx + 1}"
    params.append(limit)
    params.append(offset)

    rows = await db.fetch(query, *params)

    import json
    recs = []
    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}

    for r in rows:
        actions = r["specific_actions"]
        if isinstance(actions, str):
            try:
                actions = json.loads(actions)
            except (json.JSONDecodeError, TypeError):
                actions = []

        ai_content = r["ai_generated_content"]
        if isinstance(ai_content, str):
            try:
                ai_content = json.loads(ai_content)
            except (json.JSONDecodeError, TypeError):
                ai_content = {}

        rec = RecommendationResponse(
            id=r["id"], post_id=r["post_id"],
            problem_id=r["problem_id"],
            recommendation_type=r["recommendation_type"],
            priority=r["priority"],
            estimated_effort_hours=r["estimated_effort_hours"],
            estimated_impact=r["estimated_impact"],
            title=r["title"], summary=r["summary"],
            specific_actions=actions if isinstance(actions, list) else [],
            ai_generated_content=ai_content if isinstance(ai_content, dict) else {},
            status=r["status"],
            created_at=r["created_at"], updated_at=r["updated_at"],
        )
        recs.append(rec)

        by_type[r["recommendation_type"]] = by_type.get(r["recommendation_type"], 0) + 1
        by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1

    return RecommendationListResponse(
        recommendations=recs, total=len(recs),
        by_type=by_type, by_priority=by_priority,
    )


@router.get(
    "/{site_id}/intelligence/recommendations/{post_id}",
    response_model=list[RecommendationResponse],
)
async def get_post_recommendations(
    site_id: UUID,
    post_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get all recommendations for a specific post."""
    await _verify_site(site_id, user_id, db)

    rows = await db.fetch(
        """
        SELECT * FROM recommendations
        WHERE post_id = $1 AND site_id = $2
        ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                 WHEN 'medium' THEN 3 ELSE 4 END
        """,
        post_id, site_id,
    )

    import json
    results = []
    for r in rows:
        actions = r["specific_actions"]
        if isinstance(actions, str):
            try:
                actions = json.loads(actions)
            except (json.JSONDecodeError, TypeError):
                actions = []

        ai_content = r["ai_generated_content"]
        if isinstance(ai_content, str):
            try:
                ai_content = json.loads(ai_content)
            except (json.JSONDecodeError, TypeError):
                ai_content = {}

        results.append(RecommendationResponse(
            id=r["id"], post_id=r["post_id"],
            problem_id=r["problem_id"],
            recommendation_type=r["recommendation_type"],
            priority=r["priority"],
            estimated_effort_hours=r["estimated_effort_hours"],
            estimated_impact=r["estimated_impact"],
            title=r["title"], summary=r["summary"],
            specific_actions=actions if isinstance(actions, list) else [],
            ai_generated_content=ai_content if isinstance(ai_content, dict) else {},
            status=r["status"],
            created_at=r["created_at"], updated_at=r["updated_at"],
        ))
    return results


@router.patch(
    "/{site_id}/intelligence/recommendations/{recommendation_id}/status",
    response_model=RecommendationResponse,
)
async def update_recommendation_status(
    site_id: UUID,
    recommendation_id: UUID,
    body: RecommendationStatusUpdate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Update the status of a recommendation (pending → in_progress → completed/dismissed)."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        """
        UPDATE recommendations SET status = $1, updated_at = NOW()
        WHERE id = $2 AND site_id = $3
        RETURNING *
        """,
        body.status, recommendation_id, site_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Record impact baseline when a recommendation is completed
    if body.status == "completed":
        try:
            from app.services.impact_tracking import ImpactTracker
            tracker = ImpactTracker()
            await tracker.record_completion(db, recommendation_id)
        except Exception:
            logger.warning(
                "Failed to record impact baseline for %s", recommendation_id, exc_info=True,
            )

    import json
    actions = row["specific_actions"]
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except (json.JSONDecodeError, TypeError):
            actions = []

    ai_content = row["ai_generated_content"]
    if isinstance(ai_content, str):
        try:
            ai_content = json.loads(ai_content)
        except (json.JSONDecodeError, TypeError):
            ai_content = {}

    return RecommendationResponse(
        id=row["id"], post_id=row["post_id"],
        problem_id=row["problem_id"],
        recommendation_type=row["recommendation_type"],
        priority=row["priority"],
        estimated_effort_hours=row["estimated_effort_hours"],
        estimated_impact=row["estimated_impact"],
        title=row["title"], summary=row["summary"],
        specific_actions=actions if isinstance(actions, list) else [],
        ai_generated_content=ai_content if isinstance(ai_content, dict) else {},
        status=row["status"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


@router.post(
    "/{site_id}/intelligence/cannibalization/{pair_id}/recommend",
)
@limiter.limit("5/minute")
async def get_cannibalization_recommendation(
    request: Request,
    site_id: UUID,
    pair_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate detailed AI recommendation for a cannibalization pair.

    Called when user clicks on a cannibalization pair for specifics.
    """
    await _verify_site(site_id, user_id, db)

    from app.services.recommendations import RecommendationEngine

    engine = RecommendationEngine()
    try:
        result = await engine.generate_cannibalization_recommendation(db, site_id, pair_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Cannibalization recommendation failed: %s", e)
        raise HTTPException(status_code=500, detail="Recommendation generation failed")

    return result


# ──────────────── Phase 6: Ecosystem Visuals ────────────────


@router.get(
    "/{site_id}/intelligence/ecosystem-visuals",
    response_model=EcosystemVisualsResponse,
)
async def get_ecosystem_visuals(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get ecosystem visual metadata — rivers, grass, weather, animals, terrain features."""
    await _verify_site(site_id, user_id, db)

    from app.services.ecosystem_visuals import EcosystemVisualsService

    service = EcosystemVisualsService()
    try:
        result = await service.compute_visuals(db, site_id)
    except Exception as e:
        logger.error("Ecosystem visuals computation failed for site %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail="Failed to compute ecosystem visuals")

    return EcosystemVisualsResponse(**result)


# ── On-demand enrichment ──────────────────────────────────────────────────────

@router.post("/{site_id}/intelligence/recommendations/{rec_id}/enrich")
async def enrich_recommendation_on_demand(
    site_id: UUID,
    rec_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Enrich a single recommendation with Claude AI guidance (~3 seconds)."""
    await _verify_site(site_id, user_id, db)
    from app.services.on_demand_enrichment import enrich_recommendation
    result = await enrich_recommendation(db, rec_id, site_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Quick scan (health + problems + recs only, ~30s) ─────────────────────────

@router.post("/{site_id}/intelligence/quick-scan")
async def quick_scan(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Re-run health scoring + problem detection + recommendations only (~30s).
    Does NOT re-crawl or re-cluster. Use this for fast refreshes."""
    await _verify_site(site_id, user_id, db)

    async def _run():
        import time
        t0 = time.time()
        try:
            from app.services.fast_recommendations import generate_fast_recommendations
            from app.services.health_scoring import HealthScorer
            from app.services.problem_detection import ProblemDetector

            pool = await get_pool()
            async with pool.acquire() as conn:
                hs = HealthScorer()
                await hs.score_site(conn, site_id)

                pd = ProblemDetector()
                await pd.detect_all(conn, site_id)

                await generate_fast_recommendations(conn, site_id)
            logger.info("Quick scan complete for %s in %.1fs", site_id, time.time() - t0)
        except Exception as e:
            logger.error("Quick scan failed for %s: %s", site_id, e)

    background_tasks.add_task(_run)
    return {"message": "Quick scan started — refreshes health, problems, and recommendations (~30s)", "status": "running"}


# ── AI Readiness Scan ─────────────────────────────────────────────────────────

@router.post("/{site_id}/intelligence/ai-readiness")
async def ai_readiness_scan(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Run AI-era readiness scoring for all posts (2026 SEO signals).

    Scores each post on:
    - AI Citability Score: likelihood AI systems will cite this post (tables, data, experience)
    - E-E-A-T Score: author signals, dates, credentials, credible citations
    - Schema Score: JSON-LD structured data completeness
    - Extraction Score: content structure optimised for AI answer extraction

    Then runs problem detection to flag low scores as actionable issues.
    Zero new API calls — pure content analysis on already-crawled HTML.
    ~1-3 min depending on site size."""
    await _verify_site(site_id, user_id, db)

    async def _run():
        import time
        t0 = time.time()
        pool = await get_pool()
        try:
            from app.services.ai_citability import AICitabilityService
            from app.services.problem_detection import ProblemDetector

            async with pool.acquire() as conn:
                result = await AICitabilityService().score_site(conn, site_id)
                logger.info("AI scoring done: %s", result)

            async with pool.acquire() as conn:
                pd = ProblemDetector()
                await pd._detect_ai_readiness_issues(conn, site_id)

            logger.info("AI readiness scan complete for %s in %.1fs", site_id, time.time() - t0)
        except Exception as e:
            logger.error("AI readiness scan failed for %s: %s", site_id, e)
            logger.exception("Stack trace for above error")

    background_tasks.add_task(_run)
    return {
        "message": "AI readiness scan started — scoring all posts for 2026 SEO signals (~1-3 min)",
        "status": "running",
        "signals": ["ai_citability", "eeat", "schema_markup", "extraction_structure"],
    }


# ── Chunk-level cannibalization confirmation ──────────────────────────────────

@router.post("/{site_id}/intelligence/cannibalization/confirm-chunks")
async def confirm_chunk_overlap(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Confirm or deny cannibalization pairs using chunk-level embedding similarity.
    Runs in background — checks each pair's section-level overlap."""
    await _verify_site(site_id, user_id, db)

    async def _run():
        from app.services.chunk_cannibalization import confirm_chunk_overlap as _confirm
        result = await _confirm(db, site_id)
        logger.info("Chunk confirmation for %s: %s", site_id, result)

    background_tasks.add_task(_run)
    return {"message": "Chunk-level cannibalization confirmation started in background", "status": "running"}


# ── Claude intent for ambiguous posts ────────────────────────────────────────

@router.post("/{site_id}/intelligence/intent/claude-classify")
async def claude_classify_intent(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Re-classify ambiguous posts using Claude for accurate intent signals."""
    await _verify_site(site_id, user_id, db)

    async def _run():
        from app.services.claude_intent import classify_ambiguous_posts
        result = await classify_ambiguous_posts(db, site_id)
        logger.info("Claude intent for %s: %s", site_id, result)

    background_tasks.add_task(_run)
    return {"message": "Claude intent classification started in background", "status": "running"}


@router.get("/{site_id}/intelligence/ai-scores")
async def get_ai_scores(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get aggregate AI readiness scores for the site dashboard card."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        """
        SELECT
            COUNT(phs.post_id) FILTER (WHERE phs.ai_citability_score IS NOT NULL) AS total_scored,
            ROUND(AVG(phs.ai_citability_score)::numeric, 1) AS avg_citability,
            ROUND(AVG(phs.eeat_score)::numeric, 1) AS avg_eeat,
            ROUND(AVG(phs.schema_score)::numeric, 1) AS avg_schema,
            ROUND(AVG(phs.extraction_score)::numeric, 1) AS avg_extraction,
            ROUND(
                (COUNT(*) FILTER (WHERE phs.schema_score > 0))::numeric /
                NULLIF(COUNT(*), 0) * 100, 1
            ) AS pct_has_schema,
            ROUND(
                (COUNT(*) FILTER (WHERE phs.ai_citability_score >= 60))::numeric /
                NULLIF(COUNT(*) FILTER (WHERE phs.ai_citability_score IS NOT NULL), 0) * 100, 1
            ) AS pct_ai_ready
        FROM post_health_scores phs
        JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1
        """,
        site_id,
    )

    if not row or not row["total_scored"]:
        return {
            "total_scored": 0,
            "avg_citability": None,
            "avg_eeat": None,
            "avg_schema": None,
            "avg_extraction": None,
            "pct_has_schema": None,
            "pct_ai_ready": None,
        }

    return {
        "total_scored": int(row["total_scored"] or 0),
        "avg_citability": float(row["avg_citability"] or 0),
        "avg_eeat": float(row["avg_eeat"] or 0),
        "avg_schema": float(row["avg_schema"] or 0),
        "avg_extraction": float(row["avg_extraction"] or 0),
        "pct_has_schema": float(row["pct_has_schema"] or 0),
        "pct_ai_ready": float(row["pct_ai_ready"] or 0),
    }


# ── Content Briefs (RAG-powered) ─────────────────────────────────────────────

from pydantic import BaseModel as _BriefBaseModel


class ContentBriefRequest(_BriefBaseModel):
    """Request body for content brief generation."""
    topic: str


@router.post("/{site_id}/intelligence/briefs")
@limiter.limit("5/minute")
async def generate_content_brief(
    request: Request,
    site_id: UUID,
    body: ContentBriefRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate a RAG-powered content brief for a new post topic.

    Pre-checks for cannibalization against existing content, pulls cluster
    benchmarks, plans internal links, and generates a full outline that
    avoids overlap with existing posts.

    Returns:
    - Cannibalization risk assessment (high/medium/low)
    - Suggested titles, outline, word count target
    - Internal links to/from the new post
    - Topics to explicitly AVOID
    - Content angle to differentiate
    """
    await _verify_site(site_id, user_id, db)

    if not body.topic or len(body.topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic must be at least 3 characters")

    from app.services.content_briefs import ContentBriefGenerator

    generator = ContentBriefGenerator()
    result = await generator.generate_brief(db, site_id, body.topic.strip())

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/{site_id}/intelligence/briefs")
async def list_content_briefs(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all content briefs for a site."""
    await _verify_site(site_id, user_id, db)

    rows = await db.fetch(
        """
        SELECT id, target_keyword, suggested_titles, recommended_word_count,
               cannibalization_risk, content_angle, difficulty_level,
               status, created_at
        FROM content_briefs
        WHERE site_id = $1
        ORDER BY created_at DESC
        LIMIT 50
        """,
        site_id,
    )

    return [
        {
            "id": str(r["id"]),
            "target_keyword": r["target_keyword"],
            "suggested_titles": r["suggested_titles"] or [],
            "recommended_word_count": r["recommended_word_count"],
            "cannibalization_risk": r["cannibalization_risk"],
            "content_angle": r["content_angle"],
            "difficulty_level": r["difficulty_level"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/{site_id}/intelligence/briefs/{brief_id}")
async def get_content_brief(
    site_id: UUID,
    brief_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get a single content brief with full detail."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        "SELECT * FROM content_briefs WHERE id = $1 AND site_id = $2",
        brief_id, site_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Brief not found")

    import json as _json

    outline = row["outline"]
    if isinstance(outline, str):
        try:
            outline = _json.loads(outline)
        except (ValueError, TypeError):
            outline = []

    links_from = row.get("internal_links_from")
    if isinstance(links_from, str):
        try:
            links_from = _json.loads(links_from)
        except (ValueError, TypeError):
            links_from = []

    links_to = row.get("internal_links_to")
    if isinstance(links_to, str):
        try:
            links_to = _json.loads(links_to)
        except (ValueError, TypeError):
            links_to = []

    return {
        "id": str(row["id"]),
        "site_id": str(row["site_id"]),
        "target_keyword": row["target_keyword"],
        "secondary_keywords": row["secondary_keywords"] or [],
        "suggested_titles": row["suggested_titles"] or [],
        "recommended_word_count": row["recommended_word_count"],
        "outline": outline,
        "questions_to_answer": row["questions_to_answer"] or [],
        "cannibalization_risk": row.get("cannibalization_risk"),
        "differentiation_notes": row.get("differentiation_notes"),
        "avoid_topics": row.get("avoid_topics") or [],
        "internal_links_from": links_from or [],
        "internal_links_to": links_to or [],
        "content_angle": row.get("content_angle"),
        "difficulty_level": row.get("difficulty_level"),
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.delete("/{site_id}/intelligence/briefs/{brief_id}", status_code=204)
async def delete_content_brief(
    site_id: UUID,
    brief_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Delete a content brief."""
    await _verify_site(site_id, user_id, db)

    result = await db.execute(
        "DELETE FROM content_briefs WHERE id = $1 AND site_id = $2",
        brief_id, site_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Brief not found")


# ──────────────── Position Alerts (Continuous Monitoring) ────────────────


@router.get(
    "/{site_id}/intelligence/alerts",
    response_model=AlertsListResponse,
)
async def list_alerts(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    status: str | None = None,
    limit: int = 50,
):
    """Get recent position monitoring alerts for a site."""
    await _verify_site(site_id, user_id, db)

    from app.services.position_monitor import PositionMonitor

    monitor = PositionMonitor()
    alerts = await monitor.get_alerts(db, site_id, status=status, limit=limit)

    return AlertsListResponse(
        alerts=[PositionAlertResponse(**a) for a in alerts],
        total=len(alerts),
    )


# ──────────────── Since Last Visit ────────────────


@router.get(
    "/{site_id}/intelligence/since-last-visit",
    response_model=SinceLastVisitResponse,
)
async def since_last_visit(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get changes since the user's last visit for the Today view."""
    await _verify_site(site_id, user_id, db)

    # Get last check-in timestamp from user_streaks
    last_visit_row = await db.fetchrow(
        "SELECT last_check_in FROM user_streaks WHERE user_id = $1",
        user_id,
    )
    last_visit = last_visit_row["last_check_in"] if last_visit_row else None

    if not last_visit:
        return SinceLastVisitResponse(
            new_problems_count=0,
            new_alerts_count=0,
            completed_recommendations_count=0,
            new_alerts=[],
            last_visit=None,
        )

    # New problems since last visit
    new_problems = await db.fetchval(
        """
        SELECT COUNT(*) FROM content_problems
        WHERE site_id = $1 AND detected_at > $2 AND resolved_at IS NULL
        """,
        site_id,
        last_visit,
    ) or 0

    # New position alerts since last visit
    from app.services.position_monitor import PositionMonitor
    monitor = PositionMonitor()
    new_alert_list = await monitor.get_alerts_since(db, site_id, last_visit)

    # Recommendations completed since last visit
    completed_recs = await db.fetchval(
        """
        SELECT COUNT(*) FROM recommendations
        WHERE site_id = $1 AND status = 'completed' AND updated_at > $2
        """,
        site_id,
        last_visit,
    ) or 0

    return SinceLastVisitResponse(
        new_problems_count=new_problems,
        new_alerts_count=len(new_alert_list),
        completed_recommendations_count=completed_recs,
        new_alerts=[PositionAlertResponse(**a) for a in new_alert_list[:5]],
        last_visit=last_visit.isoformat() if last_visit else None,
    )


# ──────────────── Analysis Diff ────────────────


@router.get("/{site_id}/intelligence/analysis-diff")
async def get_analysis_diff(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get the most recent analysis diff (before/after comparison)."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        """SELECT score_before, score_after, score_delta,
                  factor_changes, improvements, new_issues, degradations, analyzed_at
           FROM analysis_diffs
           WHERE site_id = $1
           ORDER BY analyzed_at DESC LIMIT 1""",
        site_id,
    )
    if not row:
        return None

    import json

    def _parse(val: str | list | None) -> list:
        if val is None:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "score_before": float(row["score_before"]) if row["score_before"] is not None else None,
        "score_after": float(row["score_after"]) if row["score_after"] is not None else None,
        "score_delta": float(row["score_delta"]) if row["score_delta"] is not None else None,
        "factor_changes": _parse(row["factor_changes"]),
        "improvements": _parse(row["improvements"]),
        "new_issues": _parse(row["new_issues"]),
        "degradations": _parse(row["degradations"]),
        "analyzed_at": row["analyzed_at"].isoformat() if row["analyzed_at"] else None,
    }


# ──────────────── Impact Estimate ────────────────

# Estimated health score points per recommendation type.
_IMPACT_WEIGHTS: dict[str, float] = {
    "merge": 3.0,
    "expand": 2.0,
    "optimize": 1.5,
    "refresh": 1.5,
    "interlink": 1.0,
    "growth": 1.0,
    "delete": 0.5,
}


@router.get(
    "/{site_id}/intelligence/recommendations/impact-estimate",
    response_model=ImpactEstimateResponse,
)
async def get_impact_estimate(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Estimate health score impact from recommendations completed since last analysis."""
    await _verify_site(site_id, user_id, db)

    # Find last analysis timestamp
    last_analysis = await db.fetchval(
        "SELECT analyzed_at FROM health_score_history WHERE site_id = $1 ORDER BY analyzed_at DESC LIMIT 1",
        site_id,
    )

    # Count completed recs by type since last analysis (or all if no analysis yet)
    if last_analysis:
        rows = await db.fetch(
            """SELECT recommendation_type, COUNT(*) AS cnt
               FROM recommendations
               WHERE site_id = $1 AND status = 'completed' AND updated_at > $2
               GROUP BY recommendation_type""",
            site_id, last_analysis,
        )
    else:
        rows = await db.fetch(
            """SELECT recommendation_type, COUNT(*) AS cnt
               FROM recommendations
               WHERE site_id = $1 AND status = 'completed'
               GROUP BY recommendation_type""",
            site_id,
        )

    completed_count = sum(r["cnt"] for r in rows)
    if completed_count == 0:
        return ImpactEstimateResponse(estimated_points=0, completed_since_last_analysis=0)

    # Compute weighted sum
    total_posts = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id) or 1
    raw_points = sum(
        _IMPACT_WEIGHTS.get(r["recommendation_type"], 1.0) * r["cnt"]
        for r in rows
    )
    # Scale: points per rec diminish as more are completed (log-ish scaling)
    estimated = min(15.0, raw_points / max(total_posts / 50, 1))

    return ImpactEstimateResponse(
        estimated_points=round(estimated, 1),
        completed_since_last_analysis=completed_count,
    )


# ──────────────── ROI Summary ────────────────


@router.get(
    "/{site_id}/intelligence/roi-summary",
    response_model=ROISummaryResponse,
)
async def get_roi_summary(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get ROI summary for the Today view — traffic recovery estimate and health change."""
    await _verify_site(site_id, user_id, db)

    # Completed recommendations count
    completed_recs = await db.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND status = 'completed'",
        site_id,
    ) or 0

    # Estimated traffic recovery from impact tracking
    traffic_recovery = await db.fetchval(
        """
        SELECT COALESCE(SUM(
            GREATEST(0, COALESCE(latest_traffic, 0) - COALESCE(baseline_traffic, 0))
        ), 0)
        FROM impact_tracking
        WHERE site_id = $1
        """,
        site_id,
    ) or 0

    # Traffic value estimate ($1.00 per organic visit benchmark)
    traffic_value = float(traffic_recovery) * 1.0

    # Days since first completed recommendation
    first_completed = await db.fetchval(
        """
        SELECT MIN(updated_at) FROM recommendations
        WHERE site_id = $1 AND status = 'completed'
        """,
        site_id,
    )
    from datetime import datetime
    days_active = 0
    if first_completed:
        days_active = (datetime.now(UTC) - first_completed).days

    # Health score change: earliest vs latest from health_score_history
    health_history = await db.fetch(
        """
        SELECT score, analyzed_at FROM health_score_history
        WHERE site_id = $1
        ORDER BY analyzed_at ASC
        """,
        site_id,
    )

    initial_health = None
    current_health = None
    health_change = None
    if health_history and len(health_history) >= 2:
        initial_health = float(health_history[0]["score"])
        current_health = float(health_history[-1]["score"])
        health_change = current_health - initial_health

    return ROISummaryResponse(
        completed_recommendations=completed_recs,
        estimated_traffic_recovery=int(traffic_recovery),
        estimated_traffic_value=round(traffic_value, 2),
        days_active=days_active,
        health_score_change=round(health_change, 1) if health_change is not None else None,
        initial_health_score=round(initial_health, 1) if initial_health is not None else None,
        current_health_score=round(current_health, 1) if current_health is not None else None,
    )


# ──────────────── Top Content Gap ────────────────


@router.get(
    "/{site_id}/intelligence/top-content-gap",
    response_model=TopContentGapResponse | None,
)
async def get_top_content_gap(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get the top content gap for the Today view — a high-impression query with no targeted post.

    Uses content_gaps table populated by the gap analyzer, joined with cluster
    labels for context. Returns the highest-opportunity gap that doesn't have
    a brief yet.
    """
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        """
        SELECT cg.id, cg.query, cg.impressions, cg.avg_position,
               c.label AS cluster_label, cg.brief
        FROM content_gaps cg
        LEFT JOIN clusters c ON c.id = cg.closest_cluster_id
        WHERE cg.site_id = $1
          AND cg.status = 'open'
        ORDER BY cg.impressions DESC
        LIMIT 1
        """,
        site_id,
    )

    if not row:
        return None

    return TopContentGapResponse(
        gap_id=str(row["id"]),
        query=row["query"],
        impressions=row["impressions"],
        avg_position=float(row["avg_position"]) if row["avg_position"] else None,
        cluster_label=row["cluster_label"],
        brief_text=row["brief"],
    )
