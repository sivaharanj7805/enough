'use client';

import { useSite } from '@/lib/hooks/useSite';
import { useSiteHealth, useAIScores } from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { HealthScoreCard } from '@/components/dashboard/HealthScoreCard';
import { EfficiencyRatio } from '@/components/dashboard/EfficiencyRatio';
import { PostBreakdown } from '@/components/dashboard/PostBreakdown';
import { TrendChart } from '@/components/dashboard/TrendChart';
import { ClusterList } from '@/components/dashboard/ClusterList';
import { AIReadinessCard } from '@/components/dashboard/AIReadinessCard';
import { Spinner } from '@/components/ui/Spinner';
import { apiFetch } from '@/lib/api';
import { mutate } from 'swr';

export default function DashboardPage() {
  const { currentSite } = useSite();
  const { data, isLoading, error } = useSiteHealth(currentSite?.id ?? null);
  const { data: aiScores, isLoading: aiLoading } = useAIScores(currentSite?.id ?? null);
  const { session } = useAuth();
  const token = session?.access_token ?? (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

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

  const handleRunAIScan = async () => {
    if (!currentSite?.id || !token) return;
    try {
      await apiFetch(`/sites/${currentSite.id}/intelligence/ai-readiness`, {
        method: 'POST',
        token: token ?? undefined,
      });
      // Refetch AI scores after ~2 min
      setTimeout(() => {
        void mutate(`/sites/${currentSite.id}/intelligence/ai-scores`);
      }, 120_000);
    } catch {
      // silent — button just triggers background task
    }
  };

  // Build AI scores object compatible with AIReadinessCard
  const aiScoresForCard = aiScores && aiScores.total_scored > 0
    ? {
        total_scored: aiScores.total_scored,
        avg_citability: aiScores.avg_citability ?? 0,
        avg_eeat: aiScores.avg_eeat ?? 0,
        avg_schema: aiScores.avg_schema ?? 0,
        avg_extraction: aiScores.avg_extraction ?? 0,
        pct_has_schema: aiScores.pct_has_schema ?? 0,
        pct_ai_ready: aiScores.pct_ai_ready ?? 0,
      }
    : null;

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

      {/* Row 2 — Post breakdown + AI Readiness side by side */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="md:col-span-2">
          <PostBreakdown
            active={data.active_posts}
            passive={data.passive_posts}
            cannibal={data.cannibalistic_posts}
            dead={data.dead_posts}
          />
        </div>
        <div>
          <AIReadinessCard
            scores={aiScoresForCard}
            loading={aiLoading}
            onRunScan={() => void handleRunAIScan()}
          />
        </div>
      </div>

      {/* Row 3 — Trend chart */}
      <TrendChart data={trendData} />

      {/* Row 4 — Clusters */}
      <ClusterList clusters={data.clusters} />
    </div>
  );
}
