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
    site_id: UUID | None = None


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
    data_completeness: float | None = None  # 0.0-1.0, fraction of signals available


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
    data_completeness: float = 1.0  # 0.0-1.0, fraction of signals available


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


# ──────────────────────────── Phase 4: Action Layer ────────────────────────────

class ClusterNarrativeResponse(BaseModel):
    """Ecosystem voice narrative for a cluster."""
    cluster_id: UUID
    narrative_text: str
    generated_at: datetime


class CalendarRecommendation(BaseModel):
    """Publishing cadence recommendation for a cluster."""
    cluster_id: UUID
    cluster_label: str | None
    ecosystem_state: str | None
    recommendation_type: str  # pause, maintain, revive, grow
    recommendation_text: str
    suggested_keywords: list[str] | None
    pause_months: int | None


class CalendarResponse(BaseModel):
    """Site-wide content calendar response."""
    site_id: UUID
    recommendations: list[CalendarRecommendation]
    summary: str


class RedirectPushRequest(BaseModel):
    """Request body for pushing redirects to WordPress."""
    redirect_map: list[RedirectEntry]


class RedirectStatusEntry(BaseModel):
    """Status of a single redirect push."""
    old_url: str
    new_url: str
    status: str
    pushed_at: datetime | None
    verified_at: datetime | None
    error: str | None


class RedirectStatusResponse(BaseModel):
    """Response for redirect push status."""
    site_id: UUID
    entries: list[RedirectStatusEntry]
    total: int
    pushed: int
    verified: int
    failed: int


# ──────────────────────────── Phase 5: Retention + Growth ────────────────────────────

class ReportHistoryEntry(BaseModel):
    """Weekly report send history."""
    id: UUID
    site_id: UUID
    subject: str
    status: str
    sent_at: datetime


class ImpactTrackingResponse(BaseModel):
    """Impact tracking for a consolidation."""
    id: UUID
    site_id: UUID
    cluster_id: UUID | None
    pillar_url: str
    consolidated_urls: list[str]
    baseline_traffic: int
    baseline_avg_position: float | None
    baseline_date: str
    latest_traffic: int | None
    latest_avg_position: float | None
    latest_check_date: str | None
    traffic_change_pct: float | None
    status: str
    days_since: int


class ImpactSnapshotResponse(BaseModel):
    """Impact snapshot at a milestone checkpoint."""
    snapshot_date: str
    traffic: int
    avg_position: float | None
    redirects_working: int
    milestone: str | None


class ImpactDetailResponse(BaseModel):
    """Detailed impact tracking with snapshots."""
    tracking: ImpactTrackingResponse
    snapshots: list[ImpactSnapshotResponse]


class ImpactCardResponse(BaseModel):
    """Shareable impact card."""
    tracking_id: UUID
    headline: str
    pillar_url: str
    days_since: int
    traffic_change: int
    traffic_change_pct: float
    posts_consolidated: int
    redirects_working: int
    summary: str


class StartTrackingRequest(BaseModel):
    """Request to start impact tracking."""
    cluster_id: UUID | None = None
    pillar_url: str
    consolidated_urls: list[str]


class StewardProfile(BaseModel):
    """Content steward profile stats."""
    user_id: str
    member_since: str
    swamps_cleared: int
    deserts_revived: int
    seedlings_planted: int
    total_posts_consolidated: int
    total_redirects_created: int
    estimated_traffic_recovered: int
    efficiency_improvement: float
    health_improvement: float


class CheckoutRequest(BaseModel):
    """Stripe checkout request."""
    price_id: str
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    """Stripe checkout session URL."""
    checkout_url: str


class SubscriptionResponse(BaseModel):
    """Current subscription details."""
    tier: str
    status: str
    stripe_subscription_id: str | None
    current_period_end: str | None


class PortalResponse(BaseModel):
    """Stripe customer portal URL."""
    portal_url: str


# ──────────────────────────── Phase 6: Living Ecosystem ────────────────────────────

# ──────────────────────────── Phase 2: Problem Detection ────────────────────────────

class ContentProblemResponse(BaseModel):
    """A detected content problem."""
    id: UUID
    post_id: UUID
    problem_type: str
    severity: str
    details: dict | None = None
    detected_at: datetime
    resolved_at: datetime | None = None


class ContentProblemSummary(BaseModel):
    """Summary of problems for a post."""
    post_id: UUID
    title: str
    url: str
    problems: list[ContentProblemResponse]


class ProblemDetectionResponse(BaseModel):
    """Result of running problem detection."""
    decay: int
    thin: int
    seo: int
    orphan: int
    total: int


class RecommendationResponse(BaseModel):
    """An AI-generated recommendation."""
    id: UUID
    post_id: UUID
    problem_id: UUID | None = None
    recommendation_type: str
    priority: str
    estimated_effort_hours: float | None = None
    estimated_impact: str | None = None
    title: str
    summary: str
    specific_actions: list[str] = []
    ai_generated_content: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class RecommendationListResponse(BaseModel):
    """List of recommendations with counts."""
    recommendations: list[RecommendationResponse]
    total: int
    by_type: dict[str, int]
    by_priority: dict[str, int]


class RecommendationStatusUpdate(BaseModel):
    """Update recommendation status."""
    status: str = Field(..., pattern=r"^(pending|in_progress|completed|dismissed)$")


class CannibalizationRecommendationRequest(BaseModel):
    """Request to generate a detailed cannibalization recommendation."""
    pair_id: UUID


class RiverData(BaseModel):
    """Internal link flow between two clusters."""
    from_cluster_id: str
    to_cluster_id: str
    forward_links: int
    backward_links: int
    total_links: int
    bidirectional_ratio: float
    width: float
    quality: str  # sparkling, clear, murky, toxic


class GrassData(BaseModel):
    """Content freshness ground cover for a cluster."""
    state: str  # fresh, maintained, overgrown, dead
    avg_days_old: int
    oldest_post_days: int | None = None
    newest_post_days: int | None = None


class WeatherData(BaseModel):
    """Traffic trend weather for a cluster."""
    state: str  # sunny, cloudy, rain, storm, fog
    recent_traffic: int
    previous_traffic: int
    change_percent: float | None = None


class AnimalData(BaseModel):
    """User behavior animal for a cluster."""
    type: str  # birds, foxes, deer, bees, vultures
    count: int
    meaning: str


class TerrainFeature(BaseModel):
    """Structural issue terrain feature for a cluster."""
    type: str  # boulders, erosion, mushrooms
    count: int
    meaning: str


class EcosystemVisualsResponse(BaseModel):
    """Full ecosystem visual metadata payload."""
    rivers: list[RiverData]
    grass: dict[str, GrassData]
    weather: dict[str, WeatherData]
    animals: dict[str, list[AnimalData]]
    water_quality_note: str | None = None
    terrain_features: dict[str, list[TerrainFeature]]
