'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
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
  X,
  ArrowDownUp,
  Undo2,
  Copy,
  Check,
} from 'lucide-react';
import { apiFetch, apiUrl } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { mutate } from 'swr';
import type { Recommendation } from '@/lib/types';

function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* fallback */ }
  };
  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-brand-border/30 text-brand-text-muted hover:text-brand-text hover:bg-brand-border/50 transition-colors ml-2 flex-shrink-0"
      title={`Copy ${label ?? ''}`}
    >
      {copied ? <Check size={10} className="text-green-500" /> : <Copy size={10} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function PushToWPBtn({
  siteId,
  postId,
  title,
  metaDescription,
  token,
}: {
  siteId: string;
  postId: string;
  title?: string;
  metaDescription?: string;
  token?: string | null;
}) {
  const [pushing, setPushing] = useState(false);
  const [result, setResult] = useState<'success' | 'error' | null>(null);

  const handlePush = async () => {
    if (!siteId || !token) return;
    setPushing(true);
    try {
      const res = await apiFetch(`/sites/${siteId}/actions/push-meta`, {
        method: 'POST',
        body: JSON.stringify({ post_id: postId, title, meta_description: metaDescription }),
        token: token ?? undefined,
      });
      const data = res as { success?: boolean };
      setResult(data.success ? 'success' : 'error');
    } catch {
      setResult('error');
    }
    setPushing(false);
    setTimeout(() => setResult(null), 3000);
  };

  return (
    <button
      onClick={() => void handlePush()}
      disabled={pushing || result === 'success'}
      className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors disabled:opacity-50"
    >
      {result === 'success' ? (
        <><Check size={12} /> Pushed to WP</>
      ) : result === 'error' ? (
        <><XCircle size={12} /> Failed</>
      ) : pushing ? (
        <>Pushing...</>
      ) : (
        <>Push to WordPress</>
      )}
    </button>
  );
}

type StatusFilter = 'all' | 'pending' | 'in_progress' | 'completed' | 'dismissed';
type SortOption = 'impact' | 'priority' | 'effort' | 'date';

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'impact', label: 'Impact' },
  { value: 'priority', label: 'Priority' },
  { value: 'effort', label: 'Effort' },
  { value: 'date', label: 'Date created' },
];

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
  differentiate: { label: 'Differentiate', icon: Layers, color: '#ec4899' },
  interlink: { label: 'Add Links', icon: Zap, color: '#22c55e' },
  redirect: { label: 'Redirect', icon: Target, color: '#ef4444' },
  update: { label: 'Update', icon: Clock, color: '#eab308' },
  growth: { label: 'Growth', icon: TrendingUp, color: '#06b6d4' },
};

// Undo toast state
interface UndoAction {
  recId: string;
  previousStatus: string;
  actionLabel: string;
  timeoutId: ReturnType<typeof setTimeout>;
}

