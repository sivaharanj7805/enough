'use client';

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useProblems, useClusters, usePostsHealth } from '@/lib/hooks/useApi';
import type { PostHealthBulk } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import {
  Search,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ExternalLink,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  X,
  FileText,
} from 'lucide-react';
import { SEVERITY_COLORS, ROLE_COLORS } from '@/lib/constants';
import type { PostRole } from '@/lib/constants';

/* ───────── Types ───────── */

type SortField = 'title' | 'word_count' | 'publish_date' | 'issues' | 'health_score' | 'role';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 25;

const ROLE_FILTER_OPTIONS: Array<{ value: PostRole | 'all'; label: string }> = [
  { value: 'all', label: 'All roles' },
  { value: 'pillar', label: 'Pillar' },
  { value: 'supporter', label: 'Supporting' },
  { value: 'dead_weight', label: 'Dead Weight' },
];

const HEALTH_FILTER_OPTIONS = [
  { value: 'all', label: 'All health' },
  { value: 'healthy', label: 'Healthy (75+)' },
  { value: 'warning', label: 'Warning (50-74)' },
  { value: 'poor', label: 'Poor (<50)' },
];

/* ───────── Sub-components ───────── */

function SortIcon({ field, current, dir }: { field: SortField; current: SortField; dir: SortDir }) {
  if (field !== current) return <ChevronsUpDown size={14} className="text-brand-text-muted/40" />;
  return dir === 'asc'
    ? <ChevronUp size={14} className="text-brand-accent" />
    : <ChevronDown size={14} className="text-brand-accent" />;
}

