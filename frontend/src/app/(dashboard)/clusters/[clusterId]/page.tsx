'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useClusterDetail, useCannibalizationPairs } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { SEVERITY_COLORS, ROLE_COLORS, ROLE_LABELS, ECOSYSTEM_COLORS } from '@/lib/constants';
import type { PostRole, EcosystemState } from '@/lib/constants';
import {
  ArrowLeft,
  FileText,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';

export default function ClusterDetailPage() {
  const params = useParams<{ clusterId: string }>();
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const clusterId = params?.clusterId ?? null;

  const { data: cluster, isLoading } = useClusterDetail(siteId, clusterId);
  const { data: allCannPairs } = useCannibalizationPairs(siteId);

  // Filter cann pairs for this cluster
  const cannPairs = (allCannPairs || []).filter((p) => p.cluster_id === clusterId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!cluster) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <p className="text-brand-text-muted">Cluster not found</p>
        <Link href="/clusters" className="text-sm text-brand-accent mt-2">← Back to clusters</Link>
      </div>
    );
  }

  const ecoInfo = cluster.ecosystem_state
    ? ECOSYSTEM_COLORS[cluster.ecosystem_state as EcosystemState]
    : null;

  const healthColor =
    (cluster.health_score ?? 0) >= 75 ? '#22c55e'
    : (cluster.health_score ?? 0) >= 50 ? '#eab308'
    : (cluster.health_score ?? 0) >= 25 ? '#f97316'
    : '#ef4444';

  // Sort posts by composite score
  const sortedPosts = [...(cluster.posts || [])].sort(
    (a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Back + Header */}
      <div>
        <Link href="/clusters" className="inline-flex items-center gap-1 text-sm text-brand-text-muted hover:text-brand-text mb-4">
          <ArrowLeft size={14} /> Back to clusters
        </Link>

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-brand-text">
              {cluster.label || 'Unlabeled Cluster'}
            </h1>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-sm text-brand-text-muted">{cluster.post_count} posts</span>
              {ecoInfo && <Badge color={ecoInfo.border}>{ecoInfo.label}</Badge>}
            </div>
          </div>
          {cluster.health_score != null && (
            <div className="text-right">
              <div className="text-3xl font-bold" style={{ color: healthColor }}>
                {Math.round(cluster.health_score)}
              </div>
              <div className="text-xs text-brand-text-muted">cluster health</div>
            </div>
          )}
        </div>
      </div>

      {/* Summary Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted">Total Posts</p>
          <p className="text-xl font-bold text-brand-text mt-1">{cluster.post_count}</p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted">Cann. Pairs</p>
          <p className="text-xl font-bold text-severity-high mt-1">{cannPairs.length}</p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted">Avg Health</p>
          <p className="text-xl font-bold mt-1" style={{ color: healthColor }}>
            {cluster.health_score != null ? Math.round(cluster.health_score) : '—'}
          </p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted">Ecosystem</p>
          <p className="text-xl font-bold text-brand-text mt-1">
            {ecoInfo?.label || '—'}
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Posts List */}
        <Card className="lg:col-span-2 !p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-brand-border">
            <h3 className="text-sm font-semibold text-brand-text">Posts in this cluster</h3>
          </div>
          <div className="divide-y divide-brand-border/50 max-h-[600px] overflow-y-auto">
            {sortedPosts.map((post) => {
              const scoreColor =
                (post.composite_score ?? 0) >= 75 ? '#22c55e'
                : (post.composite_score ?? 0) >= 50 ? '#eab308'
                : (post.composite_score ?? 0) >= 25 ? '#f97316'
                : '#ef4444';

              return (
                <div key={post.post_id} className="px-4 py-3 hover:bg-brand-surface-hover/50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <Link
                        href={`/posts/${post.post_id}`}
                        className="text-sm font-medium text-brand-text hover:text-brand-accent transition-colors line-clamp-1"
                      >
                        {post.title || 'Untitled'}
                      </Link>
                      <p className="text-xs text-brand-text-muted truncate">{post.url}</p>
                    </div>
                    <div className="flex items-center gap-3 ml-4">
                      {post.role && (
                        <Badge color={ROLE_COLORS[post.role as PostRole] || '#6b7280'}>
                          {ROLE_LABELS[post.role as PostRole] || post.role}
                        </Badge>
                      )}
                      {post.composite_score != null && (
                        <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor }}>
                          {Math.round(post.composite_score)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Cannibalization Pairs */}
        <Card>
          <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
            <AlertTriangle size={16} className="text-severity-high" />
            Cannibalization ({cannPairs.length})
          </h3>
          {cannPairs.length > 0 ? (
            <div className="space-y-4 max-h-[500px] overflow-y-auto">
              {cannPairs.map((pair) => (
                <div key={pair.id} className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge color={SEVERITY_COLORS[pair.severity]}>
                      {pair.severity}
                    </Badge>
                    <span className="text-xs text-brand-text-muted">
                      {(pair.overlap_score * 100).toFixed(0)}% overlap
                    </span>
                  </div>
                  <div className="space-y-1">
                    <Link
                      href={`/posts/${pair.post_a.post_id}`}
                      className="block text-xs text-brand-text hover:text-brand-accent truncate"
                    >
                      {pair.post_a.title}
                    </Link>
                    <div className="text-xs text-brand-text-muted text-center">↕ competing with</div>
                    <Link
                      href={`/posts/${pair.post_b.post_id}`}
                      className="block text-xs text-brand-text hover:text-brand-accent truncate"
                    >
                      {pair.post_b.title}
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-brand-text-muted text-center py-4">
              No cannibalization detected in this cluster ✓
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
