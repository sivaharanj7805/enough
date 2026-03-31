'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useState, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { usePostDetail, usePostProblems, usePostRecommendations, useCannibalizationPairs } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  ArrowLeft, ExternalLink, Calendar, FileText, AlertTriangle,
  Lightbulb, Link2, BarChart3, Search, Eye, MousePointerClick,
  TrendingUp, Clock, CheckCircle, XCircle, ChevronDown, ChevronUp,
  Image, BookOpen, Globe, Zap, Shield, Layers, GitCompare, Info, RefreshCw,
} from 'lucide-react';
import { SEVERITY_COLORS } from '@/lib/constants';
import type { Recommendation } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { mutate } from 'swr';
import { getHealthLabel, TOOLTIPS, EMPTY_STATES } from '@/lib/copy';

/* ── Section Header ───────────────────────────── */
function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold text-brand-text uppercase tracking-wider mb-3">
      {children}
    </h3>
  );
}

/* ── Health Factor Bar ────────────────────────── */
function HealthFactor({ name, score, weight, icon: Icon, tooltip }: {
  name: string; score: number | null; weight: number; icon: React.ElementType; tooltip: string;
}) {
  const isNull = score === null;
  const s = score ?? 0;
  const color = isNull ? '#5f6571' : s >= 70 ? '#22c55e' : s >= 40 ? '#f59e0b' : '#ef4444';
  const [showTip, setShowTip] = useState(false);

  return (
    <div className="relative">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <Icon size={13} style={{ color }} />
          <span className="text-xs text-brand-text">{name}</span>
          <button
            onMouseEnter={() => setShowTip(true)}
            onMouseLeave={() => setShowTip(false)}
            className="text-brand-text-muted hover:text-brand-text"
            aria-label={`Info about ${name}`}
          >
            <Info size={10} />
          </button>
        </div>
        {isNull ? (
          <span className="text-xs text-brand-text-muted">
            Not scored
            <span className="text-[10px] font-normal ml-1">({weight}%)</span>
          </span>
        ) : (
          <span className="text-xs font-semibold tabular-nums" style={{ color }}>
            {score}
            <span className="text-[10px] text-brand-text-muted font-normal ml-1">({weight}%)</span>
          </span>
        )}
      </div>
      {isNull ? (
        <div className="h-1.5 rounded-full border border-dashed border-brand-border bg-transparent flex items-center justify-center">
          <span className="text-[8px] text-brand-text-muted leading-none">Requires AI analysis</span>
        </div>
      ) : (
        <div className="h-1.5 rounded-full bg-[#1A1D26] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{ width: `${s}%`, backgroundColor: color }}
          />
        </div>
      )}
      {showTip && (
        <div className="absolute z-10 top-full mt-1 left-0 bg-[#1A1D26] border border-brand-border rounded-lg p-2 text-xs text-brand-text-muted max-w-[260px] shadow-lg">
          {tooltip}
        </div>
      )}
    </div>
  );
}

/* ── Metric Row ──────────────────────────────── */
function MetricRow({ icon: Icon, label, value, color, muted }: {
  icon: React.ElementType; label: string; value: string; color: string; muted?: boolean;
}) {
  return (
    <div className="flex justify-between items-center py-3 border-b border-brand-border">
      <div className="flex items-center gap-2">
        <Icon size={16} style={{ color }} className="shrink-0" />
        <span className="text-sm text-brand-text-muted">{label}</span>
      </div>
      <span className={`text-lg font-bold tabular-nums ${muted ? 'text-brand-text-muted' : 'text-brand-text'}`}>
        {value}
      </span>
    </div>
  );
}

/* ── Character Count Indicator ────────────────── */
function CharCount({ text, min, max }: { text: string; min: number; max: number }) {
  const len = text.length;
  const color = len >= min && len <= max ? 'text-green-400' : len > max || len < min * 0.7 ? 'text-red-400' : 'text-amber-400';
  return (
    <span className={`text-xs font-medium ${color}`}>
      {len} chars {len >= min && len <= max ? '\u2713' : `(ideal: ${min}\u2013${max})`}
    </span>
  );
}

