"""Competitor comparison endpoints."""

import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    competitor_domain: str

    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 253 or not v or "/" in v or " " in v:
            raise ValueError("Invalid domain format")
        return v


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


@router.post("/{site_id}/competitors/ai-benchmark")
async def ai_benchmark(
    site_id: UUID,
    body: CompareRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Benchmark AI readiness against a competitor.

    Crawls up to 50 pages from the competitor, scores them with the same
    AI citability/E-E-A-T/schema/extraction functions, and returns a
    head-to-head comparison with gaps and actionable insights.
    """
    await _verify_site(site_id, user_id, db)

    from app.services.competitor_benchmark import benchmark_competitor
    result = await benchmark_competitor(db, site_id, body.competitor_domain, max_pages=50)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

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
