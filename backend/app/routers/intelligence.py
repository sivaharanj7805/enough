"""Intelligence endpoints — clustering, cannibalization, health, consolidation, oracle."""

import logging
from uuid import UUID
from typing import Annotated

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
    """Background: run full intelligence pipeline in sequence with status tracking."""
    from app.services.clustering import TopicClusterer
    from app.services.cannibalization import CannibalizationDetector
    from app.services.health_scoring import HealthScorer

    logger.info("BG task: full intelligence pipeline started for site %s", site_id)
    pool = await get_pool()

    # Initialize pipeline status
    await _update_pipeline_status(pool, site_id, started=True, current_step="clustering")

    try:
        async with pool.acquire() as conn:
            # Step 1: Clustering
            clusterer = TopicClusterer()
            clusters = await clusterer.cluster_site(conn, site_id)
            logger.info("Pipeline step 1 complete: %d clusters", clusters)

        await _update_pipeline_status(
            pool, site_id,
            current_step="cannibalization",
            step_completed="clustering",
        )

        async with pool.acquire() as conn:
            # Step 2: Cannibalization
            detector = CannibalizationDetector()
            pairs = await detector.detect_for_site(conn, site_id)
            logger.info("Pipeline step 2 complete: %d cannibalization pairs", pairs)

        await _update_pipeline_status(
            pool, site_id,
            current_step="health_scoring",
            step_completed="cannibalization",
        )

        async with pool.acquire() as conn:
            # Step 3: Health scoring
            scorer = HealthScorer()
            scored = await scorer.score_site(conn, site_id)
            logger.info("Pipeline step 3 complete: %d posts scored", scored)

        await _update_pipeline_status(
            pool, site_id,
            status="completed",
            current_step=None,
            step_completed="health_scoring",
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
    background_tasks.add_task(_run_clustering, site_id)
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