function ActionCard({
  rec,
  siteId,
  token,
  expanded,
  onToggle,
  onStatusUpdate,
  cmsType,
}: {
  rec: Recommendation;
  siteId: string;
  token?: string;
  expanded: boolean;
  onToggle: () => void;
  onStatusUpdate: (recId: string, newStatus: string, previousStatus: string, label: string) => void;
  cmsType?: string;
}) {
  const currentSite = { id: siteId, cms_type: cmsType };
  const priorityColor = SEVERITY_COLORS[rec.priority as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low;
  const typeInfo = TYPE_CONFIG[rec.recommendation_type] || { label: rec.recommendation_type, icon: Lightbulb, color: '#6b7280' };
  const statusInfo = STATUS_CONFIG[rec.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.pending;

  const [enriching, setEnriching] = useState(false);
  const [enriched, setEnriched] = useState<Record<string, unknown> | null>(null);

  const handleEnrich = useCallback(async () => {
    setEnriching(true);
    try {
      const result = await apiFetch<{ enriched?: boolean; already_enriched?: boolean; guidance?: Record<string, unknown> }>(
        `/sites/${siteId}/intelligence/recommendations/${rec.id}/enrich`,
        { method: 'POST', token },
      );
      if (result.guidance) setEnriched(result.guidance);
      mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
    } catch {
      // Fail silently
    } finally {
      setEnriching(false);
    }
  }, [siteId, rec.id, token]);

  const handleStatusChange = useCallback(
    (newStatus: string, label: string) => {
      onStatusUpdate(rec.id, newStatus, rec.status, label);
    },
    [rec.id, rec.status, onStatusUpdate]
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
          {/* Estimated Impact */}
          {rec.estimated_impact && (
            <p className="text-xs text-brand-accent mt-0.5">
              ~{rec.estimated_impact}
            </p>
          )}
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

          {/* AI Enriched Guidance */}
          {(() => {
            const actionsRaw = rec.specific_actions as unknown;
            if (actionsRaw && typeof actionsRaw === 'object' && !Array.isArray(actionsRaw)) {
              const enriched = actionsRaw as { ai_enriched?: boolean; guidance?: Record<string, unknown>; original_actions?: string[] };
              if (enriched.ai_enriched && enriched.guidance) {
                const g = enriched.guidance as Record<string, unknown>;
                return (
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center gap-1.5">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 text-xs font-medium">
                        AI Analysis
                      </span>
                    </div>
                    {Object.entries(g).map(([key, val]) => {
                      if (!val) return null;
                      const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                      if (Array.isArray(val)) {
                        return (
                          <div key={key}>
                            <p className="text-xs font-medium text-brand-text-muted mb-1">{label}</p>
                            {(val as string[]).map((item, i) => (
                              <div key={i} className="flex items-start gap-2 text-sm text-brand-text mb-1">
                                <span className="text-purple-400 mt-0.5 shrink-0">&rsaquo;</span>
                                <span>{item}</span>
                              </div>
                            ))}
                          </div>
                        );
                      }
                      return (
                        <div key={key}>
                          <p className="text-xs font-medium text-brand-text-muted">{label}</p>
                          <p className="text-sm text-brand-text mt-0.5">{String(val)}</p>
                        </div>
                      );
                    })}
                    {enriched.original_actions && enriched.original_actions.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-brand-border/30">
                        <p className="text-xs text-brand-text-muted mb-1">Quick actions</p>
                        {enriched.original_actions.map((action, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-brand-text-muted">
                            <span className="text-brand-accent mt-0.5 shrink-0">&bull;</span>
                            <span>{action}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }
            }

            // Fallback: plain array
            const actions = Array.isArray(actionsRaw) ? actionsRaw as string[] : [];
            return actions.length > 0 ? (
              <div className="mt-3 space-y-1.5">
                <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
                {actions.map((action, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-brand-text">
                    <span className="text-brand-accent mt-0.5 shrink-0">&bull;</span>
                    <span>{action}</span>
                  </div>
                ))}
              </div>
            ) : null;
          })()}

          {rec.ai_generated_content && Object.keys(rec.ai_generated_content).length > 0 && (() => {
            const ai = rec.ai_generated_content as Record<string, string>;
            return (
              <div className="mt-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                <p className="text-xs font-medium text-brand-text-muted mb-1">AI-Generated Content</p>
                {ai.meta_description && (
                  <div className="flex items-start justify-between">
                    <p className="text-xs text-brand-text italic">
                      Meta: &quot;{ai.meta_description}&quot;
                    </p>
                    <CopyBtn text={ai.meta_description} label="meta description" />
                  </div>
                )}
                {ai.suggested_title && (
                  <div className="flex items-start justify-between mt-1">
                    <p className="text-xs text-brand-text">
                      Title: &quot;{ai.suggested_title}&quot;
                    </p>
                    <CopyBtn text={ai.suggested_title} label="title" />
                  </div>
                )}
                {ai.outline && (
                  <div className="flex items-start justify-between mt-1">
                    <pre className="text-xs text-brand-text whitespace-pre-wrap font-sans flex-1">
                      {ai.outline}
                    </pre>
                    <CopyBtn text={ai.outline} label="outline" />
                  </div>
                )}
              </div>
            );
          })()}

          {/* ── Action Buttons from RAG data ── */}
          {(() => {
            const ai = (rec.ai_generated_content ?? {}) as Record<string, string>;
            const isWordPress = currentSite?.cms_type === 'wordpress';
            const hasMeta = ai.meta_description || ai.suggested_title || ai.new_title || ai.suggested_new_title;
            const clusterId = ai.cluster_id as string | undefined;
            const isMerge = ['merge', 'redirect', 'consolidate'].includes(rec.recommendation_type);
            const linkTargets = ai.link_targets as unknown as Array<{ title: string; url: string; similarity: number; suggested_anchor: string }> | undefined;

            if (!hasMeta && !clusterId && !linkTargets) return null;

            return (
              <div className="mt-3 flex flex-wrap gap-2">
                {/* Push to WordPress — uses /push-meta endpoint */}
                {isWordPress && hasMeta && (
                  <PushToWPBtn
                    siteId={currentSite?.id ?? ''}
                    postId={rec.post_id}
                    title={(ai.suggested_title || ai.new_title || ai.suggested_new_title) as string | undefined}
                    metaDescription={ai.meta_description as string | undefined}
                    token={token}
                  />
                )}
                {/* Deep link to consolidation flow */}
                {isMerge && clusterId && (
                  <Link
                    href={`/consolidation/${clusterId}`}
                    className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#f97316]/10 text-[#f97316] hover:bg-[#f97316]/20 transition-colors"
                  >
                    <Layers size={12} /> Start Consolidation →
                  </Link>
                )}
                {/* Redirect map download */}
                {isMerge && clusterId && (
                  <a
                    href={apiUrl(`/sites/${currentSite?.id}/intelligence/consolidation/${clusterId}/redirect-map?format=htaccess`)}
                    download
                    className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#64748b]/10 text-[#94a3b8] hover:bg-[#64748b]/20 transition-colors"
                  >
                    <FileText size={12} /> Download Redirects
                  </a>
                )}
              </div>
            );
          })()}

          {/* ── Interlink targets from RAG (specific posts + anchor text) ── */}
          {(() => {
            const ai = (rec.ai_generated_content ?? {}) as Record<string, string>;
            const linkTargets = ai.link_targets as unknown as Array<{ title: string; url: string; similarity: number; suggested_anchor: string }> | undefined;
            if (!linkTargets || linkTargets.length === 0) return null;

            return (
              <div className="mt-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                <p className="text-xs font-medium text-brand-text-muted mb-2">Link from these posts:</p>
                <div className="space-y-1.5">
                  {linkTargets.map((target, i) => (
                    <div key={i} className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-[10px] text-green-500 font-mono flex-shrink-0">{Math.round(target.similarity * 100)}%</span>
                        <a href={target.url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-text truncate hover:text-blue-400">
                          {target.title}
                        </a>
                      </div>
                      <CopyBtn text={target.suggested_anchor} label="anchor text" />
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* On-demand AI Enrichment */}
          {!enriched && (() => {
            const actionsRaw = rec.specific_actions as unknown;
            const isEnriched = actionsRaw && typeof actionsRaw === 'object' && !Array.isArray(actionsRaw) && (actionsRaw as Record<string, unknown>).ai_enriched;
            return !isEnriched ? (
              <div className="mt-3">
                <button
                  onClick={() => void handleEnrich()}
                  disabled={enriching}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 text-purple-400 text-xs font-medium hover:bg-purple-500/20 transition-colors disabled:opacity-50"
                >
                  {enriching ? (
                    <svg className="animate-spin w-3 h-3" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                  ) : <span>*</span>}
                  {enriching ? 'Getting AI analysis...' : 'Get AI Analysis'}
                </button>
              </div>
            ) : null;
          })()}

          {enriched && (
            <div className="mt-3 rounded-lg bg-purple-500/5 border border-purple-500/20 p-3 space-y-2">
              <p className="text-xs font-medium text-purple-400">AI Analysis (just generated)</p>
              {Object.entries(enriched).map(([key, val]) => {
                if (!val) return null;
                const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                if (Array.isArray(val)) {
                  return (
                    <div key={key}>
                      <p className="text-xs font-medium text-brand-text-muted mb-1">{label}</p>
                      {(val as string[]).map((item, i) => (
                        <div key={i} className="flex gap-2 text-xs text-brand-text mb-0.5">
                          <span className="text-purple-400 shrink-0">&rsaquo;</span><span>{item}</span>
                        </div>
                      ))}
                    </div>
                  );
                }
                return (
                  <div key={key}>
                    <p className="text-xs font-medium text-brand-text-muted">{label}</p>
                    <p className="text-xs text-brand-text">{String(val)}</p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Status Actions */}
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            {rec.status === 'pending' && (
              <>
                <button
                  onClick={() => handleStatusChange('in_progress', 'Started')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                >
                  <Play size={12} /> Start Working
                </button>
                <button
                  onClick={() => handleStatusChange('dismissed', 'Dismissed')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  <XCircle size={12} /> Dismiss
                </button>
              </>
            )}
            {rec.status === 'in_progress' && (
              <>
                <button
                  onClick={() => handleStatusChange('completed', 'Marked complete')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
                >
                  <CheckCircle size={12} /> Mark Complete
                </button>
                <button
                  onClick={() => handleStatusChange('pending', 'Moved to To Do')}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  <Clock size={12} /> Move to To Do
                </button>
              </>
            )}
            {rec.status === 'completed' && (
              <Badge color="#22c55e">Completed</Badge>
            )}
            {rec.status === 'dismissed' && (
              <button
                onClick={() => handleStatusChange('pending', 'Restored')}
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
  const [sortBy, setSortBy] = useState<SortOption>('impact');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [undoAction, setUndoAction] = useState<UndoAction | null>(null);
  const undoTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const hasActiveFilters = statusFilter !== 'pending' || typeFilter !== 'all';

  const clearAllFilters = useCallback(() => {
    setStatusFilter('pending');
    setTypeFilter('all');
  }, []);

  // Handle status update with undo support
  const handleStatusUpdate = useCallback(
    async (recId: string, newStatus: string, previousStatus: string, label: string) => {
      // Clear any existing undo timeout
      if (undoTimeoutRef.current) {
        clearTimeout(undoTimeoutRef.current);
      }

      // Perform the status update
      try {
        await apiFetch(`/sites/${siteId}/intelligence/recommendations/${recId}/status`, {
          method: 'PATCH',
          body: JSON.stringify({ status: newStatus }),
          token: session?.access_token,
        });
        mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
      } catch {
        return; // Don't show undo if the action failed
      }

      // Show undo toast for completed/dismissed actions
      if (newStatus === 'completed' || newStatus === 'dismissed') {
        const timeoutId = setTimeout(() => {
          setUndoAction(null);
        }, 5000);

        undoTimeoutRef.current = timeoutId;
        setUndoAction({ recId, previousStatus, actionLabel: label, timeoutId });
      }
    },
    [siteId, session?.access_token]
  );

  // Handle undo
  const handleUndo = useCallback(async () => {
    if (!undoAction) return;
    clearTimeout(undoAction.timeoutId);
    if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current);

    try {
      await apiFetch(`/sites/${siteId}/intelligence/recommendations/${undoAction.recId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: undoAction.previousStatus }),
        token: session?.access_token,
      });
      mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
    } catch {
      // Fail silently
    }

    setUndoAction(null);
  }, [undoAction, siteId, session?.access_token]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current);
    };
  }, []);

  // Filtered and sorted recs
  const filtered = useMemo(() => {
    let result = recs;
    if (statusFilter !== 'all') {
      result = result.filter((r) => r.status === statusFilter);
    }
    if (typeFilter !== 'all') {
      result = result.filter((r) => r.recommendation_type === typeFilter);
    }

    // Sort
    const priorityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    return [...result].sort((a, b) => {
      switch (sortBy) {
        case 'impact': {
          // Sort by estimated_impact (parse numeric value if possible), then priority
          const aImpact = parseFloat(a.estimated_impact || '0') || 0;
          const bImpact = parseFloat(b.estimated_impact || '0') || 0;
          if (bImpact !== aImpact) return bImpact - aImpact;
          return (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
        }
        case 'priority':
          return (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
        case 'effort': {
          const aEffort = a.estimated_effort_hours || 999;
          const bEffort = b.estimated_effort_hours || 999;
          return aEffort - bEffort;
        }
        case 'date':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        default:
          return 0;
      }
    });
  }, [recs, statusFilter, typeFilter, sortBy]);

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
          {recs.length} recommendations -- Track progress and complete actions to improve your content
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
          <span>{statusCounts.pending} to do</span>
          <span>{statusCounts.in_progress} in progress</span>
          <span>{statusCounts.completed} done</span>
          <span>{statusCounts.dismissed} dismissed</span>
          {totalHours > 0 && (
            <span className="ml-auto">
              {totalHours > 200
                ? `200+ hrs estimated -- prioritize top items first`
                : `~${totalHours.toFixed(0)}h estimated for current view`}
            </span>
          )}
        </div>
      </Card>

      {/* Status Tabs + Sort */}
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

        {/* Sort Dropdown */}
        <div className="flex items-center gap-2 ml-auto shrink-0">
          <ArrowDownUp size={12} className="text-brand-text-muted" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="rounded-lg border border-brand-border bg-brand-bg px-2 py-1.5 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>Sort: {opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Type Filter + Clear All */}
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

        {/* Clear All Filters */}
        {hasActiveFilters && (
          <button
            onClick={clearAllFilters}
            className="ml-auto flex items-center gap-1 text-xs text-brand-text-muted hover:text-brand-text transition-colors"
          >
            <X size={12} />
            Clear all filters
          </button>
        )}
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
              cmsType={currentSite?.cms_type}
              expanded={expandedId === rec.id}
              onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
              onStatusUpdate={handleStatusUpdate}
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

      {/* Undo Toast */}
      {undoAction && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-200">
          <div className="flex items-center gap-3 rounded-lg bg-brand-surface border border-brand-border shadow-lg px-4 py-3">
            <span className="text-sm text-brand-text">
              {undoAction.actionLabel}
            </span>
            <button
              onClick={() => void handleUndo()}
              className="flex items-center gap-1.5 text-sm font-medium text-brand-accent hover:text-brand-accent-hover transition-colors"
            >
              <Undo2 size={14} />
              Undo
            </button>
            <button
              onClick={() => { clearTimeout(undoAction.timeoutId); setUndoAction(null); }}
              className="text-brand-text-muted hover:text-brand-text transition-colors ml-1"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
