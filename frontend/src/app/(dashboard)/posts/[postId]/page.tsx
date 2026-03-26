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
  Image, BookOpen, Hash, Globe, Zap, Shield, Activity, RefreshCw,
  Layers, GitCompare, Info,
} from 'lucide-react';
import { SEVERITY_COLORS } from '@/lib/constants';
import type { Recommendation } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { mutate } from 'swr';
import { getHealthLabel, TOOLTIPS } from '@/lib/copy';

// ─── Health Factor Bar ─────────────────────────
function HealthFactor({ name, score, icon: Icon, tooltip }: {
  name: string; score: number | null; icon: React.ElementType; tooltip: string;
}) {
  const s = score ?? 0;
  const color = s >= 70 ? '#22c55e' : s >= 40 ? '#f59e0b' : '#ef4444';
  const [showTip, setShowTip] = useState(false);

  return (
    <div className="relative">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Icon size={14} style={{ color }} />
          <span className="text-sm text-brand-text">{name}</span>
          <button
            onMouseEnter={() => setShowTip(true)}
            onMouseLeave={() => setShowTip(false)}
            className="text-brand-text-muted hover:text-brand-text"
            aria-label={`Info about ${name}`}
          >
            <Info size={12} />
          </button>
        </div>
        <span className="text-sm font-semibold" style={{ color }}>
          {score !== null ? score : '—'}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[#1A1D26] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${s}%`, backgroundColor: color }}
        />
      </div>
      {showTip && (
        <div className="absolute z-10 top-full mt-1 left-0 bg-[#1A1D26] border border-[#23262F] rounded-lg p-2 text-xs text-brand-text-secondary max-w-[280px] shadow-lg">
          {tooltip}
        </div>
      )}
    </div>
  );
}

// ─── Recommendation Card ─────────────────────────
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
    <Card className="!p-4">
      <div className="flex items-start gap-3">
        <div className="mt-1 rounded-lg p-1.5" style={{ backgroundColor: `${priorityColor}15` }}>
          <Lightbulb size={16} style={{ color: priorityColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge color={priorityColor}>{rec.priority}</Badge>
            <span className="text-xs text-brand-text-muted">{typeLabels[rec.recommendation_type] || rec.recommendation_type}</span>
            {rec.estimated_effort_hours && (
              <span className="text-xs text-brand-text-muted">~{rec.estimated_effort_hours}h effort</span>
            )}
          </div>
          <h4 className="text-sm font-medium text-brand-text mt-2">{rec.title}</h4>
          <p className="text-sm text-brand-text-muted mt-1">{rec.summary}</p>

          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-brand-accent mt-2 hover:underline"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? 'Collapse' : 'View Full Plan'}
          </button>

          {expanded && (
            <div className="mt-3 space-y-2">
              {rec.specific_actions.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
                  {rec.specific_actions.map((action, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-brand-text">
                      <span className="text-brand-accent mt-0.5">•</span><span>{action}</span>
                    </div>
                  ))}
                </div>
              )}
              {rec.ai_generated_content && Object.keys(rec.ai_generated_content).length > 0 && (() => {
                const ai = rec.ai_generated_content as Record<string, string>;
                return (
                  <div className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                    <p className="text-xs font-medium text-brand-text-muted mb-1">AI-Generated Content</p>
                    {ai.meta_description && <p className="text-xs text-brand-text italic">Meta: &quot;{ai.meta_description}&quot;</p>}
                    {ai.suggested_title && <p className="text-xs text-brand-text mt-1">Title: &quot;{ai.suggested_title}&quot;</p>}
                  </div>
                );
              })()}
            </div>
          )}

          <div className="mt-3 flex items-center gap-2">
            {rec.status === 'pending' && (
              <>
                <button onClick={() => void handleStatusUpdate('in_progress')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors">
                  <Clock size={12} /> Start
                </button>
                <button onClick={() => void handleStatusUpdate('completed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors">
                  <CheckCircle size={12} /> Mark as Done
                </button>
                <button onClick={() => void handleStatusUpdate('dismissed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors">
                  <XCircle size={12} /> Dismiss
                </button>
              </>
            )}
            {rec.status === 'in_progress' && (
              <button onClick={() => void handleStatusUpdate('completed')} className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors">
                <CheckCircle size={12} /> Mark as Done
              </button>
            )}
            {rec.status === 'completed' && <Badge color="#22c55e">Completed</Badge>}
            {rec.status === 'dismissed' && <Badge color="#6b7280">Dismissed</Badge>}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ─── Character Count Indicator ──────────────────
function CharCount({ text, min, max }: { text: string; min: number; max: number }) {
  const len = text.length;
  const isGood = len >= min && len <= max;
  return (
    <span className={`text-xs font-medium ${isGood ? 'text-green-400' : 'text-amber-400'}`}>
      {len} chars {isGood ? '✓' : `(ideal: ${min}-${max})`}
    </span>
  );
}

// ─── Skeleton ───────────────────────────────────
function PostDetailSkeleton() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-pulse">
      <div><Skeleton variant="text" className="w-32 h-4 mb-4" /><Skeleton variant="text" className="w-96 h-7" /><Skeleton variant="text" className="w-64 h-4 mt-2" /></div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} variant="rectangular" className="h-20 rounded-lg" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-6"><Skeleton variant="rectangular" className="h-64 rounded-xl" /><Skeleton variant="rectangular" className="h-48 rounded-xl" /></div>
        <div className="lg:col-span-2 space-y-4"><Skeleton variant="rectangular" className="h-48 rounded-xl" /><Skeleton variant="rectangular" className="h-48 rounded-xl" /></div>
      </div>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────
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

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <FileText size={40} className="text-brand-text-muted mb-3" />
        <p className="text-lg font-semibold text-brand-text">Post not found</p>
        <p className="text-sm text-brand-text-muted mt-1">This post may have been removed or the URL is incorrect.</p>
        <Link href="/posts" className="text-sm text-brand-accent mt-4 hover:underline">← Back to posts</Link>
      </div>
    );
  }

  const problems = problemsSummary?.problems || [];
  const recommendations = recs || [];

  // Post cannibalization pairs
  const postCannib = (cannibPairs || []).filter(
    p => p.post_a.post_id === postId || p.post_b.post_id === postId
  );

  // GSC summary
  const gscMetrics = post.gsc_metrics || [];
  const totalClicks = gscMetrics.reduce((s, m) => s + m.clicks, 0);
  const totalImpressions = gscMetrics.reduce((s, m) => s + m.impressions, 0);
  const avgPosition = gscMetrics.length > 0 ? gscMetrics.reduce((s, m) => s + (m.avg_position || 0), 0) / gscMetrics.length : null;
  const avgCTR = totalImpressions > 0 ? (totalClicks / totalImpressions) * 100 : 0;

  // GA4 summary
  const ga4Metrics = post.ga4_metrics || [];
  const totalPageviews = ga4Metrics.reduce((s, m) => s + m.pageviews, 0);
  const avgEngagement = ga4Metrics.length > 0 ? ga4Metrics.reduce((s, m) => s + m.avg_engagement_time_seconds, 0) / ga4Metrics.length : null;

  // Internal links
  const internalLinks = post.internal_links || [];

  // Health score
  const healthScore = (post as unknown as Record<string, unknown>).composite_score as number | undefined ?? (post as unknown as Record<string, unknown>).health_score as number | undefined ?? null;
  const healthLabel = healthScore !== null ? getHealthLabel(healthScore) : null;
  const scoreColor = healthScore !== null
    ? healthScore >= 80 ? '#22c55e' : healthScore >= 60 ? '#3b82f6' : healthScore >= 40 ? '#f59e0b' : healthScore >= 20 ? '#ef4444' : '#991b1b'
    : '#5f6571';

  // Factor scores (from API or approximate)
  const factors = (post as unknown as Record<string, unknown>).factor_scores as Record<string, number> | undefined;
  const metaTitle = (post as unknown as Record<string, unknown>).meta_title as string | undefined ?? '';
  const metaDesc = (post as unknown as Record<string, unknown>).meta_description as string | undefined ?? '';
  const readability = (post as unknown as Record<string, unknown>).readability_score as number | undefined ?? null;
  const h1Count = (post as unknown as Record<string, unknown>).h1_count as number | undefined ?? null;
  const h2Count = (post as unknown as Record<string, unknown>).h2_count as number | undefined ?? null;
  const h3Count = (post as unknown as Record<string, unknown>).h3_count as number | undefined ?? null;
  const imageCount = (post as unknown as Record<string, unknown>).image_count as number | undefined ?? null;
  const pagerank = (post as unknown as Record<string, unknown>).pagerank_score as number | undefined ?? null;
  const role = (post as unknown as Record<string, unknown>).role as string | undefined ?? null;
  const clusterId = (post as unknown as Record<string, unknown>).cluster_id as string | undefined ?? null;
  const clusterName = (post as unknown as Record<string, unknown>).cluster_name as string | undefined ?? null;

  const roleBadgeColor = role === 'pillar' ? '#3b82f6' : role === 'dead_weight' ? '#ef4444' : '#6b7280';
  const roleLabel = role === 'pillar' ? 'Pillar' : role === 'dead_weight' ? 'Dead Weight' : role === 'supporting' ? 'Supporting' : role;

  const readabilityLabel = readability !== null
    ? readability > 60 ? 'Easy to read' : readability > 30 ? 'Moderate' : 'Difficult'
    : null;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Back + Header */}
      <div>
        <Link href="/posts" className="inline-flex items-center gap-1 text-sm text-brand-text-muted hover:text-brand-text mb-4">
          <ArrowLeft size={14} /> Back to posts
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-semibold text-brand-text line-clamp-2">{post.title || 'Untitled'}</h1>
              {roleLabel && <Badge color={roleBadgeColor}>{roleLabel}</Badge>}
            </div>
            <div className="flex items-center gap-4 mt-2 text-sm text-brand-text-muted flex-wrap">
              {post.url && (
                <a href={post.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 hover:text-brand-accent truncate max-w-[400px]">
                  <ExternalLink size={12} /> {post.url.replace(/^https?:\/\//, '')}
                </a>
              )}
              {post.publish_date && (
                <span className="flex items-center gap-1">
                  <Calendar size={12} /> Published {new Date(post.publish_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              )}
              {!!(post as unknown as Record<string, unknown>).modified_date && (
                <span className="flex items-center gap-1">
                  <RefreshCw size={12} /> Updated {new Date((post as unknown as Record<string, unknown>).modified_date as string).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              )}
              {clusterId && (
                <Link href={`/clusters/${clusterId}`} className="flex items-center gap-1 hover:text-brand-accent">
                  <Layers size={12} /> {clusterName || 'View Cluster'}
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Health Score + Factor Breakdown */}
      <Card>
        <div className="flex flex-col md:flex-row gap-8">
          {/* Overall Score */}
          <div className="flex flex-col items-center justify-center md:w-48 shrink-0">
            <div className="text-5xl font-bold" style={{ color: scoreColor }}>
              {healthScore !== null ? Math.round(healthScore) : '—'}
            </div>
            <div className="text-sm mt-1" style={{ color: scoreColor }}>
              {healthLabel?.label || 'No data'}
            </div>
            <p className="text-xs text-brand-text-muted mt-1 text-center max-w-[200px]">
              {healthLabel?.description || TOOLTIPS.healthScore}
            </p>
          </div>

          {/* 6-Factor Breakdown */}
          <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <HealthFactor name="Traffic" score={factors?.traffic ?? null} icon={Eye} tooltip="Based on pageviews and session data from Google Analytics." />
            <HealthFactor name="Ranking" score={factors?.ranking ?? null} icon={TrendingUp} tooltip="Based on average search position from Google Search Console." />
            <HealthFactor name="Engagement" score={factors?.engagement ?? null} icon={Activity} tooltip="Based on time on page, bounce rate, and scroll depth." />
            <HealthFactor name="Freshness" score={factors?.freshness ?? null} icon={Clock} tooltip="Based on how recently the content was published or updated." />
            <HealthFactor name="Content Depth" score={factors?.content_depth ?? null} icon={BookOpen} tooltip="Based on word count, heading structure, and topic coverage." />
            <HealthFactor name="Technical SEO" score={factors?.technical_seo ?? null} icon={Shield} tooltip="Based on meta tags, heading hierarchy, image optimization, and internal links." />
          </div>
        </div>
      </Card>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {[
          { icon: Eye, label: 'Pageviews', value: totalPageviews > 0 ? totalPageviews.toLocaleString() : '—', color: '#3b82f6' },
          { icon: MousePointerClick, label: 'Clicks', value: totalClicks > 0 ? totalClicks.toLocaleString() : '—', color: '#22c55e' },
          { icon: Search, label: 'Impressions', value: totalImpressions > 0 ? totalImpressions.toLocaleString() : '—', color: '#8b5cf6' },
          { icon: TrendingUp, label: 'Avg Position', value: avgPosition ? avgPosition.toFixed(1) : '—', color: '#f97316' },
          { icon: BarChart3, label: 'CTR', value: avgCTR > 0 ? `${avgCTR.toFixed(1)}%` : '—', color: '#06b6d4' },
          { icon: Clock, label: 'Avg Time', value: avgEngagement ? `${Math.round(avgEngagement)}s` : '—', color: '#eab308' },
        ].map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="flex items-center gap-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
            <div className="rounded-lg p-2" style={{ backgroundColor: `${color}15` }}>
              <Icon size={16} style={{ color }} />
            </div>
            <div>
              <p className="text-xs text-brand-text-muted">{label}</p>
              <p className="text-sm font-bold text-brand-text">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Content Analysis */}
      <Card>
        <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
          <FileText size={16} className="text-brand-accent" /> Content Analysis
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-brand-text-muted">Word Count</p>
            <p className="text-sm font-semibold text-brand-text">{post.word_count?.toLocaleString() ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Headings</p>
            <p className="text-sm font-semibold text-brand-text">
              {h1Count !== null || h2Count !== null || h3Count !== null
                ? `H1: ${h1Count ?? 0} · H2: ${h2Count ?? 0} · H3: ${h3Count ?? 0}`
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Images</p>
            <p className="text-sm font-semibold text-brand-text flex items-center gap-1">
              <Image size={12} /> {imageCount !== null ? imageCount : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-text-muted">Readability</p>
            <p className="text-sm font-semibold text-brand-text">
              {readability !== null ? `${readability.toFixed(0)} — ${readabilityLabel}` : '—'}
            </p>
          </div>
        </div>

        {/* Meta Title */}
        {metaTitle && (
          <div className="mt-4 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-brand-text-muted">Meta Title</p>
              <CharCount text={metaTitle} min={50} max={60} />
            </div>
            <p className="text-sm text-brand-text">{metaTitle}</p>
          </div>
        )}

        {/* Meta Description */}
        {metaDesc && (
          <div className="mt-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-brand-text-muted">Meta Description</p>
              <CharCount text={metaDesc} min={150} max={160} />
            </div>
            <p className="text-sm text-brand-text">{metaDesc}</p>
          </div>
        )}

        {/* PageRank */}
        {pagerank !== null && (
          <div className="mt-3 flex items-center gap-2 text-sm">
            <Globe size={14} className="text-brand-accent" />
            <span className="text-brand-text-muted">PageRank:</span>
            <span className="font-semibold text-brand-text">{pagerank.toFixed(2)}</span>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Issues + Links + Cannibalization */}
        <div className="space-y-6">
          {/* Detected Issues */}
          <Card>
            <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
              <AlertTriangle size={16} className="text-severity-high" /> Issues ({problems.length})
            </h3>
            {problems.length > 0 ? (
              <div className="space-y-3">
                {problems.map((problem) => (
                  <div key={problem.id} className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge color={SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low}>{problem.severity}</Badge>
                      <span className="text-xs font-medium text-brand-text">{problem.problem_type.replace(/_/g, ' ')}</span>
                    </div>
                    {problem.details && (
                      <p className="text-xs text-brand-text-muted mt-1">
                        {(problem.details as Record<string, unknown>).issue
                          ? String((problem.details as Record<string, unknown>).issue)
                          : JSON.stringify(problem.details).slice(0, 200)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-brand-text-muted text-center py-4">No problems detected on this post</p>
            )}
          </Card>

          {/* Outbound Internal Links */}
          <Card>
            <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
              <Link2 size={16} className="text-brand-accent" /> Outbound Links ({internalLinks.length})
            </h3>
            {internalLinks.length > 0 ? (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {internalLinks.map((link, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-brand-accent mt-0.5">→</span>
                    <div className="min-w-0">
                      <p className="text-brand-text truncate">{link.anchor_text || 'No anchor text'}</p>
                      <p className="text-xs text-brand-text-muted truncate">{link.target_url}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-brand-text-muted text-center py-4">No outbound internal links — this post is an orphan</p>
            )}
          </Card>

          {/* Inbound Links */}
          <Card>
            <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
              <Link2 size={16} className="text-green-400" /> Inbound Links
            </h3>
            <p className="text-sm text-brand-text-muted text-center py-4">
              Inbound link data is computed during analysis. Check the landscape view for link flow visualization.
            </p>
          </Card>

          {/* Cannibalization Warnings */}
          <Card>
            <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
              <GitCompare size={16} className="text-amber-400" /> Cannibalization ({postCannib.length})
            </h3>
            {postCannib.length > 0 ? (
              <div className="space-y-3">
                {postCannib.map((pair) => {
                  const otherTitle = pair.post_a.post_id === postId ? pair.post_b.title : pair.post_a.title;
                  const otherId = pair.post_a.post_id === postId ? pair.post_b.post_id : pair.post_a.post_id;
                  return (
                    <div key={pair.id} className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                      <div className="flex items-center justify-between mb-1">
                        <Link href={`/posts/${otherId}`} className="text-sm text-brand-accent hover:underline truncate">
                          {otherTitle || 'Unknown post'}
                        </Link>
                        <span className="text-xs font-semibold text-amber-400 shrink-0 ml-2">
                          {Math.round((pair.overlap_score || 0) * 100)}% similar
                        </span>
                      </div>
                      <Badge color={SEVERITY_COLORS[pair.severity as keyof typeof SEVERITY_COLORS] || '#6b7280'}>
                        {pair.severity}
                      </Badge>
                    </div>
                  );
                })}
                <Link href="/cannibalization" className="text-xs text-brand-accent hover:underline block text-center mt-2">
                  View all cannibalization pairs →
                </Link>
              </div>
            ) : (
              <p className="text-sm text-brand-text-muted text-center py-4">No cannibalization detected</p>
            )}
          </Card>
        </div>

        {/* Right Column: Recommendations */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="text-lg font-semibold text-brand-text flex items-center gap-2">
            <Zap size={20} className="text-brand-accent" /> Recommendations ({recommendations.length})
          </h3>

          {recommendations.length > 0 ? (
            <div className="space-y-4">
              {recommendations.map((rec) => (
                <RecommendationCard key={rec.id} rec={rec} siteId={siteId!} token={session?.access_token} />
              ))}
            </div>
          ) : (
            <Card>
              <div className="text-center py-8">
                <Lightbulb size={32} className="text-brand-text-muted mx-auto mb-2" />
                <p className="text-sm text-brand-text-muted">No recommendations for this post</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
