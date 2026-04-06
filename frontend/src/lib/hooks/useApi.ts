'use client';

import { useSWRFetch } from './useSWRFetch';
import type {
  SiteListResponse,
  SiteHealth,
  Cluster,
  ClusterDetail,
  CannibalizationPair,
  ConsolidationPlan,
  ConsolidationDetail,
  ClusterNarrative,
  CalendarResponse,
  RedirectStatusResponse,
  PostListResponse,
  PostDetail,
  ContentProblem,
  ContentProblemSummary,
  Recommendation,
  RecommendationListResponse,
  AlertsListResponse,
  SinceLastVisitResponse,
  ROISummary,
  TopContentGap,
  AIScores,
  Subscription,
} from '@/lib/types';
import type { EcosystemVisualsResponse } from '@/lib/types/phase6';

export function useSites() {
  return useSWRFetch<SiteListResponse>('/sites');
}

export function useSiteHealth(siteId: string | null) {
  return useSWRFetch<SiteHealth>(siteId ? `/sites/${siteId}/intelligence/health` : null);
}

export function useClusters(siteId: string | null) {
  return useSWRFetch<Cluster[]>(siteId ? `/sites/${siteId}/intelligence/clusters` : null);
}

export function useClusterDetail(siteId: string | null, clusterId: string | null) {
  return useSWRFetch<ClusterDetail>(
    siteId && clusterId ? `/sites/${siteId}/intelligence/clusters/${clusterId}` : null
  );
}

export function useCannibalizationPairs(siteId: string | null) {
  return useSWRFetch<CannibalizationPair[]>(
    siteId ? `/sites/${siteId}/intelligence/cannibalization` : null
  );
}

export function useConsolidationPlans(siteId: string | null) {
  return useSWRFetch<ConsolidationPlan[]>(
    siteId ? `/sites/${siteId}/intelligence/consolidation` : null
  );
}

export function useConsolidationDetail(siteId: string | null, clusterId: string | null) {
  return useSWRFetch<ConsolidationDetail>(
    siteId && clusterId ? `/sites/${siteId}/intelligence/consolidation/${clusterId}` : null
  );
}

// ─── Phase 4: Action Layer ───────────────────────

export function useClusterNarrative(siteId: string | null, clusterId: string | null) {
  return useSWRFetch<ClusterNarrative>(
    siteId && clusterId
      ? `/sites/${siteId}/intelligence/clusters/${clusterId}/narrative`
      : null
  );
}

export function useCalendar(siteId: string | null) {
  return useSWRFetch<CalendarResponse>(
    siteId ? `/sites/${siteId}/intelligence/calendar` : null
  );
}

export function useRedirectStatus(siteId: string | null) {
  return useSWRFetch<RedirectStatusResponse>(
    siteId ? `/sites/${siteId}/redirects/status` : null
  );
}

// ─── Posts ───────────────────────────────────────

export function usePosts(siteId: string | null, limit = 50, offset = 0) {
  return useSWRFetch<PostListResponse>(
    siteId ? `/sites/${siteId}/posts?limit=${limit}&offset=${offset}` : null
  );
}

export function usePostDetail(siteId: string | null, postId: string | null) {
  return useSWRFetch<PostDetail>(
    siteId && postId ? `/sites/${siteId}/posts/${postId}` : null
  );
}

/** Bulk post health scores, roles, and cluster assignments for the Posts list page. */
export interface PostHealthBulk {
  post_id: string;
  title: string | null;
  url: string | null;
  word_count: number | null;
  publish_date: string | null;
  composite_score: number | null;
  role: string | null;
  trend: string | null;
  score_confidence: string | null;
  ai_citability_score: number | null;
  cluster_id: string | null;
  cluster_label: string | null;
}

export function usePostsHealth(siteId: string | null) {
  return useSWRFetch<PostHealthBulk[]>(
    siteId ? `/sites/${siteId}/posts/health` : null
  );
}

// ─── Problems ────────────────────────────────────

export function useProblems(siteId: string | null, problemType?: string, severity?: string) {
  const params = new URLSearchParams();
  if (problemType) params.set('problem_type', problemType);
  if (severity) params.set('severity', severity);
  const qs = params.toString();
  return useSWRFetch<ContentProblem[]>(
    siteId ? `/sites/${siteId}/intelligence/problems${qs ? `?${qs}` : ''}` : null
  );
}

export function usePostProblems(siteId: string | null, postId: string | null) {
  return useSWRFetch<ContentProblemSummary>(
    siteId && postId ? `/sites/${siteId}/intelligence/problems/${postId}` : null
  );
}

// ─── Recommendations ─────────────────────────────

export function useRecommendations(siteId: string | null, filters?: { type?: string; priority?: string; status?: string }) {
  const params = new URLSearchParams();
  if (filters?.type) params.set('recommendation_type', filters.type);
  if (filters?.priority) params.set('priority', filters.priority);
  if (filters?.status) params.set('status', filters.status);
  const qs = params.toString();
  return useSWRFetch<RecommendationListResponse>(
    siteId ? `/sites/${siteId}/intelligence/recommendations${qs ? `?${qs}` : ''}` : null
  );
}

export function usePostRecommendations(siteId: string | null, postId: string | null) {
  return useSWRFetch<Recommendation[]>(
    siteId && postId ? `/sites/${siteId}/intelligence/recommendations/${postId}` : null
  );
}

// ─── Phase 6: Living Ecosystem ───────────────────

export function useEcosystemVisuals(siteId: string | null) {
  return useSWRFetch<EcosystemVisualsResponse>(
    siteId ? `/sites/${siteId}/intelligence/ecosystem-visuals` : null
  );
}

// ─── 2026 AI Readiness ───────────────────────────

export function useAIScores(siteId: string | null) {
  return useSWRFetch<AIScores>(
    siteId ? `/sites/${siteId}/intelligence/ai-scores` : null
  );
}

// ─── Subscription ────────────────────────────────

export function useSubscription() {
  return useSWRFetch<Subscription>('/billing/subscription');
}

// ─── Monitoring & ROI ───────────────────────────

export function useAlerts(siteId: string | null) {
  return useSWRFetch<AlertsListResponse>(
    siteId ? `/sites/${siteId}/intelligence/alerts` : null
  );
}

export function useSinceLastVisit(siteId: string | null) {
  return useSWRFetch<SinceLastVisitResponse>(
    siteId ? `/sites/${siteId}/intelligence/since-last-visit` : null
  );
}

export function useROISummary(siteId: string | null) {
  return useSWRFetch<ROISummary>(
    siteId ? `/sites/${siteId}/intelligence/roi-summary` : null
  );
}

export function useHealthHistory(siteId: string | null) {
  return useSWRFetch<Array<{ score: number; factor_scores: Record<string, number>; analyzed_at: string | null }>>(
    siteId ? `/sites/${siteId}/intelligence/health/history` : null
  );
}

export function useAnalysisDiff(siteId: string | null) {
  return useSWRFetch<import('@/lib/types').AnalysisDiff | null>(
    siteId ? `/sites/${siteId}/intelligence/analysis-diff` : null
  );
}

export function useImpactEstimate(siteId: string | null) {
  return useSWRFetch<import('@/lib/types').ImpactEstimate>(
    siteId ? `/sites/${siteId}/intelligence/recommendations/impact-estimate` : null
  );
}

export function useTopContentGap(siteId: string | null) {
  return useSWRFetch<TopContentGap | null>(
    siteId ? `/sites/${siteId}/intelligence/top-content-gap` : null
  );
}
