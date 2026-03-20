'use client';

import { useState, useMemo, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useCannibalizationPairs, useClusters } from '@/lib/hooks/useApi';
import { NetworkGraph } from '@/components/cannibalization/NetworkGraph';
import { PairDetailPanel } from '@/components/cannibalization/PairDetailPanel';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { SEVERITY_COLORS } from '@/lib/constants';
import type { Severity } from '@/lib/constants';
import type { PostHealth } from '@/lib/types';
import {
  ChevronDown,
  ChevronRight,
  ArrowDownUp,
} from 'lucide-react';

const ALL_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

type SortOption = 'severity' | 'similarity' | 'traffic';

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'severity', label: 'Severity' },
  { value: 'similarity', label: 'Similarity Score' },
  { value: 'traffic', label: 'Traffic Impact' },
];

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export default function CannibalizationPage() {
  const { currentSite } = useSite();
  const { data: pairs, isLoading: pairsLoading, error: pairsError } = useCannibalizationPairs(currentSite?.id ?? null);
  const { data: clusters } = useClusters(currentSite?.id ?? null);

  const [severityFilter, setSeverityFilter] = useState<Severity[]>(ALL_SEVERITIES);
  const [clusterFilter, setClusterFilter] = useState<string | null>(null);
  const [selectedPairId, setSelectedPairId] = useState<string | null>(null);
  const [, setSelectedNodeId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('severity');
  const [expandedPlanIds, setExpandedPlanIds] = useState<Set<string>>(new Set());

  // Derive unique posts from pairs
  const posts: PostHealth[] = useMemo(() => {
    if (!pairs) return [];
    const map = new Map<string, PostHealth>();
    pairs.forEach((p) => {
      if (!map.has(p.post_a.post_id)) {
        map.set(p.post_a.post_id, p.post_a);
      }
      if (!map.has(p.post_b.post_id)) {
        map.set(p.post_b.post_id, p.post_b);
      }
    });
    return Array.from(map.values());
  }, [pairs]);

  const selectedPair = pairs?.find((p) => p.id === selectedPairId) ?? null;

  // Summary stats
  const summaryStats = useMemo(() => {
    if (!pairs) return { total: 0, exact: 0 };
    const exact = pairs.filter((p) => p.overlap_score >= 0.9).length;
    return { total: pairs.length, exact };
  }, [pairs]);

  // Filtered and sorted pairs for the list view
  const sortedPairs = useMemo(() => {
    if (!pairs) return [];
    let result = [...pairs];

    // Apply severity filter
    result = result.filter((p) => severityFilter.includes(p.severity));

    // Apply cluster filter
    if (clusterFilter) {
      result = result.filter((p) => p.cluster_id === clusterFilter);
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'severity':
          return (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
        case 'similarity':
          return b.overlap_score - a.overlap_score;
        case 'traffic': {
          const aTraffic = (a.post_a.traffic_contribution ?? 0) + (a.post_b.traffic_contribution ?? 0);
          const bTraffic = (b.post_a.traffic_contribution ?? 0) + (b.post_b.traffic_contribution ?? 0);
          return bTraffic - aTraffic;
        }
        default:
          return 0;
      }
    });

    return result;
  }, [pairs, severityFilter, clusterFilter, sortBy]);

  const toggleSeverity = useCallback((s: Severity) => {
    setSeverityFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  }, []);

  const togglePlan = useCallback((id: string) => {
    setExpandedPlanIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSelectNode = useCallback((id: string | null) => {
    setSelectedNodeId(id);
    setSelectedPairId(null);
  }, []);

  const handleSelectEdge = useCallback((id: string | null) => {
    setSelectedPairId(id);
    setSelectedNodeId(null);
  }, []);

  if (pairsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (pairsError) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load cannibalization data</p>
          <p className="text-xs text-red-400 mt-1">{pairsError.message}</p>
        </div>
      </div>
    );
  }

  if (!pairs || pairs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-lg font-medium text-brand-text">No Cannibalization Detected</p>
          <p className="text-sm text-brand-text-muted mt-1">
            Your content ecosystem is clean -- no overlapping posts found.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full -m-6">
      <div className="flex-1 flex flex-col">
        {/* Summary Stat */}
        <div className="px-4 py-3 bg-brand-surface border-b border-brand-border">
          <p className="text-sm text-brand-text">
            <span className="font-bold text-brand-text">{summaryStats.total}</span>{' '}
            cannibalization pairs detected.{' '}
            <span className="font-bold text-severity-high">{summaryStats.exact}</span>{' '}
            are exact duplicates.
          </p>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-4 border-b border-brand-border bg-brand-surface px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-brand-text-muted">Severity:</span>
            {ALL_SEVERITIES.map((s) => (
              <button
                key={s}
                onClick={() => toggleSeverity(s)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  severityFilter.includes(s)
                    ? 'text-white'
                    : 'text-brand-text-muted bg-brand-surface-hover'
                }`}
                style={severityFilter.includes(s) ? {
                  backgroundColor: {
                    critical: '#ef4444',
                    high: '#f97316',
                    medium: '#eab308',
                    low: '#6b7280',
                  }[s],
                } : undefined}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Sort Options */}
          <div className="flex items-center gap-2 ml-4">
            <ArrowDownUp size={12} className="text-brand-text-muted" />
            <span className="text-xs font-medium text-brand-text-muted">Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="rounded-lg border border-brand-border bg-brand-bg px-2 py-1 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {clusters && clusters.length > 0 && (
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs font-medium text-brand-text-muted">Cluster:</span>
              <select
                value={clusterFilter ?? ''}
                onChange={(e) => setClusterFilter(e.target.value || null)}
                className="rounded-lg border border-brand-border bg-brand-bg px-2 py-1 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
              >
                <option value="">All clusters</option>
                {clusters.map((c) => (
                  <option key={c.id} value={c.id}>{c.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Graph */}
        <div className="flex-1 relative">
          <NetworkGraph
            posts={posts}
            pairs={pairs}
            onSelectNode={handleSelectNode}
            onSelectEdge={handleSelectEdge}
            severityFilter={severityFilter}
            clusterFilter={clusterFilter}
          />

          {/* Pair Cards Overlay (scrollable list at bottom) */}
          <div className="absolute bottom-0 left-0 right-0 max-h-[40%] overflow-y-auto bg-brand-surface/95 backdrop-blur-sm border-t border-brand-border">
            <div className="p-4 space-y-3">
              {sortedPairs.map((pair) => {
                const isExpanded = expandedPlanIds.has(pair.id);
                const isHighOverlap = pair.overlap_score >= 0.9;
                const strategy = pair.severity === 'critical' || pair.severity === 'high'
                  ? 'merge'
                  : 'differentiate';

                return (
                  <div
                    key={pair.id}
                    className={`rounded-lg border p-3 transition-colors cursor-pointer ${
                      selectedPairId === pair.id
                        ? 'border-brand-accent bg-brand-accent/5'
                        : 'border-brand-border/50 bg-brand-bg hover:border-brand-border-hover'
                    }`}
                    onClick={() => handleSelectEdge(pair.id)}
                  >
                    <div className="flex items-center gap-3">
                      <Badge color={SEVERITY_COLORS[pair.severity]}>{pair.severity}</Badge>
                      <span className="text-xs text-brand-text-muted">
                        {(pair.overlap_score * 100).toFixed(0)}% overlap
                      </span>
                      <span className="flex-1 text-xs text-brand-text truncate">
                        {pair.post_a.title} vs {pair.post_b.title}
                      </span>
                      <button
                        onClick={(e) => { e.stopPropagation(); togglePlan(pair.id); }}
                        className="flex items-center gap-1 text-xs text-brand-accent hover:text-brand-accent-hover font-medium shrink-0"
                      >
                        View Plan
                        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      </button>
                    </div>

                    {/* Expanded Plan */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-brand-border/50">
                        <div className="rounded-lg bg-brand-surface p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                              strategy === 'merge'
                                ? 'bg-orange-500/10 text-orange-400'
                                : 'bg-blue-500/10 text-blue-400'
                            }`}>
                              {strategy === 'merge' ? 'Merge Strategy' : 'Differentiation Strategy'}
                            </span>
                            {isHighOverlap && (
                              <span className="text-xs text-red-400 font-medium">Exact duplicate</span>
                            )}
                          </div>
                          {strategy === 'merge' ? (
                            <div className="space-y-2 text-sm text-brand-text">
                              <p>
                                Merge <span className="font-medium">&quot;{pair.post_b.title}&quot;</span> into{' '}
                                <span className="font-medium">&quot;{pair.post_a.title}&quot;</span>
                              </p>
                              <ul className="space-y-1 text-xs text-brand-text-muted list-disc list-inside">
                                <li>Combine unique content from both posts into the stronger one</li>
                                <li>Set up a 301 redirect from the weaker post</li>
                                <li>Update internal links pointing to the removed post</li>
                                <li>Monitor rankings for 2-4 weeks after merge</li>
                              </ul>
                            </div>
                          ) : (
                            <div className="space-y-2 text-sm text-brand-text">
                              <p>
                                Differentiate these posts by adjusting their target keywords and angles.
                              </p>
                              <ul className="space-y-1 text-xs text-brand-text-muted list-disc list-inside">
                                <li>Narrow the focus of &quot;{pair.post_b.title}&quot; to a subtopic</li>
                                <li>Add unique data, examples, or perspectives to each post</li>
                                <li>Adjust title tags and H1s to clearly distinguish topics</li>
                                <li>Interlink between the two posts with descriptive anchor text</li>
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Detail panel */}
      {selectedPair && (
        <PairDetailPanel
          pair={selectedPair}
          onClose={() => setSelectedPairId(null)}
        />
      )}
    </div>
  );
}
