'use client';

import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useClusters, useCannibalizationPairs } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ECOSYSTEM_COLORS } from '@/lib/constants';
import type { EcosystemState } from '@/lib/constants';
import {
  Layers,
  FileText,
  AlertTriangle,
  TrendingUp,
  ArrowRight,
} from 'lucide-react';

function ClusterCard({
  cluster,
  cannPairCount,
}: {
  cluster: {
    id: string;
    label: string | null;
    description?: string | null;
    ecosystem_state: EcosystemState | null;
    health_score: number | null;
    post_count: number;
  };
  cannPairCount: number;
}) {
  const healthColor =
    (cluster.health_score ?? 0) >= 75 ? '#22c55e'
    : (cluster.health_score ?? 0) >= 50 ? '#eab308'
    : (cluster.health_score ?? 0) >= 25 ? '#f97316'
    : '#ef4444';

  const ecoInfo = cluster.ecosystem_state
    ? ECOSYSTEM_COLORS[cluster.ecosystem_state]
    : null;

  return (
    <Link href={`/clusters/${cluster.id}`}>
      <Card className="group hover:border-brand-border-hover transition-all duration-200 h-full">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-brand-text group-hover:text-brand-accent transition-colors line-clamp-1">
              {cluster.label || 'Unlabeled Cluster'}
            </h3>
            {cluster.description && (
              <p className="text-xs text-brand-text-muted mt-1 line-clamp-2">{cluster.description}</p>
            )}
            {ecoInfo && !cluster.description && (
              <Badge className="mt-1.5" color={ecoInfo.border}>
                {ecoInfo.label}
              </Badge>
            )}
          </div>
          {cluster.health_score != null && (
            <div className="text-right">
              <div className="text-2xl font-bold" style={{ color: healthColor }}>
                {Math.round(cluster.health_score)}
              </div>
              <div className="text-xs text-brand-text-muted">health</div>
            </div>
          )}
        </div>

        <div className="space-y-2 mt-4">
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-brand-text-muted">
              <FileText size={14} /> Posts
            </span>
            <span className="font-medium text-brand-text">{cluster.post_count}</span>
          </div>

          {cannPairCount > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-severity-high">
                <AlertTriangle size={14} /> Cannibalization pairs
              </span>
              <span className="font-medium text-severity-high">{cannPairCount}</span>
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-1 text-xs font-medium text-brand-accent opacity-0 group-hover:opacity-100 transition-opacity">
          View cluster <ArrowRight size={12} />
        </div>
      </Card>
    </Link>
  );
}

export default function ClustersPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const { data: clusters, isLoading } = useClusters(siteId);
  const { data: cannPairs } = useCannibalizationPairs(siteId);

  // Count cannibalization pairs per cluster
  const cannCountByCluster: Record<string, number> = {};
  for (const pair of cannPairs || []) {
    cannCountByCluster[pair.cluster_id] = (cannCountByCluster[pair.cluster_id] || 0) + 1;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!clusters || clusters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center">
        <div className="rounded-full bg-brand-surface-hover p-6 mb-4">
          <Layers size={48} className="text-brand-text-muted" />
        </div>
        <h2 className="text-xl font-semibold text-brand-text">No clusters yet</h2>
        <p className="mt-2 text-brand-text-muted max-w-md">
          Run the intelligence pipeline to discover topic clusters in your content.
        </p>
      </div>
    );
  }

  // Sort: most posts first
  const sorted = [...clusters].sort((a, b) => b.post_count - a.post_count);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-brand-text">Topic Clusters</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          {clusters.length} clusters · {clusters.reduce((sum, c) => sum + c.post_count, 0)} posts total
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted uppercase tracking-wider">Clusters</p>
          <p className="text-2xl font-bold text-brand-text mt-1">{clusters.length}</p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted uppercase tracking-wider">Largest Cluster</p>
          <p className="text-2xl font-bold text-brand-text mt-1">{sorted[0]?.post_count || 0}</p>
          <p className="text-xs text-brand-text-muted truncate">{sorted[0]?.label || '—'}</p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted uppercase tracking-wider">Avg Cluster Size</p>
          <p className="text-2xl font-bold text-brand-text mt-1">
            {Math.round(clusters.reduce((sum, c) => sum + c.post_count, 0) / clusters.length)}
          </p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted uppercase tracking-wider">Cann. Pairs</p>
          <p className="text-2xl font-bold text-severity-high mt-1">{(cannPairs || []).length}</p>
        </Card>
      </div>

      {/* Cluster Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {sorted.map((cluster) => (
          <ClusterCard
            key={cluster.id}
            cluster={cluster}
            cannPairCount={cannCountByCluster[cluster.id] || 0}
          />
        ))}
      </div>
    </div>
  );
}
