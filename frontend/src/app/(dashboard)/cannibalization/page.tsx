'use client';

import { useState, useMemo, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useCannibalizationPairs, useClusters } from '@/lib/hooks/useApi';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { SEVERITY_COLORS } from '@/lib/constants';
import type { Severity } from '@/lib/constants';
import { ArrowDownUp, ExternalLink, CheckCircle2 } from 'lucide-react';

const ALL_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

type SortOption = 'severity' | 'similarity' | 'cluster';

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'severity', label: 'Severity' },
  { value: 'similarity', label: 'Similarity' },
  { value: 'cluster', label: 'Cluster' },
];

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export default function CannibalizationPage() {
  const { currentSite } = useSite();
  const { data: pairs, isLoading, error } = useCannibalizationPairs(currentSite?.id ?? null);
  const { data: clusters } = useClusters(currentSite?.id ?? null);

  const [severityFilter, setSeverityFilter] = useState<Severity[]>(ALL_SEVERITIES);
  const [clusterFilter, setClusterFilter] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('severity');

  /* ── Summary stats ── */
  const stats = useMemo(() => {
    if (!pairs) return { total: 0, critical: 0, high: 0, medium: 0 };
    return {
      total: pairs.length,
      critical: pairs.filter((p) => p.severity === 'critical').length,
      high: pairs.filter((p) => p.severity === 'high').length,
      medium: pairs.filter((p) => p.severity === 'medium').length,
    };
  }, [pairs]);

  /* ── Filtered + sorted pairs ── */
  const sortedPairs = useMemo(() => {
    if (!pairs) return [];
    let result = pairs.filter((p) => severityFilter.includes(p.severity));
    if (clusterFilter) result = result.filter((p) => p.cluster_id === clusterFilter);

    result.sort((a, b) => {
      switch (sortBy) {
        case 'severity':
          return (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
        case 'similarity':
          return b.overlap_score - a.overlap_score;
        case 'cluster':
          return (a.cluster_id ?? '').localeCompare(b.cluster_id ?? '');
        default:
          return 0;
      }
    });
    return result;
  }, [pairs, severityFilter, clusterFilter, sortBy]);

  const clusterLabel = useCallback(
    (clusterId: string) => clusters?.find((c) => c.id === clusterId)?.label ?? 'Unknown cluster',
    [clusters],
  );

  const toggleSeverity = useCallback((s: Severity) => {
    setSeverityFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  }, []);

  /* ── Loading ── */
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  /* ── Error ── */
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load cannibalization data</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  /* ── Empty state ── */
  if (!pairs || pairs.length === 0) {
    return (
      <div className="space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-bold text-brand-text">Cannibalization</h1>
          <p className="text-sm text-brand-text-muted mt-1">
            Detect posts competing against each other in search results.
          </p>
        </div>
        <div className="flex flex-col items-center justify-center rounded-xl border border-brand-border bg-brand-surface py-20">
          <CheckCircle2 size={40} className="text-green-500 mb-3" />
          <p className="text-lg font-semibold text-brand-text">No cannibalization detected</p>
          <p className="text-sm text-brand-text-muted mt-1 max-w-md text-center">
            Great news -- your content targets distinct topics effectively. No overlapping pairs were found.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* ── Page header ── */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-text">Cannibalization</h1>
          <p className="text-sm text-brand-text-muted mt-1">
            Posts competing for the same keywords reduce each other&apos;s ranking potential.
          </p>
        </div>
        <span className="text-sm text-brand-text-muted">
          {stats.total} {stats.total === 1 ? 'pair' : 'pairs'} found
        </span>
      </div>

      {/* ── Summary stat cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Total Pairs" value={stats.total} color="#6366f1" />
        <StatCard label="Critical" value={stats.critical} color={SEVERITY_COLORS.critical} />
        <StatCard label="High" value={stats.high} color={SEVERITY_COLORS.high} />
        <StatCard label="Medium" value={stats.medium} color={SEVERITY_COLORS.medium} />
      </div>

      {/* ── Filter bar ── */}
      <div className="flex flex-wrap items-center gap-4 rounded-xl border border-brand-border bg-brand-surface px-5 py-3">
        {/* Severity toggles */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-text-muted">Severity:</span>
          {ALL_SEVERITIES.map((s) => (
            <button
              key={s}
              aria-label={`Filter ${s} severity`}
              onClick={() => toggleSeverity(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
                severityFilter.includes(s) ? 'text-white' : 'text-brand-text-muted bg-brand-surface'
              }`}
              style={
                severityFilter.includes(s)
                  ? { backgroundColor: SEVERITY_COLORS[s] }
                  : { border: `1px solid ${SEVERITY_COLORS[s]}40`, color: SEVERITY_COLORS[s] }
              }
            >
              {s}
            </button>
          ))}
        </div>

        {/* Sort dropdown */}
        <div className="flex items-center gap-2 ml-auto">
          <ArrowDownUp size={14} className="text-brand-text-muted" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            aria-label="Sort pairs"
            className="rounded-lg border border-brand-border bg-brand-bg px-2 py-1 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Cluster filter */}
        {clusters && clusters.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              value={clusterFilter ?? ''}
              onChange={(e) => setClusterFilter(e.target.value || null)}
              aria-label="Filter by cluster"
              className="rounded-lg border border-brand-border bg-brand-bg px-2 py-1 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
            >
              <option value="">All clusters</option>
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>{c.label ?? c.id}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ── Pair count after filtering ── */}
      {sortedPairs.length !== stats.total && (
        <p className="text-xs text-brand-text-muted">
          Showing {sortedPairs.length} of {stats.total} pairs
        </p>
      )}

      {/* ── Pair cards ── */}
      <div className="space-y-4">
        {sortedPairs.map((pair) => {
          const pct = Math.round(pair.overlap_score * 100);
          const cluster = clusterLabel(pair.cluster_id);

          return (
            <div
              key={pair.id}
              className="rounded-xl border border-brand-border bg-brand-surface p-5 transition-colors hover:border-brand-accent/40"
            >
              {/* Top row: severity + similarity + cluster */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Badge color={SEVERITY_COLORS[pair.severity]}>{pair.severity}</Badge>
                  {pair.chunk_confirmed && (
                    <span className="text-xs text-green-500 font-medium" title="Confirmed at section level">
                      Verified
                    </span>
                  )}
                  <span className="text-xs text-brand-text-muted">{cluster}</span>
                </div>
                <div className="text-right">
                  <span className="text-2xl font-bold text-brand-text">{pct}</span>
                  <span className="text-sm font-medium text-brand-text-muted">%</span>
                  <p className="text-[10px] text-brand-text-muted leading-none mt-0.5">similarity</p>
                </div>
              </div>

              {/* Post A vs Post B */}
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
                {/* Post A */}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-brand-text line-clamp-1" title={pair.post_a.title}>
                    {pair.post_a.title}
                  </p>
                  <p className="text-xs text-brand-text-muted truncate" title={pair.post_a.url}>
                    {pair.post_a.url}
                  </p>
                </div>

                {/* Divider */}
                <div className="flex items-center gap-2">
                  <div className="w-8 h-px bg-brand-border" />
                  <span className="text-xs font-semibold text-brand-text-muted uppercase">vs</span>
                  <div className="w-8 h-px bg-brand-border" />
                </div>

                {/* Post B */}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-brand-text line-clamp-1" title={pair.post_b.title}>
                    {pair.post_b.title}
                  </p>
                  <p className="text-xs text-brand-text-muted truncate" title={pair.post_b.url}>
                    {pair.post_b.url}
                  </p>
                </div>
              </div>

              {/* Bottom row: recommendation link */}
              <div className="mt-4 pt-3 border-t border-brand-border/50 flex items-center justify-between">
                {pair.overlapping_queries && pair.overlapping_queries.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-brand-text-muted">Shared queries:</span>
                    {pair.overlapping_queries.slice(0, 3).map((q) => (
                      <span
                        key={q}
                        className="inline-block rounded bg-brand-bg px-1.5 py-0.5 text-[10px] text-brand-text-muted"
                      >
                        {q}
                      </span>
                    ))}
                    {pair.overlapping_queries.length > 3 && (
                      <span className="text-[10px] text-brand-text-muted">
                        +{pair.overlapping_queries.length - 3} more
                      </span>
                    )}
                  </div>
                )}
                <a
                  href={`/actions?search=${encodeURIComponent(pair.post_a.title)}`}
                  className="ml-auto flex items-center gap-1 text-xs font-medium text-brand-accent hover:text-brand-accent/80 transition-colors"
                >
                  View recommendation
                  <ExternalLink size={12} />
                </a>
              </div>
            </div>
          );
        })}
      </div>

      {/* Filtered empty */}
      {sortedPairs.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-brand-border bg-brand-surface py-12">
          <p className="text-sm text-brand-text-muted">No pairs match the current filters.</p>
        </div>
      )}
    </div>
  );
}

/* ── Stat card component ── */
function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl border border-brand-border bg-brand-surface p-5">
      <p className="text-xs font-medium text-brand-text-muted">{label}</p>
      <p className="text-2xl font-bold mt-1" style={{ color }}>
        {value}
      </p>
    </div>
  );
}
