'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useSite } from '@/lib/hooks/useSite';
import { useRecommendations } from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch, apiUrl } from '@/lib/api';
import { mutate } from 'swr';
import { empty, recType as REC_TYPE_LABELS, EMPTY_STATES, BUTTON_LABELS } from '@/lib/copy';
import type { Recommendation } from '@/lib/types';
import {
  CheckCircle, Clock, Play, XCircle, Lightbulb, FileText, Target,
  Layers, Zap, TrendingUp, ChevronDown, ChevronRight, X, Copy, Check,
  ArrowRight, Undo2, Search,
} from 'lucide-react';

// ── Constants ────────────────────────────────────────

type StatusKey = 'pending' | 'in_progress' | 'completed' | 'dismissed';
type SortOption = 'priority' | 'impact' | 'effort' | 'date';
const RECS_PER_PAGE = 20;
const PRIORITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const PRIORITY_COLORS: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#6b7280' };

const STATUS_TABS: Array<{ key: StatusKey | 'all'; label: string; icon: React.ElementType; color: string }> = [
  { key: 'all', label: 'All', icon: Lightbulb, color: '#a78bfa' },
  { key: 'pending', label: 'To Do', icon: Clock, color: '#eab308' },
  { key: 'in_progress', label: 'In Progress', icon: Play, color: '#3b82f6' },
  { key: 'completed', label: 'Done', icon: CheckCircle, color: '#22c55e' },
  { key: 'dismissed', label: 'Dismissed', icon: XCircle, color: '#6b7280' },
];

const TI: Record<string, { icon: React.ElementType; color: string }> = {
  expand: { icon: FileText, color: '#3b82f6' }, optimize: { icon: Target, color: '#8b5cf6' },
  merge: { icon: Layers, color: '#f97316' }, differentiate: { icon: Layers, color: '#ec4899' },
  interlink: { icon: Zap, color: '#22c55e' }, redirect: { icon: Target, color: '#ef4444' },
  update: { icon: Clock, color: '#eab308' }, growth: { icon: TrendingUp, color: '#06b6d4' },
  seo_fix: { icon: Target, color: '#8b5cf6' }, add_schema: { icon: FileText, color: '#06b6d4' },
  improve_ai_citability: { icon: Zap, color: '#a78bfa' }, strengthen_eeat: { icon: TrendingUp, color: '#22c55e' },
  improve_ai_structure: { icon: Layers, color: '#3b82f6' }, rewrite: { icon: FileText, color: '#ef4444' },
};

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'priority', label: 'Priority' },
  { value: 'impact', label: 'Impact' },
  { value: 'effort', label: 'Effort (low first)' },
  { value: 'date', label: 'Newest' },
];

// ── Small helpers ────────────────────────────────────

