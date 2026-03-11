'use client';

import { useSite } from '@/lib/hooks/useSite';
import { useSiteHealth } from '@/lib/hooks/useApi';
import { HealthScoreCard } from '@/components/dashboard/HealthScoreCard';
import { EfficiencyRatio } from '@/components/dashboard/EfficiencyRatio';
import { PostBreakdown } from '@/components/dashboard/PostBreakdown';
import { TrendChart } from '@/components/dashboard/TrendChart';
import { ClusterList } from '@/components/dashboard/ClusterList';
import { Spinner } from '@/components/ui/Spinner';

export default function DashboardPage() {
  const { currentSite } = useSite();
  const { data, isLoading, error } = useSiteHealth(currentSite?.id ?? null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load dashboard data</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-lg font-medium text-brand-text">No data yet</p>
          <p className="text-sm text-brand-text-muted mt-1">
            Connect a site and run the ecosystem analysis to see your dashboard.
          </p>
        </div>
      </div>
    );
  }

  // Transform trends dict into chart-friendly format
  const trendData = Object.entries(data.trends).map(([key, value]) => ({
    date: key,
    pageviews: value,
  }));

  return (
    <div className="space-y-6">
      {/* Row 1 — Hero metrics */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <HealthScoreCard
          title="Content Health Score"
          value={Math.round(data.content_health_score)}
          trend="stable"
          description="Overall ecosystem health"
        />
        <EfficiencyRatio
          ratio={data.content_efficiency_ratio}
          trend="stable"
        />
        <HealthScoreCard
          title="Total Posts"
          value={data.total_posts}
          trend="stable"
          description={`${data.active_posts} active · ${data.dead_posts} dead`}
        />
      </div>

      {/* Row 2 — Post breakdown */}
      <PostBreakdown
        active={data.active_posts}
        passive={data.passive_posts}
        cannibal={data.cannibalistic_posts}
        dead={data.dead_posts}
      />

      {/* Row 3 — Trend chart */}
      <TrendChart data={trendData} />

      {/* Row 4 — Clusters */}
      <ClusterList clusters={data.clusters} />
    </div>
  );
}
