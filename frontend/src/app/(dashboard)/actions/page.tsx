'use client';

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useRecommendations } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { SEVERITY_COLORS } from '@/lib/constants';
import {
  CheckCircle,
  Clock,
  Play,
  XCircle,
  Lightbulb,
  FileText,
  Target,
  Layers,
  Zap,
  TrendingUp,
  ArrowRight,
  Filter,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { mutate } from 'swr';
import type { Recommendation } from '@/lib/types';

type StatusFilter = 'all' | 'pending' | 'in_progress' | 'completed' | 'dismissed';

const STATUS_CONFIG = {
  pending: { label: 'To Do', icon: Clock, color: '#eab308', bgClass: 'bg-yellow-500/10' },
  in_progress: { label: 'In Progress', icon: Play, color: '#3b82f6', bgClass: 'bg-blue-500/10' },
  completed: { label: 'Done', icon: CheckCircle, color: '#22c55e', bgClass: 'bg-green-500/10' },
  dismissed: { label: 'Dismissed', icon: XCircle, color: '#6b7280', bgClass: 'bg-gray-500/10' },
};

const TYPE_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  expand: { label: 'Expand Content', icon: FileText, color: '#3b82f6' },
  optimize: { label: 'SEO Fix', icon: Target, color: '#8b5cf6' },
  merge: { label: 'Merge Posts', icon: Layers, color: '#f97316' },
  interlink: { label: 'Add Links', icon: Zap, color: '#22c55e' },
  update: { label: 'Update', icon: Clock, color: '#eab308' },
  growth: { label: 'Growth', icon: TrendingUp, color: '#06b6d4' },
};

