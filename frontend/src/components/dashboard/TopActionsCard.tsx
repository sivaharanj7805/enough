'use client';

import { useRecommendations } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import Link from 'next/link';
import { ArrowRight, Zap } from 'lucide-react';

const PRIORITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#64748b',
};

const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

interface TopActionsCardProps {
  siteId: string;
}

export function TopActionsCard({ siteId }: TopActionsCardProps) {
  const { data, isLoading } = useRecommendations(siteId, { status: 'pending', priority: 'high' });

  const topRecs = data?.recommendations?.slice(0, 3) ?? [];
  const totalCount = data?.total ?? 0;

  if (isLoading) {
    return (
      <Card>
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-brand-surface-hover rounded w-1/3" />
          <div className="h-12 bg-brand-surface-hover rounded" />
          <div className="h-12 bg-brand-surface-hover rounded" />
          <div className="h-12 bg-brand-surface-hover rounded" />
        </div>
      </Card>
    );
  }

  if (topRecs.length === 0) {
    return (
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Zap size={16} className="text-brand-accent" />
          <p className="text-sm font-semibold text-brand-text">Top Priorities</p>
        </div>
        <p className="text-sm text-brand-text-muted">No pending high-priority actions. Your content is in good shape.</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-brand-accent" />
          <p className="text-sm font-semibold text-brand-text">Top Priorities</p>
        </div>
        <span className="text-xs text-brand-text-muted">{totalCount} total actions</span>
      </div>

      <div className="space-y-2">
        {topRecs.map((rec) => (
          <div
            key={rec.id}
            className="flex items-start gap-3 p-3 rounded-lg bg-brand-bg border border-brand-border/50 hover:border-brand-border transition-colors"
          >
            <div
              className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: PRIORITY_COLORS[rec.priority] ?? '#64748b' }}
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-brand-text truncate">{rec.title}</p>
              <p className="text-xs text-brand-text-muted mt-0.5">
                {PRIORITY_LABELS[rec.priority] ?? rec.priority} ·{' '}
                {rec.estimated_effort_hours != null
                  ? `${rec.estimated_effort_hours}h effort`
                  : 'Quick win'}
              </p>
            </div>
          </div>
        ))}
      </div>

      <Link
        href="/actions"
        className="mt-4 flex items-center justify-center gap-1.5 text-xs text-brand-accent hover:text-brand-accent/80 transition-colors font-medium"
      >
        View all {totalCount} actions <ArrowRight size={12} />
      </Link>
    </Card>
  );
}
