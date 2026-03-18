'use client';

import { use } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { Loader2, ExternalLink, AlertTriangle, Trophy, Target, Users } from 'lucide-react';

interface AuditCluster {
  label: string;
  description: string | null;
  post_count: number;
  health_score: number;
  ecosystem_state: string;
}

interface AuditCannPair {
  post_a_title: string;
  post_a_url: string;
  post_b_title: string;
  post_b_url: string;
  overlap_score: number;
  severity: string;
  recommendation: string | null;
}

interface AuditRec {
  title: string;
  summary: string | null;
  rec_type: string;
  post_title: string;
  post_url: string;
  priority: number;
}

interface AuditTopPost {
  title: string;
  url: string;
  health_score: number;
  role: string;
  issue: string | null;
}

interface AuditReport {
  site_name: string;
  site_domain: string;
  total_posts: number;
  analyzed_at: string | null;
  overall_health: number;
  cluster_count: number;
  problem_count: number;
  rec_count: number;
  cann_pair_count: number;
  orphan_count: number;
  thin_content_count: number;
  exact_duplicate_count: number;
  top_clusters: AuditCluster[];
  top_cann_pairs: AuditCannPair[];
  top_recs: AuditRec[];
  worst_posts: AuditTopPost[];
  best_posts: AuditTopPost[];
  headline: string;
  key_findings: string[];
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

const REC_TYPE_COLORS: Record<string, string> = {
  merge: '#ef4444',
  redirect: '#f97316',
  differentiate: '#eab308',
  expand: '#3b82f6',
  optimize: '#8b5cf6',
  interlink: '#22c55e',
  growth: '#06b6d4',
};

const HEALTH_COLOR = (score: number) =>
  score >= 65 ? '#22c55e' : score >= 40 ? '#eab308' : '#ef4444';

const ECOSYSTEM_EMOJI: Record<string, string> = {
  forest: '🌲',
  meadow: '🌿',
  seedbed: '🌱',
  swamp: '🌾',
  desert: '🏜️',
};

export default function ReportPage({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = use(params);
  const auth = useAuth();
  const token = auth.session?.access_token;

  const { data: report, isLoading, error } = useSWRFetch<AuditReport>(
    token && siteId ? `/sites/${siteId}/audit-report` : null
  );

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto animate-spin text-[#22c55e] mb-3" size={32} />
          <p className="text-sm text-[#64748b]">Building your audit report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center">
        <p className="text-[#64748b]">Report not available. Run the analysis first.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-[#e2e8f0]">
      {/* Header */}
      <div className="border-b border-[#1e293b] bg-[#111827]">
        <div className="max-w-5xl mx-auto px-6 py-6">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-medium text-[#22c55e] bg-[#22c55e]/10 px-2 py-0.5 rounded-full">
                  Content Audit
                </span>
                {report.analyzed_at && (
                  <span className="text-xs text-[#475569]">
                    {new Date(report.analyzed_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                  </span>
                )}
              </div>
              <h1 className="text-2xl font-bold text-[#e2e8f0]">{report.site_name}</h1>
              <a
                href={`https://${report.site_domain}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-sm text-[#64748b] hover:text-[#22c55e] mt-0.5 transition-colors"
              >
                {report.site_domain} <ExternalLink size={12} />
              </a>
            </div>
            <div className="text-right">
              <div
                className="text-4xl font-black"
                style={{ color: HEALTH_COLOR(report.overall_health) }}
              >
                {report.overall_health}
              </div>
              <div className="text-xs text-[#64748b] mt-0.5">Health Score</div>
            </div>
          </div>

          <p className="mt-4 text-sm text-[#94a3b8] leading-relaxed max-w-3xl">
            {report.headline}
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-10">

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Posts Analyzed', value: report.total_posts, icon: '📄', color: '#22c55e' },
            { label: 'Topic Clusters', value: report.cluster_count, icon: '🗂️', color: '#3b82f6' },
            { label: 'Recommendations', value: report.rec_count, icon: '✦', color: '#8b5cf6' },
            { label: 'Cann. Pairs', value: report.cann_pair_count, icon: '⚠️', color: '#ef4444' },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl bg-[#111827] border border-[#1e293b] p-4">
              <div className="text-2xl mb-1">{stat.icon}</div>
              <div className="text-2xl font-bold" style={{ color: stat.color }}>{stat.value}</div>
              <div className="text-xs text-[#64748b] mt-0.5">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Problem breakdown */}
        <div className="rounded-xl bg-[#111827] border border-[#1e293b] p-6">
          <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
            <AlertTriangle size={16} className="text-[#eab308]" /> Issues Detected
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Cannibalizing Pairs', value: report.cann_pair_count, color: '#ef4444' },
              { label: 'Exact Duplicates', value: report.exact_duplicate_count, color: '#f97316' },
              { label: 'Orphan Posts', value: report.orphan_count, color: '#eab308' },
              { label: 'Thin Content', value: report.thin_content_count, color: '#3b82f6' },
            ].map((item) => (
              <div key={item.label} className="text-center p-3 rounded-lg bg-[#0a0f1a]">
                <div className="text-2xl font-bold" style={{ color: item.color }}>{item.value}</div>
                <div className="text-xs text-[#64748b] mt-0.5">{item.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Key findings */}
        {report.key_findings.length > 0 && (
          <div className="rounded-xl bg-[#111827] border border-[#1e293b] p-6">
            <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
              <Target size={16} className="text-[#22c55e]" /> Key Findings
            </h2>
            <ul className="space-y-2">
              {report.key_findings.map((f, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-[#94a3b8]">
                  <span className="text-[#22c55e] mt-0.5 shrink-0">›</span>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Topic clusters */}
        {report.top_clusters.length > 0 && (
          <div>
            <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
              <span>🗺️</span> Topic Clusters
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {report.top_clusters.map((c, i) => (
                <div key={i} className="rounded-xl bg-[#111827] border border-[#1e293b] p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{ECOSYSTEM_EMOJI[c.ecosystem_state] ?? '🌱'}</span>
                      <p className="text-sm font-semibold text-[#e2e8f0]">{c.label}</p>
                    </div>
                    <span className="text-sm font-bold shrink-0" style={{ color: HEALTH_COLOR(c.health_score) }}>
                      {c.health_score}
                    </span>
                  </div>
                  {c.description && (
                    <p className="text-xs text-[#64748b] mt-1.5 ml-8 line-clamp-2">{c.description}</p>
                  )}
                  <p className="text-xs text-[#475569] mt-1.5 ml-8">{c.post_count} posts</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top cannibalization pairs */}
        {report.top_cann_pairs.length > 0 && (
          <div>
            <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
              <span>⚠️</span> Top Cannibalization Pairs
              <span className="text-xs font-normal text-[#64748b]">— posts competing for the same keywords</span>
            </h2>
            <div className="space-y-3">
              {report.top_cann_pairs.slice(0, 5).map((pair, i) => (
                <div key={i} className="rounded-xl bg-[#111827] border border-[#1e293b] p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        color: SEVERITY_COLORS[pair.severity] ?? '#eab308',
                        background: (SEVERITY_COLORS[pair.severity] ?? '#eab308') + '20',
                      }}
                    >
                      {pair.severity.toUpperCase()}
                    </span>
                    <span className="text-xs text-[#475569]">
                      {(pair.overlap_score * 100).toFixed(0)}% overlap
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-[#0a0f1a] p-2">
                      <p className="text-xs font-medium text-[#e2e8f0] line-clamp-2">{pair.post_a_title}</p>
                      <a href={pair.post_a_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-[#475569] hover:text-[#22c55e] flex items-center gap-0.5 mt-0.5">
                        View <ExternalLink size={10} />
                      </a>
                    </div>
                    <div className="rounded-lg bg-[#0a0f1a] p-2">
                      <p className="text-xs font-medium text-[#e2e8f0] line-clamp-2">{pair.post_b_title}</p>
                      <a href={pair.post_b_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-[#475569] hover:text-[#22c55e] flex items-center gap-0.5 mt-0.5">
                        View <ExternalLink size={10} />
                      </a>
                    </div>
                  </div>
                  {pair.recommendation && (
                    <p className="text-xs text-[#22c55e] mt-2">→ {pair.recommendation}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top recommendations */}
        {report.top_recs.length > 0 && (
          <div>
            <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
              <Users size={16} className="text-[#8b5cf6]" /> Top Priority Actions
            </h2>
            <div className="space-y-2">
              {report.top_recs.map((rec, i) => (
                <div key={i} className="rounded-xl bg-[#111827] border border-[#1e293b] p-4">
                  <div className="flex items-start gap-3">
                    <span
                      className="shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full mt-0.5"
                      style={{
                        color: REC_TYPE_COLORS[rec.rec_type] ?? '#64748b',
                        background: (REC_TYPE_COLORS[rec.rec_type] ?? '#64748b') + '20',
                      }}
                    >
                      {rec.rec_type}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-[#e2e8f0]">{rec.title}</p>
                      {rec.summary && <p className="text-xs text-[#64748b] mt-0.5 line-clamp-2">{rec.summary}</p>}
                      <a href={rec.post_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-[#475569] hover:text-[#22c55e] flex items-center gap-0.5 mt-1">
                        {rec.post_title} <ExternalLink size={10} />
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top performers */}
        {report.best_posts.length > 0 && (
          <div>
            <h2 className="text-base font-semibold text-[#e2e8f0] mb-4 flex items-center gap-2">
              <Trophy size={16} className="text-[#22c55e]" /> Top Performing Posts
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {report.best_posts.map((p, i) => (
                <div key={i} className="rounded-xl bg-[#111827] border border-[#1e293b] p-4 flex items-start gap-3">
                  <span className="text-2xl font-black text-[#22c55e] shrink-0">{p.health_score}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[#e2e8f0] line-clamp-2">{p.title}</p>
                    <a href={p.url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-[#475569] hover:text-[#22c55e] flex items-center gap-0.5 mt-0.5">
                      View post <ExternalLink size={10} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-[#1e293b] pt-6 text-center">
          <p className="text-sm text-[#475569]">
            Generated by{' '}
            <span className="text-[#22c55e] font-semibold">enough</span>
            {' '}— Content Ecosystem Intelligence
          </p>
          <p className="text-xs text-[#1e293b] mt-1">enough.app</p>
        </div>
      </div>
    </div>
  );
}
