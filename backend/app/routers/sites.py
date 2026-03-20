"""Site management endpoints."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id, require_site_limit
from app.models.schemas import SiteCreate, SiteResponse, SiteListResponse
from app.utils.encryption import encrypt_value

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_url_not_internal(url: str | None, field_name: str) -> None:
    """Prevent SSRF by rejecting URLs pointing to internal/private IP ranges."""
    if not url:
        return
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Reject non-HTTP schemes
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(
                status_code=422,
                detail=f"{field_name}: only http/https URLs are allowed",
            )

        # Try to parse as IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name}: internal/private IP addresses are not allowed",
                )
        except ValueError:
            # Not an IP — hostname like example.com, check for localhost
            if hostname.lower() in ("localhost", "::1") or hostname.endswith(".local"):
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name}: localhost and .local domains are not allowed",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("URL validation error for %s=%r: %s", field_name, url, e)


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(
    body: SiteCreate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    _tier: None = Depends(require_site_limit),
):
    """Add a new site for crawling."""
    # Validate URLs to prevent SSRF attacks against internal infrastructure
    _validate_url_not_internal(body.wordpress_url, "wordpress_url")
    _validate_url_not_internal(body.sitemap_url, "sitemap_url")

    encrypted_wp_password = encrypt_value(body.wordpress_app_password) if body.wordpress_app_password else None

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
            body.wordpress_url, encrypted_wp_password,
            body.sitemap_url, body.ga4_property_id, body.gsc_site_url,
        )
        return _sanitize_site_response(row)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=400, detail="User profile not found")
    except Exception as e:
        logger.error("Failed to create site: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create site")


@router.get("", response_model=SiteListResponse)
async def list_sites(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all sites for the authenticated user."""
    rows = await db.fetch(
        "SELECT * FROM sites WHERE user_id = $1 ORDER BY created_at DESC",
        user_id,
    )
    sites = [_sanitize_site_response(r) for r in rows]
    return SiteListResponse(sites=sites, total=len(sites))


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get a single site by ID."""
    row = await db.fetchrow(
        "SELECT * FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return _sanitize_site_response(row)


@router.delete("/{site_id}", status_code=204)
async def delete_site(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Remove a site and all associated data (cascades)."""
    result = await db.execute(
        "DELETE FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Site not found")


class GoogleTokenUpdate(BaseModel):
    refresh_token: str


@router.put("/{site_id}/google-token", status_code=200)
async def store_google_token(
    site_id: UUID,
    body: GoogleTokenUpdate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Store an encrypted Google refresh token for GA4/GSC access."""
    encrypted_token = encrypt_value(body.refresh_token)
    result = await db.execute(
        "UPDATE sites SET google_tokens = $1, updated_at = NOW() WHERE id = $2 AND user_id = $3",
        encrypted_token, site_id, user_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Site not found")
    return {"message": "Google refresh token stored securely"}


def _sanitize_site_response(row) -> SiteResponse:
    """Build a SiteResponse, stripping encrypted fields from output."""
    data = dict(row)
    data.pop("wordpress_app_password", None)
    data.pop("google_refresh_token", None)
    return SiteResponse(**data)
