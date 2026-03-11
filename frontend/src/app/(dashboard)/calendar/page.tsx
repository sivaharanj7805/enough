'use client';

import { useState, useCallback } from 'react';
import {
  Calendar as CalendarIcon,
  RefreshCw,
  Download,
  Pause,
  Check,
  RotateCcw,
  TrendingUp,
  Tag,
} from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useCalendar } from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type { CalendarRecommendation, TaskTriggerResponse } from '@/lib/types';

const TYPE_CONFIG: Record<
  string,
  {
    icon: typeof Pause;
    color: string;
    bgColor: string;
    borderColor: string;
    label: string;
    emoji: string;
  }
> = {
  pause: {
    icon: Pause,
    color: '#ef4444',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    label: "Don't Publish",
    emoji: '🔴',
  },
  maintain: {
    icon: Check,
    color: '#22c55e',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
    label: 'Maintain',
    emoji: '🟢',
  },
  revive: {
    icon: RotateCcw,
    color: '#eab308',
    bgColor: 'bg-yellow-500/10',
    borderColor: 'border-yellow-500/30',
    label: 'Revive',
    emoji: '🟡',
  },
  grow: {
    icon: TrendingUp,
    color: '#3b82f6',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    label: 'Grow',
    emoji: '🔵',
  },
};

function RecommendationCard({ rec }: { rec: CalendarRecommendation }) {
  const config = TYPE_CONFIG[rec.recommendation_type] ?? TYPE_CONFIG.maintain;
  const Icon = config.icon;

  return (
    <Card className={`${config.bgColor} border ${config.borderColor}`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0" style={{ color: config.color }}>
          <Icon size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-brand-text">
              {rec.cluster_label ?? 'Unlabeled Cluster'}
            </span>
            {rec.ecosystem_state && (
              <Badge color={config.color}>{rec.ecosystem_state}</Badge>
            )}
          </div>
          <p className="text-sm text-brand-text-muted leading-relaxed">
            {rec.recommendation_text}
          </p>
          {rec.pause_months != null && (
            <p className="mt-2 text-xs font-medium" style={{ color: config.color }}>
              ⏸ Pause for {rec.pause_months} month{rec.pause_months !== 1 ? 's' : ''}
            </p>
          )}
          {rec.suggested_keywords && rec.suggested_keywords.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Tag size={12} className="text-brand-text-muted mt-0.5" />
              {rec.suggested_keywords.map((kw) => (
                <span
                  key={kw}
                  className="rounded-full bg-brand-surface px-2.5 py-0.5 text-xs text-brand-text border border-brand-border"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

export default function CalendarPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const { data: calendar, isLoading, error, mutate } = useCalendar(
    currentSite?.id ?? null
  );
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    if (!currentSite || !session?.access_token) return;
    setRefreshing(true);
    try {
      await apiFetch<TaskTriggerResponse>(
        `/sites/${currentSite.id}/intelligence/calendar/generate`,
        { method: 'POST', token: session.access_token }
      );
      // Wait a bit then refresh
      setTimeout(() => {
        void mutate();
        setRefreshing(false);
      }, 3000);
    } catch {
      setRefreshing(false);
    }
  }, [currentSite, session, mutate]);

  const handleExportCsv = useCallback(() => {
    if (!calendar) return;
    const header = 'cluster_label,ecosystem_state,type,recommendation,keywords,pause_months';
    const rows = calendar.recommendations.map((r) => {
      const keywords = r.suggested_keywords?.join('; ') ?? '';
      return `"${r.cluster_label ?? ''}","${r.ecosystem_state ?? ''}","${r.recommendation_type}","${r.recommendation_text.replace(/"/g, '""')}","${keywords}","${r.pause_months ?? ''}"`;
    });
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'content-calendar.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, [calendar]);

  if (!currentSite) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-brand-text-muted">Select a site to view calendar</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load calendar</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            onClick={handleRefresh}
          >
            Generate Recommendations
          </Button>
        </div>
      </div>
    );
  }

  const recommendations = calendar?.recommendations ?? [];
  const grouped: Record<string, CalendarRecommendation[]> = {
    pause: [],
    revive: [],
    grow: [],
    maintain: [],
  };
  for (const rec of recommendations) {
    (grouped[rec.recommendation_type] ?? []).push(rec);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CalendarIcon size={24} className="text-brand-accent" />
          <div>
            <h1 className="text-xl font-bold text-brand-text">Content Calendar</h1>
            <p className="text-sm text-brand-text-muted">
              Data-backed publishing cadence recommendations
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportCsv}
            disabled={recommendations.length === 0}
          >
            <Download size={14} />
            Export CSV
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Generating...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Site-wide summary */}
      {calendar?.summary && (
        <Card>
          <h3 className="text-xs font-semibold text-brand-text-muted uppercase tracking-wide mb-2">
            Quarterly Summary
          </h3>
          <pre className="text-sm text-brand-text whitespace-pre-wrap font-sans leading-relaxed">
            {calendar.summary}
          </pre>
        </Card>
      )}

      {/* Empty state */}
      {recommendations.length === 0 && (
        <Card>
          <div className="text-center py-8">
            <CalendarIcon size={40} className="mx-auto text-brand-text-muted mb-3" />
            <p className="text-brand-text-muted">No recommendations yet</p>
            <p className="text-xs text-brand-text-muted mt-1">
              Click &quot;Refresh&quot; to generate publishing recommendations
            </p>
          </div>
        </Card>
      )}

      {/* Grouped recommendations */}
      {(['pause', 'revive', 'grow', 'maintain'] as const).map((type) => {
        const recs = grouped[type];
        if (!recs || recs.length === 0) return null;
        const config = TYPE_CONFIG[type];
        return (
          <div key={type}>
            <h2 className="text-sm font-semibold text-brand-text mb-3 flex items-center gap-2">
              <span>{config.emoji}</span>
              <span>{config.label}</span>
              <span className="text-brand-text-muted font-normal">({recs.length})</span>
            </h2>
            <div className="space-y-3">
              {recs.map((rec) => (
                <RecommendationCard key={rec.cluster_id} rec={rec} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
