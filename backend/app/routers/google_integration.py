"""Google OAuth2 + GSC/GA4 sync endpoints."""
from __future__ import annotations

import json
import os
import secrets
import time
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.dependencies import get_current_user_id
from app.database import get_db
from app.services.google_auth import (
    decrypt_token,
    encrypt_token,
    exchange_code,
    get_auth_url,
    get_valid_token,
)
from app.services.gsc_sync import GSCSyncService
from app.services.ga4_sync import GA4SyncService

router = APIRouter(tags=["google"])


# ── OAuth Flow ────────────────────────────────────────────────────────────────

@router.get("/sites/{site_id}/google/connect")
async def start_google_oauth(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Redirect user to Google OAuth consent screen."""
    site = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not site:
        raise HTTPException(404, "Site not found")

    state = f"{site_id}:{user_id}:{secrets.token_urlsafe(16)}"
    auth_url = get_auth_url(state)
    return {"auth_url": auth_url}


@router.get("/auth/google/callback")
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    db: asyncpg.Connection = Depends(get_db),
):
    """Handle Google OAuth callback and store tokens."""
    if error:
        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings?google_error={error}")

    parts = state.split(":")
    if len(parts) < 2:
        raise HTTPException(400, "Invalid state")

    site_id_str, user_id = parts[0], parts[1]
    try:
        site_id = UUID(site_id_str)
    except ValueError:
        raise HTTPException(400, "Invalid site ID in state")

    try:
        token_data = await exchange_code(code)
    except Exception as e:
        raise HTTPException(500, f"Token exchange failed: {e}")

    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    encrypted = encrypt_token(token_data)

    await db.execute(
        "UPDATE sites SET google_tokens = $1 WHERE id = $2",
        encrypted, site_id,
    )

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(f"{frontend_url}/settings?google_connected=1&site_id={site_id}")


@router.delete("/sites/{site_id}/google/disconnect")
async def disconnect_google(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Remove stored Google tokens."""
    await db.execute(
        "UPDATE sites SET google_tokens = NULL WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    return {"disconnected": True}


@router.get("/sites/{site_id}/google/status")
async def google_connection_status(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Check if Google is connected and return sync status."""
    row = await db.fetchrow(
        """SELECT google_tokens, gsc_site_url, ga4_property_id,
                  last_gsc_sync, last_ga4_sync
           FROM sites WHERE id = $1 AND user_id = $2""",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(404, "Site not found")

    connected = bool(row["google_tokens"])
    return {
        "connected": connected,
        "gsc_site_url": row["gsc_site_url"],
        "ga4_property_id": row["ga4_property_id"],
        "last_gsc_sync": row["last_gsc_sync"].isoformat() if row["last_gsc_sync"] else None,
        "last_ga4_sync": row["last_ga4_sync"].isoformat() if row["last_ga4_sync"] else None,
    }


# ── GSC Endpoints ─────────────────────────────────────────────────────────────

@router.post("/sites/{site_id}/gsc/sync")
async def sync_gsc(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    days_back: int = Query(90, ge=7, le=365),
):
    """Trigger a GSC data sync."""
    svc = GSCSyncService()
    result = await svc.sync_site(db, site_id, user_id, days_back=days_back)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/sites/{site_id}/gsc/sites")
async def list_gsc_sites(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all GSC-verified sites for the connected Google account."""
    token = await get_valid_token(db, site_id, user_id)
    if not token:
        raise HTTPException(400, "Google account not connected")
    svc = GSCSyncService()
    sites = await svc.list_gsc_sites(token)
    return {"sites": sites}


class SetGSCSiteRequest(BaseModel):
    gsc_site_url: str


@router.patch("/sites/{site_id}/gsc/site-url")
async def set_gsc_site_url(
    site_id: UUID,
    body: SetGSCSiteRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Manually set the GSC site URL for a site."""
    await db.execute(
        "UPDATE sites SET gsc_site_url = $1 WHERE id = $2 AND user_id = $3",
        body.gsc_site_url, site_id, user_id,
    )
    return {"gsc_site_url": body.gsc_site_url}


# ── GA4 Endpoints ─────────────────────────────────────────────────────────────

@router.post("/sites/{site_id}/ga4/sync")
async def sync_ga4(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    days_back: int = Query(90, ge=7, le=365),
):
    """Trigger a GA4 data sync."""
    svc = GA4SyncService()
    result = await svc.sync_site(db, site_id, user_id, days_back=days_back)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/sites/{site_id}/ga4/properties")
async def list_ga4_properties(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all GA4 properties for the connected Google account."""
    token = await get_valid_token(db, site_id, user_id)
    if not token:
        raise HTTPException(400, "Google account not connected")
    svc = GA4SyncService()
    properties = await svc.list_ga4_properties(token)
    return {"properties": properties}


class SetGA4PropertyRequest(BaseModel):
    property_id: str


@router.patch("/sites/{site_id}/ga4/property-id")
async def set_ga4_property_id(
    site_id: UUID,
    body: SetGA4PropertyRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Manually set the GA4 property ID for a site."""
    await db.execute(
        "UPDATE sites SET ga4_property_id = $1 WHERE id = $2 AND user_id = $3",
        body.property_id, site_id, user_id,
    )
    return {"property_id": body.property_id}


# ── Combined sync ─────────────────────────────────────────────────────────────

@router.post("/sites/{site_id}/google/sync-all")
async def sync_all_google_data(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    days_back: int = Query(90, ge=7, le=365),
):
    """Sync both GSC and GA4 data in one call."""
    gsc_result = await GSCSyncService().sync_site(db, site_id, user_id, days_back=days_back)
    ga4_result = await GA4SyncService().sync_site(db, site_id, user_id, days_back=days_back)
    return {
        "gsc": gsc_result,
        "ga4": ga4_result,
    }
