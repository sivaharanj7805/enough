"""Pydantic models for request/response schemas."""

from datetime import datetime, date
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


# ──────────────────────────── Auth ────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


# ──────────────────────────── Sites ────────────────────────────

class SiteCreate(BaseModel):
    name: str
    domain: str
    cms_type: str = Field(..., pattern=r"^(wordpress|sitemap|hubspot|webflow|ghost|other)$")
    wordpress_url: str | None = None
    wordpress_app_password: str | None = None
    sitemap_url: str | None = None
    ga4_property_id: str | None = None
    gsc_site_url: str | None = None


class SiteResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    domain: str
    cms_type: str | None
    wordpress_url: str | None
    sitemap_url: str | None
    ga4_property_id: str | None
    gsc_site_url: str | None
    last_crawl_at: datetime | None
    last_analytics_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SiteListResponse(BaseModel):
    sites: list[SiteResponse]
    total: int


# ──────────────────────────── Posts ────────────────────────────

class InternalLinkSchema(BaseModel):
    target_url: str
    anchor_text: str | None = None


class PostResponse(BaseModel):
    id: UUID
    site_id: UUID
    url: str
    slug: str | None
    title: str
    body_text: str | None
    publish_date: datetime | None
    modified_date: datetime | None
    cms_categories: list[str] | None
    cms_tags: list[str] | None
    word_count: int | None
    content_hash: str | None
    created_at: datetime
    updated_at: datetime


class PostDetailResponse(PostResponse):
    """Post with full metrics."""
    ga4_metrics: list["GA4MetricResponse"] = []
    gsc_metrics: list["GSCMetricResponse"] = []
    internal_links: list[InternalLinkSchema] = []


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    total: int


# ──────────────────────────── Analytics ────────────────────────────

class GA4MetricResponse(BaseModel):
    date: date
    pageviews: int
    sessions: int
    engaged_sessions: int
    avg_engagement_time_seconds: float
    bounce_rate: float
    conversions: int


class GSCMetricResponse(BaseModel):
    date: date
    query: str
    impressions: int
    clicks: int
    avg_position: float | None
    ctr: float


class AnalyticsOverview(BaseModel):
    total_posts: int
    total_pageviews: int
    total_sessions: int
    total_clicks: int
    total_impressions: int
    avg_position: float | None
    date_range_start: date | None
    date_range_end: date | None


# ──────────────────────────── Ingestion ────────────────────────────

class CrawlStatusResponse(BaseModel):
    site_id: UUID
    status: str  # idle, crawling, completed, failed
    posts_found: int = 0
    posts_processed: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class TaskTriggerResponse(BaseModel):
    message: str
    site_id: UUID


# Rebuild forward refs
PostDetailResponse.model_rebuild()
