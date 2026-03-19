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

export interface AIScores {
  total_scored: number;
  avg_citability: number | null;
  avg_eeat: number | null;
  avg_schema: number | null;
  avg_extraction: number | null;
  pct_has_schema: number | null;
  pct_ai_ready: number | null;
}

export function useAIScores(siteId: string | null) {
  return useSWRFetch<AIScores>(
    siteId ? `/sites/${siteId}/intelligence/ai-scores` : null
  );
}

// ─── Subscription ────────────────────────────────

interface Subscription {
  tier: string;
  status: string;
  stripe_subscription_id: string | null;
  current_period_end: string | null;
}

export function useSubscription() {
  return useSWRFetch<Subscription>('/billing/subscription');
}
