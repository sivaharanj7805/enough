'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, LineChart, Line,
} from 'recharts';
import {
  BarChart3, TrendingUp, FileText, Layers, AlertTriangle,
  ArrowUpRight, Activity, ShieldAlert,
} from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import {
  useSiteHealth, usePosts, useClusters, useCannibalizationPairs,
  useProblems, useAIScores, useHealthHistory,
} from '@/lib/hooks/useApi';
import type { Post, SiteHealth, Cluster, ContentProblem } from '@/lib/types';

// ── Chart config ────────────────────────────────────

const COLORS = {
  blue: '#3B82F6',
  green: '#22C55E',
  amber: '#F59E0B',
  red: '#EF4444',
  purple: '#8B5CF6',
  cyan: '#06B6D4',
};

const TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: '#13151B',
    border: '1px solid #23262F',
    borderRadius: 8,
    fontSize: 12,
    color: '#E8EAED',
  },
  labelStyle: { color: '#9BA1AD' },
};

const AXIS_TICK = { fontSize: 10, fill: '#9BA1AD' };

// ── Shared components ───────────────────────────────

function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-xl bg-brand-surface border border-brand-border p-5 ${className}`}>
      <div className="h-3 w-20 bg-brand-border rounded mb-4" />
      <div className="h-8 w-24 bg-brand-border rounded" />
    </div>
  );
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-brand-border bg-brand-surface p-5 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-lg font-semibold text-brand-text">{children}</h2>;
}

function StatCard({
  label, value, icon: Icon, color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-brand-text-muted uppercase tracking-wider">{label}</span>
        <Icon size={14} className="text-brand-text-muted" />
      </div>
      <p className={`text-2xl font-bold ${color ?? 'text-brand-text'}`}>{value}</p>
    </Card>
  );
}

function EmptyStateCard({
  icon: Icon, title, description, href,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  href?: string;
}) {
  return (
    <Card className="!border-dashed flex flex-col items-center text-center gap-3 py-8">
      <div className="w-10 h-10 rounded-full bg-brand-accent/10 flex items-center justify-center">
        <Icon size={18} className="text-brand-accent" />
      </div>
      <h3 className="text-sm font-semibold text-brand-text">{title}</h3>
      <p className="text-xs text-brand-text-muted max-w-xs">{description}</p>
      {href && (
        <Link
          href={href}
          className="mt-1 text-xs font-medium text-brand-accent hover:text-brand-accent-hover transition-colors flex items-center gap-1"
        >
          Go to Settings <ArrowUpRight size={12} />
        </Link>
      )}
    </Card>
  );
}

function scoreColor(score: number): string {
  if (score >= 60) return 'text-brand-success';
  if (score >= 40) return 'text-brand-warning';
  return 'text-brand-critical';
}

function barFill(score: number): string {
  if (score >= 60) return COLORS.green;
  if (score >= 40) return COLORS.amber;
  return COLORS.red;
}

// ── Data derivation hooks ───────────────────────────

function useHealthFactors(health: SiteHealth | undefined) {
  return useMemo(() => {
    if (!health) return [];
    return [
      { factor: 'Overall Health', value: Math.round(health.content_health_score ?? 0), max: 100 },
      { factor: 'Efficiency', value: Math.min(100, Math.round(health.content_efficiency_ratio ?? 0)), max: 100 },
      { factor: 'Active Ratio', value: health.total_posts > 0 ? Math.round((health.active_posts / health.total_posts) * 100) : 0, max: 100 },
      { factor: 'Data Coverage', value: Math.round((health.data_completeness ?? 0) * 100), max: 100 },
      { factor: 'Date Coverage', value: Math.round((health.modified_date_coverage ?? 0) * 100), max: 100 },
      { factor: 'AI Enriched', value: health.total_posts > 0 ? Math.min(100, Math.round((health.ai_enriched_count / health.total_posts) * 100)) : 0, max: 100 },
    ];
  }, [health]);
}

function useContentRoles(health: SiteHealth | undefined) {
  return useMemo(() => {
    if (!health || health.total_posts === 0) return [];
    return [
      { role: 'Active', count: health.active_posts, fill: COLORS.green },
      { role: 'Passive', count: health.passive_posts, fill: COLORS.amber },
      { role: 'Cannibalistic', count: health.cannibalistic_posts, fill: COLORS.red },
      { role: 'Dead Weight', count: health.dead_posts, fill: COLORS.purple },
    ];
  }, [health]);
}

function useTopClusters(clusters: Cluster[] | undefined) {
  return useMemo(() => {
    if (!clusters) return [];
    return clusters
      .filter(c => c.label)
      .sort((a, b) => b.post_count - a.post_count)
      .slice(0, 8)
      .map(c => ({
        label: c.label ?? 'Unnamed',
        posts: c.post_count,
        score: Math.round(c.health_score ?? 0),
      }));
  }, [clusters]);
}

function useProblemSummary(problems: ContentProblem[] | undefined) {
  return useMemo(() => {
    if (!problems || problems.length === 0) return [];
    const counts: Record<string, number> = {};
    problems.forEach(p => {
      counts[p.problem_type] = (counts[p.problem_type] || 0) + 1;
    });
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 8)
      .map(([type, count]) => ({ type, count }));
  }, [problems]);
}

function usePublishingVelocity(posts: Post[]) {
  return useMemo(() => {
    const months: Record<string, number> = {};
    posts.forEach(p => {
      const d = p.publish_date || p.created_at;
      if (d) {
        const key = d.slice(0, 7);
        months[key] = (months[key] || 0) + 1;
      }
    });
    return Object.entries(months)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-12)
      .map(([month, count]) => ({ month, count }));
  }, [posts]);
}

// ── Main Page ───────────────────────────────────────

export default function OverviewPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;

  const { data: health, isLoading: healthLoading } = useSiteHealth(siteId);
  const { data: postsData, isLoading: postsLoading } = usePosts(siteId, 200);
  const { data: clusters, isLoading: clustersLoading } = useClusters(siteId);
  const { data: cannibPairs } = useCannibalizationPairs(siteId);
  const { data: aiScores } = useAIScores(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: healthHistory } = useHealthHistory(siteId);

  const posts = postsData?.posts ?? [];
  const isLoading = healthLoading || postsLoading || clustersLoading;

  const healthFactors = useHealthFactors(health);
  const contentRoles = useContentRoles(health);
  const topClusters = useTopClusters(clusters ?? undefined);
  const problemSummary = useProblemSummary(problems ?? undefined);
  const velocity = usePublishingVelocity(posts);

  const hasGA4 = !!currentSite?.ga4_property_id;

  // ── No site selected ──
  if (!currentSite) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-12rem)] gap-4 text-center">
        <BarChart3 size={36} className="text-brand-text-muted" />
        <h2 className="text-lg font-semibold text-brand-text">No site selected</h2>
        <p className="text-sm text-brand-text-muted">Select a site from the sidebar to view analytics.</p>
      </div>
    );
  }

  // ── Loading skeleton ──
  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <div className="h-6 w-32 bg-brand-border rounded animate-pulse mb-2" />
          <div className="h-4 w-48 bg-brand-border rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonBlock key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="animate-pulse rounded-xl bg-brand-surface border border-brand-border p-5">
              <div className="h-3 w-24 bg-brand-border rounded mb-4" />
              <div className="h-40 bg-brand-border rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Empty state ──
  if (posts.length === 0 && !health) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold text-brand-text">Overview</h1>
          <p className="text-sm text-brand-text-muted mt-1">{currentSite.domain}</p>
        </div>
        <div className="flex flex-col items-center justify-center h-[calc(100vh-16rem)] gap-4 text-center">
          <BarChart3 size={36} className="text-brand-text-muted" />
          <h2 className="text-lg font-semibold text-brand-text">No data yet</h2>
          <p className="text-sm text-brand-text-muted max-w-md">
            Crawl your site to unlock content analytics. Connect Google Analytics for traffic data.
          </p>
        </div>
      </div>
    );
  }

  const healthScore = health ? Math.round(health.content_health_score) : null;
  const efficiency = health ? Math.min(100, Math.round(health.content_efficiency_ratio ?? 0)) : null;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* ── Page header ── */}
      <div>
        <h1 className="text-xl font-bold text-brand-text">Overview</h1>
        <p className="text-sm text-brand-text-muted mt-1">{currentSite.domain}</p>
      </div>

      {/* ── Top stat cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Health Score"
          value={healthScore != null ? `${healthScore}%` : '--'}
          icon={Activity}
          color={healthScore != null ? scoreColor(healthScore) : undefined}
        />
        <StatCard label="Total Posts" value={posts.length} icon={FileText} />
        <StatCard
          label="Content Efficiency"
          value={efficiency != null ? `${efficiency}%` : '--'}
          icon={TrendingUp}
        />
        <StatCard
          label="Cannibalization Pairs"
          value={cannibPairs?.length ?? '--'}
          icon={ShieldAlert}
        />
      </div>

      {/* ── Health breakdown ── */}
      {healthFactors.length > 0 && (
        <Card>
          <SectionTitle>Health Breakdown</SectionTitle>
          <div className="mt-4 space-y-3">
            {healthFactors.map(f => (
              <div key={f.factor} className="flex items-center gap-3">
                <span className="text-xs text-brand-text-muted w-28 shrink-0">{f.factor}</span>
                <div className="flex-1 h-2 bg-brand-border rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, f.value)}%`,
                      backgroundColor: barFill(f.value),
                    }}
                  />
                </div>
                <span className={`text-xs font-semibold w-10 text-right ${scoreColor(f.value)}`}>
                  {f.value}%
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── Two-column: Content distribution + Cluster performance ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Content distribution */}
        {contentRoles.length > 0 && (
          <Card>
            <SectionTitle>Content Distribution</SectionTitle>
            <div className="mt-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={contentRoles}>
                  <XAxis dataKey="role" tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Posts">
                    {contentRoles.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {health && (
              <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                {contentRoles.map(r => (
                  <div key={r.role}>
                    <p className="text-lg font-bold text-brand-text">{r.count}</p>
                    <p className="text-[10px] text-brand-text-muted uppercase tracking-wider">{r.role}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {/* Cluster performance */}
        {topClusters.length > 0 ? (
          <Card>
            <SectionTitle>Cluster Performance</SectionTitle>
            <div className="mt-4 overflow-y-auto max-h-80">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-brand-text-muted border-b border-brand-border">
                    <th className="pb-2 text-left font-medium">Cluster</th>
                    <th className="pb-2 text-right font-medium">Posts</th>
                    <th className="pb-2 text-right font-medium">Health</th>
                  </tr>
                </thead>
                <tbody>
                  {topClusters.map(c => (
                    <tr key={c.label} className="border-b border-brand-border/50 hover:bg-brand-surface-hover transition-colors">
                      <td className="py-2.5 text-brand-text break-words">{c.label}</td>
                      <td className="py-2.5 text-brand-text-secondary text-right">{c.posts}</td>
                      <td className={`py-2.5 text-right font-semibold ${scoreColor(c.score)}`}>
                        {c.score}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          <Card className="flex items-center justify-center">
            <div className="text-center py-6">
              <Layers size={24} className="mx-auto text-brand-text-muted mb-2" />
              <p className="text-sm text-brand-text-muted">No clusters detected yet</p>
            </div>
          </Card>
        )}
      </div>

      {/* ── Traffic data / GA4 empty state ── */}
      {!hasGA4 && (
        <EmptyStateCard
          icon={BarChart3}
          title="Connect Google Analytics for traffic data"
          description="See pageviews, sessions, engagement metrics, and traffic trends across your content."
          href="/settings"
        />
      )}

      {/* ── Two-column: Problem summary + Publishing velocity ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Problem summary */}
        {problemSummary.length > 0 ? (
          <Card>
            <SectionTitle>Issues Detected</SectionTitle>
            <div className="mt-4 space-y-2.5">
              {problemSummary.map(p => (
                <div key={p.type} className="flex items-center gap-3">
                  <AlertTriangle size={12} className="text-brand-warning shrink-0" />
                  <span className="text-sm text-brand-text capitalize flex-1 truncate">
                    {p.type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-sm font-semibold text-brand-text tabular-nums">{p.count}</span>
                </div>
              ))}
            </div>
          </Card>
        ) : (
          <Card className="flex items-center justify-center">
            <div className="text-center py-6">
              <AlertTriangle size={24} className="mx-auto text-brand-text-muted mb-2" />
              <p className="text-sm text-brand-text-muted">No problems detected</p>
            </div>
          </Card>
        )}

        {/* Publishing velocity */}
        {velocity.length > 0 ? (
          <Card>
            <SectionTitle>Publishing Velocity</SectionTitle>
            <div className="mt-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={velocity}>
                  <XAxis dataKey="month" tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="count" fill={COLORS.purple} radius={[4, 4, 0, 0]} name="Posts" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        ) : (
          <Card className="flex items-center justify-center">
            <div className="text-center py-6">
              <FileText size={24} className="mx-auto text-brand-text-muted mb-2" />
              <p className="text-sm text-brand-text-muted">No publish date data available</p>
            </div>
          </Card>
        )}
      </div>

      {/* ── AI Readiness ── */}
      {aiScores && aiScores.total_scored > 0 && (
        <Card>
          <SectionTitle>AI Readiness</SectionTitle>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            {([
              { label: 'Citability', value: aiScores.avg_citability },
              { label: 'E-E-A-T', value: aiScores.avg_eeat },
              { label: 'Schema', value: aiScores.avg_schema },
              { label: 'Extraction', value: aiScores.avg_extraction },
            ] as const).map(({ label, value }) => {
              const v = Math.round(value ?? 0);
              return (
                <div key={label} className="text-center rounded-lg bg-brand-bg p-4">
                  <p className={`text-2xl font-bold ${scoreColor(v)}`}>{v}</p>
                  <p className="text-xs text-brand-text-muted mt-1">{label}</p>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ── Health history ── */}
      {healthHistory && healthHistory.length > 1 && (
        <Card>
          <SectionTitle>Health Score Over Time</SectionTitle>
          <div className="mt-4 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={[...healthHistory]
                  .sort((a, b) => new Date(a.analyzed_at ?? 0).getTime() - new Date(b.analyzed_at ?? 0).getTime())
                  .map(h => ({
                    date: h.analyzed_at
                      ? new Date(h.analyzed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                      : '?',
                    score: Math.round(h.score),
                  }))}
              >
                <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tick={AXIS_TICK} tickLine={false} axisLine={false} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke={COLORS.blue}
                  strokeWidth={2}
                  dot={{ fill: COLORS.blue, r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </div>
  );
}
