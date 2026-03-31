"""Analytics and post data endpoints."""

import json
import logging
import re
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.schemas import (
    AnalyticsOverview,
    GA4MetricResponse,
    GSCMetricResponse,
    InternalLinkSchema,
    PostDetailResponse,
    PostListResponse,
    PostResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_display_score(value: float | None, *, is_ratio: bool = False) -> float | None:
    """Convert a raw factor score to a 0-100 display value.

    Some scores (like internal_link_score) are stored as 0.0-1.0 ratios;
    others (like freshness_score, content_depth_score) are already 0-100.
    """
    if value is None:
        return None
    if is_ratio:
        return round(min(100.0, max(0.0, value * 100)), 1)
    return round(min(100.0, max(0.0, value)), 1)


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


@router.get("/{site_id}/posts/health", response_model=list)
async def list_post_health(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Bulk endpoint: all post health scores, roles, clusters for a site.

    Returns a flat list for O(1) client-side lookup by post_id.
    Used by the Posts list page to populate Health, Role, Cluster columns.
    """
    await _verify_site_ownership(site_id, user_id, db)

    rows = await db.fetch(
        """
        SELECT DISTINCT ON (p.id)
               p.id AS post_id,
               p.title,
               p.url,
               p.word_count,
               p.publish_date,
               phs.composite_score,
               phs.role,
               phs.trend,
               phs.score_confidence,
               phs.ai_citability_score,
               c.id AS cluster_id,
               c.label AS cluster_label
        FROM posts p
        INNER JOIN post_health_scores phs ON phs.post_id = p.id
        LEFT JOIN post_clusters pc ON pc.post_id = p.id
        LEFT JOIN clusters c ON c.id = pc.cluster_id
        WHERE p.site_id = $1
          AND phs.composite_score IS NOT NULL
        ORDER BY p.id
        """,
        site_id,
    )
    return [
        {
            "post_id": str(r["post_id"]),
            "title": r["title"],
            "url": r["url"],
            "word_count": r["word_count"],
            "publish_date": r["publish_date"].isoformat() if r["publish_date"] else None,
            "composite_score": r["composite_score"],
            "role": r["role"],
            "trend": r["trend"],
            "score_confidence": r["score_confidence"],
            "ai_citability_score": r["ai_citability_score"],
            "cluster_id": str(r["cluster_id"]) if r["cluster_id"] else None,
            "cluster_label": r["cluster_label"],
        }
        for r in rows
    ]


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

    # ── Extract content structure counts from headings jsonb + body_html ──
    headings_raw = post_data.get("headings")
    if isinstance(headings_raw, str):
        try:
            headings_raw = json.loads(headings_raw)
        except (json.JSONDecodeError, TypeError):
            headings_raw = None

    h1_count = 0
    h2_count = 0
    h3_count = 0
    if isinstance(headings_raw, list):
        for h in headings_raw:
            tag = (h.get("tag") or h.get("level") or "").lower() if isinstance(h, dict) else ""
            if tag in ("h1", "1"):
                h1_count += 1
            elif tag in ("h2", "2"):
                h2_count += 1
            elif tag in ("h3", "3"):
                h3_count += 1
    headings_count = h1_count + h2_count + h3_count

    # Count images from body_html
    body_html = post_data.get("body_html") or ""
    image_count = len(re.findall(r"<img[\s>]", body_html, re.IGNORECASE))

    # Extract meta_description and meta_title from posts table columns
    meta_description = post_data.get("meta_description")
    # meta_title: use title column as fallback (posts table has no separate meta_title column)
    meta_title = post_data.get("title", "")

    # Fetch health scores + AI signals for this post (pipeline-computed data)
    health_row = await db.fetchrow(
        """SELECT internal_pagerank, ai_citability_score, eeat_score,
                  schema_score, extraction_score, ai_signals,
                  composite_score, role, trend, score_confidence,
                  traffic_contribution, ranking_strength,
                  internal_link_score, engagement_score,
                  freshness_score, content_depth_score,
                  technical_seo_score
           FROM post_health_scores WHERE post_id = $1""",
        post_id,
    )
    ai_signals = None
    composite_score = None
    role = None
    ai_citability_score = None
    factor_scores = None
    if health_row:
        post_data["pagerank_score"] = health_row["internal_pagerank"]
        sig = health_row["ai_signals"]
        if isinstance(sig, str):
            sig = json.loads(sig)
        ai_signals = sig
        composite_score = health_row["composite_score"]
        role = health_row["role"]
        ai_citability_score = health_row["ai_citability_score"]

        # Compute AI readiness score from 4 AI dimensions (same as health_scoring.py)
        ai_dims = [v for v in [
            health_row["ai_citability_score"],
            health_row["eeat_score"],
            health_row["schema_score"],
            health_row["extraction_score"],
        ] if v is not None]
        ai_readiness = sum(ai_dims) / len(ai_dims) if ai_dims else None

        # Compute content_richness (engagement_score is the predicted_engagement proxy)
        engagement = health_row["engagement_score"]
        content_depth = health_row["content_depth_score"]
        content_richness = engagement  # engagement_score already captures richness signals

        # Build factor_scores dict with keys matching what the frontend expects
        factor_scores = {
            "ai_readiness": _to_display_score(ai_readiness),
            "content_depth": _to_display_score(content_depth),
            "content_richness": _to_display_score(content_richness),
            "freshness": _to_display_score(health_row["freshness_score"]),
            "internal_links": _to_display_score(health_row["internal_link_score"], is_ratio=True),
            "technical_seo": _to_display_score(health_row["technical_seo_score"]),
            # Keep raw values too for debugging / advanced views
            "traffic_contribution": health_row["traffic_contribution"],
            "ranking_strength": health_row["ranking_strength"],
        }

    # Fetch cluster info via post_clusters + clusters
    cluster_row = await db.fetchrow(
        """SELECT c.id AS cluster_id, c.label AS cluster_name
           FROM post_clusters pc
           JOIN clusters c ON c.id = pc.cluster_id
           WHERE pc.post_id = $1""",
        post_id,
    )
    cluster_id = str(cluster_row["cluster_id"]) if cluster_row else None
    cluster_name = cluster_row["cluster_name"] if cluster_row else None

    # Remove body_html from response (too large, not needed by frontend)
    post_data.pop("body_html", None)
    # Remove headings raw jsonb from post_data (we send structured counts instead)
    raw_headings = post_data.pop("headings", None)
    # Remove meta_description from post_data to avoid duplicate kwarg
    post_data.pop("meta_description", None)

    return PostDetailResponse(
        **post_data,
        composite_score=composite_score,
        role=role,
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        factor_scores=factor_scores,
        ai_citability_score=ai_citability_score,
        ga4_metrics=ga4_metrics,
        gsc_metrics=gsc_metrics,
        internal_links=internal_links,
        ai_signals=ai_signals,
        meta_description=meta_description,
        meta_title=meta_title,
        headings=raw_headings if isinstance(raw_headings, list) else None,
        headings_count=headings_count,
        h1_count=h1_count,
        h2_count=h2_count,
        h3_count=h3_count,
        image_count=image_count,
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
