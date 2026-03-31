"""Site management endpoints."""

import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id, require_site_limit
from app.models.schemas import SiteCreate, SiteListResponse, SiteResponse
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


class SiteSettingsUpdate(BaseModel):
    url: str | None = None
    cms_type: str | None = None
    recrawl_schedule: str | None = None


class NotificationSettingsUpdate(BaseModel):
    digest_frequency: str | None = None


@router.patch("/{site_id}/settings")
async def update_site_settings(
    site_id: UUID,
    body: SiteSettingsUpdate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Update site settings (URL, CMS type, recrawl schedule)."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    if body.url:
        _validate_url_not_internal(body.url, "url")

    updates: list[str] = []
    params: list = []
    idx = 1

    if body.url is not None:
        updates.append(f"domain = ${idx}")
        from urllib.parse import urlparse
        parsed = urlparse(body.url if "://" in body.url else f"https://{body.url}")
        domain = parsed.netloc or parsed.path
        params.append(domain.replace("www.", "").strip("/"))
        idx += 1

    if body.cms_type is not None:
        valid_cms = ("wordpress", "sitemap", "hubspot", "webflow", "ghost", "other")
        if body.cms_type not in valid_cms:
            raise HTTPException(status_code=422, detail=f"cms_type must be one of: {', '.join(valid_cms)}")
        updates.append(f"cms_type = ${idx}")
        params.append(body.cms_type)
        idx += 1

    if body.recrawl_schedule is not None:
        valid_schedules = ("manual", "weekly", "monthly")
        if body.recrawl_schedule not in valid_schedules:
            raise HTTPException(status_code=422, detail=f"recrawl_schedule must be one of: {', '.join(valid_schedules)}")
        updates.append(f"recrawl_schedule = ${idx}")
        params.append(body.recrawl_schedule)
        idx += 1

    if not updates:
        return {"message": "No changes"}

    updates.append("updated_at = NOW()")
    query = f"UPDATE sites SET {', '.join(updates)} WHERE id = ${idx} AND user_id = ${idx + 1}"
    params.extend([site_id, user_id])
    await db.execute(query, *params)

    return {"message": "Site settings updated"}


@router.patch("/{site_id}/notifications")
async def update_notification_settings(
    site_id: UUID,
    body: NotificationSettingsUpdate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Update notification preferences for a site."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    if body.digest_frequency is not None:
        valid_freqs = ("weekly", "biweekly", "monthly", "off")
        if body.digest_frequency not in valid_freqs:
            raise HTTPException(status_code=422, detail=f"digest_frequency must be one of: {', '.join(valid_freqs)}")
        await db.execute(
            "UPDATE sites SET digest_frequency = $1, updated_at = NOW() WHERE id = $2 AND user_id = $3",
            body.digest_frequency, site_id, user_id,
        )

    return {"message": "Notification preferences updated"}


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
    data.pop("google_tokens", None)
    return SiteResponse(**data)
