'use client';

import { useState } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import {
  useSiteHealth,
  useRecommendations,
  useAIScores,
  useClusters,
  useProblems,
  useCannibalizationPairs,
  useHealthHistory,
  useAnalysisDiff,
  useImpactEstimate,
} from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch, apiUrl } from '@/lib/api';
import { retention } from '@/lib/copy';
import { Skeleton } from '@/components/ui/Skeleton';
import { PipelineProgress } from '@/components/dashboard/PipelineProgress';
import Link from 'next/link';
import { ArrowRight, AlertTriangle, RefreshCw, X, Download, FileText, Settings, TrendingUp, TrendingDown, CheckCircle, BarChart3 } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { Recommendation, Cluster } from '@/lib/types';

// ── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(s: number): string {
  if (s >= 75) return '#22c55e';
  if (s >= 60) return '#3b82f6';
  if (s >= 40) return '#f59e0b';
  return '#ef4444';
}
function scoreTw(s: number): string {
  if (s >= 75) return 'text-green-500';
  if (s >= 60) return 'text-blue-500';
  if (s >= 40) return 'text-amber-500';
  return 'text-red-500';
}
function scoreLabel(s: number): string {
  if (s >= 75) return 'excellent';
  if (s >= 60) return 'good';
  if (s >= 40) return 'moderate';
  return 'poor';
}
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const PRI_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const PRI_COLOR: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#64748b' };
const CARD = 'rounded-xl border border-brand-border bg-brand-surface p-5';

// ── Skeleton ────────────────────────────────────────────────────────────────

function TodaySkeleton() {
  return (
    <div className="max-w-4xl mx-auto space-y-6 py-2">
      <div className="flex items-center justify-between">
        <div><Skeleton width={80} height={28} /><Skeleton width={180} height={14} className="mt-2" /></div>
        <div className="flex gap-2"><Skeleton width={110} height={36} /><Skeleton width={130} height={36} /></div>
      </div>
      <Skeleton variant="card" height={120} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => <Skeleton key={i} variant="card" height={90} />)}
      </div>
      <Skeleton variant="card" height={200} />
      <Skeleton variant="card" height={140} />
    </div>
  );
}

// ── RecCard ─────────────────────────────────────────────────────────────────

