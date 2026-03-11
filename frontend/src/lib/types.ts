import type { EcosystemState, PostRole, Severity, Trend } from './constants';

// ─── Site ────────────────────────────────────────
export interface Site {
  id: string;
  name: string;
  domain: string;
  cms_type: 'wordpress' | 'other';
  sitemap_url: string | null;
  ga4_property_id: string | null;
  gsc_site_url: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Posts ────────────────────────────────────────
export interface Post {
  id: string;
  site_id: string;
  title: string;
  url: string;
  slug: string;
  word_count: number;
  published_at: string | null;
  updated_at: string | null;
  status: string;
  content_hash: string | null;
}

export interface PostHealth {
  post_id: string;
  title: string;
  url: string;
  role: PostRole;
  health_score: number;
  traffic_90d: number;
  trend: Trend;
  cluster_id: string | null;
  keyword_count: number;
}

export interface PostDetail extends Post {
  health: PostHealth | null;
  ga4_metrics: GA4Metric[];
  gsc_metrics: GSCMetric[];
}

// ─── Analytics ───────────────────────────────────
export interface GA4Metric {
  date: string;
  pageviews: number;
  sessions: number;
  avg_engagement_time: number;
  bounce_rate: number;
}

export interface GSCMetric {
  date: string;
  query: string;
  impressions: number;
  clicks: number;
  position: number;
  ctr: number;
}

// ─── Clusters ────────────────────────────────────
export interface Cluster {
  id: string;
  site_id: string;
  label: string;
  post_count: number;
  ecosystem_state: EcosystemState;
  health_score: number;
  primary_keyword: string | null;
}

export interface ClusterDetail extends Cluster {
  posts: PostHealth[];
}

// ─── Cannibalization ─────────────────────────────
export interface CannibalizationPair {
  id: string;
  post_a_id: string;
  post_b_id: string;
  post_a_title: string;
  post_b_title: string;
  post_a_url: string;
  post_b_url: string;
  overlap_score: number;
  severity: Severity;
  overlapping_queries: string[];
  recommendation: string;
  cluster_id: string | null;
}

// ─── Site Health ─────────────────────────────────
export interface SiteHealth {
  health_score: number;
  health_trend: Trend;
  efficiency_ratio: number;
  efficiency_trend: Trend;
  total_posts: number;
  active_posts: number;
  passive_posts: number;
  cannibal_posts: number;
  dead_posts: number;
  traffic_series: TrafficDataPoint[];
  clusters: Cluster[];
}

export interface TrafficDataPoint {
  date: string;
  pageviews: number;
}

// ─── Consolidation ──────────────────────────────
export interface ConsolidationPlan {
  id: string;
  cluster_id: string;
  cluster_label: string;
  priority_score: number;
  pillar_post_title: string;
  pillar_post_url: string;
  merge_count: number;
  redirect_count: number;
  estimated_traffic_recovery: number;
  is_quick_win: boolean;
}

export interface ConsolidationDetail extends ConsolidationPlan {
  pillar_post: PostHealth;
  merge_candidates: MergeCandidate[];
  dead_weight: PostHealth[];
  redirect_map: RedirectEntry[];
  estimated_effort_hours: number;
}

export interface MergeCandidate {
  post_id: string;
  title: string;
  url: string;
  similarity_score: number;
  word_count: number;
  health_score: number;
}

export interface RedirectEntry {
  old_url: string;
  new_url: string;
  post_title: string;
  reason: string;
}

export interface ConsolidationDraft {
  cluster_id: string;
  title: string;
  content_markdown: string;
  word_count: number;
  generated_at: string;
}

// ─── Oracle ──────────────────────────────────────
export interface OracleRequest {
  content: string;
  target_keyword: string | null;
}

export type OracleConfidence = 'publish' | 'update' | 'skip';

export interface OracleVerdict {
  confidence: OracleConfidence;
  confidence_score: number;
  reasoning: string;
  recommendation: string;
  similar_posts: SimilarPost[];
  existing_post_to_update: string | null;
  cluster_id: string | null;
}

export interface SimilarPost {
  post_id: string;
  title: string;
  url: string;
  similarity_score: number;
  ranking_position: number | null;
  traffic_90d: number;
}

// ─── Pipeline ────────────────────────────────────
export interface PipelineStatus {
  stage: string;
  progress: number;
  message: string;
  completed: boolean;
  error: string | null;
}

// ─── Auth ────────────────────────────────────────
export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
}
