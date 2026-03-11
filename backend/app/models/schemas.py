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


# ──────────────────────────── Phase 2: Intelligence ────────────────────────────

class ClusterSummary(BaseModel):
    """Lightweight cluster info for dashboard listings."""
    id: UUID
    label: str | None
    ecosystem_state: str | None
    post_count: int


class PostHealthResponse(BaseModel):
    """Post with health metrics and role assignment."""
    post_id: UUID
    title: str
    url: str
    composite_score: float | None
    role: str | None
    trend: str | None
    traffic_contribution: float | None
    ranking_strength: float | None
    internal_link_score: float | None


class ClusterResponse(BaseModel):
    """Cluster with ecosystem state and health score."""
    id: UUID
    site_id: UUID
    label: str | None
    ecosystem_state: str | None
    health_score: float | None
    post_count: int
    created_at: datetime
    updated_at: datetime


class ClusterDetailResponse(ClusterResponse):
    """Cluster with full post list and health details."""
    posts: list[PostHealthResponse] = []


class CannibalizationPairResponse(BaseModel):
    """A pair of posts cannibalizing each other."""
    id: UUID
    cluster_id: UUID
    post_a: PostHealthResponse
    post_b: PostHealthResponse
    overlap_score: float
    severity: str
    overlapping_queries: list[str] | None


class SiteHealthResponse(BaseModel):
    """Site-wide health dashboard."""
    content_health_score: float
    total_posts: int
    active_posts: int
    passive_posts: int
    cannibalistic_posts: int
    dead_posts: int
    content_efficiency_ratio: float
    clusters: list[ClusterSummary]
    trends: dict[str, float]


class PillarPostInfo(BaseModel):
    """Pillar post summary for consolidation plans."""
    post_id: str
    title: str
    url: str
    composite_score: float


class MergeCandidateInfo(BaseModel):
    """Merge candidate details."""
    post_id: str
    title: str
    url: str
    composite_score: float
    word_count: int


class RedirectEntry(BaseModel):
    """A single redirect mapping."""
    old_url: str
    new_url: str


class ConsolidationPlanResponse(BaseModel):
    """Ranked consolidation opportunity for a swamp cluster."""
    cluster_id: str
    cluster_label: str | None
    priority_score: float
    pillar_post: PillarPostInfo
    merge_candidates_count: int
    dead_weight_count: int
    estimated_traffic_recovery: int
    estimated_effort: float
    is_quick_win: bool


class ConsolidationDetailResponse(ConsolidationPlanResponse):
    """Detailed consolidation plan with full post lists."""
    merge_candidates: list[MergeCandidateInfo] = []
    dead_weight: list[MergeCandidateInfo] = []
    redirect_map: list[RedirectEntry] = []


class ConsolidationDraftResponse(BaseModel):
    """AI-generated consolidated draft."""
    draft_markdown: str
    redirect_map: list[RedirectEntry]


class SimilarPostInfo(BaseModel):
    """Similar post info from the Oracle."""
    post_id: str
    title: str
    url: str
    similarity_score: float | None = None
    distance: float | None = None
    avg_position: float | None = None
    total_clicks: int | None = None
    word_count: int | None = None
    source: str


class OracleRequest(BaseModel):
    """Pre-publish oracle request body."""
    draft_text: str | None = None
    target_keyword: str | None = None


class OracleVerdictResponse(BaseModel):
    """Pre-publish oracle verdict."""
    confidence: str
    verdict: str
    reasoning: str
    similar_posts: list[SimilarPostInfo]
    cluster_state: str | None
    recommendation: str


class PipelineStatusResponse(BaseModel):
    """Intelligence pipeline job status."""
    site_id: UUID
    status: str  # idle, running, completed, failed
    current_step: str | None = None
    steps_completed: list[str] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