function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      aria-label={`Copy ${label ?? 'text'}`}
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* noop */ }
      }}
      className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-brand-border/30 text-brand-text-muted hover:text-brand-text hover:bg-brand-border/50 transition-colors shrink-0"
    >
      {copied ? <Check size={10} className="text-green-500" /> : <Copy size={10} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function PushToWPBtn({ siteId, postId, title, metaDescription, token }: {
  siteId: string; postId: string; title?: string; metaDescription?: string; token?: string | null;
}) {
  const [state, setState] = useState<'idle' | 'pushing' | 'success' | 'error'>('idle');
  const push = async () => {
    if (!token) return;
    setState('pushing');
    try {
      const res = await apiFetch(`/sites/${siteId}/actions/push-meta`, {
        method: 'POST', body: JSON.stringify({ post_id: postId, title, meta_description: metaDescription }), token,
      }) as { success?: boolean };
      setState(res.success ? 'success' : 'error');
    } catch { setState('error'); }
    setTimeout(() => setState('idle'), 3000);
  };
  return (
    <button onClick={() => void push()} disabled={state !== 'idle'} aria-label="Push to WordPress"
      className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors disabled:opacity-50">
      {state === 'success' ? <><Check size={12} /> Pushed</> : state === 'error' ? <><XCircle size={12} /> Failed</> : state === 'pushing' ? <>Pushing...</> : <>Push to WordPress</>}
    </button>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-brand-surface-hover ${className ?? ''}`} />;
}

// ── ActionCard ───────────────────────────────────────

function ActionCard({ rec, siteId, token, expanded, onToggle, onStatusUpdate, cmsType, highlighted }: {
  rec: Recommendation; siteId: string; token?: string; expanded: boolean;
  onToggle: () => void; onStatusUpdate: (id: string, next: string, prev: string, label: string) => void; cmsType?: string; highlighted?: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlighted && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlighted]);
  const pColor = PRIORITY_COLORS[rec.priority] ?? '#6b7280';
  const typeEntry = TI[rec.recommendation_type] ?? { icon: Lightbulb, color: '#6b7280' };
  const TypeIcon = typeEntry.icon;
  const typeLabel = REC_TYPE_LABELS[rec.recommendation_type] ?? rec.recommendation_type;
  const isDone = rec.status === 'completed';
  const isDismissed = rec.status === 'dismissed';

  const [enriching, setEnriching] = useState(false);
  const [enriched, setEnriched] = useState<Record<string, unknown> | null>(null);

  const enrich = useCallback(async () => {
    setEnriching(true);
    try {
      const r = await apiFetch<{ guidance?: Record<string, unknown> }>(`/sites/${siteId}/intelligence/recommendations/${rec.id}/enrich`, { method: 'POST', token });
      if (r.guidance) setEnriched(r.guidance);
      mutate((k: unknown) => Array.isArray(k) && typeof k[0] === 'string' && k[0].includes('recommendations'));
    } catch { /* noop */ } finally { setEnriching(false); }
  }, [siteId, rec.id, token]);

  const changeStatus = useCallback((next: string, label: string) => onStatusUpdate(rec.id, next, rec.status, label), [rec.id, rec.status, onStatusUpdate]);

  const actionsRaw = rec.specific_actions as unknown;
  const isEnrichedObj = actionsRaw && typeof actionsRaw === 'object' && !Array.isArray(actionsRaw);
  const enrichedData = isEnrichedObj ? actionsRaw as { ai_enriched?: boolean; guidance?: Record<string, unknown>; original_actions?: string[] } : null;
  const plainActions = Array.isArray(actionsRaw) ? actionsRaw as string[] : [];
  const ai = (rec.ai_generated_content ?? {}) as Record<string, string>;
  const isWordPress = cmsType === 'wordpress';
  const hasMeta = ai.meta_description || ai.suggested_title || ai.new_title || ai.suggested_new_title;
  const clusterId = ai.cluster_id;
  const isMerge = ['merge', 'redirect', 'consolidate'].includes(rec.recommendation_type);
  const linkTargets = ai.link_targets as unknown as Array<{ title: string; url: string; similarity: number; suggested_anchor: string }> | undefined;

  return (
    <div ref={cardRef} data-rec-id={rec.id} className={`rounded-xl border bg-brand-surface overflow-hidden transition-colors hover:border-brand-border-hover ${highlighted ? 'border-brand-accent ring-2 ring-brand-accent/30' : 'border-brand-border'} ${isDismissed ? 'opacity-60' : ''}`}>
      <button onClick={onToggle} className="w-full flex items-center gap-3 px-5 py-4 text-left" aria-label={`Toggle details for ${rec.title}`}>
        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: pColor }} />
        <div className="rounded-lg p-1.5 shrink-0" style={{ backgroundColor: `${typeEntry.color}15` }}>
          <TypeIcon size={14} style={{ color: typeEntry.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: pColor }}>{rec.priority}</span>
            <span className="text-[11px] text-brand-text-muted">{typeLabel}</span>
            {rec.confidence && <span className="text-[10px] text-brand-text-muted/60 ml-auto hidden sm:inline">{rec.confidence} confidence</span>}
          </div>
          <p className={`text-sm font-medium mt-0.5 line-clamp-1 ${isDone ? 'line-through text-brand-text-muted' : 'text-brand-text'}`}>{rec.title}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {rec.estimated_effort_hours != null && <span className="text-xs text-brand-text-muted tabular-nums">{rec.estimated_effort_hours}h</span>}
          {expanded ? <ChevronDown size={14} className="text-brand-text-muted" /> : <ChevronRight size={14} className="text-brand-text-muted" />}
        </div>
      </button>
      {expanded && (
        <div className="px-5 pb-5 border-t border-brand-border pt-4 space-y-4">
          <p className="text-sm text-brand-text-muted leading-relaxed">{rec.summary}</p>
          {enrichedData?.ai_enriched && enrichedData.guidance && (
            <div className="space-y-2">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 text-xs font-medium">AI Analysis</span>
              {Object.entries(enrichedData.guidance).map(([key, val]) => {
                if (!val) return null;
                const lbl = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                if (Array.isArray(val)) return (
                  <div key={key}>
                    <p className="text-xs font-medium text-brand-text-muted mb-1">{lbl}</p>
                    {(val as string[]).map((item, i) => <p key={i} className="text-sm text-brand-text pl-3 border-l-2 border-purple-500/30 mb-1">{item}</p>)}
                  </div>
                );
                return <div key={key}><p className="text-xs font-medium text-brand-text-muted">{lbl}</p><p className="text-sm text-brand-text mt-0.5">{String(val)}</p></div>;
              })}
              {enrichedData.original_actions && enrichedData.original_actions.length > 0 && (
                <div className="pt-2 border-t border-brand-border/30">
                  <p className="text-xs text-brand-text-muted mb-1">Quick actions</p>
                  {enrichedData.original_actions.map((a, i) => <p key={i} className="text-xs text-brand-text-muted pl-3 border-l border-brand-accent/30">{a}</p>)}
                </div>
              )}
            </div>
          )}
          {!enrichedData?.ai_enriched && plainActions.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
              {plainActions.map((a, i) => <p key={i} className="text-sm text-brand-text pl-3 border-l-2 border-brand-accent/30">{a}</p>)}
            </div>
          )}
          {rec.ai_generated_content && Object.keys(rec.ai_generated_content).length > 0 && (ai.meta_description || ai.suggested_title || ai.outline) && (
            <div className="rounded-lg bg-brand-bg p-3 border border-brand-border/50 space-y-1.5">
              <p className="text-xs font-medium text-brand-text-muted">AI-Generated Content</p>
              {ai.meta_description && <div className="flex items-start justify-between gap-2"><p className="text-xs text-brand-text italic">Meta: &quot;{ai.meta_description}&quot;</p><CopyBtn text={ai.meta_description} label="meta description" /></div>}
              {ai.suggested_title && <div className="flex items-start justify-between gap-2"><p className="text-xs text-brand-text">Title: &quot;{ai.suggested_title}&quot;</p><CopyBtn text={ai.suggested_title} label="title" /></div>}
              {ai.outline && <div className="flex items-start justify-between gap-2"><pre className="text-xs text-brand-text whitespace-pre-wrap font-sans flex-1">{ai.outline}</pre><CopyBtn text={ai.outline} label="outline" /></div>}
            </div>
          )}
          {linkTargets && linkTargets.length > 0 && (
            <div className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
              <p className="text-xs font-medium text-brand-text-muted mb-2">Link from these posts:</p>
              <div className="space-y-1.5">
                {linkTargets.map((t, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[10px] text-green-500 font-mono shrink-0">{Math.round(t.similarity * 100)}%</span>
                      <a href={t.url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-text truncate hover:text-blue-400">{t.title}</a>
                    </div>
                    <CopyBtn text={t.suggested_anchor} label="anchor text" />
                  </div>
                ))}
              </div>
            </div>
          )}
          {(hasMeta || clusterId || linkTargets) && (
            <div className="flex flex-wrap gap-2">
              {isWordPress && hasMeta && <PushToWPBtn siteId={siteId} postId={rec.post_id} title={(ai.suggested_title || ai.new_title || ai.suggested_new_title) as string | undefined} metaDescription={ai.meta_description as string | undefined} token={token} />}
              {isMerge && clusterId && <Link href={`/consolidation/${clusterId}`} className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#f97316]/10 text-[#f97316] hover:bg-[#f97316]/20 transition-colors"><Layers size={12} /> Start Consolidation</Link>}
              {isMerge && clusterId && <a href={apiUrl(`/sites/${siteId}/intelligence/consolidation/${clusterId}/redirect-map?format=htaccess`)} download className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#64748b]/10 text-[#94a3b8] hover:bg-[#64748b]/20 transition-colors"><FileText size={12} /> Download Redirects</a>}
            </div>
          )}
          {!enriched && !enrichedData?.ai_enriched && (
            <button onClick={() => void enrich()} disabled={enriching} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 text-purple-400 text-xs font-medium hover:bg-purple-500/20 transition-colors disabled:opacity-50" aria-label="Get AI analysis">
              {enriching ? <svg className="animate-spin w-3 h-3" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : null}
              {enriching ? 'Getting AI analysis...' : 'Get AI Analysis'}
            </button>
          )}
          {enriched && (
            <div className="rounded-lg bg-purple-500/5 border border-purple-500/20 p-3 space-y-2">
              <p className="text-xs font-medium text-purple-400">AI Analysis (just generated)</p>
              {Object.entries(enriched).map(([key, val]) => {
                if (!val) return null;
                const lbl = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                if (Array.isArray(val)) return <div key={key}><p className="text-xs font-medium text-brand-text-muted mb-1">{lbl}</p>{(val as string[]).map((item, i) => <p key={i} className="text-sm text-brand-text pl-3 border-l-2 border-purple-500/30 mb-1">{item}</p>)}</div>;
                return <div key={key}><p className="text-xs font-medium text-brand-text-muted">{lbl}</p><p className="text-xs text-brand-text">{String(val)}</p></div>;
              })}
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            {rec.status === 'pending' && (
              <>
                <Link href={`/patcher?recId=${rec.id}`} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors" aria-label="Start working"><Play size={12} /> Start Working</Link>
                <button onClick={() => changeStatus('completed', 'Marked done')} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors" aria-label="Mark as done"><CheckCircle size={12} /> {BUTTON_LABELS.markAsDone}</button>
                <button onClick={() => changeStatus('dismissed', 'Dismissed')} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Dismiss"><XCircle size={12} /> {BUTTON_LABELS.dismiss}</button>
              </>
            )}
            {rec.status === 'in_progress' && (
              <>
                <button onClick={() => changeStatus('completed', 'Marked done')} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors" aria-label="Mark complete"><CheckCircle size={12} /> Mark Complete</button>
                <button onClick={() => changeStatus('pending', 'Moved to To Do')} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Move to To Do"><Clock size={12} /> Move to To Do</button>
              </>
            )}
            {rec.status === 'completed' && <span className="inline-flex items-center gap-1 text-xs font-medium text-green-400"><CheckCircle size={12} /> Completed</span>}
            {rec.status === 'dismissed' && <button onClick={() => changeStatus('pending', 'Restored')} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Restore"><Clock size={12} /> Restore</button>}
            <Link href={`/posts/${rec.post_id}`} className="ml-auto flex items-center gap-1 text-xs text-brand-accent hover:text-brand-accent-hover" aria-label="View post">View Post <ArrowRight size={12} /></Link>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ────────────────────────────────────────

export default function ActionsPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const searchParams = useSearchParams();
  const highlightId = searchParams.get('highlight');
  const siteId = currentSite?.id ?? null;
  const { data: recsData, isLoading } = useRecommendations(siteId);

  const [statusFilter, setStatusFilter] = useState<StatusKey | 'all'>('pending');
  const [typeFilter, setTypeFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [sortBy, setSortBy] = useState<SortOption>('priority');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const [undoAction, setUndoAction] = useState<{ recId: string; prev: string; label: string; tid: ReturnType<typeof setTimeout> } | null>(null);
  const undoRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (undoRef.current) clearTimeout(undoRef.current); }, []);

  // When a highlight param is present, show all statuses so the card is visible, and expand it
  const highlightApplied = useRef(false);
  useEffect(() => {
    if (highlightId && recsData && !highlightApplied.current) {
      highlightApplied.current = true;
      setStatusFilter('all');
      setTypeFilter('all');
      setPriorityFilter('all');
      setSearchTerm('');
      setExpandedId(highlightId);
      // Find which page the highlighted rec is on
      const allRecs = recsData.recommendations ?? [];
      const idx = allRecs.findIndex((r: Recommendation) => r.id === highlightId);
      if (idx >= 0) {
        setPage(Math.floor(idx / RECS_PER_PAGE));
      }
    }
  }, [highlightId, recsData]);

  const recs = recsData?.recommendations ?? [];

  const counts = useMemo(() => {
    const c = { all: recs.length, pending: 0, in_progress: 0, completed: 0, dismissed: 0 };
    for (const r of recs) { const s = r.status as keyof typeof c; if (s in c) c[s]++; }
    return c;
  }, [recs]);

  const availableTypes = useMemo(() => {
    const byType = recsData?.by_type ?? {};
    return Object.entries(byType).filter(([, count]) => count > 0);
  }, [recsData]);

  const filtered = useMemo(() => {
    let result = recs;
    if (statusFilter !== 'all') result = result.filter(r => r.status === statusFilter);
    if (typeFilter !== 'all') result = result.filter(r => r.recommendation_type === typeFilter);
    if (priorityFilter !== 'all') result = result.filter(r => r.priority === priorityFilter);
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      result = result.filter(r => (r.title ?? '').toLowerCase().includes(q) || (r.summary ?? '').toLowerCase().includes(q));
    }
    return [...result].sort((a, b) => {
      switch (sortBy) {
        case 'priority': return (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3);
        case 'impact': { const ai = parseFloat(a.estimated_impact || '0') || 0; const bi = parseFloat(b.estimated_impact || '0') || 0; return bi - ai || (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3); }
        case 'effort': return (a.estimated_effort_hours ?? 999) - (b.estimated_effort_hours ?? 999);
        case 'date': return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        default: return 0;
      }
    });
  }, [recs, statusFilter, typeFilter, priorityFilter, searchTerm, sortBy]);

  const paged = useMemo(() => filtered.slice(page * RECS_PER_PAGE, (page + 1) * RECS_PER_PAGE), [filtered, page]);
  const totalPages = Math.ceil(filtered.length / RECS_PER_PAGE);

  const handleStatusUpdate = useCallback(async (recId: string, next: string, prev: string, label: string) => {
    if (undoRef.current) clearTimeout(undoRef.current);
    try {
      await apiFetch(`/sites/${siteId}/intelligence/recommendations/${recId}/status`, { method: 'PATCH', body: JSON.stringify({ status: next }), token: session?.access_token });
      mutate((k: unknown) => Array.isArray(k) && typeof k[0] === 'string' && k[0].includes('recommendations'));
    } catch { return; }
    if (next === 'completed' || next === 'dismissed') {
      const tid = setTimeout(() => setUndoAction(null), 5000);
      undoRef.current = tid;
      setUndoAction({ recId, prev, label, tid });
    }
  }, [siteId, session?.access_token]);

  const handleUndo = useCallback(async () => {
    if (!undoAction) return;
    clearTimeout(undoAction.tid);
    if (undoRef.current) clearTimeout(undoRef.current);
    try {
      await apiFetch(`/sites/${siteId}/intelligence/recommendations/${undoAction.recId}/status`, { method: 'PATCH', body: JSON.stringify({ status: undoAction.prev }), token: session?.access_token });
      mutate((k: unknown) => Array.isArray(k) && typeof k[0] === 'string' && k[0].includes('recommendations'));
    } catch { /* noop */ }
    setUndoAction(null);
  }, [undoAction, siteId, session?.access_token]);

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-16 w-full" />
        <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
      </div>
    );
  }

  const completionPct = recs.length > 0 ? Math.round((counts.completed / recs.length) * 100) : 0;
  const pendingCount = counts.pending + counts.in_progress;

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-brand-text">Actions</h1>
          {pendingCount > 0 && (
            <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-brand-accent/10 text-brand-accent">{pendingCount} pending</span>
          )}
        </div>
        <p className="text-sm text-brand-text-muted mt-1">Prioritized recommendations to improve your content</p>
      </div>

      {recs.length > 0 && (
        <div className="rounded-xl border border-brand-border bg-brand-surface px-5 py-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-brand-text">Progress</span>
            <span className="text-sm text-brand-text-muted tabular-nums">{counts.completed} of {recs.length} done</span>
          </div>
          <div className="h-2 rounded-full bg-brand-surface-hover overflow-hidden">
            <div className="h-full rounded-full bg-green-500 transition-all duration-500" style={{ width: `${completionPct}%` }} />
          </div>
          <div className="flex items-center gap-5 mt-2.5 text-xs text-brand-text-muted">
            <span>{counts.pending} to do</span>
            <span>{counts.in_progress} in progress</span>
            <span>{counts.completed} done</span>
            <span>{counts.dismissed} dismissed</span>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-brand-border bg-brand-surface px-5 py-4 space-y-3">
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {STATUS_TABS.map(tab => (
            <button key={tab.key} onClick={() => { setStatusFilter(tab.key); setPage(0); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${statusFilter === tab.key ? 'bg-brand-surface-hover text-brand-text ring-1 ring-brand-accent/30' : 'text-brand-text-muted hover:bg-brand-surface-hover/50'}`}>
              <tab.icon size={13} style={{ color: statusFilter === tab.key ? tab.color : undefined }} />
              {tab.label}
              <span className="text-[11px] tabular-nums opacity-60">{counts[tab.key as keyof typeof counts] ?? recs.length}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <select value={priorityFilter} onChange={e => { setPriorityFilter(e.target.value); setPage(0); }} aria-label="Filter by priority"
            className="rounded-lg bg-brand-bg border border-brand-border px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none">
            <option value="all">All priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(0); }} aria-label="Filter by type"
            className="rounded-lg bg-brand-bg border border-brand-border px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none">
            <option value="all">All types</option>
            {availableTypes.map(([type, count]) => <option key={type} value={type}>{REC_TYPE_LABELS[type] ?? type} ({count})</option>)}
          </select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value as SortOption)} aria-label="Sort recommendations"
            className="rounded-lg bg-brand-bg border border-brand-border px-3 py-2 text-sm text-brand-text focus:border-brand-accent focus:outline-none">
            {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>Sort: {o.label}</option>)}
          </select>
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-text-muted" />
            <input type="text" value={searchTerm} onChange={e => { setSearchTerm(e.target.value); setPage(0); }}
              placeholder="Search recommendations..." aria-label="Search recommendations"
              className="w-full pl-8 pr-3 py-2 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text placeholder-brand-text-muted focus:border-brand-accent focus:outline-none" />
          </div>
          {(statusFilter !== 'pending' || typeFilter !== 'all' || priorityFilter !== 'all' || searchTerm) && (
            <button onClick={() => { setStatusFilter('pending'); setTypeFilter('all'); setPriorityFilter('all'); setSearchTerm(''); setPage(0); }}
              className="flex items-center gap-1 text-xs text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Clear all filters">
              <X size={12} /> Clear
            </button>
          )}
        </div>
      </div>

      {filtered.length > 0 ? (
        <div className="space-y-3">
          <p className="text-xs text-brand-text-muted tabular-nums">
            Showing {page * RECS_PER_PAGE + 1}&ndash;{Math.min((page + 1) * RECS_PER_PAGE, filtered.length)} of {filtered.length}
          </p>

          {paged.map(rec => (
            <ActionCard key={rec.id} rec={rec} siteId={siteId!} token={session?.access_token} cmsType={currentSite?.cms_type}
              expanded={expandedId === rec.id} onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)} onStatusUpdate={handleStatusUpdate}
              highlighted={highlightId === rec.id} />
          ))}

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-brand-text border border-brand-border hover:bg-brand-surface-hover disabled:opacity-30 transition-colors" aria-label="Previous page">Previous</button>
              <span className="text-xs text-brand-text-muted tabular-nums">Page {page + 1} of {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                className="px-3 py-1.5 rounded-lg text-xs text-brand-text border border-brand-border hover:bg-brand-surface-hover disabled:opacity-30 transition-colors" aria-label="Next page">Next</button>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-brand-border bg-brand-surface text-center py-16 px-6">
          <CheckCircle size={36} className="text-brand-text-muted/40 mx-auto mb-3" />
          <p className="text-sm font-medium text-brand-text">
            {statusFilter !== 'all' && statusFilter !== 'pending' ? `No ${STATUS_TABS.find(t => t.key === statusFilter)?.label.toLowerCase()} recommendations` : recs.length === 0 ? EMPTY_STATES.recommendations.title : counts.pending === 0 ? EMPTY_STATES.recommendationsDone.title : empty.noRecommendations.title}
          </p>
          <p className="text-xs text-brand-text-muted mt-1">
            {recs.length === 0 ? EMPTY_STATES.recommendations.description : counts.pending === 0 && statusFilter === 'pending' ? EMPTY_STATES.recommendationsDone.description : empty.noRecommendations.description}
          </p>
        </div>
      )}

      {undoAction && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-200">
          <div className="flex items-center gap-3 rounded-xl bg-brand-surface border border-brand-border shadow-lg px-4 py-3">
            <span className="text-sm text-brand-text">{undoAction.label}</span>
            <button onClick={() => void handleUndo()} className="flex items-center gap-1.5 text-sm font-medium text-brand-accent hover:text-brand-accent-hover transition-colors" aria-label="Undo action"><Undo2 size={14} /> Undo</button>
            <button onClick={() => { clearTimeout(undoAction.tid); setUndoAction(null); }} className="text-brand-text-muted hover:text-brand-text transition-colors ml-1" aria-label="Dismiss undo"><X size={14} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
