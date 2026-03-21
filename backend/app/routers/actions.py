"""Action Layer endpoints — ecosystem voice, content calendar, redirect push, meta push."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id
from app.models.schemas import (
    ClusterNarrativeResponse,
    CalendarResponse,
    CalendarRecommendation,
    RedirectPushRequest,
    RedirectStatusResponse,
    RedirectStatusEntry,
    TaskTriggerResponse,
    PushMetaRequest,
    PushMetaResponse,
)

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


async def _run_narrative_generation(site_id: UUID) -> None:
    """Background: generate narratives for all clusters."""
    from app.services.ecosystem_voice import EcosystemVoice

    logger.info("BG task: narrative generation started for site %s", site_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            voice = EcosystemVoice()
            count = await voice.generate_for_site(conn, site_id)
            logger.info(
                "BG task: narrative generation complete — %d narratives for site %s",
                count, site_id,
            )
        except Exception as e:
            logger.error(
                "BG task: narrative generation failed for site %s: %s", site_id, e
            )


async def _run_calendar_generation(site_id: UUID) -> None:
    """Background: generate calendar recommendations for all clusters."""
    from app.services.calendar_restraint import CalendarRestraint

    logger.info("BG task: calendar generation started for site %s", site_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            calendar = CalendarRestraint()
            results = await calendar.generate_for_site(conn, site_id)
            logger.info(
                "BG task: calendar generation complete — %d recommendations for site %s",
                len(results), site_id,
            )
        except Exception as e:
            logger.error(
                "BG task: calendar generation failed for site %s: %s", site_id, e
            )


# ──────────────────── Ecosystem Voice ────────────────────


@router.get(
    "/{site_id}/intelligence/clusters/{cluster_id}/narrative",
    response_model=ClusterNarrativeResponse,
)
async def get_cluster_narrative(
    site_id: UUID,
    cluster_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get the ecosystem voice narrative for a cluster."""
    await _verify_site(site_id, user_id, db)

    # Verify cluster belongs to site
    cluster = await db.fetchrow(
        "SELECT id FROM clusters WHERE id = $1 AND site_id = $2",
        cluster_id, site_id,
    )
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from app.services.ecosystem_voice import EcosystemVoice

    voice = EcosystemVoice()
    narrative = await voice.get_narrative(db, cluster_id)
    if not narrative:
        raise HTTPException(
            status_code=404,
            detail="No narrative generated yet. Trigger generation first.",
        )

    return ClusterNarrativeResponse(**narrative)


