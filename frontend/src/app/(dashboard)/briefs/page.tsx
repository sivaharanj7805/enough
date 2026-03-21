'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import {
  FileText,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  Clock,
} from 'lucide-react';

// ─── Types ──────────────────────────────────────────

interface BriefSummary {
  id: string;
  target_keyword: string;
  suggested_titles: string[];
  recommended_word_count: number;
  cannibalization_risk: 'low' | 'medium' | 'high';
  content_angle: string;
  difficulty_level: 'easy' | 'medium' | 'hard';
  status: 'draft' | 'in_progress' | 'completed';
  created_at: string;
}

interface OutlineItem {
  heading: string;
  subheadings: string[];
  notes: string;
}

interface InternalLink {
  url: string;
  anchor: string;
}

interface BriefDetail extends BriefSummary {
  secondary_keywords: string[];
  outline: OutlineItem[];
  questions_to_answer: string[];
  differentiation_notes: string;
  avoid_topics: string[];
  internal_links_from: InternalLink[];
  internal_links_to: InternalLink[];
  updated_at: string;
}

// ─── Helpers ────────────────────────────────────────

const RISK_STYLE: Record<string, { label: string; cls: string }> = {
  low: { label: 'Low Risk', cls: 'text-[#22c55e] bg-[#22c55e]/10' },
  medium: { label: 'Med Risk', cls: 'text-[#eab308] bg-[#eab308]/10' },
  high: { label: 'High Risk', cls: 'text-[#ef4444] bg-[#ef4444]/10' },
};

const DIFFICULTY_STYLE: Record<string, { label: string; cls: string }> = {
  easy: { label: 'Easy', cls: 'text-[#22c55e] bg-[#22c55e]/10' },
  medium: { label: 'Medium', cls: 'text-[#eab308] bg-[#eab308]/10' },
  hard: { label: 'Hard', cls: 'text-[#ef4444] bg-[#ef4444]/10' },
};

