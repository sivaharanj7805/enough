'use client';

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useProblems } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { SEVERITY_COLORS } from '@/lib/constants';
import {
  AlertTriangle,
  FileText,
  Search,
  Link2,
  Eye,
  TrendingDown,
  Shrink,
  BookOpen,
  Ghost,
  BarChart3,
  Filter,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Sparkles,
} from 'lucide-react';

type IssueTab = 'all' | 'cannibalization' | 'decay' | 'thin' | 'seo' | 'orphan' | 'readability' | 'ai_readiness';

type SortField = 'severity' | 'type' | 'post';
type SortDir = 'asc' | 'desc';

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const TABS: Array<{ key: IssueTab; label: string; icon: React.ElementType; types: string[] }> = [
  { key: 'all', label: 'All Issues', icon: AlertTriangle, types: [] },
  { key: 'seo', label: 'SEO', icon: Search, types: ['seo_no_images', 'seo_title_length', 'seo_missing_meta', 'seo_no_internal_links', 'seo_no_h1', 'seo_no_og', 'seo_no_jsonld', 'seo_no_canonical', 'duplicate_content'] },
  { key: 'thin', label: 'Thin Content', icon: Shrink, types: ['thin_content', 'thin_below_cluster_avg'] },
  { key: 'decay', label: 'Decay', icon: TrendingDown, types: ['content_decay', 'proxy_decay'] },
  { key: 'orphan', label: 'Orphans', icon: Ghost, types: ['orphan'] },
  { key: 'readability', label: 'Readability', icon: BookOpen, types: ['readability_too_complex'] },
  { key: 'ai_readiness', label: 'AI Readiness', icon: Sparkles, types: ['ai_no_schema', 'ai_low_citability', 'ai_missing_eeat', 'ai_poor_extraction'] },
];

const ISSUE_LABELS: Record<string, { label: string; description: string; icon: React.ElementType }> = {
  seo_no_images: { label: 'Missing Images', description: 'Post has no images — visual content improves engagement and rankings', icon: Eye },
  seo_title_length: { label: 'Title Length', description: 'Title is too long or too short for optimal SEO display', icon: FileText },
  seo_missing_meta: { label: 'Missing Meta', description: 'No meta description — Google will auto-generate one (badly)', icon: Search },
  seo_no_internal_links: { label: 'No Internal Links', description: 'Post doesn\'t link to other content on the site', icon: Link2 },
  seo_no_h1: { label: 'Missing H1', description: 'No H1 heading tag found — critical for page structure', icon: FileText },
  seo_no_og: { label: 'Missing Open Graph', description: 'No OG tags — social shares will look generic', icon: Eye },
  seo_no_jsonld: { label: 'Missing JSON-LD', description: 'No structured data — missing out on rich snippets', icon: BarChart3 },
  seo_no_canonical: { label: 'Missing Canonical', description: 'No canonical tag — risk of duplicate content issues', icon: Link2 },
  thin_content: { label: 'Thin Content', description: 'Content is below minimum word count for its type', icon: Shrink },
  thin_below_cluster_avg: { label: 'Below Cluster Average', description: 'Significantly shorter than similar posts in the same topic', icon: Shrink },
  content_decay: { label: 'Traffic Decay', description: 'Traffic has declined significantly over recent months', icon: TrendingDown },
  proxy_decay: { label: 'Stale Content', description: 'Content contains outdated references or hasn\'t been updated', icon: TrendingDown },
  orphan: { label: 'Orphan Page', description: 'No internal links point to this page — invisible to users and crawlers', icon: Ghost },
  readability_too_complex: { label: 'Hard to Read', description: 'Readability score is below threshold for the site\'s industry', icon: BookOpen },
  velocity_decline: { label: 'Publishing Decline', description: 'Publishing frequency has dropped significantly', icon: TrendingDown },
  duplicate_content: { label: 'Duplicate Content', description: 'Identical content exists at another URL — set up a 301 redirect', icon: AlertTriangle },
  ai_no_schema: { label: 'No Schema Markup', description: 'Missing structured data that AI models use for citations', icon: Sparkles },
  ai_low_citability: { label: 'Low Citability', description: 'Content is not structured for AI citation — add clear claims and sources', icon: Sparkles },
  ai_missing_eeat: { label: 'Missing E-E-A-T Signals', description: 'No author bio, credentials, or experience signals found', icon: Sparkles },
  ai_poor_extraction: { label: 'Poor AI Extraction', description: 'Content structure makes it hard for AI models to extract key facts', icon: Sparkles },
};

