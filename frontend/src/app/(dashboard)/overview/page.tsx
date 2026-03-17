'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import {
  useSiteHealth,
  useClusters,
  useCannibalizationPairs,
  useProblems,
  useRecommendations,
} from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ProgressBar } from '@/components/ui/ProgressBar';
import {
  AlertTriangle,
  FileText,
  Layers,
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Zap,
  Target,
  ArrowRight,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';
import { SEVERITY_COLORS, ROLE_COLORS, ROLE_LABELS } from '@/lib/constants';
import type { PostRole } from '@/lib/constants';

// ─── Health Score Ring ───────────────────────────
function HealthRing({ score, size = 160 }: { score: number; size?: number }) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color =
    score >= 75 ? '#22c55e' : score >= 50 ? '#eab308' : score >= 25 ? '#f97316' : '#ef4444';
  const label =
    score >= 75 ? 'Healthy' : score >= 50 ? 'Moderate' : score >= 25 ? 'At Risk' : 'Critical';

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#1f2937"
          strokeWidth={8}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-3xl font-bold text-brand-text">{Math.round(score)}</div>
        <div className="text-xs font-medium" style={{ color }}>
          {label}
        </div>
      </div>
    </div>
  );
}

// ─── Stat Card ───────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  subtext,
  color,
  href,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subtext?: string;
  color: string;
  href?: string;
}) {
  const content = (
    <Card className="group relative overflow-hidden hover:border-brand-border-hover transition-all duration-200">
      <div className="absolute inset-0 opacity-5" style={{ background: `linear-gradient(135deg, ${color}, transparent)` }} />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">{label}</p>
          <p className="mt-2 text-2xl font-bold text-brand-text">{value}</p>
          {subtext && <p className="mt-1 text-xs text-brand-text-muted">{subtext}</p>}
        </div>
        <div className="rounded-lg p-2" style={{ backgroundColor: `${color}15` }}>
          <Icon size={20} style={{ color }} />
        </div>
      </div>
      {href && (
        <div className="mt-3 flex items-center gap-1 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity" style={{ color }}>
          View details <ArrowRight size={12} />
        </div>
      )}
    </Card>
  );

  return href ? <Link href={href}>{content}</Link> : content;
}

