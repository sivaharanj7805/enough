'use client';

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { usePosts, useSiteHealth, useProblems } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import {
  Search,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ExternalLink,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
} from 'lucide-react';
import { SEVERITY_COLORS, ROLE_COLORS, ROLE_LABELS } from '@/lib/constants';
import type { Post } from '@/lib/types';

type SortField = 'title' | 'word_count' | 'publish_date' | 'updated_at' | 'issues';
type SortDir = 'asc' | 'desc';

function SortIcon({ field, currentField, currentDir }: { field: SortField; currentField: SortField; currentDir: SortDir }) {
  if (field !== currentField) return <ChevronsUpDown size={14} className="text-brand-text-muted/50" />;
  return currentDir === 'asc' ? <ChevronUp size={14} className="text-brand-accent" /> : <ChevronDown size={14} className="text-brand-accent" />;
}

function HealthDot({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-brand-text-muted">—</span>;
  const color = score >= 75 ? '#22c55e' : score >= 50 ? '#eab308' : score >= 25 ? '#f97316' : '#ef4444';
  return (
    <div className="flex items-center gap-2">
      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-sm font-medium text-brand-text">{Math.round(score)}</span>
    </div>
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

  const PAGE_SIZE = 50;
  const { data: postsData, isLoading } = usePosts(siteId, 500, 0); // Load all for client-side filtering
  const { data: health } = useSiteHealth(siteId);
  const { data: problems } = useProblems(siteId);

  // Build issue count per post
  const issueCountMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const p of problems || []) {
      map[p.post_id] = (map[p.post_id] || 0) + 1;
    }
    return map;
  }, [problems]);

  // Build health score map from site health clusters
  const healthScoreMap = useMemo(() => {
    const map: Record<string, { score: number | null; role: string | null; cluster: string | null }> = {};
    if (health?.clusters) {
      // We don't have per-post health from this endpoint — will show issue count instead
    }
    return map;
  }, [health]);

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
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return posts;
  }, [postsData, search, healthFilter, sortField, sortDir, issueCountMap]);

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

          {/* Count */}
          <span className="text-xs text-brand-text-muted">
            Showing {pagedPosts.length} of {filteredPosts.length}
          </span>
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
                return (
                  <tr
                    key={post.id}
                    className="hover:bg-brand-surface-hover/50 transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[400px]">
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
                      <span className="text-sm text-brand-text">
                        {post.word_count?.toLocaleString() || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-brand-text-muted">
                        {post.publish_date
                          ? new Date(post.publish_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                          : '—'}
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
                  <td colSpan={6} className="px-4 py-12 text-center text-sm text-brand-text-muted">
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