function SortIcon({ field, currentField, currentDir }: { field: SortField; currentField: SortField; currentDir: SortDir }) {
  if (field !== currentField) return <ChevronsUpDown size={12} className="text-brand-text-muted/50" />;
  return currentDir === 'asc' ? <ChevronUp size={12} className="text-brand-accent" /> : <ChevronDown size={12} className="text-brand-accent" />;
}

export default function IssuesDashboardPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const { data: problems, isLoading } = useProblems(siteId);
  const [activeTab, setActiveTab] = useState<IssueTab>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<SortField>('severity');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Group problems by type for tab counts
  const tabCounts = useMemo(() => {
    const counts: Record<string, number> = { all: 0 };
    for (const tab of TABS) {
      counts[tab.key] = 0;
    }
    for (const p of problems || []) {
      counts.all++;
      for (const tab of TABS) {
        if (tab.types.includes(p.problem_type)) {
          counts[tab.key]++;
        }
      }
    }
    return counts;
  }, [problems]);

  // Filter problems
  const filteredProblems = useMemo(() => {
    let result = problems || [];

    // Tab filter
    if (activeTab !== 'all') {
      const tab = TABS.find((t) => t.key === activeTab);
      if (tab) {
        result = result.filter((p) => tab.types.includes(p.problem_type));
      }
    }

    // Severity filter
    if (severityFilter !== 'all') {
      result = result.filter((p) => p.severity === severityFilter);
    }

    // Sort
    result = [...result].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'severity':
          cmp = (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
          break;
        case 'type':
          cmp = a.problem_type.localeCompare(b.problem_type);
          break;
        case 'post':
          cmp = a.post_id.localeCompare(b.post_id);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [problems, activeTab, severityFilter, sortField, sortDir]);

  // Severity breakdown for the active tab
  const severityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const p of filteredProblems) {
      const sev = p.severity as keyof typeof counts;
      if (sev in counts) counts[sev]++;
    }
    return counts;
  }, [filteredProblems]);

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortField(field);
        setSortDir('asc');
      }
    },
    [sortField]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">Issues Dashboard</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          {(problems || []).length} issues detected · Fix these to improve your content health score
        </p>
      </div>

      {/* Issue count bar */}
      {filteredProblems.length > 0 && (
        <Card className="!p-3">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="ml-auto text-xs text-brand-text-muted">
              {filteredProblems.length} issues in view
            </span>
          </div>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-2 border-b border-brand-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg whitespace-nowrap transition-colors ${
              activeTab === tab.key
                ? 'bg-brand-surface-hover text-brand-accent border-b-2 border-brand-accent'
                : 'text-brand-text-muted hover:text-brand-text hover:bg-brand-surface-hover/50'
            }`}
          >
            <tab.icon size={14} />
            {tab.label}
            <span className={`ml-1 text-xs rounded-full px-1.5 py-0.5 ${
              activeTab === tab.key ? 'bg-brand-accent/20 text-brand-accent' : 'bg-brand-surface-hover text-brand-text-muted'
            }`}>
              {tabCounts[tab.key]}
            </span>
          </button>
        ))}
      </div>

      {/* Severity Breakdown for Active Tab */}
      <div className="flex items-center gap-3 flex-wrap">
        {(Object.entries(severityCounts) as Array<[string, number]>).map(([sev, count]) => {
          const color = SEVERITY_COLORS[sev as keyof typeof SEVERITY_COLORS];
          return (
            <button
              key={sev}
              onClick={() => setSeverityFilter(severityFilter === sev ? 'all' : sev)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                severityFilter === sev
                  ? 'ring-2 ring-offset-1 ring-offset-brand-bg'
                  : 'hover:opacity-80'
              }`}
              style={{
                backgroundColor: `${color}15`,
                color: color,
                ...(severityFilter === sev ? { ringColor: color } : {}),
              }}
            >
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
              {sev}: {count}
            </button>
          );
        })}
        {severityFilter !== 'all' && (
          <button
            onClick={() => setSeverityFilter('all')}
            className="text-xs text-brand-text-muted hover:text-brand-text transition-colors"
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Sortable Column Headers */}
      <div className="flex items-center gap-4 px-4 py-2 bg-brand-bg/50 rounded-lg border border-brand-border/50">
        <button
          onClick={() => handleSort('severity')}
          className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text"
        >
          Severity <SortIcon field="severity" currentField={sortField} currentDir={sortDir} />
        </button>
        <button
          onClick={() => handleSort('type')}
          className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text"
        >
          Type <SortIcon field="type" currentField={sortField} currentDir={sortDir} />
        </button>
        <button
          onClick={() => handleSort('post')}
          className="flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-brand-text-muted hover:text-brand-text ml-auto"
        >
          Post <SortIcon field="post" currentField={sortField} currentDir={sortDir} />
        </button>
      </div>

      {/* Issues List */}
      {filteredProblems.length > 0 ? (
        <div className="space-y-3">
          {filteredProblems.map((problem) => {
            const info = ISSUE_LABELS[problem.problem_type] || {
              label: problem.problem_type.replace(/_/g, ' '),
              description: '',
              icon: AlertTriangle,
            };
            const details = problem.details as Record<string, unknown> | null;

            return (
              <Card key={problem.id} className="!p-4 hover:border-brand-border-hover transition-colors">
                <div className="flex items-start gap-3">
                  <div
                    className="mt-0.5 rounded-lg p-1.5 shrink-0"
                    style={{ backgroundColor: `${SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low}15` }}
                  >
                    <info.icon
                      size={16}
                      style={{ color: SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge color={SEVERITY_COLORS[problem.severity as keyof typeof SEVERITY_COLORS] || SEVERITY_COLORS.low}>
                        {problem.severity}
                      </Badge>
                      <span className="text-sm font-medium text-brand-text">{info.label}</span>
                    </div>
                    <p className="text-xs text-brand-text-muted mt-1">{info.description}</p>

                    {/* Issue-specific details */}
                    {details?.issue != null && (
                      <p className="text-sm text-brand-text mt-2 bg-brand-bg rounded-lg p-2 border border-brand-border/50">
                        {String(details.issue as string)}
                      </p>
                    )}
                    {details?.word_count != null && (
                      <p className="text-xs text-brand-text-muted mt-1">
                        Word count: {String(details.word_count)}
                        {details.threshold != null ? ` · Target: ${String(details.threshold)}+ words` : ' · Below recommended length'}
                      </p>
                    )}
                    {details?.readability_score != null && (
                      <p className="text-xs text-brand-text-muted mt-1">
                        Readability: {String(details.readability_score)} · Grade: {String(details.grade_level || '—')}
                      </p>
                    )}
                  </div>
                  <Link
                    href={`/posts/${problem.post_id}`}
                    className="shrink-0 text-xs text-brand-accent hover:text-brand-accent-hover font-medium"
                  >
                    View Post →
                  </Link>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <div className="text-center py-12">
            <AlertTriangle size={32} className="text-brand-text-muted mx-auto mb-2" />
            <p className="text-sm text-brand-text-muted">
              {severityFilter !== 'all' || activeTab !== 'all'
                ? 'No issues match the current filters'
                : 'No issues detected — your content is in great shape!'}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
