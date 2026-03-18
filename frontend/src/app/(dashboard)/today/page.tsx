'use client';

import { useState } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useSiteHealth, useRecommendations, useAIScores } from '@/lib/hooks/useApi';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import Link from 'next/link';
import { mutate } from 'swr';
import {
  ArrowRight,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  Zap,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react';
import type { Recommendation } from '@/lib/types';

const PRIORITY_COLOR: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#64748b',
};

const REC_TYPE_LABEL: Record<string, string> = {
  merge:                  'Merge posts',
  expand:                 'Expand content',
  interlink:              'Add internal links',
  add_schema:             'Add schema markup',
  improve_ai_citability:  'Boost AI citability',
  strengthen_eeat:        'Strengthen E-E-A-T',
  improve_ai_structure:   'Improve AI structure',
  rewrite:                'Rewrite post',
  redirect:               'Set up redirect',
  seo_fix:                'SEO fix',
};

function HealthRing({ score }: { score: number }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color = score >= 70 ? '#22c55e' : score >= 45 ? '#eab308' : '#ef4444';

  return (
    <div className="relative flex items-center justify-center score-animate" style={{ width: 140, height: 140 }}>
      <svg width={140} height={140} className="-rotate-90">
        <circle cx={70} cy={70} r={r} fill="none" stroke="#1e293b" strokeWidth={10} />
        <circle
          cx={70} cy={70} r={r} fill="none"
          stroke={color} strokeWidth={10}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeLinecap="round"
          className="ring-animate"
          style={{ transition: 'stroke-dasharray 1s ease-out' }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-4xl font-bold" style={{ color }}>{score}</div>
        <div className="text-xs text-[#64748b] mt-0.5">/ 100</div>
      </div>
    </div>
  );
}

const CONFIDENCE_STYLE: Record<string, { label: string; cls: string }> = {
  high:     { label: 'High confidence', cls: 'text-[#22c55e] bg-[#22c55e]/10' },
  medium:   { label: 'Worth investigating', cls: 'text-[#eab308] bg-[#eab308]/10' },
  low:      { label: 'Moderate confidence', cls: 'text-[#94a3b8] bg-[#94a3b8]/10' },
};

function PriorityCard({ rec, index }: { rec: Recommendation; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);
  const color = PRIORITY_COLOR[rec.priority] ?? '#64748b';
  const conf = rec.confidence ? CONFIDENCE_STYLE[rec.confidence] ?? CONFIDENCE_STYLE.medium : null;

  return (
    <div
      className="rounded-xl border bg-[#111827] overflow-hidden transition-colors hover:border-[#334155] card-in"
      style={{ borderColor: index === 0 ? color + '40' : '#1e293b', animationDelay: `${index * 60}ms` }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-3 p-4 text-left"
      >
        {/* Priority indicator */}
        <div className="flex-shrink-0 mt-0.5 flex flex-col items-center gap-1">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
          {index === 0 && (
            <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color }}>
              #{index + 1}
            </span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ backgroundColor: color + '20', color }}>
              {rec.priority}
            </span>
            <span className="text-xs text-[#64748b]">
              {REC_TYPE_LABEL[rec.recommendation_type] ?? rec.recommendation_type}
            </span>
          </div>
          <p className="text-sm font-medium text-[#e2e8f0] mt-1.5 leading-snug">{rec.title}</p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {rec.estimated_effort_hours != null && (
              <div className="flex items-center gap-1 text-xs text-[#64748b]">
                <Clock size={11} />
                <span>{rec.estimated_effort_hours}h effort</span>
              </div>
            )}
            {conf && (
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${conf.cls}`}>
                {conf.label}
              </span>
            )}
          </div>
        </div>
        <div className="flex-shrink-0 text-[#64748b]">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-[#1e293b]">
          <p className="text-sm text-[#94a3b8] mt-3 leading-relaxed">{rec.summary}</p>
          {rec.specific_actions.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {rec.specific_actions.map((action, i) => (
                <div key={i} className="flex items-start gap-2">
                  <CheckCircle2 size={13} className="flex-shrink-0 mt-0.5 text-[#22c55e]" />
                  <span className="text-xs text-[#94a3b8]">{action}</span>
                </div>
              ))}
            </div>
          )}
          <Link
            href="/explore?tab=recommendations"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-[#22c55e] hover:text-[#16a34a] transition-colors"
          >
            View full recommendation <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </div>
  );
}

export default function TodayPage() {
  const { currentSite } = useSite();
  const { data: health, isLoading: healthLoading } = useSiteHealth(currentSite?.id ?? null);
  const { data: recsData, isLoading: recsLoading } = useRecommendations(
    currentSite?.id ?? null,
    { status: 'pending' }
  );
  const { data: aiScores } = useAIScores(currentSite?.id ?? null);
  const { session } = useAuth();
  const token = session?.access_token ?? (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const isLoading = healthLoading || recsLoading;

  const topRecs = recsData?.recommendations?.slice(0, 5) ?? [];
  const totalRecs = recsData?.total ?? 0;
  const criticalCount = recsData?.by_priority?.critical ?? 0;
  const highCount = recsData?.by_priority?.high ?? 0;
  const urgentCount = criticalCount + highCount;

  const handleRunAIScan = async () => {
    if (!currentSite?.id || !token) return;
    try {
      await apiFetch(`/sites/${currentSite.id}/intelligence/ai-readiness`, {
        method: 'POST',
        token: token ?? undefined,
      });
      setTimeout(() => {
        void mutate(`/sites/${currentSite.id}/intelligence/ai-scores`);
      }, 120_000);
    } catch { /* background task */ }
  };

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 py-2">
        {/* Hero skeleton */}
        <div className="flex items-center gap-8 p-6 rounded-2xl bg-[#111827] border border-[#1e293b]">
          <div className="skeleton w-[140px] h-[140px] rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-3">
            <div className="skeleton h-3 w-24 rounded" />
            <div className="skeleton h-7 w-3/4 rounded" />
            <div className="skeleton h-4 w-1/2 rounded" />
            <div className="flex gap-6 mt-2">
              {[1,2,3,4].map(i => <div key={i} className="skeleton h-10 w-14 rounded" />)}
            </div>
          </div>
        </div>
        {/* Cards skeleton */}
        {[1,2,3].map(i => (
          <div key={i} className="skeleton h-20 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (!health) {
    return (
      <div className="max-w-3xl mx-auto space-y-4 py-2">
        {/* Demo banner */}
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#22c55e]/5 border border-[#22c55e]/20">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#22c55e]">Demo</span>
            <p className="text-sm text-[#94a3b8]">
              Showing Close.com — 958 posts analyzed. Connect your blog to see your own data.
            </p>
          </div>
          <Link
            href="/onboarding"
            className="flex-shrink-0 text-xs font-medium text-[#22c55e] hover:text-[#16a34a] transition-colors ml-4"
          >
            Analyze my blog →
          </Link>
        </div>

        {/* Demo health hero */}
        <div className="flex items-center gap-8 p-6 rounded-2xl bg-[#111827] border border-[#1e293b]">
          <HealthRing score={45} />
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-1">Content Health · Demo</p>
            <h1 className="text-2xl font-bold text-[#e2e8f0] leading-tight">
              958 posts across 31 topic clusters.
            </h1>
            <p className="text-sm text-[#64748b] mt-1.5">
              <span className="text-[#f97316] font-medium">200+ urgent issues</span>
              {' '}need attention · 724 total actions
            </p>
            <div className="flex flex-wrap gap-4 mt-4">
              {[
                { v: 724, l: 'Active', c: '#e2e8f0' },
                { v: 200, l: 'Cannibalizing', c: '#f97316' },
                { v: 179, l: 'Orphans', c: '#64748b' },
                { v: 0,   l: 'Schema markup', c: '#ef4444' },
              ].map(({ v, l, c }) => (
                <div key={l} className="text-center">
                  <div className="text-xl font-bold" style={{ color: c }}>{v}</div>
                  <div className="text-[11px] text-[#64748b]">{l}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Demo CTA */}
        <div className="text-center py-8">
          <p className="text-[#64748b] text-sm mb-4">
            This is a live analysis of Close.com&apos;s blog. Your site may look very different.
          </p>
          <Link
            href="/onboarding"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#22c55e] text-[#0a0f1a] font-semibold text-sm hover:bg-[#16a34a] transition-colors"
          >
            Analyze my blog <ArrowRight size={14} />
          </Link>
          <p className="mt-3 text-xs text-[#334155]">
            🔒 Read-only — we never modify your content
          </p>
        </div>
      </div>
    );
  }

  const healthScore = Math.round(health.content_health_score);

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-2">
      {/* ── Hero: Health score + site summary ── */}
      <div className="flex items-center gap-8 p-6 rounded-2xl bg-[#111827] border border-[#1e293b]">
        <HealthRing score={healthScore} />
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-1">
            Content Health
          </p>
          <h1 className="text-2xl font-bold text-[#e2e8f0] leading-tight">
            {health.total_posts} posts across {health.clusters?.length ?? 0} topic clusters.
          </h1>
          <p className="text-sm text-[#64748b] mt-1.5">
            {urgentCount > 0 ? (
              <>
                <span className="text-[#f97316] font-medium">{urgentCount} urgent issues</span>
                {' '}need attention · {totalRecs} total actions
              </>
            ) : (
              `${totalRecs} actions available · no critical issues`
            )}
          </p>
          {/* Quick stats row */}
          <div className="flex flex-wrap gap-4 mt-4">
            <div className="text-center">
              <div className="text-xl font-bold text-[#e2e8f0]">{health.active_posts}</div>
              <div className="text-[11px] text-[#64748b]">Active</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-[#f97316]">{health.cannibalistic_posts}</div>
              <div className="text-[11px] text-[#64748b]">Cannibalizing</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-[#64748b]">{health.dead_posts}</div>
              <div className="text-[11px] text-[#64748b]">Dead weight</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-[#e2e8f0]">
                {health.content_efficiency_ratio.toFixed(1)}%
              </div>
              <div className="text-[11px] text-[#64748b]">Efficient</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── AI Readiness nudge (if not scanned or low score) ── */}
      {aiScores && aiScores.total_scored > 0 && (aiScores.pct_ai_ready ?? 0) < 10 && (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/20">
          <div className="flex items-center gap-3">
            <Zap size={16} className="text-amber-400 flex-shrink-0" />
            <p className="text-sm text-[#e2e8f0]">
              Only{' '}
              <span className="font-semibold text-amber-400">
                {(aiScores.pct_ai_ready ?? 0).toFixed(0)}%
              </span>{' '}
              of posts are AI-ready — zero schema markup detected.
            </p>
          </div>
          <Link href="/explore?tab=recommendations&type=add_schema"
            className="flex-shrink-0 text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors ml-4">
            Fix this →
          </Link>
        </div>
      )}

      {!aiScores || aiScores.total_scored === 0 ? (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#1e293b]/60 border border-[#1e293b]">
          <div className="flex items-center gap-3">
            <Zap size={16} className="text-amber-400 flex-shrink-0" />
            <p className="text-sm text-[#94a3b8]">
              AI readiness not scanned — see how your posts score for AI citations and schema.
            </p>
          </div>
          <button
            onClick={() => void handleRunAIScan()}
            className="flex-shrink-0 text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors ml-4"
          >
            Run scan →
          </button>
        </div>
      ) : null}

      {/* ── Priority Actions ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={15} className="text-[#22c55e]" />
            <h2 className="text-sm font-semibold text-[#e2e8f0]">Your top priorities</h2>
          </div>
          <Link
            href="/explore?tab=recommendations"
            className="text-xs text-[#64748b] hover:text-[#22c55e] transition-colors flex items-center gap-1"
          >
            All {totalRecs} actions <ArrowRight size={11} />
          </Link>
        </div>

        {topRecs.length === 0 ? (
          <Card>
            <div className="text-center py-6">
              <CheckCircle2 size={32} className="text-[#22c55e] mx-auto mb-3" />
              <p className="text-sm font-medium text-[#e2e8f0]">All caught up</p>
              <p className="text-xs text-[#64748b] mt-1">No pending high-priority actions right now.</p>
            </div>
          </Card>
        ) : (
          <div className="space-y-3">
            {topRecs.map((rec, i) => (
              <PriorityCard key={rec.id} rec={rec} index={i} />
            ))}
          </div>
        )}
      </div>

      {/* ── Alert tray ── */}
      {urgentCount > 0 && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b]">
          <AlertTriangle size={15} className="text-[#ef4444] flex-shrink-0" />
          <p className="text-sm text-[#94a3b8]">
            {criticalCount > 0 && (
              <span className="text-[#ef4444] font-medium">{criticalCount} critical · </span>
            )}
            {highCount > 0 && (
              <span className="text-[#f97316] font-medium">{highCount} high priority · </span>
            )}
            <Link href="/explore?tab=recommendations" className="hover:text-[#e2e8f0] transition-colors">
              View all issues →
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}
