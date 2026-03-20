'use client';

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { usePosts, useSiteHealth, useProblems, useClusters } from '@/lib/hooks/useApi';
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
} from 'lucide-react';
import { SEVERITY_COLORS, ROLE_COLORS, ROLE_LABELS } from '@/lib/constants';
import type { PostRole } from '@/lib/constants';
import type { Post } from '@/lib/types';

type SortField = 'title' | 'word_count' | 'publish_date' | 'updated_at' | 'issues' | 'health_score' | 'role';
type SortDir = 'asc' | 'desc';

const ROLE_FILTER_OPTIONS: Array<{ value: PostRole | 'all'; label: string }> = [
  { value: 'all', label: 'All roles' },
  { value: 'pillar', label: 'Pillar' },
  { value: 'supporter', label: 'Supporting' },
  { value: 'dead_weight', label: 'Dead Weight' },
];

const ISSUE_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'seo_no_images', label: 'Missing Images' },
  { value: 'seo_title_length', label: 'Title Length' },
  { value: 'seo_missing_meta', label: 'Missing Meta' },
  { value: 'seo_no_internal_links', label: 'No Internal Links' },
  { value: 'thin_content', label: 'Thin Content' },
  { value: 'content_decay', label: 'Traffic Decay' },
  { value: 'proxy_decay', label: 'Stale Content' },
  { value: 'orphan', label: 'Orphan' },
  { value: 'readability_too_complex', label: 'Hard to Read' },
  { value: 'duplicate_content', label: 'Duplicate Content' },
  { value: 'ai_no_schema', label: 'No Schema' },
  { value: 'ai_low_citability', label: 'Low Citability' },
];

function SortIcon({ field, currentField, currentDir }: { field: SortField; currentField: SortField; currentDir: SortDir }) {
  if (field !== currentField) return <ChevronsUpDown size={14} className="text-brand-text-muted/50" />;
  return currentDir === 'asc' ? <ChevronUp size={14} className="text-brand-accent" /> : <ChevronDown size={14} className="text-brand-accent" />;
}

function HealthBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-brand-text-muted">--</span>;
  const color = score >= 75 ? '#22c55e' : score >= 50 ? '#eab308' : score >= 25 ? '#f97316' : '#ef4444';
  const bg = score >= 75 ? 'bg-green-500/10' : score >= 50 ? 'bg-yellow-500/10' : score >= 25 ? 'bg-orange-500/10' : 'bg-red-500/10';
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${bg}`}
      style={{ color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {Math.round(score)}
    </span>
  );
}

function RoleBadge({ role }: { role: string | null }) {
  if (!role) return <span className="text-xs text-brand-text-muted">--</span>;
  const colorMap: Record<string, string> = {
    pillar: '#3b82f6',
    supporter: '#6b7280',
    dead_weight: '#ef4444',
    competitor: '#f97316',
  };
  const labelMap: Record<string, string> = {
    pillar: 'Pillar',
    supporter: 'Supporting',
    dead_weight: 'Dead Weight',
    competitor: 'Competitor',
  };
  const color = colorMap[role] || '#6b7280';
  return (
    <Badge color={color}>
      {labelMap[role] || role}
    </Badge>
  );
}

export default function PostsListPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;

  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState<SortField>('publish_date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [clusterFilter, setClusterFilter] = useState<string>('all');
  const [healthFilter, setHealthFilter] = useState<string>('all');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [issueTypeFilters, setIssueTypeFilters] = useState<string[]>([]);

  const PAGE_SIZE = 50;
  const { data: postsData, isLoading } = usePosts(siteId, 500, 0);
  const { data: health } = useSiteHealth(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: clusters } = useClusters(siteId);

  // Build issue count per post and issue types per post
  const { issueCountMap, issueTypesMap } = useMemo(() => {
    const countMap: Record<string, number> = {};
    const typesMap: Record<string, Set<string>> = {};
    for (const p of problems || []) {
      countMap[p.post_id] = (countMap[p.post_id] || 0) + 1;
      if (!typesMap[p.post_id]) typesMap[p.post_id] = new Set();
      typesMap[p.post_id].add(p.problem_type);
    }
    return { issueCountMap: countMap, issueTypesMap: typesMap };
  }, [problems]);

  // Build health score + role + cluster map from site health clusters and cluster details
  const postMetaMap = useMemo(() => {
    const map: Record<string, { score: number | null; role: string | null; clusterId: string | null; clusterLabel: string | null }> = {};
    if (health?.clusters && clusters) {
      // We'll build from clusters data - iterate through available cluster data
      // The cluster detail endpoint has per-post health, but we only have summary here
      // Use clusters list to map posts to clusters
    }
    return map;
  }, [health, clusters]);

  // Toggle issue type filter
  const toggleIssueType = useCallback((type: string) => {
    setIssueTypeFilters((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
    setPage(0);
  }, []);

  // Filter and sort posts
  const filteredPosts = useMemo(() => {
    let posts = postsData?.posts || [];

    // Search filter
    if (search) {
      const q = search.toLowerCase();
      posts = posts.filter(
        (p) =>
          (p.title || '').toLowerCase().includes(q) ||
          (p.url || '').toLowerCase().includes(q)
      );
    }

    // Health filter
    if (healthFilter !== 'all') {
      const issueThreshold = healthFilter === 'critical' ? 3 : healthFilter === 'issues' ? 1 : 0;
      posts = posts.filter((p) => (issueCountMap[p.id] || 0) >= issueThreshold);
    }

    // Role filter
    if (roleFilter !== 'all') {
      posts = posts.filter((p) => {
        const meta = postMetaMap[p.id];
        return meta?.role === roleFilter;
      });
    }

    // Cluster filter
    if (clusterFilter !== 'all') {
      posts = posts.filter((p) => {
        const meta = postMetaMap[p.id];
        return meta?.clusterId === clusterFilter;
      });
    }

    // Issue type filter (multi-select: post must have at least one of the selected types)
    if (issueTypeFilters.length > 0) {
      posts = posts.filter((p) => {
        const types = issueTypesMap[p.id];
        if (!types) return false;
        return issueTypeFilters.some((t) => types.has(t));
      });
    }

    // Sort
    posts = [...posts].sort((a, b) => {
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
        case 'updated_at':
          cmp = new Date(a.updated_at || 0).getTime() - new Date(b.updated_at || 0).getTime();
          break;
        case 'issues':
          cmp = (issueCountMap[a.id] || 0) - (issueCountMap[b.id] || 0);
          break;
        case 'health_score': {
          const aScore = postMetaMap[a.id]?.score ?? -1;
          const bScore = postMetaMap[b.id]?.score ?? -1;
          cmp = aScore - bScore;
          break;
        }
        case 'role': {
          const roleOrder: Record<string, number> = { pillar: 0, supporter: 1, competitor: 2, dead_weight: 3 };
          const aRole = postMetaMap[a.id]?.role;
          const bRole = postMetaMap[b.id]?.role;
          cmp = (roleOrder[aRole || ''] ?? 99) - (roleOrder[bRole || ''] ?? 99);
          break;
        }
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return posts;
  }, [postsData, search, healthFilter, roleFilter, clusterFilter, issueTypeFilters, sortField, sortDir, issueCountMap, issueTypesMap, postMetaMap]);

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
    [sortField]
  );

  const hasActiveFilters = search !== '' || healthFilter !== 'all' || roleFilter !== 'all' || clusterFilter !== 'all' || issueTypeFilters.length > 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">All Posts</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          {filteredPosts.length} posts{search ? ` matching "${search}"` : ''} · Sort, filter, and click any post for details
        </p>
      </div>

      {/* Filters Bar */}
      <Card className="!p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-text-muted" />
            <input
              type="text"
              placeholder="Search posts by title or URL..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              className="w-full rounded-lg border border-brand-border bg-brand-bg pl-10 pr-4 py-2 text-sm text-brand-text placeholder:text-brand-text-muted/50 focus:border-brand-accent focus:outline-none focus:ring-1 focus:ring-brand-accent"
            />
          </div>

          {/* Health Filter */}
          <select
            value={healthFilter}
            onChange={(e) => { setHealthFilter(e.target.value); setPage(0); }}
            className="rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none"
          >
            <option value="all">All posts</option>
            <option value="issues">Has issues</option>
            <option value="critical">3+ issues</option>
          </select>

          {/* Cluster Filter */}
          {clusters && clusters.length > 0 && (
            <select
              value={clusterFilter}
              onChange={(e) => { setClusterFilter(e.target.value); setPage(0); }}
              className="rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none"
            >
              <option value="all">All clusters</option>
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>{c.label || 'Unlabeled'}</option>
              ))}
            </select>
          )}

          {/* Role Filter */}
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value); setPage(0); }}
            className="rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none"
          >
            {ROLE_FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Count */}
          <span className="text-xs text-brand-text-muted">
            Showing {pagedPosts.length} of {filteredPosts.length}
          </span>
        </div>

        {/* Issue Type Multi-Select */}
        <div className="flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-brand-border/50">
          <span className="text-xs font-medium text-brand-text-muted shrink-0">Issue type:</span>
          {ISSUE_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => toggleIssueType(opt.value)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                issueTypeFilters.includes(opt.value)
                  ? 'bg-brand-accent/15 text-brand-accent ring-1 ring-brand-accent/30'
                  : 'bg-brand-surface-hover text-brand-text-muted hover:text-brand-text'
              }`}
            >
              {opt.label}
            </button>
          ))}
          {hasActiveFilters && (
            <button
              onClick={() => {
                setSearch('');
                setHealthFilter('all');
                setRoleFilter('all');
                setClusterFilter('all');
                setIssueTypeFilters([]);
                setPage(0);
              }}
              className="ml-auto flex items-center gap-1 text-xs text-brand-text-muted hover:text-brand-text transition-colors"
            >
              <X size={12} />
              Clear all filters
            </button>
          )}
        </div>
      </Card>

      {/* Table */}
      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-brand-border bg-brand-bg/50">
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('title')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Title <SortIcon field="title" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('health_score')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Health <SortIcon field="health_score" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('role')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Role <SortIcon field="role" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <span className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">
                    Cluster
                  </span>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('word_count')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Words <SortIcon field="word_count" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('publish_date')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Published <SortIcon field="publish_date" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('updated_at')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Updated <SortIcon field="updated_at" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3">
                  <button onClick={() => handleSort('issues')} className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text">
                    Issues <SortIcon field="issues" currentField={sortField} currentDir={sortDir} />
                  </button>
                </th>
                <th className="w-10 px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border/50">
              {pagedPosts.map((post) => {
                const issueCount = issueCountMap[post.id] || 0;
                const meta = postMetaMap[post.id];
                return (
                  <tr
                    key={post.id}
                    className="hover:bg-brand-surface-hover/50 transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[300px]">
                      <Link
                        href={`/posts/${post.id}`}
                        className="text-sm font-medium text-brand-text hover:text-brand-accent transition-colors line-clamp-1"
                      >
                        {post.title || 'Untitled'}
                      </Link>
                      <p className="text-xs text-brand-text-muted truncate mt-0.5">
                        {post.url}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <HealthBadge score={meta?.score ?? null} />
                    </td>
                    <td className="px-4 py-3">
                      <RoleBadge role={meta?.role ?? null} />
                    </td>
                    <td className="px-4 py-3">
                      {meta?.clusterId ? (
                        <Link
                          href={`/clusters/${meta.clusterId}`}
                          className="text-xs text-brand-accent hover:text-brand-accent-hover hover:underline transition-colors line-clamp-1"
                        >
                          {meta.clusterLabel || 'View cluster'}
                        </Link>
                      ) : (
                        <span className="text-xs text-brand-text-muted">--</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-brand-text">
                        {post.word_count?.toLocaleString() || '--'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-brand-text-muted">
                        {post.publish_date
                          ? new Date(post.publish_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                          : '--'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-brand-text-muted">
                        {new Date(post.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {issueCount > 0 ? (
                        <Badge color={issueCount >= 3 ? SEVERITY_COLORS.critical : issueCount >= 2 ? SEVERITY_COLORS.high : SEVERITY_COLORS.medium}>
                          <AlertTriangle size={10} className="mr-1" />
                          {issueCount}
                        </Badge>
                      ) : (
                        <span className="text-xs text-brand-text-muted">Clean</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {post.url && (
                        <a
                          href={post.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-text-muted hover:text-brand-text transition-colors"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
              {pagedPosts.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-sm text-brand-text-muted">
                    {search ? `No posts matching "${search}"` : 'No posts found'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center gap-1 rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text disabled:opacity-30 hover:bg-brand-surface-hover transition-colors"
          >
            <ArrowLeft size={14} /> Previous
          </button>
          <span className="text-sm text-brand-text-muted">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="flex items-center gap-1 rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text disabled:opacity-30 hover:bg-brand-surface-hover transition-colors"
          >
            Next <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