function ActionCard({
  rec,
  siteId,
  token,
  expanded,
  onToggle,
}: {
  rec: Recommendation;
  siteId: string;
  token?: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const priorityColor = SEVERITY_COLORS[rec.priority as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low;
  const typeInfo = TYPE_CONFIG[rec.recommendation_type] || { label: rec.recommendation_type, icon: Lightbulb, color: '#6b7280' };
  const statusInfo = STATUS_CONFIG[rec.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.pending;

  const handleStatusUpdate = useCallback(
    async (status: string) => {
      try {
        await apiFetch(`/sites/${siteId}/intelligence/recommendations/${rec.id}/status`, {
          method: 'PATCH',
          body: JSON.stringify({ status }),
          token,
        });
        mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
      } catch {
        // Fail silently
      }
    },
    [siteId, rec.id, token]
  );

  return (
    <Card className="!p-0 overflow-hidden hover:border-brand-border-hover transition-colors">
      {/* Main Row */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        <div className="rounded-lg p-1.5 shrink-0" style={{ backgroundColor: `${typeInfo.color}15` }}>
          <typeInfo.icon size={16} style={{ color: typeInfo.color }} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge color={priorityColor}>{rec.priority}</Badge>
            <span className="text-xs text-brand-text-muted">{typeInfo.label}</span>
          </div>
          <p className="text-sm font-medium text-brand-text mt-1 line-clamp-1">{rec.title}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {rec.estimated_effort_hours && (
            <span className="text-xs text-brand-text-muted">{rec.estimated_effort_hours}h</span>
          )}
          <div className={`flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${statusInfo.bgClass}`} style={{ color: statusInfo.color }}>
            <statusInfo.icon size={12} />
            {statusInfo.label}
          </div>
          {expanded ? <ChevronDown size={14} className="text-brand-text-muted" /> : <ChevronRight size={14} className="text-brand-text-muted" />}
        </div>
      </button>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-brand-border/50 pt-3">
          <p className="text-sm text-brand-text-muted">{rec.summary}</p>

          {rec.specific_actions.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
              {rec.specific_actions.map((action, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-brand-text">
                  <span className="text-brand-accent mt-0.5 shrink-0">•</span>
                  <span>{action}</span>
                </div>
              ))}
            </div>
          )}

          {rec.ai_generated_content && Object.keys(rec.ai_generated_content).length > 0 && (() => {
            const ai = rec.ai_generated_content as Record<string, string>;
            return (
              <div className="mt-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                <p className="text-xs font-medium text-brand-text-muted mb-1">AI-Generated Content</p>
                {ai.meta_description && (
                  <p className="text-xs text-brand-text italic">
                    Meta: &quot;{ai.meta_description}&quot;
                  </p>
                )}
                {ai.suggested_title && (
                  <p className="text-xs text-brand-text mt-1">
                    Title: &quot;{ai.suggested_title}&quot;
                  </p>
                )}
                {ai.outline && (
                  <pre className="text-xs text-brand-text mt-1 whitespace-pre-wrap font-sans">
                    {ai.outline}
                  </pre>
                )}
              </div>
            );
          })()}

          {/* Status Actions */}
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            {rec.status === 'pending' && (
              <>
                <button
                  onClick={() => void handleStatusUpdate('in_progress')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                >
                  <Play size={12} /> Start Working
                </button>
                <button
                  onClick={() => void handleStatusUpdate('dismissed')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  <XCircle size={12} /> Dismiss
                </button>
              </>
            )}
            {rec.status === 'in_progress' && (
              <>
                <button
                  onClick={() => void handleStatusUpdate('completed')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
                >
                  <CheckCircle size={12} /> Mark Complete
                </button>
                <button
                  onClick={() => void handleStatusUpdate('pending')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  <Clock size={12} /> Move to To Do
                </button>
              </>
            )}
            {rec.status === 'completed' && (
              <Badge color="#22c55e">✓ Completed</Badge>
            )}
            {rec.status === 'dismissed' && (
              <button
                onClick={() => void handleStatusUpdate('pending')}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
              >
                <Clock size={12} /> Restore
              </button>
            )}

            <Link
              href={`/posts/${rec.post_id}`}
              className="ml-auto flex items-center gap-1 text-xs text-brand-accent hover:text-brand-accent-hover"
            >
              View Post <ArrowRight size={12} />
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function ActionQueuePage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const siteId = currentSite?.id ?? null;
  const { data: recsData, isLoading } = useRecommendations(siteId);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const recs = recsData?.recommendations || [];

  // Status counts
  const statusCounts = useMemo(() => {
    const counts = { all: recs.length, pending: 0, in_progress: 0, completed: 0, dismissed: 0 };
    for (const r of recs) {
      const s = r.status as keyof typeof counts;
      if (s in counts) counts[s]++;
    }
    return counts;
  }, [recs]);

  // Filtered recs
  const filtered = useMemo(() => {
    let result = recs;
    if (statusFilter !== 'all') {
      result = result.filter((r) => r.status === statusFilter);
    }
    if (typeFilter !== 'all') {
      result = result.filter((r) => r.recommendation_type === typeFilter);
    }
    // Sort: critical first, then by type
    return result.sort((a, b) => {
      const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      return (priorityOrder[a.priority as keyof typeof priorityOrder] || 3) - (priorityOrder[b.priority as keyof typeof priorityOrder] || 3);
    });
  }, [recs, statusFilter, typeFilter]);

  // Estimated total hours
  const totalHours = useMemo(
    () => filtered.reduce((sum, r) => sum + (r.estimated_effort_hours || 0), 0),
    [filtered]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const completionRate = recs.length > 0 ? (statusCounts.completed / recs.length) * 100 : 0;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">Action Queue</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          {recs.length} recommendations · Track progress and complete actions to improve your content
        </p>
      </div>

      {/* Progress Bar */}
      <Card className="!p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-brand-text">Overall Progress</span>
          <span className="text-sm text-brand-text-muted">
            {statusCounts.completed} of {recs.length} completed ({completionRate.toFixed(0)}%)
          </span>
        </div>
        <ProgressBar value={statusCounts.completed} max={recs.length || 1} />
        <div className="flex items-center gap-6 mt-3 text-xs text-brand-text-muted">
          <span>🕐 {statusCounts.pending} to do</span>
          <span>🔵 {statusCounts.in_progress} in progress</span>
          <span>✅ {statusCounts.completed} done</span>
          <span>⏭ {statusCounts.dismissed} dismissed</span>
          {totalHours > 0 && <span className="ml-auto">~{totalHours.toFixed(0)}h estimated for current view</span>}
        </div>
      </Card>

      {/* Status Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {(Object.entries(STATUS_CONFIG) as Array<[StatusFilter, typeof STATUS_CONFIG[keyof typeof STATUS_CONFIG]]>).map(
          ([key, config]) => (
            <button
              key={key}
              onClick={() => setStatusFilter(key)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                statusFilter === key
                  ? 'bg-brand-surface-hover text-brand-text ring-1 ring-brand-accent/30'
                  : 'text-brand-text-muted hover:bg-brand-surface-hover/50'
              }`}
            >
              <config.icon size={14} style={{ color: config.color }} />
              {config.label}
              <span className="text-xs rounded-full px-1.5 bg-brand-surface-hover/50">
                {statusCounts[key]}
              </span>
            </button>
          )
        )}
        <button
          onClick={() => setStatusFilter('all')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            statusFilter === 'all'
              ? 'bg-brand-surface-hover text-brand-text ring-1 ring-brand-accent/30'
              : 'text-brand-text-muted hover:bg-brand-surface-hover/50'
          }`}
        >
          All ({recs.length})
        </button>
      </div>

      {/* Type Filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter size={14} className="text-brand-text-muted" />
        <button
          onClick={() => setTypeFilter('all')}
          className={`px-3 py-1 text-xs rounded-full transition-colors ${
            typeFilter === 'all' ? 'bg-brand-accent/10 text-brand-accent' : 'bg-brand-surface-hover text-brand-text-muted hover:text-brand-text'
          }`}
        >
          All types
        </button>
        {Object.entries(TYPE_CONFIG).map(([type, config]) => {
          const count = (recsData?.by_type || {})[type] || 0;
          if (count === 0) return null;
          return (
            <button
              key={type}
              onClick={() => setTypeFilter(typeFilter === type ? 'all' : type)}
              className={`flex items-center gap-1 px-3 py-1 text-xs rounded-full transition-colors ${
                typeFilter === type ? 'bg-brand-accent/10 text-brand-accent' : 'bg-brand-surface-hover text-brand-text-muted hover:text-brand-text'
              }`}
            >
              <config.icon size={10} />
              {config.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Recommendations List */}
      {filtered.length > 0 ? (
        <div className="space-y-3">
          {filtered.map((rec) => (
            <ActionCard
              key={rec.id}
              rec={rec}
              siteId={siteId!}
              token={session?.access_token}
              expanded={expandedId === rec.id}
              onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <div className="text-center py-12">
            <CheckCircle size={32} className="text-brand-text-muted mx-auto mb-2" />
            <p className="text-sm text-brand-text-muted">
              {statusFilter !== 'all'
                ? `No ${STATUS_CONFIG[statusFilter as keyof typeof STATUS_CONFIG]?.label.toLowerCase() || statusFilter} recommendations`
                : 'No recommendations yet. Run the intelligence pipeline first.'}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
