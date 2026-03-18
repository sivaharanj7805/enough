"""Intelligence endpoints — clustering, cannibalization, health, consolidation, oracle."""

import logging
from uuid import UUID
from typing import Annotated

# In-memory lock to prevent concurrent pipeline runs per site
_running_pipelines: set[UUID] = set()

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id

limiter = Limiter(key_func=get_remote_address)
from app.models.schemas import (
    TaskTriggerResponse,
    ClusterResponse,
    ClusterDetailResponse,
    PostHealthResponse,
    CannibalizationPairResponse,
    SiteHealthResponse,
    ClusterSummary,
    ConsolidationPlanResponse,
    ConsolidationDetailResponse,
    ConsolidationDraftResponse,
    RedirectEntry,
    OracleRequest,
    OracleVerdictResponse,
    SimilarPostInfo,
    PillarPostInfo,
    MergeCandidateInfo,
    PipelineStatusResponse,
    EcosystemVisualsResponse,
    ContentProblemResponse,
    ContentProblemSummary,
    ProblemDetectionResponse,
    RecommendationResponse,
    RecommendationListResponse,
    RecommendationStatusUpdate,
    CannibalizationRecommendationRequest,
)

from app.utils.task_retry import with_retry

logger = logging.getLogger(__name__)
router = APIRouter()


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
        await _run_clustering(site_id)
    finally:
        _running_pipelines.discard(site_id)


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
    from datetime import datetime, timezone
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
                site_id, current_step, datetime.now(timezone.utc),
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
            params.append(datetime.now(timezone.utc))
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
    from app.services.clustering import TopicClusterer
    from app.services.cannibalization import CannibalizationDetector
    from app.services.health_scoring import HealthScorer
    from app.services.problem_detection import ProblemDetector
    from app.services.recommendations import RecommendationEngine

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

        # Step 5: AI Recommendations
        async with pool.acquire() as conn:
            engine = RecommendationEngine()
            recs = await engine.generate_for_site(conn, site_id)
            logger.info("Pipeline step 5 complete: %d recommendations generated", recs)

        await _update_pipeline_status(
            pool, site_id,
            status="completed",
            current_step=None,
            step_completed="recommendations",
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
    if site_id in _running_pipelines:
        raise HTTPException(status_code=429, detail="Pipeline already running for this site")
    _running_pipelines.add(site_id)
    background_tasks.add_task(_run_clustering_safe, site_id)
    return TaskTriggerResponse(message="Clustering started", site_id=site_id)


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
        SELECT * FROM clusters
        WHERE site_id = $1
        AND id NOT IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
        ORDER BY post_count DESC
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
               ph.traffic_contribution, ph.ranking_strength, ph.internal_link_score
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
):
    """List all cannibalization pairs grouped by cluster, sorted by severity."""
    await _verify_site(site_id, user_id, db)

    severity_order = "CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"
    rows = await db.fetch(
        f"""
        SELECT cp.id, cp.cluster_id, cp.overlap_score, cp.severity,
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
        """,
        site_id,
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
    cannibalistic_posts = roles.get("competitor", 0)
    dead_posts = roles.get("dead_weight", 0)
    passive_posts = total_posts - active_posts - cannibalistic_posts - dead_posts

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

    return SiteHealthResponse(
        content_health_score=float(avg_health),
        total_posts=total_posts,
        active_posts=active_posts,
        passive_posts=passive_posts,
        cannibalistic_posts=cannibalistic_posts,
        dead_posts=dead_posts,
        content_efficiency_ratio=round(efficiency, 3),
        clusters=clusters,
        trends=trends,
        data_completeness=data_completeness,
        modified_date_coverage=round(modified_date_coverage, 3),
        ai_enriched_count=int(ai_enriched_count or 0),
    )


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
        result = await planner.generate_draft(db, cluster_id)
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
    limit: int = 200,
    offset: int = 0,
):
    """List all detected content problems for a site."""
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
        from app.services.recommendations import RecommendationEngine
        pool = await get_pool()
        async with pool.acquire() as conn:
            engine = RecommendationEngine()
            count = await engine.generate_for_site(conn, sid)
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
):
    """List all recommendations for a site with optional filters."""
    await _verify_site(site_id, user_id, db)

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
            from app.services.health_scoring import HealthScoringService
            from app.services.problem_detection import ProblemDetectionService
            from app.services.fast_recommendations import generate_fast_recommendations

            hs = HealthScoringService()
            await hs.score_site(db, site_id)

            pd = ProblemDetectionService()
            await pd.detect_problems(db, site_id)

            await generate_fast_recommendations(db, site_id)
            logger.info("Quick scan complete for %s in %.1fs", site_id, time.time() - t0)
        except Exception as e:
            logger.error("Quick scan failed for %s: %s", site_id, e)

    background_tasks.add_task(_run)
    return {"message": "Quick scan started — refreshes health, problems, and recommendations (~30s)", "status": "running"}


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
