"""Site management endpoints."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Header

from app.database import get_db
from app.models.schemas import SiteCreate, SiteResponse, SiteListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_user_id(authorization: Annotated[str, Header()]) -> str:
    """Extract user ID from the authorization header.

    In production this would validate the Supabase JWT.
    For Phase 1, we accept the user_id directly as a bearer token
    or validate via Supabase.
    """
    token = authorization.replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization")
    # Phase 1: trust the token as user_id for development
    # Production: validate JWT via Supabase and extract sub claim
    return token


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(
    body: SiteCreate,
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Add a new site for crawling."""
    try:
        row = await db.fetchrow(
            """
            INSERT INTO sites (user_id, name, domain, cms_type, wordpress_url,
                               wordpress_app_password, sitemap_url,
                               ga4_property_id, gsc_site_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            user_id, body.name, body.domain, body.cms_type,
            body.wordpress_url, body.wordpress_app_password,
            body.sitemap_url, body.ga4_property_id, body.gsc_site_url,
        )
        return SiteResponse(**dict(row))
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=400, detail="User profile not found")
    except Exception as e:
        logger.error("Failed to create site: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create site")


@router.get("", response_model=SiteListResponse)
async def list_sites(
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all sites for the authenticated user."""
    rows = await db.fetch(
        "SELECT * FROM sites WHERE user_id = $1 ORDER BY created_at DESC",
        user_id,
    )
    sites = [SiteResponse(**dict(r)) for r in rows]
    return SiteListResponse(sites=sites, total=len(sites))


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get a single site by ID."""
    row = await db.fetchrow(
        "SELECT * FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return SiteResponse(**dict(row))


@router.delete("/{site_id}", status_code=204)
async def delete_site(
    site_id: UUID,
    user_id: Annotated[str, Depends(_get_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Remove a site and all associated data (cascades)."""
    result = await db.execute(
        "DELETE FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Site not found")
