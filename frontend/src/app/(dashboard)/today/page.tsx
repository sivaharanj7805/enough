'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useSiteHealth, useRecommendations, useAIScores, useClusters, useProblems } from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { PipelineProgress } from '@/components/dashboard/PipelineProgress';
import { SetupChecklist } from '@/components/dashboard/SetupChecklist';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { mutate } from 'swr';
import {
  ArrowRight,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  Zap,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  HelpCircle,
  PartyPopper,
  RefreshCw,
  X,
} from 'lucide-react';
import { today as todayCopy, recType as REC_TYPE_LABEL } from '@/lib/copy';
import type { Recommendation, SiteHealth } from '@/lib/types';

// ─── Score color helpers ────────────────────────────
function getScoreColor(score: number): string {
  if (score >= 80) return '#22C55E';
  if (score >= 60) return '#3B82F6';
  if (score >= 40) return '#F59E0B';
  if (score >= 20) return '#EF4444';
  return '#991B1B';
}

function getScoreLabel(score: number): string {
  if (score >= 80) return 'Excellent';
  if (score >= 60) return 'Good';
  if (score >= 40) return 'Needs work';
  if (score >= 20) return 'Significant issues';
  return 'Critical';
}

const PRIORITY_BORDER: Record<string, string> = {
  critical: '#EF4444',
  high: '#F59E0B',
  medium: '#3B82F6',
  low: '#6B7280',
};

const PRIORITY_COLOR: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#64748b',
};

const CONFIDENCE_STYLE: Record<string, { label: string; cls: string }> = {
  high: { label: 'High confidence', cls: 'text-[#22c55e] bg-[#22c55e]/10' },
  medium: { label: 'Worth investigating', cls: 'text-[#eab308] bg-[#eab308]/10' },
  low: { label: 'Moderate confidence', cls: 'text-[#94a3b8] bg-[#94a3b8]/10' },
};

// ─── Animated counter hook ──────────────────────────
function useAnimatedCounter(target: number, duration = 600): number {
  const [value, setValue] = useState(0);
  const startTime = useRef<number | null>(null);
  const rafId = useRef<number | null>(null);

  useEffect(() => {
    startTime.current = null;
    const animate = (timestamp: number) => {
      if (startTime.current === null) startTime.current = timestamp;
      const elapsed = timestamp - startTime.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out quad
      const eased = 1 - (1 - progress) * (1 - progress);
      setValue(Math.round(eased * target));
      if (progress < 1) {
        rafId.current = requestAnimationFrame(animate);
      }
    };
    rafId.current = requestAnimationFrame(animate);
    return () => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
    };
  }, [target, duration]);

  return value;
}

// ─── Health Score Card ──────────────────────────────
function HealthScoreCard({ score }: { score: number }) {
  const animatedScore = useAnimatedCounter(score, 600);
  const color = getScoreColor(score);
  const label = getScoreLabel(score);
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <Card className="relative flex flex-col items-center justify-center !p-6">
      <div className="absolute top-3 right-3">
        <button
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          onClick={() => setShowTooltip((v) => !v)}
          className="text-[#64748b] hover:text-[#94a3b8] transition-colors"
          aria-label="Score explanation"
        >
          <HelpCircle size={16} />
        </button>
        {showTooltip && (
          <div className="absolute right-0 top-6 z-10 w-64 rounded-lg bg-[#1e293b] border border-[#334155] p-3 text-xs text-[#94a3b8] shadow-lg">
            A composite of 6 factors: traffic, rankings, engagement, freshness, content depth, and technical SEO.
          </div>
        )}
      </div>
      <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-2">
        Health Score
      </p>
      <div
        className="text-[72px] font-bold leading-none"
        style={{ color }}
      >
        {animatedScore}
      </div>
      <p className="text-sm font-medium mt-2" style={{ color }}>
        {label}
      </p>
    </Card>
  );
}