const STATUS_STYLE: Record<string, { label: string; icon: typeof Clock; cls: string }> = {
  draft: { label: 'Draft', icon: FileText, cls: 'text-[#94a3b8] bg-[#94a3b8]/10' },
  in_progress: { label: 'In Progress', icon: Clock, cls: 'text-[#3b82f6] bg-[#3b82f6]/10' },
  completed: { label: 'Completed', icon: CheckCircle, cls: 'text-[#22c55e] bg-[#22c55e]/10' },
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ─── Rate Limit Indicator ───────────────────────────

function RateLimitIndicator({ remaining }: { remaining: number }) {
  const max = 5;
  return (
    <div className="flex items-center gap-2 text-xs text-brand-text-muted">
      <div className="flex gap-0.5">
        {Array.from({ length: max }).map((_, i) => (
          <div
            key={i}
            className={`w-1.5 h-3 rounded-sm ${
              i < remaining ? 'bg-[#3b82f6]' : 'bg-[#1e293b]'
            }`}
          />
        ))}
      </div>
      <span>{remaining}/min remaining</span>
    </div>
  );
}

// ─── Brief Detail Panel ─────────────────────────────

function BriefDetailPanel({ detail }: { detail: BriefDetail }) {
  return (
    <div className="border-t border-brand-border px-5 pb-5 space-y-5">
      {/* Secondary Keywords */}
      {detail.secondary_keywords?.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Secondary Keywords
          </p>
          <div className="flex flex-wrap gap-1.5">
            {detail.secondary_keywords.map((kw, i) => (
              <span
                key={i}
                className="text-xs px-2 py-1 rounded-md bg-[#1e293b] text-[#94a3b8]"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Suggested Titles */}
      {detail.suggested_titles?.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Suggested Titles
          </p>
          <ul className="space-y-1">
            {detail.suggested_titles.map((title, i) => (
              <li key={i} className="text-sm text-[#e2e8f0]">
                {i + 1}. {title}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Content Angle */}
      {detail.content_angle && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Content Angle
          </p>
          <p className="text-sm text-[#94a3b8]">{detail.content_angle}</p>
        </div>
      )}

      {/* Outline */}
      {detail.outline?.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Outline
          </p>
          <div className="space-y-3">
            {detail.outline.map((section, i) => (
              <div key={i} className="rounded-lg bg-[#0f172a] p-3 border border-[#1e293b]">
                <p className="text-sm font-medium text-[#e2e8f0]">{section.heading}</p>
                {section.subheadings?.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5 ml-4">
                    {section.subheadings.map((sub, j) => (
                      <li key={j} className="text-xs text-[#94a3b8] list-disc">
                        {sub}
                      </li>
                    ))}
                  </ul>
                )}
                {section.notes && (
                  <p className="text-xs text-[#64748b] mt-1.5 italic">{section.notes}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Questions to Answer */}
      {detail.questions_to_answer?.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Questions to Answer
          </p>
          <ul className="space-y-1">
            {detail.questions_to_answer.map((q, i) => (
              <li key={i} className="text-sm text-[#94a3b8] flex items-start gap-2">
                <span className="text-[#3b82f6] font-bold mt-0.5">?</span>
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Differentiation Notes */}
      {detail.differentiation_notes && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Differentiation Notes
          </p>
          <p className="text-sm text-[#94a3b8]">{detail.differentiation_notes}</p>
        </div>
      )}

      {/* Avoid Topics */}
      {detail.avoid_topics?.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
            Topics to Avoid
          </p>
          <div className="flex flex-wrap gap-1.5">
            {detail.avoid_topics.map((topic, i) => (
              <span
                key={i}
                className="text-xs px-2 py-1 rounded-md bg-[#ef4444]/10 text-[#ef4444]"
              >
                {topic}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Internal Links */}
      {(detail.internal_links_from?.length > 0 || detail.internal_links_to?.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {detail.internal_links_from?.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
                Link From (existing pages)
              </p>
              <ul className="space-y-1">
                {detail.internal_links_from.map((link, i) => (
                  <li key={i} className="text-xs text-[#94a3b8]">
                    <span className="text-[#3b82f6]">{link.anchor}</span>
                    <span className="text-[#64748b] ml-1 truncate">{link.url}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {detail.internal_links_to?.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2">
                Link To (target pages)
              </p>
              <ul className="space-y-1">
                {detail.internal_links_to.map((link, i) => (
                  <li key={i} className="text-xs text-[#94a3b8]">
                    <span className="text-[#3b82f6]">{link.anchor}</span>
                    <span className="text-[#64748b] ml-1 truncate">{link.url}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Word count + dates */}
      <div className="flex items-center gap-4 text-xs text-[#64748b] pt-2 border-t border-[#1e293b]">
        <span>Recommended: {detail.recommended_word_count?.toLocaleString()} words</span>
        {detail.updated_at && <span>Updated: {formatDate(detail.updated_at)}</span>}
      </div>
    </div>
  );
}

// ─── Brief Card ─────────────────────────────────────

function BriefCard({
  brief,
  siteId,
  token,
  onDelete,
}: {
  brief: BriefSummary;
  siteId: string;
  token: string | null;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<BriefDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const risk = RISK_STYLE[brief.cannibalization_risk] ?? RISK_STYLE.low;
  const difficulty = DIFFICULTY_STYLE[brief.difficulty_level] ?? DIFFICULTY_STYLE.medium;
  const status = STATUS_STYLE[brief.status] ?? STATUS_STYLE.draft;
  const StatusIcon = status.icon;

  const handleToggle = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (!detail) {
      setLoadingDetail(true);
      try {
        const data = await apiFetch<BriefDetail>(
          `/sites/${siteId}/intelligence/briefs/${brief.id}`,
          { token: token ?? undefined }
        );
        setDetail(data);
      } catch {
        // Keep expanded but show no extra detail
      } finally {
        setLoadingDetail(false);
      }
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await apiFetch(`/sites/${siteId}/intelligence/briefs/${brief.id}`, {
        method: 'DELETE',
        token: token ?? undefined,
      });
      onDelete(brief.id);
    } catch {
      // silent
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <div className="rounded-xl border border-brand-border bg-brand-surface overflow-hidden transition-colors hover:border-[#334155]">
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Keyword + badges */}
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <h3 className="text-base font-semibold text-brand-text truncate">
                {brief.target_keyword}
              </h3>
            </div>

            <div className="flex items-center gap-2 flex-wrap mb-2">
              <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${risk.cls}`}>
                {risk.label}
              </span>
              <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${difficulty.cls}`}>
                {difficulty.label}
              </span>
              <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded flex items-center gap-1 ${status.cls}`}>
                <StatusIcon size={10} />
                {status.label}
              </span>
            </div>

            {/* Content angle preview */}
            {brief.content_angle && (
              <p className="text-sm text-brand-text-muted line-clamp-2 mb-2">
                {brief.content_angle}
              </p>
            )}

            {/* Meta row */}
            <div className="flex items-center gap-3 text-xs text-brand-text-muted">
              <span>{brief.recommended_word_count?.toLocaleString()} words</span>
              <span>{formatDate(brief.created_at)}</span>
              {brief.suggested_titles?.length > 0 && (
                <span>{brief.suggested_titles.length} title ideas</span>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {confirmDelete ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => void handleDelete()}
                  disabled={deleting}
                  className="text-xs font-medium px-2 py-1 rounded-md bg-[#ef4444]/10 text-[#ef4444] hover:bg-[#ef4444]/20 transition-colors disabled:opacity-50"
                >
                  {deleting ? 'Deleting...' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="text-xs font-medium px-2 py-1 rounded-md text-brand-text-muted hover:text-brand-text transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="p-1.5 rounded-md text-brand-text-muted hover:text-[#ef4444] hover:bg-[#ef4444]/10 transition-colors"
                aria-label="Delete brief"
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        </div>

        {/* Expand toggle */}
        <button
          onClick={() => void handleToggle()}
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
        >
          {expanded ? 'Hide Details' : 'View Details'}
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* Expanded detail */}
      {expanded && (
        loadingDetail ? (
          <div className="border-t border-brand-border px-5 py-6 flex items-center justify-center">
            <Spinner size="sm" />
            <span className="ml-2 text-sm text-brand-text-muted">Loading brief details...</span>
          </div>
        ) : detail ? (
          <BriefDetailPanel detail={detail} />
        ) : null
      )}
    </div>
  );
}

// ─── Empty State ────────────────────────────────────

function EmptyState() {
  return (
    <Card className="!p-10 text-center">
      <FileText size={40} className="text-[#3b82f6] mx-auto mb-4 opacity-50" />
      <h3 className="text-lg font-semibold text-brand-text mb-2">
        No content briefs yet
      </h3>
      <p className="text-sm text-brand-text-muted max-w-md mx-auto">
        Create your first content brief by entering a topic above. The AI will generate
        a comprehensive brief including keyword analysis, outline, and internal linking suggestions.
      </p>
    </Card>
  );
}

// ─── Main Page ──────────────────────────────────────

export default function BriefsPage() {
  const { currentSite } = useSite();
  const { session, token: authToken } = useAuth();
  const token = session?.access_token ?? authToken;

  const [briefs, setBriefs] = useState<BriefSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [topic, setTopic] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [rateRemaining, setRateRemaining] = useState(5);

  const siteId = currentSite?.id ?? null;

  // Fetch briefs
  const fetchBriefs = useCallback(async () => {
    if (!siteId || !token) return;
    setLoading(true);
    try {
      const data = await apiFetch<BriefSummary[]>(
        `/sites/${siteId}/intelligence/briefs`,
        { token }
      );
      setBriefs(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [siteId, token]);

  useEffect(() => {
    void fetchBriefs();
  }, [fetchBriefs]);

  // Create brief
  const handleCreate = async () => {
    if (!siteId || !token || !topic.trim() || creating) return;
    if (rateRemaining <= 0) {
      setError('Rate limit reached. Please wait a minute before creating another brief.');
      return;
    }

    setCreating(true);
    setError(null);
    try {
      const newBrief = await apiFetch<BriefSummary>(
        `/sites/${siteId}/intelligence/briefs`,
        {
          method: 'POST',
          body: JSON.stringify({ topic: topic.trim() }),
          token,
        }
      );
      setBriefs((prev) => [newBrief, ...prev]);
      setTopic('');
      setRateRemaining((r) => Math.max(0, r - 1));

      // Restore rate limit after 60s
      setTimeout(() => {
        setRateRemaining((r) => Math.min(5, r + 1));
      }, 60_000);
    } catch (err) {
      if (err instanceof Error && err.message.includes('429')) {
        setError('Rate limit reached. Please wait a minute before creating another brief.');
        setRateRemaining(0);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to create brief');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (id: string) => {
    setBriefs((prev) => prev.filter((b) => b.id !== id));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleCreate();
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-2">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FileText size={24} className="text-[#3b82f6]" />
        <div>
          <h1 className="text-xl font-bold text-brand-text">Content Briefs</h1>
          <p className="text-sm text-brand-text-muted">
            Generate AI-powered content briefs for new topics
          </p>
        </div>
      </div>

      {/* Create form */}
      <Card className="!p-5">
        <div className="flex gap-3 items-start">
          <div className="flex-1">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter a topic (e.g., 'How to improve blog SEO')"
              className="w-full rounded-lg bg-brand-bg border border-brand-border text-sm
                         text-brand-text placeholder-[#64748b] px-4 py-2.5 focus:outline-none
                         focus:border-[#3b82f6] transition-colors"
              disabled={creating}
            />
            {error && (
              <div className="flex items-center gap-1.5 mt-2 text-xs text-[#ef4444]">
                <AlertTriangle size={12} />
                {error}
              </div>
            )}
          </div>
          <button
            onClick={() => void handleCreate()}
            disabled={!topic.trim() || creating || rateRemaining <= 0}
            className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg
                       bg-[#3b82f6] text-white text-sm font-medium
                       hover:bg-[#2563eb] transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating ? (
              <>
                <Spinner size="sm" className="text-white" />
                Generating...
              </>
            ) : (
              <>
                <Plus size={16} />
                Create Brief
              </>
            )}
          </button>
        </div>
        <div className="mt-3">
          <RateLimitIndicator remaining={rateRemaining} />
        </div>
      </Card>

      {/* Brief list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner size="lg" />
        </div>
      ) : briefs.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
            {briefs.length} brief{briefs.length !== 1 ? 's' : ''}
          </p>
          {briefs.map((brief) => (
            <BriefCard
              key={brief.id}
              brief={brief}
              siteId={siteId!}
              token={token}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
