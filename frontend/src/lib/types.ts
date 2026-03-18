/**
 * TypeScript types matching backend Pydantic schemas exactly.
 * Any field name here MUST match the JSON key the backend API returns.
 */

import type { EcosystemState, PostRole, Severity, Trend } from './constants';

// ─── Site ────────────────────────────────────────
export interface Site {
  id: string;
  name: string;
  domain: string;
  cms_type: 'wordpress' | 'sitemap' | 'hubspot' | 'webflow' | 'ghost' | 'other';
  sitemap_url: string | null;
  ga4_property_id: string | null;
  gsc_site_url: string | null;
  last_crawl_at: string | null;
  last_analytics_sync_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SiteListResponse {
  sites: Site[];
  total: number;
}

// ─── Posts ────────────────────────────────────────
export interface Post {
  id: string;
  site_id: string;
  url: string;
  slug: string | null;
  title: string;
  body_text: string | null;
  publish_date: string | null;
  modified_date: string | null;
  content_hash: string | null;
  cms_categories: string[];
  cms_tags: string[];
  word_count: number | null;
  created_at: string;
  updated_at: string;
}

/** Matches backend PostHealthResponse exactly */
export interface PostHealth {
  id?: string;
  post_id: string;
  title: string;
  url: string;
  composite_score: number | null;
  role: PostRole | null;
  trend: Trend | null;
  traffic_contribution: number | null;
  ranking_strength: number | null;
  internal_link_score: number | null;
}

// ─── Analytics ───────────────────────────────────
export interface GA4Metric {
  id: string;
  post_id: string;
  date: string;
  pageviews: number;
  sessions: number;
  engaged_sessions: number;
  avg_engagement_time_seconds: number;
  bounce_rate: number;
  conversions: number;
}

export interface GSCMetric {
  id: string;
  post_id: string;
  date: string;
  query: string;
  impressions: number;
  clicks: number;
  avg_position: number | null;
  ctr: number;
}

export interface InternalLink {
  target_url: string;
  anchor_text: string | null;
}

export interface PostDetail extends Post {
  ga4_metrics: GA4Metric[];
  gsc_metrics: GSCMetric[];
  internal_links: InternalLink[];
}

export interface PostListResponse {
  posts: Post[];
  total: number;
}

export interface AnalyticsOverview {
  total_posts: number;
  total_pageviews: number;
  total_sessions: number;
  total_clicks: number;
  total_impressions: number;
  avg_position: number | null;
  date_range_start: string | null;
  date_range_end: string | null;
}

// ─── Clusters ────────────────────────────────────
/** Matches backend ClusterSummary */
export interface ClusterSummary {
  id: string;
  label: string | null;
  ecosystem_state: EcosystemState | null;
  post_count: number;
}

/** Matches backend ClusterResponse */
export interface Cluster {
  id: string;
  site_id: string;
  label: string | null;
  description: string | null;
  ecosystem_state: EcosystemState | null;
  health_score: number | null;
  post_count: number;
  created_at: string;
  updated_at: string;
}

/** Matches backend ClusterDetailResponse */
export interface ClusterDetail extends Cluster {
  posts: PostHealth[];
}

// ─── Cannibalization ─────────────────────────────
/** Matches backend CannibalizationPairResponse */
export interface CannibalizationPair {
  id: string;
  cluster_id: string;
  post_a: PostHealth;
  post_b: PostHealth;
  overlap_score: number;
  severity: Severity;
  overlapping_queries: string[] | null;
}

// ─── Site Health ─────────────────────────────────
/** Matches backend SiteHealthResponse */
export interface SiteHealth {
  content_health_score: number;
  total_posts: number;
  active_posts: number;
  passive_posts: number;
  cannibalistic_posts: number;
  dead_posts: number;
  content_efficiency_ratio: number;
  clusters: ClusterSummary[];
  trends: Record<string, number>; // { "30d": number, "60d": number, "90d": number }
  data_completeness: number
  modified_date_coverage: number
  ai_enriched_count: number; // 0.0-1.0 fraction of available data signals
}

// ─── Consolidation ──────────────────────────────
/** Matches backend PillarPostInfo */
export interface PillarPostInfo {
  post_id: string;
  title: string;
  url: string;
  composite_score: number;
}

/** Matches backend MergeCandidateInfo */
export interface MergeCandidateInfo {
  post_id: string;
  title: string;
  url: string;
  composite_score: number;
  word_count: number;
}

/** Matches backend RedirectEntry */
export interface RedirectEntry {
  old_url: string;
  new_url: string;
}

/** Matches backend ConsolidationPlanResponse */
export interface ConsolidationPlan {
  cluster_id: string;
  cluster_label: string | null;
  priority_score: number;
  pillar_post: PillarPostInfo;
  merge_candidates_count: number;
  dead_weight_count: number;
  estimated_traffic_recovery: number;
  estimated_effort: number;
  is_quick_win: boolean;
}

/** Matches backend ConsolidationDetailResponse */
export interface ConsolidationDetail extends ConsolidationPlan {
  merge_candidates: MergeCandidateInfo[];
  dead_weight: MergeCandidateInfo[];
  redirect_map: RedirectEntry[];
}

/** Matches backend ConsolidationDraftResponse */
export interface ConsolidationDraft {
  draft_markdown: string;
  redirect_map: RedirectEntry[];
}

// ─── Oracle ──────────────────────────────────────
/** Matches backend OracleRequest */
export interface OracleRequest {
  draft_text: string | null;
  target_keyword: string | null;
}

/** Matches backend SimilarPostInfo */
export interface SimilarPost {
  post_id: string;
  title: string;
  url: string;
  similarity_score: number | null;
  distance: number | null;
  avg_position: number | null;
  total_clicks: number | null;
  word_count: number | null;
  source: string;
}

/** Matches backend OracleVerdictResponse */
export interface OracleVerdict {
  confidence: 'high' | 'medium' | 'low';
  verdict: 'publish' | 'update_existing' | 'skip';
  reasoning: string;
  similar_posts: SimilarPost[];
  cluster_state: EcosystemState | null;
  recommendation: string;
}

// ─── Pipeline ────────────────────────────────────
/** Matches backend PipelineStatusResponse */
export interface PipelineStatus {
  site_id: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  current_step: 'clustering' | 'cannibalization' | 'health_scoring' | null;
  steps_completed: string[];
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

// ─── Crawl ───────────────────────────────────────
/** Matches backend CrawlStatusResponse */
export interface CrawlStatus {
  site_id: string;
  status: 'idle' | 'crawling' | 'completed' | 'failed';
  posts_found: number;
  posts_processed: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

/** Matches backend TaskTriggerResponse */
export interface TaskTriggerResponse {
  message: string;
  site_id: string;
}

// ─── Phase 4: Action Layer ───────────────────────

/** Matches backend ClusterNarrativeResponse */
export interface ClusterNarrative {
  cluster_id: string;
  narrative_text: string;
  generated_at: string;
}

/** Matches backend CalendarRecommendation */
export interface CalendarRecommendation {
  cluster_id: string;
  cluster_label: string | null;
  ecosystem_state: string | null;
  recommendation_type: string;
  recommendation_text: string;
  suggested_keywords: string[] | null;
  pause_months: number | null;
}

/** Matches backend CalendarResponse */
export interface CalendarResponse {
  site_id: string;
  recommendations: CalendarRecommendation[];
  summary: string;
}

/** Matches backend RedirectPushRequest */
export interface RedirectPushRequest {
  redirect_map: RedirectEntry[];
}

/** Matches backend RedirectStatusEntry */
export interface RedirectStatusEntry {
  old_url: string;
  new_url: string;
  status: string;
  pushed_at: string | null;
  verified_at: string | null;
  error: string | null;
}

/** Matches backend RedirectStatusResponse */
export interface RedirectStatusResponse {
  site_id: string;
  entries: RedirectStatusEntry[];
  total: number;
  pushed: number;
  verified: number;
  failed: number;
}

// ─── Problems ────────────────────────────────────
export interface ContentProblem {
  id: string;
  post_id: string;
  problem_type: string;
  severity: string;
  details: Record<string, unknown> | null;
  detected_at: string;
  resolved_at: string | null;
}

export interface ContentProblemSummary {
  post_id: string;
  title: string;
  url: string;
  problems: ContentProblem[];
}

// ─── Recommendations ─────────────────────────────
export interface Recommendation {
  id: string;
  post_id: string;
  problem_id: string | null;
  recommendation_type: string;
  priority: string;
  estimated_effort_hours: number | null;
  estimated_impact: string | null;
  title: string;
  summary: string;
  specific_actions: string[];
  ai_generated_content: Record<string, unknown> | null;
  status: string;
  confidence?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecommendationListResponse {
  recommendations: Recommendation[];
  total: number;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
}

// ─── Auth ────────────────────────────────────────
export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
}