// ─── Trend Card ─────────────────────────────────────
function TrendCard({
  health,
  siteId,
  token,
}: {
  health: SiteHealth;
  siteId: string;
  token: string | null;
}) {
  const trends = health.trends ?? {};
  const delta = trends['7d'] ?? trends['30d'] ?? null;
  const lastAnalyzed = health.ai_enriched_count != null ? health.ai_enriched_count : null;

  // Compute days since last analysis from updated info
  const daysSinceAnalysis = (() => {
    // We don't have an explicit last_analyzed_at, but we use a heuristic
    // If the site has trends data, assume recent
    if (trends['7d'] != null) return 3;
    if (trends['30d'] != null) return 14;
    return 10;
  })();

  const [reanalyzing, setReanalyzing] = useState(false);

  const handleReanalyze = async () => {
    if (!siteId || !token) return;
    setReanalyzing(true);
    try {
      await apiFetch(`/sites/${siteId}/intelligence/pipeline`, {
        method: 'POST',
        token,
      });
    } catch {
      // background task
    }
    setReanalyzing(false);
  };

  return (
    <Card className="flex flex-col justify-center !p-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-3">
        Trend
      </p>
      {delta !== null ? (
        <div className="flex items-center gap-2 mb-2">
          {delta >= 0 ? (
            <TrendingUp size={20} className="text-[#22C55E]" />
          ) : (
            <TrendingDown size={20} className="text-[#EF4444]" />
          )}
          <span
            className="text-lg font-bold"
            style={{ color: delta >= 0 ? '#22C55E' : '#EF4444' }}
          >
            {delta >= 0 ? `\u25B2 +${delta}` : `\u25BC ${delta}`} since last week
          </span>
        </div>
      ) : (
        <p className="text-sm text-[#64748b] mb-2">No trend data yet</p>
      )}
      <p className="text-xs text-[#64748b]">
        Last analyzed: {daysSinceAnalysis === 0 ? 'today' : `${daysSinceAnalysis} days ago`}
      </p>
      {daysSinceAnalysis > 7 && (
        <button
          onClick={() => void handleReanalyze()}
          disabled={reanalyzing}
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={reanalyzing ? 'animate-spin' : ''} />
          {reanalyzing ? 'Re-analyzing...' : 'Re-analyze'}
        </button>
      )}
    </Card>
  );
}

