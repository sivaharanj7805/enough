"""Competitor comparison endpoints."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    competitor_domain: str


async def _verify_site(site_id: UUID, user_id: str, db: asyncpg.Connection) -> None:
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


@router.post("/{site_id}/competitors/compare")
async def compare_competitor(
    site_id: UUID,
    body: CompareRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Compare site content against a competitor domain."""
    await _verify_site(site_id, user_id, db)

    from app.services.competitor_compare import CompetitorCompareService

    service = CompetitorCompareService()
    result = await service.compare(db, site_id, body.competitor_domain)

    return result


@router.get("/{site_id}/competitors")
async def list_comparisons(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List previous competitor comparisons."""
    await _verify_site(site_id, user_id, db)

    from app.services.competitor_compare import CompetitorCompareService

    service = CompetitorCompareService()
    results = await service.list_comparisons(db, site_id)

    return {"comparisons": results}