function RecCard({ rec, index }: { rec: Recommendation; index: number }) {
  const color = PRI_COLOR[rec.priority] ?? '#64748b';
  return (
    <div className={`${CARD} flex items-start gap-4`}>
      <span className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white" style={{ backgroundColor: color }}>
        {index}
      </span>
      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-semibold text-brand-text">{rec.title}</h3>
        <p className="text-xs text-brand-text-muted mt-0.5 line-clamp-1">{rec.summary}</p>
      </div>
      <Link
        href={`/actions?highlight=${rec.id}`}
        className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-medium text-brand-accent hover:text-brand-accent-hover transition-colors whitespace-nowrap"
        aria-label={`Do recommendation: ${rec.title}`}
      >
        Do it <ArrowRight size={12} />
      </Link>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function TodayPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const { session } = useAuth();
  const token = session?.access_token ?? (typeof window !== 'undefined' ? localStorage.getItem('tended_access_token') : null);

  const { data: health, isLoading: healthLoading } = useSiteHealth(siteId);
  const { data: recsData, isLoading: recsLoading } = useRecommendations(siteId);
  const { data: aiScores } = useAIScores(siteId);
  const { data: clusters } = useClusters(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: cannibPairs } = useCannibalizationPairs(siteId);
  const { data: healthHistory } = useHealthHistory(siteId);
  const { data: analysisDiff } = useAnalysisDiff(siteId);
  const { data: impactEstimate } = useImpactEstimate(siteId);

  const [alertDismissed, setAlertDismissed] = useState(false);
  const [diffDismissed, setDiffDismissed] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  // ── Derived data ──
  const allRecs = recsData?.recommendations ?? [];
  const pendingRecs = allRecs.filter((r) => r.status === 'pending');
  const completedRecs = allRecs.filter((r) => r.status === 'completed');
  const totalRecs = allRecs.length;
  const completedTotal = completedRecs.length;
  const completedPct = totalRecs > 0 ? Math.round((completedTotal / totalRecs) * 100) : 0;

  const problemCount = Array.isArray(problems) ? problems.length : 0;
  const resolvedProblems = Array.isArray(problems) ? problems.filter((p) => p.resolved_at !== null).length : 0;

  const cannibPairCount = Array.isArray(cannibPairs) ? cannibPairs.length : 0;
  const cannibPostCount = Array.isArray(cannibPairs)
    ? new Set(cannibPairs.flatMap((p) => [p.post_a.post_id, p.post_b.post_id])).size
    : 0;

  const aiReadyPct = Math.round(aiScores?.pct_ai_ready ?? 0);
  const aiTotalScored = aiScores?.total_scored ?? 0;

  const prevScore = healthHistory && healthHistory.length >= 2 ? healthHistory[healthHistory.length - 2].score : null;
  const prevDate = healthHistory && healthHistory.length >= 2 ? healthHistory[healthHistory.length - 2].analyzed_at : null;
  const currentScore = health ? Math.round(health.content_health_score) : 0;
  const scoreDelta = prevScore !== null ? currentScore - Math.round(prevScore) : null;

  const topRecs = [...pendingRecs].sort((a, b) => (PRI_ORDER[a.priority] ?? 99) - (PRI_ORDER[b.priority] ?? 99)).slice(0, 3);

  const sortedClusters = [...(clusters ?? [])]
    .filter((c): c is Cluster & { health_score: number } => c.health_score !== null)
    .sort((a, b) => a.health_score - b.health_score);

  const ga4Connected = !!currentSite?.ga4_property_id;

  // Sparkline data — sorted oldest to newest
  const sparklineData = healthHistory && healthHistory.length >= 3
    ? [...healthHistory]
        .filter((h) => h.analyzed_at)
        .sort((a, b) => new Date(a.analyzed_at!).getTime() - new Date(b.analyzed_at!).getTime())
        .map((h) => ({ score: Math.round(h.score) }))
    : null;

  // Impact estimate
  const estPoints = impactEstimate?.estimated_points ?? 0;
  const estCompleted = impactEstimate?.completed_since_last_analysis ?? 0;

  // Analysis diff — show if recent (within 7 days) and not dismissed
  const showDiff = !diffDismissed && analysisDiff && analysisDiff.score_delta !== null
    && analysisDiff.analyzed_at
    && Date.now() - new Date(analysisDiff.analyzed_at).getTime() < 7 * 86400000;

  const newIssueCount = Array.isArray(problems)
    ? problems.filter((p) => p.resolved_at === null && Date.now() - new Date(p.detected_at).getTime() < 7 * 86400000).length
    : 0;
  const showHealthDrop = !alertDismissed && scoreDelta !== null && scoreDelta < -3;
  const showNewIssues = !alertDismissed && !showHealthDrop && newIssueCount > 0;

  // ── Handlers ──
  const flash = (msg: string) => { setStatusMsg(msg); setTimeout(() => setStatusMsg(null), 6000); };

  const handleReanalyze = async () => {
    if (!siteId || !token) return;
    setReanalyzing(true);
    setStatusMsg(null);
    try {
      await apiFetch(`/sites/${siteId}/pipeline`, { method: 'POST', token });
      flash('Re-analysis started. This may take 10-40 minutes.');
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Failed to start re-analysis.');
    }
    setReanalyzing(false);
  };

  const handleDownloadPdf = async () => {
    if (!siteId || !token) return;
    setDownloadingPdf(true);
    try {
      const res = await fetch(apiUrl(`/sites/${siteId}/audit-report/pdf`), { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`Failed to download PDF (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tended-audit-${currentSite?.domain ?? 'report'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Failed to download PDF.');
    }
    setDownloadingPdf(false);
  };

  // ── Loading / empty states ──
  if (healthLoading || recsLoading) return <TodaySkeleton />;
  if (!health) {
    if (siteId) return <div className="max-w-4xl mx-auto space-y-6 py-2"><PipelineProgress siteId={siteId} /></div>;
    return (
      <div className="max-w-4xl mx-auto py-12 text-center">
        <FileText size={40} className="text-brand-text-tertiary mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-brand-text mb-2">No blog connected yet</h2>
        <p className="text-sm text-brand-text-muted mb-6 max-w-md mx-auto">
          Connect your blog to see your content health score, find issues, and get prioritized recommendations.
        </p>
        <Link href="/onboarding" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-accent text-white font-semibold text-sm hover:bg-brand-accent-hover transition-colors" aria-label="Start onboarding">
          Analyze my blog <ArrowRight size={14} />
        </Link>
      </div>
    );
  }

  const lastAnalyzed = currentSite?.last_crawl_at ? fmtDate(currentSite.last_crawl_at) : 'Analysis complete';

  let healthContext: string;
  if (scoreDelta !== null && scoreDelta > 0 && prevDate) {
    healthContext = `Up ${scoreDelta} points since ${fmtDate(prevDate)}. Your fixes are working.`;
  } else if (scoreDelta !== null && scoreDelta < 0 && prevDate) {
    healthContext = `Down ${Math.abs(scoreDelta)} points since ${fmtDate(prevDate)}.${newIssueCount > 0 ? ` ${newIssueCount} new issues detected.` : ''}`;
  } else {
    healthContext = `Based on content analysis of ${health.total_posts} posts.`;
  }

  const timelineItems = completedRecs.slice(0, 3).map((rec) => ({
    label: rec.title,
    date: fmtDate(rec.updated_at),
  }));

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-2">
      {siteId && <PipelineProgress siteId={siteId} />}

      {/* 1. Alert Banner */}
      {showHealthDrop && (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30">
          <div className="flex items-center gap-3">
            <AlertTriangle size={16} className="text-red-500 flex-shrink-0" />
            <p className="text-sm text-brand-text">
              Health score dropped <span className="font-semibold text-red-500">{Math.abs(scoreDelta!)} points</span> since last analysis.
            </p>
          </div>
          <button onClick={() => setAlertDismissed(true)} className="text-brand-text-tertiary hover:text-brand-text-muted transition-colors flex-shrink-0" aria-label="Dismiss alert"><X size={16} /></button>
        </div>
      )}
      {showNewIssues && (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/30">
          <div className="flex items-center gap-3">
            <AlertTriangle size={16} className="text-amber-500 flex-shrink-0" />
            <p className="text-sm text-brand-text">
              <span className="font-semibold text-amber-500">{newIssueCount} new issue{newIssueCount !== 1 ? 's' : ''}</span> detected.
            </p>
          </div>
          <button onClick={() => setAlertDismissed(true)} className="text-brand-text-tertiary hover:text-brand-text-muted transition-colors flex-shrink-0" aria-label="Dismiss alert"><X size={16} /></button>
        </div>
      )}

      {/* 2. Header Row */}
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-brand-text">Today</h1>
          {siteId && (
            <div className="flex items-center gap-2">
              <button onClick={() => void handleReanalyze()} disabled={reanalyzing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-brand-text bg-brand-surface border border-brand-border hover:border-brand-border-hover hover:bg-brand-surface-hover transition-colors disabled:opacity-50"
                aria-label="Re-analyze content">
                <RefreshCw size={12} className={reanalyzing ? 'animate-spin' : ''} />
                {reanalyzing ? 'Re-analyzing...' : 'Re-analyze'}
              </button>
              <button onClick={() => void handleDownloadPdf()} disabled={downloadingPdf}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-brand-text bg-brand-surface border border-brand-border hover:border-brand-border-hover hover:bg-brand-surface-hover transition-colors disabled:opacity-50"
                aria-label="Download PDF report">
                <Download size={12} className={downloadingPdf ? 'animate-pulse' : ''} />
                {downloadingPdf ? 'Downloading...' : 'Download PDF'}
              </button>
            </div>
          )}
        </div>
        <p className="text-xs text-brand-text-tertiary mt-1">Last analyzed: {lastAnalyzed}</p>
      </div>

      {statusMsg && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-brand-accent/5 border border-brand-accent/20 text-sm text-brand-text">{statusMsg}</div>
      )}

      {/* 3. Health Score Card + Sparkline */}
      <div className={CARD}>
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-4">
              <span className="text-5xl font-bold" style={{ color: scoreColor(currentScore) }}>{currentScore}</span>
              {scoreDelta !== null && scoreDelta !== 0 ? (
                <span className={`text-lg font-semibold ${scoreDelta > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {scoreDelta > 0 ? `\u2191${scoreDelta}` : `\u2193${Math.abs(scoreDelta)}`}
                </span>
              ) : (
                <span className="text-lg font-semibold text-brand-text-tertiary">&mdash;</span>
              )}
            </div>
            <p className="text-sm font-medium text-brand-text-muted mt-1">Content Health Score ({scoreLabel(currentScore)})</p>
            <p className="text-xs text-brand-text-tertiary mt-1">{healthContext}</p>
          </div>
          {sparklineData && (
            <div className="w-[120px] h-[48px] flex-shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparklineData}>
                  <Line type="monotone" dataKey="score" stroke={scoreColor(currentScore)} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Analysis Diff Card */}
      {showDiff && analysisDiff && (
        <div className={`${CARD} space-y-3`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 size={16} className="text-brand-accent" />
              <h3 className="text-sm font-semibold text-brand-text">{retention.diffTitle}</h3>
            </div>
            <button onClick={() => setDiffDismissed(true)} className="text-brand-text-tertiary hover:text-brand-text-muted transition-colors" aria-label={retention.diffDismiss}><X size={14} /></button>
          </div>
          {analysisDiff.score_before !== null && analysisDiff.score_after !== null && analysisDiff.score_delta !== null && (
            <p className="text-sm text-brand-text font-medium">
              {retention.diffScoreChange(Math.round(analysisDiff.score_before), Math.round(analysisDiff.score_after), Math.round(analysisDiff.score_delta))}
            </p>
          )}
          {analysisDiff.improvements.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-green-500 mb-1 flex items-center gap-1"><CheckCircle size={12} /> {retention.diffImprovements}</p>
              <ul className="text-xs text-brand-text-muted space-y-0.5 pl-4">
                {analysisDiff.improvements.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}
          {analysisDiff.new_issues.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-amber-500 mb-1 flex items-center gap-1"><AlertTriangle size={12} /> {retention.diffNewIssues}</p>
              <ul className="text-xs text-brand-text-muted space-y-0.5 pl-4">
                {analysisDiff.new_issues.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}
          {analysisDiff.factor_changes.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-brand-text-muted mb-1">{retention.diffFactorChanges}</p>
              <div className="space-y-1">
                {analysisDiff.factor_changes.slice(0, 4).map((fc) => (
                  <div key={fc.factor} className="flex items-center gap-2 text-xs">
                    {fc.delta > 0 ? <TrendingUp size={12} className="text-green-500" /> : <TrendingDown size={12} className="text-red-500" />}
                    <span className="text-brand-text-muted capitalize">{fc.factor.replace(/_/g, ' ')}</span>
                    <span className="text-brand-text-tertiary">{fc.before.toFixed(0)} &rarr; {fc.after.toFixed(0)}</span>
                    <span className={`font-semibold ${fc.delta > 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {fc.delta > 0 ? '+' : ''}{fc.delta.toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 4. Four Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={CARD}>
          <p className={`text-2xl font-bold ${scoreTw(aiReadyPct)}`}>{aiReadyPct}% AI-Ready</p>
          <p className="text-xs text-brand-text-tertiary mt-1">of your {aiTotalScored} posts</p>
        </div>
        <div className={CARD}>
          <p className="text-2xl font-bold text-red-500">{problemCount} Issue{problemCount !== 1 ? 's' : ''}</p>
          <p className="text-xs text-green-500 mt-1">{resolvedProblems} resolved</p>
        </div>
        <div className={CARD}>
          <p className="text-2xl font-bold text-amber-500">{pendingRecs.length} Pending</p>
          <p className="text-xs text-brand-text-tertiary mt-1">{completedTotal} of {totalRecs} completed ({completedPct}%)</p>
        </div>
        <div className={CARD}>
          <p className="text-2xl font-bold text-brand-text">{cannibPairCount} Pair{cannibPairCount !== 1 ? 's' : ''}</p>
          <p className="text-xs text-brand-text-tertiary mt-1">{cannibPostCount} posts with overlap</p>
        </div>
      </div>

      {/* 5. What to Do Next */}
      <section>
        <h2 className="text-lg font-semibold text-brand-text mb-3">What to Do Next</h2>
        {topRecs.length === 0 ? (
          <div className={`${CARD} text-center`}>
            <p className="text-sm text-brand-text-muted">All recommendations completed. Re-analyze to find new improvements.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {topRecs.map((rec, i) => <RecCard key={rec.id} rec={rec} index={i + 1} />)}
          </div>
        )}
      </section>

      {/* 6. Your Progress */}
      <section>
        <h2 className="text-lg font-semibold text-brand-text mb-3">Your Progress</h2>
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-brand-text">{completedTotal} of {totalRecs} recommendations completed</p>
            <span className="text-sm font-semibold text-brand-text">{completedPct}%</span>
          </div>
          <div className="w-full h-2.5 rounded-full bg-brand-border overflow-hidden">
            <div className="h-full rounded-full bg-green-500 transition-all duration-500" style={{ width: `${completedPct}%` }} />
          </div>
          {estCompleted > 0 && estPoints > 0 && (
            <p className="mt-2 text-xs text-green-500 flex items-center gap-1.5">
              <TrendingUp size={12} />
              {retention.estimatedImpact(Math.round(estPoints))}
            </p>
          )}
          <div className="mt-4 space-y-2">
            {timelineItems.map((item, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-text-tertiary flex-shrink-0" />
                <span className="text-xs text-brand-text-muted flex-1">{item.label}</span>
                <span className="text-xs text-brand-text-tertiary">{item.date}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 7. Bottom Row (2 columns) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Cluster Health */}
        <div className={CARD}>
          <h3 className="text-sm font-semibold text-brand-text mb-3">Cluster Health</h3>
          {sortedClusters.length === 0 ? (
            <p className="text-xs text-brand-text-tertiary">No clusters with health data yet.</p>
          ) : (
            <div className="space-y-2.5">
              {sortedClusters.map((cluster) => (
                <Link key={cluster.id} href={`/clusters?id=${cluster.id}`} className="flex items-center gap-3 group" aria-label={`View cluster ${cluster.label ?? 'Unnamed'}`}>
                  <span className="text-xs text-brand-text-muted truncate flex-1 group-hover:text-brand-text transition-colors">{cluster.label ?? 'Unnamed cluster'}</span>
                  <span className="text-xs font-semibold min-w-[32px] text-right" style={{ color: scoreColor(cluster.health_score) }}>{Math.round(cluster.health_score)}</span>
                  <div className="w-16 h-1.5 rounded-full bg-brand-border overflow-hidden flex-shrink-0">
                    <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(cluster.health_score, 100)}%`, backgroundColor: scoreColor(cluster.health_score) }} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Connect GA4 / Analytics status */}
        {!ga4Connected ? (
          <div className={CARD}>
            <div className="flex items-center gap-2 mb-2">
              {completedTotal >= 5 ? <BarChart3 size={16} className="text-brand-accent" /> : <Settings size={16} className="text-brand-text-muted" />}
              <h3 className="text-sm font-semibold text-brand-text">
                {completedTotal >= 5 ? retention.ga4CtaEnhancedTitle : 'Connect GA4'}
              </h3>
            </div>
            <p className="text-sm text-brand-text-muted mb-3">
              {completedTotal >= 5
                ? retention.ga4CtaEnhanced(completedTotal)
                : 'Connect Google Analytics for deeper insights.'}
            </p>
            {completedTotal < 5 && (
              <ul className="text-xs text-brand-text-tertiary space-y-1 mb-4 list-disc list-inside">
                <li>Track real traffic impact of your changes</li>
                <li>Identify declining posts before they lose rankings</li>
              </ul>
            )}
            <Link href="/settings" className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-accent hover:text-brand-accent-hover transition-colors" aria-label="Go to settings to connect GA4">
              {retention.ga4CtaConnect} <ArrowRight size={12} />
            </Link>
          </div>
        ) : (
          <div className={CARD}>
            <h3 className="text-sm font-semibold text-brand-text mb-2">Analytics Connected</h3>
            <p className="text-xs text-brand-text-tertiary">GA4 is active. Traffic data is being used to enhance your health scores and recommendations.</p>
          </div>
        )}
      </div>
    </div>
  );
}