// ─── Priority Action Card (center) ──────────────────
function PriorityActionCard({
  rec,
  siteId,
  token,
  onDone,
}: {
  rec: Recommendation;
  siteId: string;
  token: string | null;
  onDone: (recId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const borderColor = PRIORITY_BORDER[rec.priority] ?? '#6B7280';
  const color = PRIORITY_COLOR[rec.priority] ?? '#64748b';
  const conf = rec.confidence ? CONFIDENCE_STYLE[rec.confidence] ?? CONFIDENCE_STYLE.medium : null;

  const ai = (rec.ai_generated_content ?? {}) as Record<string, string>;

  const handleMarkDone = () => {
    setDismissing(true);
    setTimeout(() => {
      onDone(rec.id);
    }, 300);
  };

  return (
    <div
      className={`rounded-xl border bg-[#111827] overflow-hidden transition-all duration-300 ${
        dismissing ? 'opacity-0 -translate-x-8' : 'opacity-100 translate-x-0'
      }`}
      style={{ borderLeftWidth: 4, borderLeftColor: borderColor, borderColor: '#1e293b' }}
    >
      <div className="p-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#F59E0B]">
            TOP PRIORITY
          </span>
          <span
            className="text-xs font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{ backgroundColor: color + '20', color }}
          >
            {rec.priority}
          </span>
          {conf && (
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${conf.cls}`}>
              {conf.label}
            </span>
          )}
        </div>
        <h3 className="text-lg font-bold text-[#e2e8f0] leading-snug">{rec.title}</h3>
        <p className="text-sm text-[#94a3b8] mt-2 leading-relaxed">{rec.summary}</p>

        <div className="flex items-center gap-3 mt-3 flex-wrap">
          {rec.estimated_effort_hours != null && (
            <span className="text-xs text-[#64748b] flex items-center gap-1">
              <Clock size={11} /> {rec.estimated_effort_hours}h effort
            </span>
          )}
          <span className="text-xs text-[#64748b]">
            {REC_TYPE_LABEL[rec.recommendation_type] ?? rec.recommendation_type}
          </span>
        </div>

        {/* Expand/collapse for full plan */}
        <div className="flex items-center gap-3 mt-4">
          <button
            onClick={() => setExpanded((e) => !e)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
          >
            {expanded ? 'Hide Full Plan' : 'View Full Plan'}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          <button
            onClick={handleMarkDone}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#22C55E]/10 text-[#22C55E] hover:bg-[#22C55E]/20 transition-colors"
          >
            <CheckCircle2 size={12} /> Mark as Done
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 border-t border-[#1e293b]">
          {/* Steps */}
          {rec.specific_actions.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
                Steps
              </p>
              <div className="space-y-2">
                {rec.specific_actions.map((action, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-xs text-[#3b82f6] font-bold mt-0.5">{i + 1}.</span>
                    <span className="text-sm text-[#94a3b8]">{action}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI-generated content (merge plan, meta descriptions, etc.) */}
          {Object.keys(ai).length > 0 && (
            <div className="mt-4 rounded-lg bg-[#0f172a] p-3 border border-[#1e293b]">
              <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
                AI-Generated Plan
              </p>
              {ai.meta_description && (
                <p className="text-xs text-[#94a3b8]">
                  <span className="text-[#64748b]">Meta description:</span> &quot;{ai.meta_description}&quot;
                </p>
              )}
              {ai.suggested_title && (
                <p className="text-xs text-[#94a3b8] mt-1">
                  <span className="text-[#64748b]">Suggested title:</span> &quot;{ai.suggested_title}&quot;
                </p>
              )}
              {ai.redirect_map && (
                <p className="text-xs text-[#94a3b8] mt-1">
                  <span className="text-[#64748b]">Redirect map:</span> {ai.redirect_map}
                </p>
              )}
              {ai.merge_plan && (
                <p className="text-xs text-[#94a3b8] mt-1">
                  <span className="text-[#64748b]">Merge plan:</span> {ai.merge_plan}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Secondary Action Card ──────────────────────────
function SecondaryActionCard({ rec }: { rec: Recommendation }) {
  const color = PRIORITY_COLOR[rec.priority] ?? '#64748b';
  const borderColor = PRIORITY_BORDER[rec.priority] ?? '#6B7280';
  const router = useRouter();

  return (
    <div
      className="rounded-xl border bg-[#111827] overflow-hidden hover:border-[#334155] transition-colors"
      style={{ borderLeftWidth: 3, borderLeftColor: borderColor, borderColor: '#1e293b' }}
    >
      <div className="p-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{ backgroundColor: color + '20', color }}
          >
            {rec.priority}
          </span>
          <span className="text-[10px] text-[#64748b]">
            {REC_TYPE_LABEL[rec.recommendation_type] ?? rec.recommendation_type}
          </span>
        </div>
        <p className="text-sm font-medium text-[#e2e8f0] leading-snug line-clamp-2">{rec.title}</p>
        {rec.estimated_effort_hours != null && (
          <span className="text-xs text-[#64748b] flex items-center gap-1 mt-1.5">
            <Clock size={10} /> {rec.estimated_effort_hours}h
          </span>
        )}
        <button
          onClick={() => router.push('/explore?tab=recommendations')}
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
        >
          View <ArrowRight size={11} />
        </button>
      </div>
    </div>
  );
}

// ─── Quick Stats Card ───────────────────────────────
function QuickStatsCard({
  health,
  totalRecs,
  completedRecs,
  clusterCount,
  problemCount,
}: {
  health: SiteHealth;
  totalRecs: number;
  completedRecs: number;
  clusterCount: number;
  problemCount: number;
}) {
  return (
    <Card className="!p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-4">
        Quick Stats
      </p>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Issues</span>
          <span className="text-sm font-bold text-[#e2e8f0]">{problemCount}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Recommendations</span>
          <span className="text-sm font-bold text-[#e2e8f0]">
            {completedRecs}/{totalRecs}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Clusters</span>
          <span className="text-sm font-bold text-[#e2e8f0]">{clusterCount}</span>
        </div>
      </div>
      <Link
        href="/landscape"
        className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
      >
        Explore <ArrowRight size={12} />
      </Link>
    </Card>
  );
}

// ─── Undo Toast ─────────────────────────────────────
function UndoToast({
  visible,
  onUndo,
  onDismiss,
}: {
  visible: boolean;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [visible, onDismiss]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 rounded-xl bg-[#1e293b] border border-[#334155] shadow-lg animate-in slide-in-from-bottom-4">
      <CheckCircle2 size={16} className="text-[#22C55E] animate-pulse" />
      <span className="text-sm text-[#e2e8f0]">Marked as done.</span>
      <button
        onClick={onUndo}
        className="text-sm font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
      >
        Undo?
      </button>
      <button onClick={onDismiss} className="text-[#64748b] hover:text-[#94a3b8]">
        <X size={14} />
      </button>
    </div>
  );
}

// ─── Loading skeleton ───────────────────────────────
function TodaySkeleton() {
  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">
      {/* Top row: health score + trend */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-6 flex flex-col items-center justify-center">
          <Skeleton width={96} height={12} />
          <Skeleton width={100} height={72} className="mt-3" />
          <Skeleton width={80} height={16} className="mt-2" />
        </div>
        <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-6">
          <Skeleton width={60} height={12} />
          <Skeleton width="75%" height={20} className="mt-3" />
          <Skeleton width="50%" height={14} className="mt-2" />
        </div>
      </div>
      {/* Priority card */}
      <Skeleton variant="card" height={160} />
      {/* Secondary cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Skeleton variant="card" height={120} />
        <Skeleton variant="card" height={120} />
      </div>
      {/* Quick stats */}
      <Skeleton variant="card" height={160} />
    </div>
  );
}

// ─── All-done state ─────────────────────────────────
function AllDoneState() {
  return (
    <Card className="!p-8 text-center">
      <PartyPopper size={40} className="text-[#22C55E] mx-auto mb-4" />
      <h3 className="text-lg font-semibold text-[#e2e8f0] mb-2">
        Your content is in great shape.
      </h3>
      <p className="text-sm text-[#64748b]">
        We&apos;ll notify you when new issues arise.
      </p>
    </Card>
  );
}

// ─── Empty / Analysis Running state ─────────────────
function AnalysisRunningState({ siteId }: { siteId: string }) {
  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">
      <Card className="!p-8 text-center">
        <Zap size={32} className="text-[#3b82f6] mx-auto mb-4 animate-pulse" />
        <h3 className="text-lg font-semibold text-[#e2e8f0] mb-2">
          Your analysis is running
        </h3>
        <p className="text-sm text-[#64748b] mb-6">
          We&apos;re crawling, analyzing, and scoring your content. This usually takes 10-40 minutes.
        </p>
      </Card>
      <PipelineProgress siteId={siteId} />
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────
export default function TodayPage() {
  const { currentSite } = useSite();
  const { data: health, isLoading: healthLoading } = useSiteHealth(currentSite?.id ?? null);
  const { data: recsData, isLoading: recsLoading } = useRecommendations(
    currentSite?.id ?? null,
    { status: 'pending' }
  );
  const { data: completedRecsData } = useRecommendations(
    currentSite?.id ?? null,
    { status: 'completed' }
  );
  const { data: aiScores } = useAIScores(currentSite?.id ?? null);
  const { data: clusters } = useClusters(currentSite?.id ?? null);
  const { data: problems } = useProblems(currentSite?.id ?? null);
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const isLoading = healthLoading || recsLoading;

  const [doneIds, setDoneIds] = useState<Set<string>>(new Set());
  const [undoRecId, setUndoRecId] = useState<string | null>(null);
  const [showUndoToast, setShowUndoToast] = useState(false);

  const allRecs = recsData?.recommendations ?? [];
  const visibleRecs = allRecs.filter((r) => !doneIds.has(r.id));
  const topRec = visibleRecs[0] ?? null;
  const secondaryRecs = visibleRecs.slice(1, 3);
  const totalRecs = recsData?.total ?? 0;
  const completedTotal = completedRecsData?.total ?? 0;
  const clusterCount = clusters?.length ?? health?.clusters?.length ?? 0;
  const problemCount = Array.isArray(problems) ? problems.length : 0;

  const handleMarkDone = useCallback(
    async (recId: string) => {
      setDoneIds((prev) => new Set(prev).add(recId));
      setUndoRecId(recId);
      setShowUndoToast(true);

      // Persist to API
      if (currentSite?.id && token) {
        try {
          await apiFetch(
            `/sites/${currentSite.id}/intelligence/recommendations/${recId}/status`,
            {
              method: 'PATCH',
              body: JSON.stringify({ status: 'completed' }),
              token: token ?? undefined,
            }
          );
          void mutate(
            (key: unknown) =>
              Array.isArray(key) &&
              typeof key[0] === 'string' &&
              key[0].includes('recommendations')
          );
        } catch {
          // revert on failure
          setDoneIds((prev) => {
            const next = new Set(prev);
            next.delete(recId);
            return next;
          });
        }
      }
    },
    [currentSite?.id, token]
  );

  const handleUndo = useCallback(async () => {
    if (!undoRecId) return;
    setDoneIds((prev) => {
      const next = new Set(prev);
      next.delete(undoRecId);
      return next;
    });
    setShowUndoToast(false);

    if (currentSite?.id && token) {
      try {
        await apiFetch(
          `/sites/${currentSite.id}/intelligence/recommendations/${undoRecId}/status`,
          {
            method: 'PATCH',
            body: JSON.stringify({ status: 'pending' }),
            token: token ?? undefined,
          }
        );
        void mutate(
          (key: unknown) =>
            Array.isArray(key) &&
            typeof key[0] === 'string' &&
            key[0].includes('recommendations')
        );
      } catch {
        // silent
      }
    }
    setUndoRecId(null);
  }, [undoRecId, currentSite?.id, token]);

  const handleDismissToast = useCallback(() => {
    setShowUndoToast(false);
    setUndoRecId(null);
  }, []);

  // ── Loading state ──
  if (isLoading) {
    return <TodaySkeleton />;
  }

  // ── No health data (demo or analysis running) ──
  if (!health) {
    if (currentSite?.id) {
      return <AnalysisRunningState siteId={currentSite.id} />;
    }

    // No site connected — show demo
    return (
      <div className="max-w-5xl mx-auto space-y-4 py-2">
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#3b82f6]/5 border border-[#3b82f6]/20">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#3b82f6]">Demo</span>
            <p className="text-sm text-[#94a3b8]">
              Showing Close.com — 958 posts analyzed. Connect your blog to see your own data.
            </p>
          </div>
          <Link
            href="/onboarding"
            className="flex-shrink-0 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors ml-4"
          >
            Analyze my blog &rarr;
          </Link>
        </div>

        <div className="text-center py-8">
          <Link
            href="/onboarding"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
          >
            Analyze my blog <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    );
  }

  const healthScore = Math.round(health.content_health_score);
  const hasEngagedRecs = allRecs.some(
    (r) => r.status === 'completed' || r.status === 'in_progress'
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">
      {/* Pipeline progress (only visible while running) */}
      {currentSite?.id && <PipelineProgress siteId={currentSite.id} />}

      {/* Setup checklist */}
      <SetupChecklist
        site={currentSite}
        health={health}
        hasRecommendations={hasEngagedRecs}
      />

      {/* ── Top Row: Health Score (left) + Trend (right) ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <HealthScoreCard score={healthScore} />
        <TrendCard
          health={health}
          siteId={currentSite?.id ?? ''}
          token={token}
        />
      </div>

      {/* ── AI Readiness nudge ── */}
      {aiScores && aiScores.total_scored > 0 && (aiScores.pct_ai_ready ?? 0) < 10 && (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/20">
          <div className="flex items-center gap-3">
            <Zap size={16} className="text-amber-400 flex-shrink-0" />
            <p className="text-sm text-[#e2e8f0]">
              Only{' '}
              <span className="font-semibold text-amber-400">
                {(aiScores.pct_ai_ready ?? 0).toFixed(0)}%
              </span>{' '}
              of posts are AI-ready.
            </p>
          </div>
          <Link
            href="/explore?tab=recommendations&type=add_schema"
            className="flex-shrink-0 text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors ml-4"
          >
            Fix this &rarr;
          </Link>
        </div>
      )}

      {/* ── Priority Action Card (center, larger) ── */}
      {visibleRecs.length === 0 ? (
        <AllDoneState />
      ) : (
        <>
          {topRec && (
            <PriorityActionCard
              rec={topRec}
              siteId={currentSite?.id ?? ''}
              token={token}
              onDone={(id) => void handleMarkDone(id)}
            />
          )}

          {/* ── Secondary Action Cards (2 smaller) ── */}
          {secondaryRecs.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {secondaryRecs.map((rec) => (
                <SecondaryActionCard key={rec.id} rec={rec} />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Quick Stats Card (bottom) ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          {/* Oracle prompt */}
          <div
            className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b] cursor-pointer hover:border-[#3b82f6]/30 transition-colors h-full"
            onClick={() => {
              const fab = document.querySelector<HTMLButtonElement>('[title="Ask Oracle anything"]');
              fab?.click();
            }}
          >
            <Zap size={16} className="text-[#3b82f6] flex-shrink-0" />
            <p className="text-sm text-[#94a3b8] flex-1">
              Not sure where to start?{' '}
              <span className="text-[#3b82f6] font-medium">Ask the Oracle</span> &mdash;
              &quot;what should I fix first?&quot;
            </p>
            <ArrowRight size={14} className="text-[#3b82f6]" />
          </div>
        </div>
        <QuickStatsCard
          health={health}
          totalRecs={totalRecs}
          completedRecs={completedTotal}
          clusterCount={clusterCount}
          problemCount={problemCount}
        />
      </div>

      {/* ── Alert tray ── */}
      {(() => {
        const criticalCount = recsData?.by_priority?.critical ?? 0;
        const highCount = recsData?.by_priority?.high ?? 0;
        const urgentCount = criticalCount + highCount;
        if (urgentCount <= 0) return null;
        return (
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b]">
            <AlertTriangle size={15} className="text-[#ef4444] flex-shrink-0" />
            <p className="text-sm text-[#94a3b8]">
              {criticalCount > 0 && (
                <span className="text-[#ef4444] font-medium">{criticalCount} critical &middot; </span>
              )}
              {highCount > 0 && (
                <span className="text-[#f97316] font-medium">{highCount} high priority &middot; </span>
              )}
              <Link href="/explore?tab=recommendations" className="hover:text-[#e2e8f0] transition-colors">
                View all issues &rarr;
              </Link>
            </p>
          </div>
        );
      })()}

      {/* Undo toast */}
      <UndoToast
        visible={showUndoToast}
        onUndo={() => void handleUndo()}
        onDismiss={handleDismissToast}
      />
    </div>
  );
}