// ─── Issue Breakdown Bar ─────────────────────────
function IssueBreakdown({
  problems,
}: {
  problems: Array<{ problem_type: string; severity: string }>;
}) {
  const grouped = useMemo(() => {
    const map: Record<string, { count: number; critical: number; high: number }> = {};
    for (const p of problems) {
      if (!map[p.problem_type]) map[p.problem_type] = { count: 0, critical: 0, high: 0 };
      map[p.problem_type].count++;
      if (p.severity === 'critical') map[p.problem_type].critical++;
      if (p.severity === 'high') map[p.problem_type].high++;
    }
    return Object.entries(map).sort((a, b) => b[1].count - a[1].count);
  }, [problems]);

  const typeLabels: Record<string, string> = {
    seo_no_images: 'Missing Images',
    seo_title_length: 'Title Length',
    seo_missing_meta: 'Missing Meta',
    seo_no_internal_links: 'No Internal Links',
    thin_content: 'Thin Content',
    thin_below_cluster_avg: 'Below Average',
    readability_too_complex: 'Hard to Read',
    orphan: 'Orphan Pages',
    content_decay: 'Content Decay',
    proxy_decay: 'Stale Content',
    velocity_decline: 'Publishing Decline',
  };

  return (
    <div className="space-y-3">
      {grouped.slice(0, 8).map(([type, data]) => (
        <div key={type}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-brand-text">{typeLabels[type] || type.replace(/_/g, ' ')}</span>
            <div className="flex items-center gap-2">
              {data.critical > 0 && <Badge color={SEVERITY_COLORS.critical}>{data.critical} critical</Badge>}
              {data.high > 0 && <Badge color={SEVERITY_COLORS.high}>{data.high} high</Badge>}
              <span className="text-sm font-medium text-brand-text-muted">{data.count}</span>
            </div>
          </div>
          <div className="h-1.5 w-full rounded-full bg-brand-surface-hover overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(100, (data.count / (grouped[0]?.[1].count || 1)) * 100)}%`,
                backgroundColor: data.critical > 0 ? SEVERITY_COLORS.critical : data.high > 0 ? SEVERITY_COLORS.high : SEVERITY_COLORS.medium,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Role Distribution ───────────────────────────
function RoleDistribution({
  active,
  passive,
  cannibal,
  dead,
  total,
}: {
  active: number;
  passive: number;
  cannibal: number;
  dead: number;
  total: number;
}) {
  const roles: Array<{ key: PostRole; count: number }> = [
    { key: 'pillar', count: active },
    { key: 'supporter', count: passive },
    { key: 'competitor', count: cannibal },
    { key: 'dead_weight', count: dead },
  ];

  return (
    <div className="space-y-3">
      {roles.map(({ key, count }) => (
        <div key={key} className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: ROLE_COLORS[key] }} />
          <span className="text-sm text-brand-text flex-1">{ROLE_LABELS[key]}</span>
          <span className="text-sm font-medium text-brand-text">{count}</span>
          <span className="text-xs text-brand-text-muted w-10 text-right">
            {total > 0 ? `${Math.round((count / total) * 100)}%` : '0%'}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Recommendation Summary ──────────────────────
function RecommendationSummary({
  byType,
  byPriority,
  total,
}: {
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  total: number;
}) {
  const typeLabels: Record<string, { label: string; icon: React.ElementType; color: string }> = {
    expand: { label: 'Expand Content', icon: FileText, color: '#3b82f6' },
    optimize: { label: 'SEO Optimization', icon: Target, color: '#8b5cf6' },
    merge: { label: 'Merge Posts', icon: Layers, color: '#f97316' },
    differentiate: { label: 'Differentiate Content', icon: Shield, color: '#ec4899' },
    interlink: { label: 'Add Internal Links', icon: Zap, color: '#22c55e' },
    redirect: { label: 'Redirect Duplicates', icon: ArrowRight, color: '#ef4444' },
    update: { label: 'Update Content', icon: Clock, color: '#eab308' },
    growth: { label: 'Growth Opportunity', icon: TrendingUp, color: '#06b6d4' },
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-severity-critical" />
          <span className="text-xs text-brand-text-muted">{byPriority.critical || 0} critical</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-severity-high" />
          <span className="text-xs text-brand-text-muted">{byPriority.high || 0} high</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-severity-medium" />
          <span className="text-xs text-brand-text-muted">{byPriority.medium || 0} medium</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(byType).map(([type, count]) => {
          const info = typeLabels[type] || { label: type, icon: FileText, color: '#6b7280' };
          return (
            <div key={type} className="flex items-center gap-2 rounded-lg bg-brand-surface-hover/50 px-3 py-2">
              <info.icon size={14} style={{ color: info.color }} />
              <span className="text-xs text-brand-text">{info.label}</span>
              <span className="ml-auto text-xs font-medium" style={{ color: info.color }}>{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Quick Actions ───────────────────────────────
function QuickActions() {
  const actions = [
    { label: 'View Critical Issues', href: '/issues?severity=critical', icon: AlertTriangle, color: '#ef4444' },
    { label: 'Start Action Queue', href: '/actions', icon: CheckCircle, color: '#22c55e' },
    { label: 'View Posts List', href: '/posts', icon: FileText, color: '#3b82f6' },
    { label: 'Explore Clusters', href: '/clusters', icon: Layers, color: '#8b5cf6' },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {actions.map((a) => (
        <Link
          key={a.href}
          href={a.href}
          className="flex items-center gap-3 rounded-lg border border-brand-border bg-brand-surface p-3 hover:border-brand-border-hover hover:bg-brand-surface-hover transition-all duration-200"
        >
          <div className="rounded-lg p-1.5" style={{ backgroundColor: `${a.color}15` }}>
            <a.icon size={16} style={{ color: a.color }} />
          </div>
          <span className="text-sm font-medium text-brand-text">{a.label}</span>
        </Link>
      ))}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────
export default function OverviewPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;

  const { data: health, isLoading: healthLoading } = useSiteHealth(siteId);
  const { data: clusters } = useClusters(siteId);
  const { data: cannPairs } = useCannibalizationPairs(siteId);
  const { data: problems } = useProblems(siteId);
  const { data: recs } = useRecommendations(siteId);

  if (healthLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!health) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center">
        <div className="rounded-full bg-brand-surface-hover p-6 mb-4">
          <Layers size={48} className="text-brand-text-muted" />
        </div>
        <h2 className="text-xl font-semibold text-brand-text">No data yet</h2>
        <p className="mt-2 text-brand-text-muted max-w-md">
          Connect a site and run the intelligence pipeline to see your content ecosystem overview.
        </p>
      </div>
    );
  }

  const criticalProblems = (problems || []).filter((p) => p.severity === 'critical').length;
  const highProblems = (problems || []).filter((p) => p.severity === 'high').length;
  const totalProblems = (problems || []).length;
  const totalCannPairs = (cannPairs || []).length;
  const totalRecs = recs?.total || 0;
  const pendingRecs = (recs?.recommendations || []).filter((r) => r.status === 'pending').length;
  const completedRecs = (recs?.recommendations || []).filter((r) => r.status === 'completed').length;
  const efficiency = health.content_efficiency_ratio;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-text">
            {currentSite?.name || currentSite?.domain || 'Site Overview'}
          </h1>
          <p className="text-sm text-brand-text-muted mt-1">
            {health.total_posts} posts analyzed · {clusters?.length || 0} topic clusters · Last updated {currentSite?.last_crawl_at ? new Date(currentSite.last_crawl_at).toLocaleDateString() : 'never'}
          </p>
        </div>
      </div>

      {/* Row 1: Health Score + Key Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Health Score Hero */}
        <Card className="lg:col-span-2 flex flex-col items-center justify-center py-8">
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-4">
            Content Health Score
          </p>
          <HealthRing score={health.content_health_score} size={180} />
          {health.data_completeness < 1.0 && (
            <div className="mt-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <p className="text-xs text-amber-400 text-center">
                Based on {Math.round(health.data_completeness * 100)}% of signals — Connect GSC for full scoring
              </p>
            </div>
          )}
          {health.ai_enriched_count > 0 && (
            <div className="mt-2 px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20">
              <p className="text-xs text-purple-400 text-center">
                ✦ {health.ai_enriched_count} recommendations have AI-powered guidance
              </p>
            </div>
          )}
          {health.modified_date_coverage > 0 && (
            <div className="mt-2 px-3 py-1.5 rounded-lg bg-brand-surface-hover border border-brand-border/50">
              <p className="text-xs text-brand-text-muted text-center">
                Freshness data: {Math.round(health.modified_date_coverage * 100)}% of posts
              </p>
            </div>
          )}
          <div className="mt-4 flex items-center gap-2">
            <span className="text-sm text-brand-text-muted">Content Efficiency:</span>
            <span className="text-sm font-bold text-brand-text">
              {(efficiency * 100).toFixed(0)}%
            </span>
          </div>
        </Card>

        {/* Key Metric Cards */}
        <div className="lg:col-span-3 grid grid-cols-2 gap-4">
          <StatCard
            icon={FileText}
            label="Total Posts"
            value={health.total_posts}
            subtext={`${health.active_posts} active · ${health.dead_posts} need attention`}
            color="#3b82f6"
            href="/posts"
          />
          <StatCard
            icon={Layers}
            label="Clusters"
            value={clusters?.length || 0}
            subtext={`${health.clusters?.length || 0} topic areas identified`}
            color="#8b5cf6"
            href="/clusters"
          />
          <StatCard
            icon={AlertTriangle}
            label="Issues Found"
            value={totalProblems}
            subtext={`${criticalProblems} critical · ${highProblems} high priority`}
            color={criticalProblems > 0 ? '#ef4444' : '#eab308'}
            href="/issues"
          />
          <StatCard
            icon={Target}
            label="Cannibalization"
            value={totalCannPairs}
            subtext={totalCannPairs > 0 ? 'Posts competing with each other' : 'No conflicts found'}
            color="#f97316"
            href="/cannibalization"
          />
        </div>
      </div>

      {/* Row 2: Role Distribution + Issue Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Post Health Distribution */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">Post Health Distribution</h3>
            <Link href="/posts" className="text-xs text-brand-accent hover:text-brand-accent-hover">
              View all →
            </Link>
          </div>
          <RoleDistribution
            active={health.active_posts}
            passive={health.passive_posts}
            cannibal={health.cannibalistic_posts}
            dead={health.dead_posts}
            total={health.total_posts}
          />
        </Card>

        {/* Issue Breakdown */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">Issue Breakdown</h3>
            <Link href="/issues" className="text-xs text-brand-accent hover:text-brand-accent-hover">
              View all →
            </Link>
          </div>
          {problems && problems.length > 0 ? (
            <IssueBreakdown problems={problems} />
          ) : (
            <p className="text-sm text-brand-text-muted py-4 text-center">No issues detected</p>
          )}
        </Card>
      </div>

      {/* Row 3: Recommendations + Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AI Recommendations */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">AI Recommendations</h3>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <CheckCircle size={14} className="text-green-500" />
                <span className="text-xs text-brand-text-muted">{completedRecs} done</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Clock size={14} className="text-yellow-500" />
                <span className="text-xs text-brand-text-muted">{pendingRecs} pending</span>
              </div>
              <Link href="/actions" className="text-xs text-brand-accent hover:text-brand-accent-hover">
                Action Queue →
              </Link>
            </div>
          </div>
          {recs && recs.total > 0 ? (
            <>
              <ProgressBar
                value={completedRecs}
                max={totalRecs}
                className="mb-4"
              />
              <RecommendationSummary
                byType={recs.by_type}
                byPriority={recs.by_priority}
                total={recs.total}
              />
            </>
          ) : (
            <p className="text-sm text-brand-text-muted py-4 text-center">
              No recommendations yet. Run the intelligence pipeline first.
            </p>
          )}
        </Card>

        {/* Quick Actions */}
        <Card>
          <h3 className="text-sm font-semibold text-brand-text mb-4">Quick Actions</h3>
          <QuickActions />
        </Card>
      </div>

      {/* Row 4: Top Clusters Preview */}
      {clusters && clusters.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">Topic Clusters</h3>
            <Link href="/clusters" className="text-xs text-brand-accent hover:text-brand-accent-hover">
              View all →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {clusters.slice(0, 6).map((cluster) => (
              <Link
                key={cluster.id}
                href={`/clusters/${cluster.id}`}
                className="rounded-lg border border-brand-border bg-brand-bg p-4 hover:border-brand-border-hover transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-brand-text">{cluster.label || 'Unlabeled'}</p>
                    <p className="text-xs text-brand-text-muted mt-1">{cluster.post_count} posts</p>
                  </div>
                  {cluster.health_score != null && (
                    <span
                      className="text-lg font-bold"
                      style={{
                        color:
                          cluster.health_score >= 75
                            ? '#22c55e'
                            : cluster.health_score >= 50
                            ? '#eab308'
                            : '#ef4444',
                      }}
                    >
                      {Math.round(cluster.health_score)}
                    </span>
                  )}
                </div>
                {cluster.ecosystem_state && (
                  <Badge className="mt-2" color={cluster.ecosystem_state === 'forest' ? '#22c55e' : cluster.ecosystem_state === 'desert' ? '#f97316' : '#eab308'}>
                    {cluster.ecosystem_state}
                  </Badge>
                )}
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
