'use client';

import { useState, useEffect } from 'react';
import { Search, Users, ArrowRight, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

interface TopicInfo {
  cluster_id: string;
  label: string;
  post_count: number;
  health_score: number | null;
  ecosystem_state: string | null;
}

interface ComparisonResult {
  competitor_domain: string;
  our_stats: {
    total_posts: number;
    total_words: number;
    avg_word_count: number;
    total_clusters: number;
  };
  our_topics: TopicInfo[];
  strong_topics: TopicInfo[];
  weak_topics: TopicInfo[];
  content_gaps: Array<{ topic: string; gap_type: string; priority: number }>;
  overlap_estimate: {
    shared_topics: number;
    our_unique: number;
    their_unique_estimate: number;
  };
  recommendations: string[];
}

interface SavedComparison {
  id: string;
  competitor_domain: string;
  comparison: ComparisonResult;
  created_at: string;
}

export default function CompetitorsPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const [domain, setDomain] = useState('');
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [history, setHistory] = useState<SavedComparison[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  const siteId = currentSite?.id;

  // Load comparison history
  useEffect(() => {
    if (!siteId || !token) return;
    setLoadingHistory(true);
    apiFetch<{ comparisons: SavedComparison[] }>(
      `/sites/${siteId}/competitors`,
      { token: token ?? undefined },
    )
      .then((res) => setHistory(res.comparisons || []))
      .catch(() => setHistory([]))
      .finally(() => setLoadingHistory(false));
  }, [siteId, token]);

  const handleCompare = async () => {
    if (!siteId || !token || !domain.trim()) return;
    setComparing(true);
    try {
      const res = await apiFetch<ComparisonResult>(
        `/sites/${siteId}/competitors/compare`,
        {
          method: 'POST',
          body: JSON.stringify({ competitor_domain: domain.trim() }),
          token: token ?? undefined,
        },
      );
      setResult(res);
    } catch {
      // silent
    }
    setComparing(false);
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">
      <div className="flex items-center gap-3 mb-2">
        <Users size={24} className="text-[#3b82f6]" />
        <h1 className="text-xl font-bold text-[#e2e8f0]">Competitor Comparison</h1>
      </div>

      {/* Search bar */}
      <Card className="!p-4">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void handleCompare()}
              placeholder="Enter competitor domain (e.g. competitor.com)"
              className="w-full rounded-lg border border-[#1e293b] bg-[#0f172a] pl-10 pr-4 py-2.5 text-sm text-[#e2e8f0] placeholder-[#4b5563] focus:border-[#3b82f6] focus:outline-none transition-colors"
            />
          </div>
          <button
            onClick={() => void handleCompare()}
            disabled={comparing || !domain.trim()}
            className="px-5 py-2.5 rounded-lg bg-[#3b82f6] text-white text-sm font-medium hover:bg-[#2563eb] transition-colors disabled:opacity-50"
          >
            {comparing ? 'Analyzing...' : 'Compare'}
          </button>
        </div>
      </Card>

      {/* Results */}
      {result && <ComparisonView result={result} />}

      {/* History */}
      {!result && history.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-3">
            Previous Comparisons
          </p>
          <div className="space-y-2">
            {history.map((h) => (
              <Card
                key={h.id}
                className="!p-4 cursor-pointer hover:border-[#334155] transition-colors"
                onClick={() => setResult(h.comparison)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-[#e2e8f0]">{h.competitor_domain}</p>
                    <p className="text-xs text-[#64748b]">
                      {new Date(h.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <ArrowRight size={14} className="text-[#64748b]" />
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {!result && history.length === 0 && !loadingHistory && (
        <Card className="!p-8 text-center">
          <Users size={32} className="text-[#64748b] mx-auto mb-3" />
          <p className="text-sm text-[#64748b]">
            Enter a competitor domain above to see how your content stacks up.
          </p>
        </Card>
      )}
    </div>
  );
}

function ComparisonView({ result }: { result: ComparisonResult }) {
  return (
    <div className="space-y-6">
      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="!p-4 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-2">
            Your Posts
          </p>
          <p className="text-3xl font-bold text-[#e2e8f0]">{result.our_stats.total_posts}</p>
          <p className="text-xs text-[#64748b] mt-1">
            Avg. {result.our_stats.avg_word_count} words
          </p>
        </Card>
        <Card className="!p-4 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-2">
            Topic Clusters
          </p>
          <p className="text-3xl font-bold text-[#e2e8f0]">{result.our_stats.total_clusters}</p>
        </Card>
        <Card className="!p-4 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-2">
            vs. {result.competitor_domain}
          </p>
          <p className="text-lg font-bold text-[#e2e8f0]">
            {result.content_gaps.length} gaps found
          </p>
        </Card>
      </div>

      {/* Venn Diagram */}
      <Card className="!p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-4">
          Topic Overlap
        </p>
        <div className="flex items-center justify-center py-8">
          <VennDiagram
            leftCount={result.overlap_estimate.our_unique}
            rightCount={result.overlap_estimate.their_unique_estimate}
            overlapCount={result.overlap_estimate.shared_topics}
            leftLabel="You"
            rightLabel={result.competitor_domain}
          />
        </div>
      </Card>

      {/* Strong vs Weak Topics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Strong Topics */}
        <Card className="!p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={14} className="text-[#22c55e]" />
            <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b]">
              Your Strengths
            </p>
          </div>
          {result.strong_topics.length === 0 ? (
            <p className="text-xs text-[#64748b]">No strong topics identified yet.</p>
          ) : (
            <div className="space-y-2">
              {result.strong_topics.slice(0, 5).map((t) => (
                <div key={t.cluster_id} className="flex items-center justify-between">
                  <span className="text-sm text-[#e2e8f0] truncate">{t.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#64748b]">{t.post_count} posts</span>
                    {t.health_score !== null && (
                      <Badge color="#22c55e">{t.health_score.toFixed(0)}</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Weak Topics */}
        <Card className="!p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown size={14} className="text-[#ef4444]" />
            <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b]">
              Needs Improvement
            </p>
          </div>
          {result.weak_topics.length === 0 ? (
            <p className="text-xs text-[#64748b]">No weak topics identified.</p>
          ) : (
            <div className="space-y-2">
              {result.weak_topics.slice(0, 5).map((t) => (
                <div key={t.cluster_id} className="flex items-center justify-between">
                  <span className="text-sm text-[#e2e8f0] truncate">{t.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#64748b]">{t.post_count} posts</span>
                    {t.health_score !== null && (
                      <Badge color="#ef4444">{t.health_score.toFixed(0)}</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Content Gaps */}
      {result.content_gaps.length > 0 && (
        <Card className="!p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-[#f59e0b]" />
            <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b]">
              Content Gaps
            </p>
          </div>
          <div className="space-y-2">
            {result.content_gaps.slice(0, 10).map((gap, idx) => (
              <div key={idx} className="flex items-center justify-between">
                <span className="text-sm text-[#e2e8f0]">{gap.topic}</span>
                <Badge color="#f59e0b">{gap.gap_type.replace(/_/g, ' ')}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Recommendations */}
      {result.recommendations.length > 0 && (
        <Card className="!p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-3">
            Recommendations
          </p>
          <div className="space-y-2">
            {result.recommendations.map((rec, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className="text-xs text-[#3b82f6] font-bold mt-0.5">{idx + 1}.</span>
                <span className="text-sm text-[#94a3b8]">{rec}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function VennDiagram({
  leftCount,
  rightCount,
  overlapCount,
  leftLabel,
  rightLabel,
}: {
  leftCount: number;
  rightCount: number;
  overlapCount: number;
  leftLabel: string;
  rightLabel: string;
}) {
  return (
    <div className="relative w-80 h-48">
      {/* Left circle */}
      <div className="absolute left-4 top-4 w-40 h-40 rounded-full border-2 border-[#3b82f6] bg-[#3b82f6]/10 flex items-center justify-center">
        <div className="text-center -ml-8">
          <p className="text-2xl font-bold text-[#3b82f6]">{leftCount}</p>
          <p className="text-[10px] text-[#64748b] max-w-[60px] truncate">{leftLabel}</p>
        </div>
      </div>

      {/* Right circle */}
      <div className="absolute right-4 top-4 w-40 h-40 rounded-full border-2 border-[#a855f7] bg-[#a855f7]/10 flex items-center justify-center">
        <div className="text-center ml-8">
          <p className="text-2xl font-bold text-[#a855f7]">{rightCount}</p>
          <p className="text-[10px] text-[#64748b] max-w-[60px] truncate">{rightLabel}</p>
        </div>
      </div>

      {/* Overlap */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 text-center">
        <p className="text-lg font-bold text-[#e2e8f0]">{overlapCount}</p>
        <p className="text-[10px] text-[#64748b]">shared</p>
      </div>
    </div>
  );
}
