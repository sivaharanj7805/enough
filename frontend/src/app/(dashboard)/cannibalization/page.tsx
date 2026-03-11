'use client';

import { useState, useMemo, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useCannibalizationPairs, useClusters } from '@/lib/hooks/useApi';
import { NetworkGraph } from '@/components/cannibalization/NetworkGraph';
import { PairDetailPanel } from '@/components/cannibalization/PairDetailPanel';
import { Spinner } from '@/components/ui/Spinner';
import type { Severity } from '@/lib/constants';
import type { PostHealth } from '@/lib/types';

const ALL_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

export default function CannibalizationPage() {
  const { currentSite } = useSite();
  const { data: pairs, isLoading: pairsLoading, error: pairsError } = useCannibalizationPairs(currentSite?.id ?? null);
  const { data: clusters } = useClusters(currentSite?.id ?? null);

  const [severityFilter, setSeverityFilter] = useState<Severity[]>(ALL_SEVERITIES);
  const [clusterFilter, setClusterFilter] = useState<string | null>(null);
  const [selectedPairId, setSelectedPairId] = useState<string | null>(null);
  const [, setSelectedNodeId] = useState<string | null>(null);

  // Derive posts from pairs
  const posts: PostHealth[] = useMemo(() => {
    if (!pairs) return [];
    const map = new Map<string, PostHealth>();
    pairs.forEach((p) => {
      if (!map.has(p.post_a_id)) {
        map.set(p.post_a_id, {
          post_id: p.post_a_id,
          title: p.post_a_title,
          url: p.post_a_url,
          role: 'competitor',
          health_score: 0,
          traffic_90d: 0,
          trend: 'stable',
          cluster_id: p.cluster_id,
          keyword_count: 0,
        });
      }
      if (!map.has(p.post_b_id)) {
        map.set(p.post_b_id, {
          post_id: p.post_b_id,
          title: p.post_b_title,
          url: p.post_b_url,
          role: 'competitor',
          health_score: 0,
          traffic_90d: 0,
          trend: 'stable',
          cluster_id: p.cluster_id,
          keyword_count: 0,
        });
      }
    });
    return Array.from(map.values());
  }, [pairs]);

  const selectedPair = pairs?.find((p) => p.id === selectedPairId) ?? null;

  const toggleSeverity = useCallback((s: Severity) => {
    setSeverityFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
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
          <p className="text-2xl mb-2">🕸️</p>
          <p className="text-lg font-medium text-brand-text">No Cannibalization Detected</p>
          <p className="text-sm text-brand-text-muted mt-1">
            Your content ecosystem is clean — no overlapping posts found.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full -m-6">
      <div className="flex-1 flex flex-col">
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
        <div className="flex-1">
          <NetworkGraph
            posts={posts}
            pairs={pairs}
            onSelectNode={handleSelectNode}
            onSelectEdge={handleSelectEdge}
            severityFilter={severityFilter}
            clusterFilter={clusterFilter}
          />
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
