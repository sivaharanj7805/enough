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
  PostHealth,
  ClusterNarrative,
  CalendarResponse,
  RedirectStatusResponse,
} from '@/lib/types';

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

export function useClusterPosts(siteId: string | null, clusterId: string | null) {
  return useSWRFetch<PostHealth[]>(
    siteId && clusterId ? `/sites/${siteId}/intelligence/clusters/${clusterId}/posts` : null
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
