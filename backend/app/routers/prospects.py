"""Prospect discovery and outreach management endpoints."""

import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prospects", tags=["prospects"])


class DiscoverRequest(BaseModel):
    """Submit domains for prospect discovery."""
    domains: list[str] = []
    niche_keyword: str = ""
    source: str = "manual"  # manual, google_cse


class ProspectOutreachRequest(BaseModel):
    """Override email for outreach."""
    email: str | None = None


@router.post("/discover")
async def discover_prospects(
    body: DiscoverRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Discover prospects from a domain list or niche keyword search.

    - Manual mode: provide `domains` list directly
    - Google CSE mode: provide `niche_keyword` (requires GOOGLE_CSE_KEY env var)
    """
    from app.services.prospect_discovery import discover_prospects_google, discover_prospects_manual

    total = 0

    if body.domains:
        total += await discover_prospects_manual(db, body.domains, niche=body.niche_keyword)

    if body.niche_keyword and body.source == "google_cse":
        total += await discover_prospects_google(db, body.niche_keyword)

    return {"prospects_created": total, "source": body.source}


@router.get("")
async def list_prospects(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    status: str | None = None,
    niche: str | None = None,
    limit: int = 50,
):
    """List all prospects, optionally filtered by status or niche."""
    query = "SELECT * FROM prospects"
    params: list = []
    conditions: list[str] = []

    if status:
        conditions.append(f"status = ${len(params) + 1}")
        params.append(status)
    if niche:
        conditions.append(f"niche = ${len(params) + 1}")
        params.append(niche)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1}"
    params.append(limit)

    rows = await db.fetch(query, *params)
    return {
        "prospects": [dict(r) for r in rows],
        "total": len(rows),
    }


@router.post("/{prospect_id}/audit")
async def audit_prospect(
    prospect_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Run the full audit pipeline on a prospect domain.

    Runs in background — poll GET /prospects to check status.
    """
    prospect = await db.fetchrow("SELECT * FROM prospects WHERE id = $1", prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect not found")

    if prospect["status"] == "auditing":
        return {"message": f"Audit already running for {prospect['domain']}"}

    from app.services.prospect_discovery import run_prospect_audit
    background_tasks.add_task(run_prospect_audit, db, prospect_id)

    return {"message": f"Audit started for {prospect['domain']}", "prospect_id": str(prospect_id)}


@router.post("/{prospect_id}/outreach")
async def outreach_prospect(
    prospect_id: UUID,
    body: ProspectOutreachRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Send audit PDF and start drip email sequence for a prospect.

    Requires the prospect to be audited first. Optionally override the contact email.
    """
    prospect = await db.fetchrow("SELECT * FROM prospects WHERE id = $1", prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect not found")

    if prospect["status"] not in ("audited", "contacted"):
        raise HTTPException(400, f"Prospect must be audited first (current status: {prospect['status']})")

    email = body.email or prospect["contact_email"]
    if not email:
        raise HTTPException(400, "No contact email — provide one in the request body or run email enrichment first")

    # Update email if overridden
    if body.email:
        await db.execute("UPDATE prospects SET contact_email = $1 WHERE id = $2", email, prospect_id)

    site_id = prospect["site_id"]
    if not site_id:
        raise HTTPException(400, "Prospect has no site_id — run audit first")

    # Generate PDF and schedule drip
    from app.routers.audit_report import _build_audit_data_for_site
    from app.services.drip_sequence import DripSequenceService
    from app.services.pdf_report import generate_audit_pdf

    site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
    audit_data = await _build_audit_data_for_site(db, site_id, dict(site))
    pdf_bytes = generate_audit_pdf(audit_data)

    drip = DripSequenceService()
    await drip.schedule_drip(db, email, prospect["domain"], site_id, audit_data, pdf_bytes)

    await db.execute(
        "UPDATE prospects SET status = 'contacted', contacted_at = NOW() WHERE id = $1",
        prospect_id,
    )

    return {"message": f"Outreach sent to {email} for {prospect['domain']}", "email": email}


@router.post("/enrich-emails")
async def enrich_emails(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Find contact emails for prospects that don't have one.

    Scrapes /about and /contact pages for each prospect domain.
    """
    from app.services.prospect_discovery import enrich_prospect_emails
    enriched = await enrich_prospect_emails(db)
    return {"enriched": enriched}


@router.get("/stats")
async def prospect_stats(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Conversion funnel stats for prospect outreach."""
    stats = await db.fetchrow("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'discovered') as discovered,
            COUNT(*) FILTER (WHERE status = 'auditing') as auditing,
            COUNT(*) FILTER (WHERE status = 'audited') as audited,
            COUNT(*) FILTER (WHERE status = 'contacted') as contacted,
            COUNT(*) FILTER (WHERE status = 'responded') as responded,
            COUNT(*) FILTER (WHERE status = 'converted') as converted,
            COUNT(*) FILTER (WHERE contact_email IS NOT NULL) as with_email
        FROM prospects
    """)
    return dict(stats) if stats else {}
