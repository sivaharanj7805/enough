'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { usePostDetail, usePostProblems, usePostRecommendations } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import {
  ArrowLeft,
  ExternalLink,
  Calendar,
  FileText,
  AlertTriangle,
  Lightbulb,
  Link2,
  BarChart3,
  Search,
  Eye,
  MousePointerClick,
  TrendingUp,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { SEVERITY_COLORS } from '@/lib/constants';
import type { Recommendation } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { useCallback } from 'react';
import { mutate } from 'swr';

// ─── Recommendation Card ─────────────────────────
function RecommendationCard({
  rec,
  siteId,
  token,
}: {
  rec: Recommendation;
  siteId: string;
  token?: string;
}) {
  const priorityColor =
    rec.priority === 'critical' ? SEVERITY_COLORS.critical
    : rec.priority === 'high' ? SEVERITY_COLORS.high
    : rec.priority === 'medium' ? SEVERITY_COLORS.medium
    : SEVERITY_COLORS.low;

  const typeLabels: Record<string, string> = {
    expand: '📝 Expand',
    optimize: '🔧 Optimize',
    merge: '🔀 Merge',
    interlink: '🔗 Interlink',
    update: '🔄 Update',
    growth: '🌱 Growth',
  };

  const handleStatusUpdate = useCallback(
    async (status: string) => {
      try {
        await apiFetch(`/sites/${siteId}/intelligence/recommendations/${rec.id}/status`, {
          method: 'PATCH',
          body: JSON.stringify({ status }),
          token,
        });
        // Revalidate
        mutate((key: unknown) => Array.isArray(key) && typeof key[0] === 'string' && key[0].includes('recommendations'));
      } catch {
        // Silently fail — will show stale status
      }
    },
    [siteId, rec.id, token]
  );

  return (
    <Card className="!p-4 relative">
      <div className="flex items-start gap-3">
        <div className="mt-1 rounded-lg p-1.5" style={{ backgroundColor: `${priorityColor}15` }}>
          <Lightbulb size={16} style={{ color: priorityColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge color={priorityColor}>{rec.priority}</Badge>
            <span className="text-xs text-brand-text-muted">
              {typeLabels[rec.recommendation_type] || rec.recommendation_type}
            </span>
            {rec.estimated_effort_hours && (
              <span className="text-xs text-brand-text-muted">
                ~{rec.estimated_effort_hours}h effort
              </span>
            )}
          </div>
          <h4 className="text-sm font-medium text-brand-text mt-2">{rec.title}</h4>
          <p className="text-sm text-brand-text-muted mt-1">{rec.summary}</p>

          {/* Action Items */}
          {rec.specific_actions.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted">Action Items</p>
              {rec.specific_actions.map((action, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-brand-text">
                  <span className="text-brand-accent mt-0.5">•</span>
                  <span>{action}</span>
                </div>
              ))}
            </div>
          )}

          {/* AI Generated Content Preview */}
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
              </div>
            );
          })()}

          {/* Status Actions */}
          <div className="mt-3 flex items-center gap-2">
            {rec.status === 'pending' && (
              <>
                <button
                  onClick={() => void handleStatusUpdate('in_progress')}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                >
                  <Clock size={12} /> Start
                </button>
                <button
                  onClick={() => void handleStatusUpdate('dismissed')}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-brand-surface-hover text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  <XCircle size={12} /> Dismiss
                </button>
              </>
            )}
            {rec.status === 'in_progress' && (
              <button
                onClick={() => void handleStatusUpdate('completed')}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
              >
                <CheckCircle size={12} /> Mark Done
              </button>
            )}
            {rec.status === 'completed' && (
              <Badge color="#22c55e">✓ Completed</Badge>
            )}
            {rec.status === 'dismissed' && (
              <Badge color="#6b7280">Dismissed</Badge>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ─── Metric Box ──────────────────────────────────
function MetricBox({
  icon: Icon,
  label,
  value,
  subtext,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subtext?: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-brand-bg p-3 border border-brand-border/50">
      <div className="rounded-lg p-2" style={{ backgroundColor: `${color}15` }}>
        <Icon size={16} style={{ color }} />
      </div>
      <div>
        <p className="text-xs text-brand-text-muted">{label}</p>
        <p className="text-sm font-bold text-brand-text">{value}</p>
        {subtext && <p className="text-xs text-brand-text-muted">{subtext}</p>}
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

  if (postLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <p className="text-brand-text-muted">Post not found</p>
        <Link href="/posts" className="text-sm text-brand-accent mt-2">← Back to posts</Link>
      </div>
    );
  }

  const problems = problemsSummary?.problems || [];
  const recommendations = recs || [];

  // GSC summary
  const gscMetrics = post.gsc_metrics || [];
  const totalClicks = gscMetrics.reduce((sum, m) => sum + m.clicks, 0);
  const totalImpressions = gscMetrics.reduce((sum, m) => sum + m.impressions, 0);
  const avgPosition = gscMetrics.length > 0
    ? gscMetrics.reduce((sum, m) => sum + (m.avg_position || 0), 0) / gscMetrics.length
    : null;
  const avgCTR = totalImpressions > 0 ? (totalClicks / totalImpressions) * 100 : 0;

  // GA4 summary
  const ga4Metrics = post.ga4_metrics || [];
  const totalPageviews = ga4Metrics.reduce((sum, m) => sum + m.pageviews, 0);
  const avgBounce = ga4Metrics.length > 0
    ? ga4Metrics.reduce((sum, m) => sum + m.bounce_rate, 0) / ga4Metrics.length
    : null;
  const avgEngagement = ga4Metrics.length > 0
    ? ga4Metrics.reduce((sum, m) => sum + m.avg_engagement_time_seconds, 0) / ga4Metrics.length
    : null;

  // Internal links
  const internalLinks = post.internal_links || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Back + Header */}
      <div>
        <Link href="/posts" className="inline-flex items-center gap-1 text-sm text-brand-text-muted hover:text-brand-text mb-4">
          <ArrowLeft size={14} /> Back to posts
        </Link>

        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-brand-text line-clamp-2">
              {post.title || 'Untitled'}
            </h1>
            <div className="flex items-center gap-4 mt-2 text-sm text-brand-text-muted">
              {post.url && (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 hover:text-brand-accent truncate max-w-[400px]"
                >
                  <ExternalLink size={12} /> {post.url}
                </a>
              )}
              {post.publish_date && (
                <span className="flex items-center gap-1">
                  <Calendar size={12} />
                  {new Date(post.publish_date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                </span>
              )}
              {post.word_count && (
                <span className="flex items-center gap-1">
                  <FileText size={12} /> {post.word_count.toLocaleString()} words
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <MetricBox icon={Eye} label="Pageviews" value={totalPageviews > 0 ? totalPageviews.toLocaleString() : '—'} color="#3b82f6" />
        <MetricBox icon={MousePointerClick} label="Clicks" value={totalClicks > 0 ? totalClicks.toLocaleString() : '—'} color="#22c55e" />
        <MetricBox icon={Search} label="Impressions" value={totalImpressions > 0 ? totalImpressions.toLocaleString() : '—'} color="#8b5cf6" />
        <MetricBox icon={TrendingUp} label="Avg Position" value={avgPosition ? avgPosition.toFixed(1) : '—'} color="#f97316" />
        <MetricBox icon={BarChart3} label="CTR" value={avgCTR > 0 ? `${avgCTR.toFixed(1)}%` : '—'} color="#06b6d4" />
        <MetricBox icon={Clock} label="Avg Time" value={avgEngagement ? `${Math.round(avgEngagement)}s` : '—'} color="#eab308" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Issues + Links */}
        <div className="space-y-6">
          {/* Detected Issues */}
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2">
                <AlertTriangle size={16} className="text-severity-high" />
                Issues ({problems.length})
              </h3>
            </div>
            {problems.length > 0 ? (
              <div className="space-y-3">
                {problems.map((problem) => (
                  <div key={problem.id} className="rounded-lg bg-brand-bg p-3 border border-brand-border/50">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge color={SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low}>
                        {problem.severity}
                      </Badge>
                      <span className="text-xs font-medium text-brand-text">
                        {problem.problem_type.replace(/_/g, ' ')}
                      </span>
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
              <p className="text-sm text-brand-text-muted text-center py-4">No issues detected ✓</p>
            )}
          </Card>

          {/* Internal Links */}
          <Card>
            <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
              <Link2 size={16} className="text-brand-accent" />
              Internal Links ({internalLinks.length})
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
              <p className="text-sm text-brand-text-muted text-center py-4">
                No internal links from this post — this is an orphan
              </p>
            )}
          </Card>

          {/* Top Queries */}
          {gscMetrics.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2 mb-4">
                <Search size={16} className="text-blue-400" />
                Top Search Queries
              </h3>
              <div className="space-y-2">
                {/* Deduplicate queries and aggregate */}
                {(() => {
                  const queryMap = new Map<string, { clicks: number; impressions: number; position: number; count: number }>();
                  for (const m of gscMetrics) {
                    const existing = queryMap.get(m.query) || { clicks: 0, impressions: 0, position: 0, count: 0 };
                    queryMap.set(m.query, {
                      clicks: existing.clicks + m.clicks,
                      impressions: existing.impressions + m.impressions,
                      position: existing.position + (m.avg_position || 0),
                      count: existing.count + 1,
                    });
                  }
                  return Array.from(queryMap.entries())
                    .map(([query, data]) => ({ query, clicks: data.clicks, impressions: data.impressions, avgPos: data.position / data.count }))
                    .sort((a, b) => b.clicks - a.clicks)
                    .slice(0, 10)
                    .map((q) => (
                      <div key={q.query} className="flex items-center justify-between text-sm">
                        <span className="text-brand-text truncate flex-1">{q.query}</span>
                        <div className="flex items-center gap-3 ml-2 shrink-0">
                          <span className="text-xs text-brand-text-muted">{q.avgPos.toFixed(1)}</span>
                          <span className="text-xs font-medium text-brand-text">{q.clicks} clicks</span>
                        </div>
                      </div>
                    ));
                })()}
              </div>
            </Card>
          )}
        </div>

        {/* Right Column: AI Recommendations */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-brand-text flex items-center gap-2">
              <Lightbulb size={20} className="text-brand-accent" />
              AI Recommendations ({recommendations.length})
            </h3>
          </div>

          {recommendations.length > 0 ? (
            <div className="space-y-4">
              {recommendations.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  rec={rec}
                  siteId={siteId!}
                  token={session?.access_token}
                />
              ))}
            </div>
          ) : (
            <Card>
              <div className="text-center py-8">
                <Lightbulb size={32} className="text-brand-text-muted mx-auto mb-2" />
                <p className="text-sm text-brand-text-muted">
                  No recommendations for this post yet.
                </p>
                <p className="text-xs text-brand-text-muted mt-1">
                  Run the intelligence pipeline to generate AI recommendations.
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
