'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ECOSYSTEM_COLORS, type EcosystemState } from '@/lib/constants';
import type { ClusterSummary } from '@/lib/types';

interface ClusterListProps {
  clusters: ClusterSummary[];
}

type SortKey = 'post_count' | 'ecosystem_state';

export function ClusterList({ clusters }: ClusterListProps) {
  const [sortBy, setSortBy] = useState<SortKey>('post_count');
  const router = useRouter();

  const sorted = [...clusters].sort((a, b) => {
    if (sortBy === 'post_count') return b.post_count - a.post_count;
    return (a.ecosystem_state ?? '').localeCompare(b.ecosystem_state ?? '');
  });

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-medium text-brand-text-muted">Clusters</p>
        <div className="flex gap-1">
          {([
            { key: 'post_count' as const, label: 'Posts' },
            { key: 'ecosystem_state' as const, label: 'State' },
          ]).map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSortBy(opt.key)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                sortBy === opt.key
                  ? 'bg-brand-accent/10 text-brand-accent'
                  : 'text-brand-text-muted hover:text-brand-text'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-brand-text-muted text-center py-8">
          No clusters yet. Run ecosystem analysis first.
        </p>
      ) : (
        <div className="space-y-1">
          {sorted.map((cluster) => {
            const state = cluster.ecosystem_state as EcosystemState | null;
            const ecoColors = state ? ECOSYSTEM_COLORS[state] : null;

            return (
              <button
                key={cluster.id}
                onClick={() => router.push(`/landscape?cluster=${cluster.id}`)}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-brand-surface-hover"
              >
                <Badge color={ecoColors?.bg ?? '#6b7280'}>
                  {ecoColors?.label ?? cluster.ecosystem_state ?? 'Unknown'}
                </Badge>
                <span className="flex-1 text-sm font-medium text-brand-text truncate">
                  {cluster.label ?? 'Unlabeled'}
                </span>
                <span className="text-xs text-brand-text-muted">
                  {cluster.post_count} posts
                </span>
              </button>
            );
          })}
        </div>
      )}
    </Card>
  );
}