function HealthScore({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-brand-text-muted">--</span>;
  const rounded = Math.round(score);
  const color = rounded >= 75 ? '#22c55e' : rounded >= 50 ? '#eab308' : rounded >= 25 ? '#f97316' : '#ef4444';
  const bg = rounded >= 75 ? 'bg-green-500/10' : rounded >= 50 ? 'bg-yellow-500/10' : rounded >= 25 ? 'bg-orange-500/10' : 'bg-red-500/10';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${bg}`} style={{ color }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {rounded}
    </span>
  );
}

function RoleBadge({ role }: { role: string | null }) {
  if (!role) return <span className="text-xs text-brand-text-muted">--</span>;
  const color = ROLE_COLORS[role as PostRole] ?? '#6b7280';
  const labels: Record<string, string> = { pillar: 'Pillar', supporter: 'Supporting', dead_weight: 'Dead Weight', competitor: 'Competitor' };
  return <Badge color={color}>{labels[role] || role}</Badge>;
}

function IssuesBadge({ count }: { count: number }) {
  if (count === 0) return <span className="text-xs text-brand-text-muted">None</span>;
  const color = count >= 3 ? SEVERITY_COLORS.critical : count >= 2 ? SEVERITY_COLORS.high : SEVERITY_COLORS.medium;
  return (
    <Badge color={color}>
      <AlertTriangle size={10} className="mr-1" />
      {count}
    </Badge>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-12 h-12 rounded-full bg-brand-surface-hover flex items-center justify-center mb-4">
        <FileText size={24} className="text-brand-text-muted" />
      </div>
      <p className="text-sm font-medium text-brand-text mb-1">
        {hasFilters ? 'No posts match your filters' : 'No posts found'}
      </p>
      <p className="text-xs text-brand-text-muted">
        {hasFilters ? 'Try adjusting your search or filter criteria.' : 'Run the pipeline to crawl and analyze your content.'}
      </p>
    </div>
  );
}

/* ───────── Sortable header helper ───────── */

function SortableHeader({
  label,
  field,
  currentField,
  currentDir,
  onSort,
  className,
}: {
  label: string;
  field: SortField;
  currentField: SortField;
  currentDir: SortDir;
  onSort: (f: SortField) => void;
  className?: string;
}) {
  return (
    <th className={`text-left px-3 py-2 ${className ?? ''}`}>
      <button
        onClick={() => onSort(field)}
        className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text transition-colors"
        aria-label={`Sort by ${label}`}
      >
        {label}
        <SortIcon field={field} current={currentField} dir={currentDir} />
      </button>
    </th>
  );
}

/* ───────── Main page ───────── */

export default function PostsListPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;

  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState<SortField>('publish_date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [clusterFilter, setClusterFilter] = useState('all');
  const [healthFilter, setHealthFilter] = useState('all');
  const [roleFilter, setRoleFilter] = useState('all');

  const { data: postHealthData, isLoading } = usePostsHealth(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: clusters } = useClusters(siteId);

  // Issue count per post
  const issueCountMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const p of problems || []) {
      map[p.post_id] = (map[p.post_id] || 0) + 1;
    }
    return map;
  }, [problems]);

  // Filter + sort — postHealthData is the primary data source (analyzed posts only)
  const filteredPosts = useMemo(() => {
    let posts: PostHealthBulk[] = postHealthData || [];

    if (search) {
      const q = search.toLowerCase();
      posts = posts.filter((p) => (p.title || '').toLowerCase().includes(q) || (p.url || '').toLowerCase().includes(q));
    }

    if (healthFilter !== 'all') {
      posts = posts.filter((p) => {
        const score = p.composite_score;
        if (score == null) return false;
        if (healthFilter === 'healthy') return score >= 75;
        if (healthFilter === 'warning') return score >= 50 && score < 75;
        return score < 50; // poor
      });
    }

    if (roleFilter !== 'all') {
      posts = posts.filter((p) => p.role === roleFilter);
    }

    if (clusterFilter !== 'all') {
      posts = posts.filter((p) => p.cluster_id === clusterFilter);
    }

    return [...posts].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'title':
          cmp = (a.title || '').localeCompare(b.title || '');
          break;
        case 'word_count':
          cmp = (a.word_count || 0) - (b.word_count || 0);
          break;
        case 'publish_date':
          cmp = new Date(a.publish_date || 0).getTime() - new Date(b.publish_date || 0).getTime();
          break;
        case 'issues':
          cmp = (issueCountMap[a.post_id] || 0) - (issueCountMap[b.post_id] || 0);
          break;
        case 'health_score': {
          const aS = a.composite_score ?? -1;
          const bS = b.composite_score ?? -1;
          cmp = aS - bS;
          break;
        }
        case 'role': {
          const order: Record<string, number> = { pillar: 0, supporter: 1, competitor: 2, dead_weight: 3 };
          cmp = (order[a.role || ''] ?? 99) - (order[b.role || ''] ?? 99);
          break;
        }
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [postHealthData, search, healthFilter, roleFilter, clusterFilter, sortField, sortDir, issueCountMap]);

  const totalPages = Math.ceil(filteredPosts.length / PAGE_SIZE);
  const pagedPosts = filteredPosts.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortField(field);
        setSortDir('desc');
      }
    },
    [sortField],
  );

  const hasActiveFilters = search !== '' || healthFilter !== 'all' || roleFilter !== 'all' || clusterFilter !== 'all';

  const clearAllFilters = useCallback(() => {
    setSearch('');
    setHealthFilter('all');
    setRoleFilter('all');
    setClusterFilter('all');
    setPage(0);
  }, []);

  const formatDate = (d: string | null) =>
    d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '--';

  /* ─── Loading state ─── */

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalCount = postHealthData?.length ?? 0;

  /* ─── Render ─── */

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold text-brand-text">Posts</h1>
        <p className="text-xs text-brand-text-muted mt-0.5">
          {totalCount.toLocaleString()} total posts
          {hasActiveFilters ? ` \u00b7 ${filteredPosts.length} matching filters` : ''}
        </p>
      </div>

      {/* Filter bar */}
      <Card className="!p-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-[220px]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-text-muted" />
            <input
              type="text"
              placeholder="Search by title or URL..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              className="w-full rounded-lg bg-brand-bg border border-brand-border pl-10 pr-4 py-2 text-xs text-brand-text placeholder:text-brand-text-muted/50 focus:border-brand-accent focus:outline-none focus:ring-1 focus:ring-brand-accent"
              aria-label="Search posts"
            />
          </div>

          {/* Health filter */}
          <select
            value={healthFilter}
            onChange={(e) => { setHealthFilter(e.target.value); setPage(0); }}
            className="rounded-lg bg-brand-bg border border-brand-border px-2.5 py-1.5 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
            aria-label="Filter by health"
          >
            {HEALTH_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Cluster filter */}
          {clusters && clusters.length > 0 && (
            <select
              value={clusterFilter}
              onChange={(e) => { setClusterFilter(e.target.value); setPage(0); }}
              className="rounded-lg bg-brand-bg border border-brand-border px-2.5 py-1.5 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
              aria-label="Filter by cluster"
            >
              <option value="all">All clusters</option>
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>{c.label || 'Unlabeled'}</option>
              ))}
            </select>
          )}

          {/* Role filter */}
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value); setPage(0); }}
            className="rounded-lg bg-brand-bg border border-brand-border px-2.5 py-1.5 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
            aria-label="Filter by role"
          >
            {ROLE_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Clear all */}
          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="flex items-center gap-1 text-xs text-brand-text-muted hover:text-brand-text transition-colors"
              aria-label="Clear all filters"
            >
              <X size={12} />
              Clear all
            </button>
          )}
        </div>
      </Card>

      {/* Table */}
      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-brand-bg text-[11px] font-medium text-brand-text-muted uppercase tracking-wider">
                <SortableHeader label="Title" field="title" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="min-w-[220px]" />
                <SortableHeader label="Health" field="health_score" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Role" field="role" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <th className="text-left px-3 py-2">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-brand-text-muted">Cluster</span>
                </th>
                <SortableHeader label="Words" field="word_count" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Published" field="publish_date" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Issues" field="issues" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <th className="w-8 px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {pagedPosts.map((post) => {
                const issueCount = issueCountMap[post.post_id] || 0;
                return (
                  <tr key={post.post_id} className="border-t border-brand-border hover:bg-brand-surface-hover transition-colors">
                    {/* Title + URL */}
                    <td className="px-3 py-2 max-w-[300px]">
                      <Link
                        href={`/posts/${post.post_id}`}
                        className="text-xs font-medium text-brand-text hover:text-brand-accent transition-colors line-clamp-1"
                      >
                        {post.title || 'Untitled'}
                      </Link>
                      <p className="text-[11px] text-brand-text-muted truncate mt-0.5">{post.url}</p>
                    </td>

                    {/* Health */}
                    <td className="px-3 py-2">
                      <HealthScore score={post.composite_score} />
                    </td>

                    {/* Role */}
                    <td className="px-3 py-2">
                      <RoleBadge role={post.role} />
                    </td>

                    {/* Cluster */}
                    <td className="px-3 py-2 max-w-[160px]">
                      {post.cluster_id ? (
                        <Link
                          href={`/clusters/${post.cluster_id}`}
                          className="text-xs text-brand-accent hover:underline transition-colors line-clamp-1"
                        >
                          {post.cluster_label || 'View cluster'}
                        </Link>
                      ) : (
                        <span className="text-xs text-brand-text-muted">--</span>
                      )}
                    </td>

                    {/* Word count */}
                    <td className="px-3 py-2">
                      <span className="text-xs text-brand-text tabular-nums">
                        {post.word_count?.toLocaleString() || '--'}
                      </span>
                    </td>

                    {/* Published date */}
                    <td className="px-3 py-2">
                      <span className="text-xs text-brand-text-muted whitespace-nowrap">
                        {formatDate(post.publish_date)}
                      </span>
                    </td>

                    {/* Issues */}
                    <td className="px-3 py-2">
                      <IssuesBadge count={issueCount} />
                    </td>

                    {/* External link */}
                    <td className="px-3 py-2">
                      {post.url && (
                        <a
                          href={post.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-text-muted hover:text-brand-text transition-colors"
                          aria-label={`Open ${post.title || 'post'} in new tab`}
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Empty state */}
          {pagedPosts.length === 0 && <EmptyState hasFilters={hasActiveFilters} />}
        </div>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center gap-1 rounded-lg border border-brand-border px-2.5 py-1.5 text-xs text-brand-text disabled:opacity-30 hover:bg-brand-surface-hover transition-colors"
            aria-label="Previous page"
          >
            <ArrowLeft size={12} />
            Previous
          </button>
          <span className="text-xs text-brand-text-muted">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="flex items-center gap-1 rounded-lg border border-brand-border px-2.5 py-1.5 text-xs text-brand-text disabled:opacity-30 hover:bg-brand-surface-hover transition-colors"
            aria-label="Next page"
          >
            Next
            <ArrowRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
