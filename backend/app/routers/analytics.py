"""Analytics and post data endpoints."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.schemas import (
    PostResponse, PostDetailResponse, PostListResponse,
    GA4MetricResponse, GSCMetricResponse, InternalLinkSchema,
    AnalyticsOverview,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify_site_ownership(
    site_id: UUID, user_id: str, db: asyncpg.Connection,
) -> None:
    """Ensure the user owns the site."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


@router.get("/{site_id}/posts", response_model=PostListResponse)
async def list_posts(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all posts for a site with pagination."""
    await _verify_site_ownership(site_id, user_id, db)

    total = await db.fetchval(
        "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
    )
    rows = await db.fetch(
        """
        SELECT * FROM posts
        WHERE site_id = $1
        ORDER BY publish_date DESC NULLS LAST
        LIMIT $2 OFFSET $3
        """,
        site_id, limit, offset,
    )
    posts = [PostResponse(**dict(r)) for r in rows]
    return PostListResponse(posts=posts, total=total)


@router.get("/{site_id}/posts/{post_id}", response_model=PostDetailResponse)
async def get_post_detail(
    site_id: UUID,
    post_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get a single post with full metrics."""
    await _verify_site_ownership(site_id, user_id, db)

    post_row = await db.fetchrow(
        "SELECT * FROM posts WHERE id = $1 AND site_id = $2",
        post_id, site_id,
    )
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")

    # Fetch GA4 metrics
    ga4_rows = await db.fetch(
        "SELECT * FROM ga4_metrics WHERE post_id = $1 ORDER BY date DESC LIMIT 90",
        post_id,
    )
    ga4_metrics = [GA4MetricResponse(**dict(r)) for r in ga4_rows]

    # Fetch GSC metrics
    gsc_rows = await db.fetch(
        "SELECT * FROM gsc_metrics WHERE post_id = $1 ORDER BY date DESC LIMIT 500",
        post_id,
    )
    gsc_metrics = [GSCMetricResponse(**dict(r)) for r in gsc_rows]

    # Fetch internal links
    link_rows = await db.fetch(
        "SELECT target_url, anchor_text FROM internal_links WHERE source_post_id = $1",
        post_id,
    )
    internal_links = [InternalLinkSchema(**dict(r)) for r in link_rows]

    post_data = dict(post_row)
    return PostDetailResponse(
        **post_data,
        ga4_metrics=ga4_metrics,
        gsc_metrics=gsc_metrics,
        internal_links=internal_links,
    )


@router.get("/{site_id}/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Aggregated analytics overview for a site."""
    await _verify_site_ownership(site_id, user_id, db)

    total_posts = await db.fetchval(
        "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
    )

    ga4_agg = await db.fetchrow(
        """
        SELECT
            COALESCE(SUM(g.pageviews), 0) AS total_pageviews,
            COALESCE(SUM(g.sessions), 0) AS total_sessions,
            MIN(g.date) AS date_start,
            MAX(g.date) AS date_end
        FROM ga4_metrics g
        JOIN posts p ON p.id = g.post_id
        WHERE p.site_id = $1
        """,
        site_id,
    )

    gsc_agg = await db.fetchrow(
        """
        SELECT
            COALESCE(SUM(g.clicks), 0) AS total_clicks,
            COALESCE(SUM(g.impressions), 0) AS total_impressions,
            AVG(g.avg_position) AS avg_position
        FROM gsc_metrics g
        JOIN posts p ON p.id = g.post_id
        WHERE p.site_id = $1
        """,
        site_id,
    )

    return AnalyticsOverview(
        total_posts=total_posts or 0,
        total_pageviews=ga4_agg["total_pageviews"] if ga4_agg else 0,
        total_sessions=ga4_agg["total_sessions"] if ga4_agg else 0,
        total_clicks=gsc_agg["total_clicks"] if gsc_agg else 0,
        total_impressions=gsc_agg["total_impressions"] if gsc_agg else 0,
        avg_position=gsc_agg["avg_position"] if gsc_agg else None,
        date_range_start=ga4_agg["date_start"] if ga4_agg else None,
        date_range_end=ga4_agg["date_end"] if ga4_agg else None,
    )
