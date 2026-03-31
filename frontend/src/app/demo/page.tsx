'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  FileText,
  Layers,
  Target,
  CheckCircle,
  Clock,
  Lightbulb,
  TrendingUp,
  Zap,
  ArrowRight,
  ExternalLink,
  Search,
  Ghost,
  BookOpen,
  Shrink,
  TrendingDown,
} from 'lucide-react';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/v1';
const TOKEN = '11111111-1111-1111-1111-111111111111';
const SITE_ID = '32296e5d-7924-4d9f-92b8-7f774c634fad';

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// ─── Types ───────────────────────────────────────
interface SiteHealth {
  content_health_score: number;
  total_posts: number;
  active_posts: number;
  passive_posts: number;
  cannibalistic_posts: number;
  dead_posts: number;
  content_efficiency_ratio: number;
  clusters: Array<{ id: string; label: string | null; post_count: number; ecosystem_state: string | null }>;
}

interface Cluster {
  id: string;
  label: string | null;
  ecosystem_state: string | null;
  health_score: number | null;
  post_count: number;
}

interface Problem {
  id: string;
  post_id: string;
  problem_type: string;
  severity: string;
  details: Record<string, unknown> | null;
}

interface Rec {
  id: string;
  post_id: string;
  recommendation_type: string;
  priority: string;
  title: string;
  summary: string;
  specific_actions: string[];
  status: string;
  estimated_effort_hours: number | null;
}

interface CannPair {
  id: string;
  cluster_id: string;
  overlap_score: number;
  severity: string;
  post_a: { post_id: string; title: string; url: string };
  post_b: { post_id: string; title: string; url: string };
}

interface Post {
  id: string;
  title: string;
  url: string;
  word_count: number | null;
  publish_date: string | null;
}

// ─── Health Ring ─────────────────────────────────
function HealthRing({ score }: { score: number }) {
  const size = 180;
  const radius = (size - 16) / 2;
  const circ = 2 * Math.PI * radius;
  const progress = (score / 100) * circ;
  const color = score >= 75 ? '#22c55e' : score >= 50 ? '#eab308' : score >= 25 ? '#f97316' : '#ef4444';
  const label = score >= 75 ? 'Healthy' : score >= 50 ? 'Moderate' : score >= 25 ? 'At Risk' : 'Critical';
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="#1f2937" strokeWidth={8} />
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke={color} strokeWidth={8} strokeDasharray={circ} strokeDashoffset={circ - progress} strokeLinecap="round" className="transition-all duration-1000" />
      </svg>
      <div className="absolute text-center">
        <div className="text-3xl font-bold text-[#e2e8f0]">{Math.round(score)}</div>
        <div className="text-xs font-medium" style={{ color }}>{label}</div>
      </div>
    </div>
  );
}

