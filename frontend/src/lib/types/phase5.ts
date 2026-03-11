/** Phase 5: Retention + Growth — Types matching backend Pydantic models exactly. */

export interface ReportHistoryEntry {
  id: string;
  site_id: string;
  subject: string;
  status: string;
  sent_at: string;
}

export interface ImpactTrackingResponse {
  id: string;
  site_id: string;
  cluster_id: string | null;
  pillar_url: string;
  consolidated_urls: string[];
  baseline_traffic: number;
  baseline_avg_position: number | null;
  baseline_date: string;
  latest_traffic: number | null;
  latest_avg_position: number | null;
  latest_check_date: string | null;
  traffic_change_pct: number | null;
  status: string;
  days_since: number;
}

export interface ImpactSnapshotResponse {
  snapshot_date: string;
  traffic: number;
  avg_position: number | null;
  redirects_working: number;
  milestone: string | null;
}

export interface ImpactDetailResponse {
  tracking: ImpactTrackingResponse;
  snapshots: ImpactSnapshotResponse[];
}

export interface ImpactCardResponse {
  tracking_id: string;
  headline: string;
  pillar_url: string;
  days_since: number;
  traffic_change: number;
  traffic_change_pct: number;
  posts_consolidated: number;
  redirects_working: number;
  summary: string;
}

export interface StartTrackingRequest {
  cluster_id: string | null;
  pillar_url: string;
  consolidated_urls: string[];
}

export interface StewardProfile {
  user_id: string;
  member_since: string;
  swamps_cleared: number;
  deserts_revived: number;
  seedlings_planted: number;
  total_posts_consolidated: number;
  total_redirects_created: number;
  estimated_traffic_recovered: number;
  efficiency_improvement: number;
  health_improvement: number;
}

export interface CheckoutRequest {
  price_id: string;
  success_url: string;
  cancel_url: string;
}

export interface CheckoutResponse {
  checkout_url: string;
}

export interface SubscriptionResponse {
  tier: string;
  status: string;
  stripe_subscription_id: string | null;
  current_period_end: string | null;
}

export interface PortalResponse {
  portal_url: string;
}
