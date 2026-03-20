'use client';

import { useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useClusterDetail, useCannibalizationPairs, useProblems, useRecommendations } from '@/lib/hooks/useApi';
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
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Tag,
  Lightbulb,
  Link2,
} from 'lucide-react';

type SortField = 'title' | 'composite_score' | 'role' | 'word_count' | 'updated_at' | 'issues';
type SortDir = 'asc' | 'desc';

function SortIcon({ field, currentField, currentDir }: { field: SortField; currentField: SortField; currentDir: SortDir }) {
  if (field !== currentField) return <ChevronsUpDown size={12} className="text-brand-text-muted/50" />;
  return currentDir === 'asc' ? <ChevronUp size={12} className="text-brand-accent" /> : <ChevronDown size={12} className="text-brand-accent" />;
}

export default function ClusterDetailPage() {
  const params = useParams<{ clusterId: string }>();
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const clusterId = params?.clusterId ?? null;

  const { data: cluster, isLoading } = useClusterDetail(siteId, clusterId);
  const { data: allCannPairs } = useCannibalizationPairs(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: recsData } = useRecommendations(siteId);

  const [sortField, setSortField] = useState<SortField>('composite_score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Filter cann pairs for this cluster
  const cannPairs = (allCannPairs || []).filter((p) => p.cluster_id === clusterId);

  // Build issue count per post
  const issueCountMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const p of problems || []) {
      map[p.post_id] = (map[p.post_id] || 0) + 1;
    }
    return map;
  }, [problems]);

  // Cluster-specific recommendations
  const clusterRecs = useMemo(() => {
    if (!recsData?.recommendations || !cluster?.posts) return [];
    const postIds = new Set(cluster.posts.map((p) => p.post_id));
    return recsData.recommendations.filter((r) => postIds.has(r.post_id));
  }, [recsData, cluster]);

  // Extract top keywords from cluster label/description (heuristic: split label words)
  const topKeywords = useMemo(() => {
    if (!cluster) return [];
    const words: string[] = [];
    if (cluster.label) {
      words.push(...cluster.label.split(/[\s,·|/]+/).filter((w) => w.length > 2));
    }
    if (cluster.description) {
      const descWords = cluster.description
        .split(/[\s,·|/]+/)
        .filter((w) => w.length > 3)
        .slice(0, 10);
      words.push(...descWords);
    }
    // Dedupe and limit
    const seen = new Map<string, boolean>();
    const unique: string[] = [];
    for (const w of words) {
      const lower = w.toLowerCase();
      if (!seen.has(lower)) {
        seen.set(lower, true);
        unique.push(lower);
      }
    }
    return unique.slice(0, 10);
  }, [cluster]);

  // Bridge posts: posts in this cluster that link to posts in other clusters
  // We approximate: posts that appear in cann pairs with different cluster_ids
  const bridgePosts = useMemo(() => {
    if (!cluster?.posts || !allCannPairs) return [];
    const clusterPostIds = new Set(cluster.posts.map((p) => p.post_id));
    const bridgeIds = new Set<string>();

    for (const pair of allCannPairs || []) {
      if (pair.cluster_id !== clusterId) {
        if (clusterPostIds.has(pair.post_a.post_id)) bridgeIds.add(pair.post_a.post_id);
        if (clusterPostIds.has(pair.post_b.post_id)) bridgeIds.add(pair.post_b.post_id);
      }
    }

    return cluster.posts.filter((p) => bridgeIds.has(p.post_id));
  }, [cluster, allCannPairs, clusterId]);

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortField(field);
        setSortDir(field === 'title' ? 'asc' : 'desc');
      }
    },
    [sortField]
  );

  // Sort posts
  const sortedPosts = useMemo(() => {
    if (!cluster?.posts) return [];
    return [...cluster.posts].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'title':
          cmp = (a.title || '').localeCompare(b.title || '');
          break;
        case 'composite_score':
          cmp = (a.composite_score ?? 0) - (b.composite_score ?? 0);
          break;
        case 'role': {
          const roleOrder: Record<string, number> = { pillar: 0, supporter: 1, competitor: 2, dead_weight: 3 };
          cmp = (roleOrder[a.role || ''] ?? 99) - (roleOrder[b.role || ''] ?? 99);
          break;
        }
        case 'issues':
          cmp = (issueCountMap[a.post_id] || 0) - (issueCountMap[b.post_id] || 0);
          break;
        default:
          cmp = (a.composite_score ?? 0) - (b.composite_score ?? 0);
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [cluster, sortField, sortDir, issueCountMap]);

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
        <Link href="/clusters" className="text-sm text-brand-accent mt-2">Back to clusters</Link>
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

      {/* Top Keywords */}
      {topKeywords.length > 0 && (
        <Card className="!p-4">
          <div className="flex items-center gap-2 mb-3">
            <Tag size={14} className="text-brand-accent" />
            <h3 className="text-sm font-semibold text-brand-text">Top Keywords</h3>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {topKeywords.map((kw) => (
              <span
                key={kw}
                className="inline-flex items-center px-3 py-1 rounded-full bg-brand-accent/10 text-brand-accent text-xs font-medium"
              >
                {kw}
              </span>
            ))}
          </div>
        </Card>
      )}

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
            {cluster.health_score != null ? Math.round(cluster.health_score) : '--'}
          </p>
        </Card>
        <Card className="!p-4">
          <p className="text-xs text-brand-text-muted">Ecosystem</p>
          <p className="text-xl font-bold text-brand-text mt-1">
            {ecoInfo?.label || '--'}
          </p>
        </Card>
      </div>

      {/* Cluster-Specific Recommendations */}
      {clusterRecs.length > 0 && (
        <Card className="!p-4">
          <div className="flex items-center gap-2 mb-4">
            <Lightbulb size={14} className="text-yellow-400" />
            <h3 className="text-sm font-semibold text-brand-text">Recommendations ({clusterRecs.length})</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {clusterRecs.slice(0, 6).map((rec) => {
              const priorityColor = SEVERITY_COLORS[rec.priority as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low;
              return (
                <div
                  key={rec.id}
                  className="rounded-lg bg-brand-bg p-3 border border-brand-border/50 hover:border-brand-border-hover transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Badge color={priorityColor}>{rec.priority}</Badge>
                    <span className="text-xs text-brand-text-muted">{rec.recommendation_type}</span>
                  </div>
                  <p className="text-sm font-medium text-brand-text line-clamp-2">{rec.title}</p>
                  <p className="text-xs text-brand-text-muted mt-1 line-clamp-2">{rec.summary}</p>
                  <Link
                    href={`/posts/${rec.post_id}`}
                    className="inline-flex items-center gap-1 text-xs text-brand-accent hover:text-brand-accent-hover mt-2"
                  >
                    View post
                  </Link>
                </div>
              );
            })}
          </div>
          {clusterRecs.length > 6 && (
            <p className="text-xs text-brand-text-muted mt-3 text-center">
              +{clusterRecs.length - 6} more recommendations
            </p>
          )}
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Posts Table */}
        <Card className="lg:col-span-2 !p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-brand-border">
            <h3 className="text-sm font-semibold text-brand-text">Posts in this cluster</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-brand-border bg-brand-bg/50">
                  <th className="text-left px-4 py-2">
                    <button onClick={() => handleSort('title')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                      Title <SortIcon field="title" currentField={sortField} currentDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-2">
                    <button onClick={() => handleSort('role')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                      Role <SortIcon field="role" currentField={sortField} currentDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-2">
                    <button onClick={() => handleSort('composite_score')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                      Score <SortIcon field="composite_score" currentField={sortField} currentDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-2">
                    <button onClick={() => handleSort('issues')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                      Issues <SortIcon field="issues" currentField={sortField} currentDir={sortDir} />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/50 max-h-[600px] overflow-y-auto">
                {sortedPosts.map((post) => {
                  const scoreColor =
                    (post.composite_score ?? 0) >= 75 ? '#22c55e'
                    : (post.composite_score ?? 0) >= 50 ? '#eab308'
                    : (post.composite_score ?? 0) >= 25 ? '#f97316'
                    : '#ef4444';
                  const issues = issueCountMap[post.post_id] || 0;

                  return (
                    <tr key={post.post_id} className="hover:bg-brand-surface-hover/50 transition-colors">
                      <td className="px-4 py-3 max-w-[300px]">
                        <Link
                          href={`/posts/${post.post_id}`}
                          className="text-sm font-medium text-brand-text hover:text-brand-accent transition-colors line-clamp-1"
                        >
                          {post.title || 'Untitled'}
                        </Link>
                        <p className="text-xs text-brand-text-muted truncate">{post.url}</p>
                      </td>
                      <td className="px-4 py-3">
                        {post.role && (
                          <Badge color={ROLE_COLORS[post.role as PostRole] || '#6b7280'}>
                            {ROLE_LABELS[post.role as PostRole] || post.role}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {post.composite_score != null && (
                          <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor }}>
                            {Math.round(post.composite_score)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {issues > 0 ? (
                          <Badge color={issues >= 3 ? SEVERITY_COLORS.critical : issues >= 2 ? SEVERITY_COLORS.high : SEVERITY_COLORS.medium}>
                            <AlertTriangle size={10} className="mr-1" />
                            {issues}
                          </Badge>
                        ) : (
                          <span className="text-xs text-brand-text-muted">Clean</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Bridge Posts */}
          {bridgePosts.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
                <Link2 size={16} className="text-brand-accent" />
                Bridge Posts ({bridgePosts.length})
              </h3>
              <div className="space-y-3 max-h-[300px] overflow-y-auto">
                {bridgePosts.map((post) => (
                  <div key={post.post_id} className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                    <Link
                      href={`/posts/${post.post_id}`}
                      className="text-sm font-medium text-brand-text hover:text-brand-accent transition-colors line-clamp-1"
                    >
                      {post.title || 'Untitled'}
                    </Link>
                    <p className="text-xs text-brand-text-muted mt-1">
                      Links to other clusters
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

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
                      <div className="text-xs text-brand-text-muted text-center">competing with</div>
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
                No cannibalization detected in this cluster
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