// ─── Stat Card ───────────────────────────────────
function Stat({ icon: Icon, label, value, sub, color }: { icon: React.ElementType; label: string; value: string | number; sub?: string; color: string }) {
  return (
    <div className="rounded-xl border border-[#1f2937] bg-[#111827] p-5 relative overflow-hidden">
      <div className="absolute inset-0 opacity-5" style={{ background: `linear-gradient(135deg, ${color}, transparent)` }} />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[#94a3b8]">{label}</p>
          <p className="mt-2 text-2xl font-bold text-[#e2e8f0]">{value}</p>
          {sub && <p className="mt-1 text-xs text-[#94a3b8]">{sub}</p>}
        </div>
        <div className="rounded-lg p-2" style={{ backgroundColor: `${color}15` }}><Icon size={20} style={{ color }} /></div>
      </div>
    </div>
  );
}

// ─── Badge ───────────────────────────────────────
function Badge({ children, color }: { children: React.ReactNode; color: string }) {
  return <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium" style={{ backgroundColor: `${color}20`, color }}>{children}</span>;
}

const SEV_COLORS: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#6b7280' };
const TYPE_LABELS: Record<string, string> = {
  seo_no_images: 'Missing Images', seo_title_length: 'Title Length', seo_missing_meta: 'Missing Meta',
  thin_content: 'Thin Content', thin_below_cluster_avg: 'Below Average', orphan: 'Orphan',
  readability_too_complex: 'Hard to Read', proxy_decay: 'Stale Content',
  seo_no_internal_links: 'No Internal Links', seo_no_og: 'Missing Open Graph',
  seo_no_jsonld: 'Missing JSON-LD', seo_no_canonical: 'Missing Canonical',
};
const REC_TYPE: Record<string, { label: string; color: string }> = {
  expand: { label: '📝 Expand', color: '#3b82f6' }, optimize: { label: '🔧 Optimize', color: '#8b5cf6' },
  merge: { label: '🔀 Merge', color: '#f97316' }, interlink: { label: '🔗 Interlink', color: '#22c55e' },
  update: { label: '🔄 Update', color: '#eab308' }, growth: { label: '🌱 Growth', color: '#06b6d4' },
};

// ─── Tabs ────────────────────────────────────────
type Tab = 'overview' | 'posts' | 'clusters' | 'issues' | 'actions' | 'cannibalization';

export default function DemoPage() {
  const [tab, setTab] = useState<Tab>('overview');
  const [health, setHealth] = useState<SiteHealth | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [recs, setRecs] = useState<Rec[]>([]);
  const [cannPairs, setCannPairs] = useState<CannPair[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [h, cl, pr, rc, cp, po] = await Promise.allSettled([
          apiFetch<SiteHealth>(`/sites/${SITE_ID}/intelligence/health`),
          apiFetch<Cluster[]>(`/sites/${SITE_ID}/intelligence/clusters`),
          apiFetch<Problem[]>(`/sites/${SITE_ID}/intelligence/problems`),
          apiFetch<{ recommendations: Rec[] }>(`/sites/${SITE_ID}/intelligence/recommendations`),
          apiFetch<CannPair[]>(`/sites/${SITE_ID}/intelligence/cannibalization`),
          apiFetch<{ posts: Post[] }>(`/sites/${SITE_ID}/posts?limit=500`),
        ]);
        if (h.status === 'fulfilled') setHealth(h.value);
        if (cl.status === 'fulfilled') setClusters(cl.value);
        if (pr.status === 'fulfilled') setProblems(pr.value);
        if (rc.status === 'fulfilled') setRecs(rc.value.recommendations);
        if (cp.status === 'fulfilled') setCannPairs(cp.value);
        if (po.status === 'fulfilled') setPosts(po.value.posts);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  // Derived data
  const issuesByType = useMemo(() => {
    const m: Record<string, number> = {};
    for (const p of problems) { m[p.problem_type] = (m[p.problem_type] || 0) + 1; }
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [problems]);

  const issuesBySev = useMemo(() => {
    const m = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const p of problems) { const s = p.severity as keyof typeof m; if (s in m) m[s]++; }
    return m;
  }, [problems]);

  const recsByType = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of recs) { m[r.recommendation_type] = (m[r.recommendation_type] || 0) + 1; }
    return m;
  }, [recs]);

  if (loading) return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#22c55e] mx-auto"></div>
        <p className="text-[#94a3b8] mt-4">Loading Close.com intelligence data...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center">
      <p className="text-red-400">Error: {error}</p>
    </div>
  );

  const TABS: Array<{ key: Tab; label: string; icon: React.ElementType }> = [
    { key: 'overview', label: 'Overview', icon: Layers },
    { key: 'posts', label: `Posts (${posts.length})`, icon: FileText },
    { key: 'clusters', label: `Clusters (${clusters.length})`, icon: Layers },
    { key: 'issues', label: `Issues (${problems.length})`, icon: AlertTriangle },
    { key: 'cannibalization', label: `Cannibalization (${cannPairs.length})`, icon: Target },
    { key: 'actions', label: `Actions (${recs.length})`, icon: CheckCircle },
  ];

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-[#e2e8f0]">
      {/* Header */}
      <header className="border-b border-[#1f2937] bg-[#111827] px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-[#22c55e]">Tended</h1>
            <p className="text-xs text-[#94a3b8]">Content Ecosystem Intelligence — close.com/blog</p>
          </div>
          <Badge color="#22c55e">Demo · 600 posts analyzed</Badge>
        </div>
      </header>

      {/* Tabs */}
      <nav className="border-b border-[#1f2937] bg-[#111827]/50 px-6">
        <div className="max-w-7xl mx-auto flex gap-1 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${tab === t.key ? 'text-[#22c55e] border-b-2 border-[#22c55e]' : 'text-[#94a3b8] hover:text-[#e2e8f0]'}`}>
              <t.icon size={14} />{t.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-7xl mx-auto p-6 space-y-6">

        {/* OVERVIEW TAB */}
        {tab === 'overview' && health && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              <div className="lg:col-span-2 rounded-xl border border-[#1f2937] bg-[#111827] p-6 flex flex-col items-center">
                <p className="text-xs uppercase tracking-wider text-[#94a3b8] mb-4">Content Health Score</p>
                <HealthRing score={health.content_health_score} />
                <p className="text-sm text-[#94a3b8] mt-3">Efficiency: {(health.content_efficiency_ratio * 100).toFixed(0)}%</p>
              </div>
              <div className="lg:col-span-3 grid grid-cols-2 gap-4">
                <Stat icon={FileText} label="Total Posts" value={health.total_posts} sub={`${health.active_posts} active · ${health.dead_posts} need work`} color="#3b82f6" />
                <Stat icon={Layers} label="Topic Clusters" value={clusters.length} sub="Discovered by AI clustering" color="#8b5cf6" />
                <Stat icon={AlertTriangle} label="Issues Found" value={problems.length} sub={`${issuesBySev.critical} critical · ${issuesBySev.high} high`} color={issuesBySev.critical > 0 ? '#ef4444' : '#eab308'} />
                <Stat icon={Target} label="Cannibalization" value={cannPairs.length} sub="Posts competing with each other" color="#f97316" />
              </div>
            </div>

            {/* Recs summary */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="rounded-xl border border-[#1f2937] bg-[#111827] p-6">
                <h3 className="text-sm font-semibold mb-4">AI Recommendations ({recs.length})</h3>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(recsByType).map(([type, count]) => {
                    const info = REC_TYPE[type] || { label: type, color: '#6b7280' };
                    return (
                      <div key={type} className="flex items-center gap-2 rounded-lg bg-[#0a0f1a] px-3 py-2">
                        <span className="text-xs">{info.label}</span>
                        <span className="ml-auto text-xs font-bold" style={{ color: info.color }}>{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="rounded-xl border border-[#1f2937] bg-[#111827] p-6">
                <h3 className="text-sm font-semibold mb-4">Issue Breakdown</h3>
                <div className="space-y-2">
                  {issuesByType.slice(0, 8).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <span className="text-sm text-[#94a3b8]">{TYPE_LABELS[type] || type.replace(/_/g, ' ')}</span>
                      <span className="text-sm font-medium">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* POSTS TAB */}
        {tab === 'posts' && (
          <div className="rounded-xl border border-[#1f2937] bg-[#111827] overflow-hidden">
            <table className="w-full">
              <thead><tr className="border-b border-[#1f2937] bg-[#0a0f1a]/50">
                <th className="text-left px-4 py-3 text-xs uppercase text-[#94a3b8]">Title</th>
                <th className="text-left px-4 py-3 text-xs uppercase text-[#94a3b8]">Words</th>
                <th className="text-left px-4 py-3 text-xs uppercase text-[#94a3b8]">Published</th>
              </tr></thead>
              <tbody className="divide-y divide-[#1f2937]/50">
                {posts.slice(0, 100).map(p => (
                  <tr key={p.id} className="hover:bg-[#1f2937]/30">
                    <td className="px-4 py-3 max-w-[400px]">
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-[#e2e8f0] hover:text-[#22c55e] line-clamp-1">{p.title || 'Untitled'}</a>
                      <p className="text-xs text-[#94a3b8] truncate">{p.url}</p>
                    </td>
                    <td className="px-4 py-3 text-sm">{p.word_count?.toLocaleString() || '—'}</td>
                    <td className="px-4 py-3 text-sm text-[#94a3b8]">{p.publish_date ? new Date(p.publish_date).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {posts.length > 100 && <p className="text-center text-xs text-[#94a3b8] py-3">Showing 100 of {posts.length} posts</p>}
          </div>
        )}

        {/* CLUSTERS TAB */}
        {tab === 'clusters' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {clusters.sort((a, b) => b.post_count - a.post_count).map(c => (
              <div key={c.id} className="rounded-xl border border-[#1f2937] bg-[#111827] p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-semibold line-clamp-1">{c.label || 'Unlabeled'}</p>
                    <p className="text-xs text-[#94a3b8] mt-1">{c.post_count} posts</p>
                  </div>
                  {c.health_score != null && (
                    <span className="text-lg font-bold" style={{ color: c.health_score >= 75 ? '#22c55e' : c.health_score >= 50 ? '#eab308' : '#ef4444' }}>
                      {Math.round(c.health_score)}
                    </span>
                  )}
                </div>
                {c.ecosystem_state && <Badge color="#22c55e">{c.ecosystem_state}</Badge>}
              </div>
            ))}
          </div>
        )}

        {/* ISSUES TAB */}
        {tab === 'issues' && (
          <>
            <div className="grid grid-cols-4 gap-4">
              {Object.entries(issuesBySev).map(([sev, count]) => (
                <div key={sev} className="rounded-xl border border-[#1f2937] bg-[#111827] p-4">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: SEV_COLORS[sev] }} />
                    <span className="text-xs uppercase text-[#94a3b8]">{sev}</span>
                  </div>
                  <p className="text-2xl font-bold mt-2">{count}</p>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {problems.slice(0, 50).map(p => (
                <div key={p.id} className="rounded-xl border border-[#1f2937] bg-[#111827] px-4 py-3 flex items-center gap-3">
                  <Badge color={SEV_COLORS[p.severity] || '#6b7280'}>{p.severity}</Badge>
                  <span className="text-sm font-medium">{TYPE_LABELS[p.problem_type] || p.problem_type.replace(/_/g, ' ')}</span>
                  {p.details && (p.details as Record<string, string>).title && (
                    <span className="text-xs text-[#94a3b8] truncate flex-1">{String((p.details as Record<string, string>).title)}</span>
                  )}
                </div>
              ))}
              {problems.length > 50 && <p className="text-center text-xs text-[#94a3b8]">Showing 50 of {problems.length}</p>}
            </div>
          </>
        )}

        {/* CANNIBALIZATION TAB */}
        {tab === 'cannibalization' && (
          <div className="space-y-3">
            {cannPairs.map(pair => (
              <div key={pair.id} className="rounded-xl border border-[#1f2937] bg-[#111827] p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Badge color={SEV_COLORS[pair.severity]}>{pair.severity}</Badge>
                  <span className="text-xs text-[#94a3b8]">{(pair.overlap_score * 100).toFixed(0)}% overlap</span>
                </div>
                <div className="space-y-2">
                  <a href={pair.post_a.url} target="_blank" rel="noopener noreferrer" className="block text-sm text-[#e2e8f0] hover:text-[#22c55e] truncate">
                    {pair.post_a.title}
                  </a>
                  <p className="text-xs text-[#94a3b8] text-center">↕ competing with</p>
                  <a href={pair.post_b.url} target="_blank" rel="noopener noreferrer" className="block text-sm text-[#e2e8f0] hover:text-[#22c55e] truncate">
                    {pair.post_b.title}
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ACTIONS TAB */}
        {tab === 'actions' && (
          <div className="space-y-3">
            {recs.map(r => {
              const info = REC_TYPE[r.recommendation_type] || { label: r.recommendation_type, color: '#6b7280' };
              return (
                <div key={r.id} className="rounded-xl border border-[#1f2937] bg-[#111827] p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge color={SEV_COLORS[r.priority] || '#6b7280'}>{r.priority}</Badge>
                    <span className="text-xs" style={{ color: info.color }}>{info.label}</span>
                    {r.estimated_effort_hours && <span className="text-xs text-[#94a3b8]">~{r.estimated_effort_hours}h</span>}
                  </div>
                  <p className="text-sm font-medium">{r.title}</p>
                  <p className="text-xs text-[#94a3b8] mt-1">{r.summary}</p>
                  {r.specific_actions.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {r.specific_actions.slice(0, 3).map((a, i) => (
                        <p key={i} className="text-xs text-[#e2e8f0]">• {a}</p>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {recs.length === 0 && <p className="text-center text-[#94a3b8] py-12">Recommendations are still generating via Claude API...</p>}
          </div>
        )}

      </main>
    </div>
  );
}