@router.post(
    "/{site_id}/intelligence/narratives/generate",
    response_model=TaskTriggerResponse,
)
async def trigger_narrative_generation(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate/refresh ecosystem voice narratives for all clusters."""
    await _verify_site(site_id, user_id, db)
    background_tasks.add_task(_run_narrative_generation, site_id)
    return TaskTriggerResponse(
        message="Narrative generation started", site_id=site_id
    )


# ──────────────────── Content Calendar ────────────────────


@router.get(
    "/{site_id}/intelligence/calendar",
    response_model=CalendarResponse,
)
async def get_calendar(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get all publishing recommendations for the site."""
    await _verify_site(site_id, user_id, db)

    from app.services.calendar_restraint import CalendarRestraint

    calendar = CalendarRestraint()
    data = await calendar.get_recommendations(db, site_id)

    return CalendarResponse(
        site_id=data["site_id"],
        recommendations=[
            CalendarRecommendation(**r) for r in data["recommendations"]
        ],
        summary=data["summary"],
    )


@router.post(
    "/{site_id}/intelligence/calendar/generate",
    response_model=TaskTriggerResponse,
)
async def trigger_calendar_generation(
    site_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate/refresh publishing recommendations for all clusters."""
    await _verify_site(site_id, user_id, db)
    background_tasks.add_task(_run_calendar_generation, site_id)
    return TaskTriggerResponse(
        message="Calendar recommendation generation started", site_id=site_id
    )


# ──────────────────── Redirect Push ────────────────────


@router.post(
    "/{site_id}/redirects/push",
    response_model=RedirectStatusResponse,
)
async def push_redirects(
    site_id: UUID,
    body: RedirectPushRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Push redirects to WordPress via REST API."""
    await _verify_site(site_id, user_id, db)

    from app.services.redirect_push import RedirectPusher

    pusher = RedirectPusher()
    try:
        result = await pusher.push_redirects(
            db,
            site_id,
            [{"old_url": r.old_url, "new_url": r.new_url} for r in body.redirect_map],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Redirect push failed: %s", e)
        raise HTTPException(status_code=500, detail="Redirect push failed")

    return RedirectStatusResponse(
        site_id=result["site_id"],
        entries=[RedirectStatusEntry(**e) for e in result["entries"]],
        total=result["total"],
        pushed=result["pushed"],
        verified=result["verified"],
        failed=result["failed"],
    )


@router.get(
    "/{site_id}/redirects/status",
    response_model=RedirectStatusResponse,
)
async def get_redirect_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Check status of pushed redirects."""
    await _verify_site(site_id, user_id, db)

    from app.services.redirect_push import RedirectPusher

    pusher = RedirectPusher()
    result = await pusher.get_status(db, site_id)

    return RedirectStatusResponse(
        site_id=result["site_id"],
        entries=[RedirectStatusEntry(**e) for e in result["entries"]],
        total=result["total"],
        pushed=result["pushed"],
        verified=result["verified"],
        failed=result["failed"],
    )


@router.post(
    "/{site_id}/redirects/verify",
    response_model=RedirectStatusResponse,
)
async def verify_redirects(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Verify all pushed redirects are actually working."""
    await _verify_site(site_id, user_id, db)

    from app.services.redirect_push import RedirectPusher

    pusher = RedirectPusher()
    result = await pusher.verify_redirects(db, site_id)

    return RedirectStatusResponse(
        site_id=result["site_id"],
        entries=[RedirectStatusEntry(**e) for e in result["entries"]],
        total=result["total"],
        pushed=result["pushed"],
        verified=result["verified"],
        failed=result["failed"],
    )


# ──────────────── Redirect Map Download ────────────────


@router.get(
    "/{site_id}/intelligence/consolidation/{cluster_id}/redirect-map",
    response_class=PlainTextResponse,
)
async def download_redirect_map(
    site_id: UUID,
    cluster_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    format: str = Query("htaccess", pattern=r"^(htaccess|wordpress|csv)$"),
):
    """Download a redirect map for a consolidation plan in various formats.

    Formats: htaccess (Apache), wordpress (Redirection plugin CSV), csv (generic).
    """
    await _verify_site(site_id, user_id, db)

    from app.services.consolidation import ConsolidationPlanner

    planner = ConsolidationPlanner()
    plan = await planner.get_plan_detail(db, cluster_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consolidation plan not found")

    redirect_map = plan.get("redirect_map", [])
    if not redirect_map:
        raise HTTPException(status_code=404, detail="No redirects in this plan")

    content = ConsolidationPlanner.export_redirect_map(redirect_map, fmt=format)

    ext = {"htaccess": ".htaccess", "wordpress": ".csv", "csv": ".csv"}[format]
    media_type = "text/csv" if format in ("wordpress", "csv") else "text/plain"

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="redirects-{cluster_id}{ext}"',
        },
    )


# ──────────────── WordPress Meta Push ────────────────


@router.post(
    "/{site_id}/actions/push-meta",
    response_model=PushMetaResponse,
)
async def push_meta_to_wordpress(
    site_id: UUID,
    body: PushMetaRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Push title and meta description updates to WordPress via REST API."""
    await _verify_site(site_id, user_id, db)

    site = await db.fetchrow(
        "SELECT wordpress_url, wordpress_app_password, cms_type FROM sites WHERE id = $1",
        site_id,
    )
    if not site or site["cms_type"] != "wordpress" or not site["wordpress_url"]:
        raise HTTPException(
            status_code=400,
            detail="Site is not a WordPress site or missing WordPress URL",
        )

    from app.utils.encryption import decrypt_value
    import httpx

    wp_url = site["wordpress_url"].rstrip("/")
    app_password = ""
    if site["wordpress_app_password"]:
        app_password = decrypt_value(site["wordpress_app_password"])

    post = await db.fetchrow(
        "SELECT id, url, slug FROM posts WHERE id = $1 AND site_id = $2",
        body.post_id,
        site_id,
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    slug = post["slug"] or post["url"].rstrip("/").split("/")[-1]
    pushed_fields = []
    error = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            search_resp = await client.get(
                f"{wp_url}/wp-json/wp/v2/posts",
                params={"slug": slug, "per_page": 1},
                headers={"Authorization": f"Basic {app_password}"},
            )
            if search_resp.status_code != 200 or not search_resp.json():
                raise ValueError(f"Could not find WordPress post with slug '{slug}'")

            wp_post_id = search_resp.json()[0]["id"]

            update_data = {}
            if body.title:
                update_data["title"] = body.title
                pushed_fields.append("title")
            if body.meta_description:
                update_data["meta"] = {
                    "_yoast_wpseo_metadesc": body.meta_description,
                    "rank_math_description": body.meta_description,
                }
                update_data["excerpt"] = body.meta_description
                pushed_fields.append("meta_description")

            if not update_data:
                raise ValueError("No fields to update")

            resp = await client.post(
                f"{wp_url}/wp-json/wp/v2/posts/{wp_post_id}",
                json=update_data,
                headers={
                    "Authorization": f"Basic {app_password}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code not in (200, 201):
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"

    except Exception as e:
        error = str(e)[:300]
        logger.error("Meta push failed for post %s: %s", body.post_id, e)

    return PushMetaResponse(
        post_id=body.post_id,
        pushed_fields=pushed_fields if not error else [],
        error=error,
        success=error is None,
    )