/* ── Recommendation Card ──────────────────────── */
function RecommendationCard({ rec, siteId, token }: {
  rec: Recommendation; siteId: string; token?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const priorityColor =
    rec.priority === 'critical' ? SEVERITY_COLORS.critical
    : rec.priority === 'high' ? SEVERITY_COLORS.high
    : rec.priority === 'medium' ? SEVERITY_COLORS.medium
    : SEVERITY_COLORS.low;

  const typeLabels: Record<string, string> = {
    expand: 'Expand', optimize: 'Optimize', merge: 'Merge',
    interlink: 'Interlink', update: 'Update', differentiate: 'Differentiate',
  };

  const handleStatusUpdate = useCallback(async (status: string) => {
    try {
      await apiFetch(`/sites/${siteId}/intelligence/recommendations/${rec.id}/status`, {
        method: 'PATCH', body: JSON.stringify({ status }), token,
      });
      mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
    } catch { /* will show stale status */ }
  }, [siteId, rec.id, token]);

  return (
    <div className="rounded-xl border border-brand-border bg-brand-surface overflow-hidden">
      <div className="border-l-[3px] p-4" style={{ borderLeftColor: priorityColor }}>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge color={priorityColor}>{rec.priority}</Badge>
          <span className="text-xs text-brand-text-muted">{typeLabels[rec.recommendation_type] || rec.recommendation_type}</span>
          {rec.estimated_effort_hours && (
            <span className="text-xs text-brand-text-muted">~{rec.estimated_effort_hours}h</span>
          )}
        </div>
        <h4 className="text-sm font-medium text-brand-text mt-2">{rec.title}</h4>
        <p className="text-sm text-brand-text-muted mt-1 leading-relaxed">{rec.summary}</p>

        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs text-brand-accent mt-3 hover:underline"
          aria-label={expanded ? 'Collapse details' : 'Expand details'}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Collapse' : 'View Full Plan'}
        </button>

        {expanded && (
          <div className="mt-3 space-y-3 pt-3 border-t border-brand-border/50">
            {rec.specific_actions.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
                {rec.specific_actions.map((action, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-brand-text">
                    <span className="text-brand-accent mt-0.5">&bull;</span><span>{action}</span>
                  </div>
                ))}
              </div>
            )}
            {rec.ai_generated_content && Object.keys(rec.ai_generated_content).length > 0 && (() => {
              const ai = rec.ai_generated_content as Record<string, string>;
              return (
                <div className="rounded-lg bg-[#1A1D26] p-3 border border-brand-border/50">
                  <p className="text-xs font-medium text-brand-text-muted mb-1">AI-Generated Content</p>
                  {ai.meta_description && <p className="text-xs text-brand-text italic">Meta: &quot;{ai.meta_description}&quot;</p>}
                  {ai.suggested_title && <p className="text-xs text-brand-text mt-1">Title: &quot;{ai.suggested_title}&quot;</p>}
                </div>
              );
            })()}
          </div>
        )}

        <div className="mt-3 flex items-center gap-2 flex-wrap">
          {rec.status === 'pending' && (<>
            <button onClick={() => void handleStatusUpdate('in_progress')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors" aria-label="Start"><Clock size={12} /> Start</button>
            <button onClick={() => void handleStatusUpdate('completed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors" aria-label="Done"><CheckCircle size={12} /> Done</button>
            <button onClick={() => void handleStatusUpdate('dismissed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Dismiss"><XCircle size={12} /> Dismiss</button>
          </>)}
          {rec.status === 'in_progress' && (
            <button onClick={() => void handleStatusUpdate('completed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors" aria-label="Done"><CheckCircle size={12} /> Done</button>
          )}
          {rec.status === 'completed' && <Badge color="#22c55e">Completed</Badge>}
          {rec.status === 'dismissed' && <Badge color="#6b7280">Dismissed</Badge>}
        </div>
      </div>
    </div>
  );
}

/* ── Loading Skeleton ─────────────────────────── */
function PostDetailSkeleton() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-pulse">
      <div><Skeleton variant="text" className="w-28 h-4 mb-4" /><Skeleton variant="text" className="w-96 h-7" /><Skeleton variant="text" className="w-64 h-4 mt-2" /></div>
      <Skeleton variant="rectangular" className="h-44 rounded-xl" />
      <Skeleton variant="rectangular" className="h-48 rounded-xl" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4"><Skeleton variant="rectangular" className="h-48 rounded-xl" /><Skeleton variant="rectangular" className="h-32 rounded-xl" /></div>
        <div className="lg:col-span-2 space-y-4"><Skeleton variant="rectangular" className="h-40 rounded-xl" /><Skeleton variant="rectangular" className="h-40 rounded-xl" /></div>
      </div>
    </div>
  );
}

/* ── Main Page ────────────────────────────────── */
export default function PostDetailPage() {
  const params = useParams<{ postId: string }>();
  const { currentSite } = useSite();
  const { session } = useAuth();
  const siteId = currentSite?.id ?? null;
  const postId = params?.postId ?? null;

  const { data: post, isLoading: postLoading } = usePostDetail(siteId, postId);
  const { data: problemsSummary } = usePostProblems(siteId, postId);
  const { data: recs } = usePostRecommendations(siteId, postId);
  const { data: cannibPairs } = useCannibalizationPairs(siteId);

  if (postLoading) return <PostDetailSkeleton />;

  if (!post) return (
    <div className="flex flex-col items-center justify-center h-64">
      <FileText size={40} className="text-brand-text-muted mb-3" />
      <p className="text-lg font-semibold text-brand-text">{EMPTY_STATES.postNotFound.title}</p>
      <p className="text-sm text-brand-text-muted mt-1">{EMPTY_STATES.postNotFound.description}</p>
      <Link href="/posts" className="text-sm text-brand-accent mt-4 hover:underline flex items-center gap-1"><ArrowLeft size={14} /> Back to posts</Link>
    </div>
  );

  const problems = problemsSummary?.problems || [];
  const recommendations = recs || [];
  const postCannib = (cannibPairs || []).filter(
    (p) => p.post_a.post_id === postId || p.post_b.post_id === postId
  );

  const gscMetrics = post.gsc_metrics || [];
  const totalClicks = gscMetrics.reduce((s, m) => s + m.clicks, 0);
  const totalImpressions = gscMetrics.reduce((s, m) => s + m.impressions, 0);
  const avgPosition = gscMetrics.length ? gscMetrics.reduce((s, m) => s + (m.avg_position || 0), 0) / gscMetrics.length : null;
  const avgCTR = totalImpressions > 0 ? (totalClicks / totalImpressions) * 100 : 0;
  const ga4Metrics = post.ga4_metrics || [];
  const totalPageviews = ga4Metrics.reduce((s, m) => s + m.pageviews, 0);
  const avgEngagement = ga4Metrics.length ? ga4Metrics.reduce((s, m) => s + m.avg_engagement_time_seconds, 0) / ga4Metrics.length : null;
  const hasGA4Data = ga4Metrics.length > 0;
  const hasGSCData = gscMetrics.length > 0;
  const hasAnyAnalytics = hasGA4Data || hasGSCData;

  const healthScore = post.composite_score ?? null;
  const healthLabel = healthScore !== null ? getHealthLabel(healthScore) : null;
  const scoreColor = healthScore !== null
    ? healthScore >= 80 ? '#22c55e' : healthScore >= 60 ? '#3b82f6' : healthScore >= 40 ? '#f59e0b' : healthScore >= 20 ? '#ef4444' : '#991b1b'
    : '#5f6571';

  const factors = post.factor_scores ?? undefined;
  const metaTitle = post.meta_title ?? '';
  const metaDesc = post.meta_description ?? '';
  const readability = post.readability_score ?? null;
  const gradeLevel = post.grade_level ?? null;
  const h1Count = post.h1_count ?? null;
  const h2Count = post.h2_count ?? null;
  const h3Count = post.h3_count ?? null;
  const imageCount = post.image_count ?? null;
  const pagerank = post.pagerank_score ?? null;
  const role = post.role ?? null;
  const clusterId = post.cluster_id ?? null;
  const clusterName = post.cluster_name ?? null;
  const internalLinks = post.internal_links || [];

  const roleBadgeColor = role === 'pillar' ? '#3b82f6' : role === 'dead_weight' ? '#ef4444' : '#6b7280';
  const roleLabel = role === 'pillar' ? 'Pillar' : role === 'dead_weight' ? 'Dead Weight' : role === 'supporting' ? 'Supporting' : role;

  const totalHeadings = (h1Count ?? 0) + (h2Count ?? 0) + (h3Count ?? 0);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">

      {/* ── 1. Back Button + Header ─────────────── */}
      <div>
        <Link href="/posts" className="inline-flex items-center gap-1 text-sm text-brand-text-muted hover:text-brand-text mb-3">
          <ArrowLeft size={14} /> Back to posts
        </Link>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold text-brand-text leading-tight">{post.title || 'Untitled'}</h1>
          {roleLabel && <Badge color={roleBadgeColor}>{roleLabel}</Badge>}
        </div>
        <div className="flex items-center gap-4 mt-2 text-sm text-brand-text-muted flex-wrap">
          {post.url && (
            <a href={post.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 hover:text-brand-accent truncate max-w-[400px]" aria-label="Open post URL in new tab">
              <ExternalLink size={12} /> {post.url.replace(/^https?:\/\//, '')}
            </a>
          )}
          {post.publish_date && (
            <span className="flex items-center gap-1">
              <Calendar size={12} /> {new Date(post.publish_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          )}
          {!!post.modified_date && (
            <span className="flex items-center gap-1">
              <RefreshCw size={12} /> Updated {new Date(post.modified_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          )}
          {clusterId && (
            <Link href={`/clusters/${clusterId}`} className="flex items-center gap-1 hover:text-brand-accent" aria-label="View cluster">
              <Layers size={12} /> {clusterName || 'View Cluster'}
            </Link>
          )}
        </div>
      </div>

      {/* ── 2. Health Score Card ─────────────────── */}
      <Card className="!p-5">
        <div className="flex flex-col md:flex-row gap-8">
          <div className="flex flex-col items-center justify-center md:w-44 shrink-0">
            <div className="text-5xl font-bold tabular-nums transition-colors duration-500" style={{ color: scoreColor }}>
              {healthScore !== null ? Math.round(healthScore) : '\u2014'}
            </div>
            <p className="text-sm font-medium mt-1" style={{ color: scoreColor }}>
              {healthLabel?.label || 'No data'}
            </p>
            <p className="text-xs text-brand-text-muted mt-1 text-center max-w-[180px]">
              {healthLabel?.description || TOOLTIPS.healthScore}
            </p>
          </div>
          <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
            <HealthFactor name="AI Readiness" score={factors?.ai_readiness ?? null} weight={28} icon={Zap} tooltip="AI citability, E-E-A-T, schema markup, and extraction structure. 28% of health score." />
            <HealthFactor name="Content Depth" score={factors?.content_depth ?? null} weight={20} icon={BookOpen} tooltip="Word count, heading structure, and topic coverage. 20% of health score." />
            <HealthFactor name="Content Richness" score={factors?.content_richness ?? null} weight={20} icon={FileText} tooltip="Data density, examples, and content structure. 20% of health score." />
            <HealthFactor name="Freshness" score={factors?.freshness ?? null} weight={15} icon={Clock} tooltip="How recently the content was published or updated. 15% of health score." />
            <HealthFactor name="Internal Links" score={factors?.internal_links ?? null} weight={10} icon={Link2} tooltip="Inbound and outbound internal link count. 10% of health score." />
            <HealthFactor name="Technical SEO" score={factors?.technical_seo ?? null} weight={7} icon={Shield} tooltip="Meta tags, heading hierarchy, image optimization. 7% of health score." />
          </div>
        </div>
      </Card>

      {/* ── 3. Metrics ────────────────────────────── */}
      <Card className="!p-5">
        <SectionHeader>Traffic Metrics</SectionHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
          <div>
            <MetricRow icon={Eye} label="Pageviews" value={hasGA4Data ? totalPageviews.toLocaleString() : 'No data'} color="#3b82f6" muted={!hasGA4Data} />
            <MetricRow icon={MousePointerClick} label="Clicks" value={hasGSCData ? totalClicks.toLocaleString() : 'No data'} color="#22c55e" muted={!hasGSCData} />
            <MetricRow icon={Search} label="Impressions" value={hasGSCData ? totalImpressions.toLocaleString() : 'No data'} color="#8b5cf6" muted={!hasGSCData} />
          </div>
          <div>
            <MetricRow icon={TrendingUp} label="Avg Position" value={hasGSCData && avgPosition ? avgPosition.toFixed(1) : 'No data'} color="#f97316" muted={!hasGSCData} />
            <MetricRow icon={BarChart3} label="CTR" value={hasGSCData && avgCTR > 0 ? `${avgCTR.toFixed(1)}%` : 'No data'} color="#06b6d4" muted={!hasGSCData} />
            <MetricRow icon={Clock} label="Avg Time" value={hasGA4Data && avgEngagement ? `${Math.round(avgEngagement)}s` : 'No data'} color="#eab308" muted={!hasGA4Data} />
          </div>
        </div>
        {!hasAnyAnalytics && (
          <p className="text-xs text-brand-text-muted text-center mt-4">
            No analytics data available.{' '}
            <Link href="/settings" className="text-brand-accent hover:underline">Connect Google Analytics for traffic data</Link>
          </p>
        )}
      </Card>

      {/* ── 4. Content Analysis Card ────────────── */}
      <Card className="!p-5">
        <SectionHeader>Content Analysis</SectionHeader>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div>
            <p className="text-xs text-brand-text-muted">Word Count</p>
            <p className="text-sm font-semibold text-brand-text">{post.word_count?.toLocaleString() ?? '\u2014'}</p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Headings</p>
            <p className="text-sm font-semibold text-brand-text">
              {h1Count !== null || h2Count !== null || h3Count !== null ? totalHeadings : '\u2014'}
              {totalHeadings > 0 && (
                <span className="text-xs text-brand-text-muted font-normal ml-1">
                  (H1:{h1Count ?? 0} H2:{h2Count ?? 0} H3:{h3Count ?? 0})
                </span>
              )}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Images</p>
            <p className="text-sm font-semibold text-brand-text flex items-center gap-1">
              <Image size={12} className="text-brand-text-muted" /> {imageCount !== null ? imageCount : '\u2014'}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Readability</p>
            <p className="text-sm font-semibold text-brand-text">
              {readability !== null ? `Flesch ${readability.toFixed(0)}` : '\u2014'}
              {gradeLevel !== null && <span className="text-xs text-brand-text-muted font-normal ml-1">(Grade {Math.round(gradeLevel)})</span>}
            </p>
          </div>
        </div>

        {metaTitle && (
          <div className="rounded-lg bg-[#1A1D26] p-3 border border-brand-border/50 mb-3">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-brand-text-muted">Meta Title</p>
              <CharCount text={metaTitle} min={50} max={60} />
            </div>
            <p className="text-sm text-brand-text">{metaTitle}</p>
          </div>
        )}

        {metaDesc && (
          <div className="rounded-lg bg-[#1A1D26] p-3 border border-brand-border/50">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-brand-text-muted">Meta Description</p>
              <CharCount text={metaDesc} min={150} max={160} />
            </div>
            <p className="text-sm text-brand-text">{metaDesc}</p>
          </div>
        )}

        {pagerank !== null && (
          <div className="mt-3 flex items-center gap-2 text-sm">
            <Globe size={14} className="text-brand-accent" />
            <span className="text-brand-text-muted">PageRank:</span>
            <span className="font-semibold text-brand-text">{pagerank.toFixed(2)}</span>
          </div>
        )}
      </Card>

      {/* ── 5. Two-Column Layout ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left Column: Issues, Links, Cannibalization */}
        <div className="space-y-6">

          {/* Issues */}
          <Card className="!p-5">
            <SectionHeader><span className="flex items-center gap-2"><AlertTriangle size={14} className="text-severity-high" /> Issues ({problems.length})</span></SectionHeader>
            {problems.length > 0 ? (<div className="space-y-2">
              {problems.map((problem) => {
                const sevColor = SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low;
                return (
                  <div key={problem.id} className="rounded-lg bg-[#1A1D26] p-3 border border-brand-border/50">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: sevColor }} />
                      <Badge color={sevColor}>{problem.severity}</Badge>
                      <span className="text-xs text-brand-text truncate">{problem.problem_type.replace(/_/g, ' ')}</span>
                    </div>
                    {problem.details && (
                      <p className="text-xs text-brand-text-muted mt-1 line-clamp-2">
                        {(problem.details as Record<string, unknown>).issue ? String((problem.details as Record<string, unknown>).issue) : JSON.stringify(problem.details).slice(0, 200)}
                      </p>
                    )}
                  </div>);
              })}
            </div>) : (
              <p className="text-sm text-brand-text-muted text-center py-4">{EMPTY_STATES.issuesNone.description}</p>
            )}
          </Card>

          {/* Internal Links */}
          <Card className="!p-5">
            <SectionHeader><span className="flex items-center gap-2"><Link2 size={14} className="text-brand-accent" /> Internal Links</span></SectionHeader>
            <div className="flex items-center gap-4 mb-3">
              <div className="text-center"><p className="text-lg font-bold text-brand-text">{internalLinks.length}</p><p className="text-xs text-brand-text-muted">Outbound</p></div>
              <div className="w-px h-8 bg-brand-border" />
              <div className="text-center"><p className="text-lg font-bold text-brand-text-muted">&mdash;</p><p className="text-xs text-brand-text-muted">Inbound</p></div>
            </div>
            {internalLinks.length > 0 ? (
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {internalLinks.map((link, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-brand-accent mt-0.5 shrink-0">&rarr;</span>
                    <div className="min-w-0"><p className="text-brand-text truncate text-xs">{link.anchor_text || 'No anchor text'}</p><p className="text-[11px] text-brand-text-muted truncate">{link.target_url}</p></div>
                  </div>
                ))}
              </div>
            ) : (<p className="text-xs text-brand-text-muted text-center">No outbound internal links detected</p>)}
          </Card>

          {/* Cannibalization */}
          <Card className="!p-5">
            <SectionHeader><span className="flex items-center gap-2"><GitCompare size={14} className="text-amber-400" /> Cannibalization ({postCannib.length})</span></SectionHeader>
            {postCannib.length > 0 ? (<div className="space-y-2">
              {postCannib.map((pair) => {
                const isA = pair.post_a.post_id === postId;
                return (
                  <div key={pair.id} className="rounded-lg bg-[#1A1D26] p-3 border border-brand-border/50">
                    <div className="flex items-center justify-between gap-2">
                      <Link href={`/posts/${isA ? pair.post_b.post_id : pair.post_a.post_id}`} className="text-sm text-brand-accent hover:underline truncate">{(isA ? pair.post_b.title : pair.post_a.title) || 'Unknown post'}</Link>
                      <span className="text-xs font-semibold text-amber-400 shrink-0">{Math.round((pair.overlap_score || 0) * 100)}%</span>
                    </div>
                    <Badge color={SEVERITY_COLORS[pair.severity as keyof typeof SEVERITY_COLORS] || '#6b7280'} className="mt-1">{pair.severity}</Badge>
                  </div>);
              })}
              <Link href="/cannibalization" className="text-xs text-brand-accent hover:underline block text-center mt-2" aria-label="View all cannibalization pairs">View all pairs &rarr;</Link>
            </div>) : (
              <p className="text-sm text-brand-text-muted text-center py-4">{EMPTY_STATES.cannibalization.description}</p>
            )}
          </Card>
        </div>

        {/* Right Column: Recommendations */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-brand-accent" />
            <SectionHeader>Recommendations ({recommendations.length})</SectionHeader>
          </div>
          {recommendations.length > 0 ? (<div className="space-y-3">
            {recommendations.map((rec) => (<RecommendationCard key={rec.id} rec={rec} siteId={siteId!} token={session?.access_token} />))}
          </div>) : (
            <Card className="!p-5">
              <div className="text-center py-8"><Lightbulb size={32} className="text-brand-text-muted mx-auto mb-2" /><p className="text-sm text-brand-text-muted">{EMPTY_STATES.recommendations.description}</p></div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
