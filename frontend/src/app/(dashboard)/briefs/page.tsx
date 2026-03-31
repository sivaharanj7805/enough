'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import {
  Lightbulb, Sparkles, Trash2, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, Clock, FileText, Wand2, Link2, MessageSquare, StickyNote,
  Target, BookOpen, ShieldCheck, HelpCircle, Zap,
} from 'lucide-react';

// ─── Types ──────────────────────────────────────────
interface BriefSummary {
  id: string; target_keyword: string; suggested_titles: string[];
  recommended_word_count: number; cannibalization_risk: 'low' | 'medium' | 'high';
  content_angle: string; difficulty_level: string;
  status: 'draft' | 'in_progress' | 'completed'; created_at: string;
}
interface OutlineItem {
  heading?: string; text?: string; level?: string;
  subheadings?: string[]; bullets?: string[];
  notes?: string; estimated_words?: number;
}
interface ILink { url?: string; anchor?: string; post_title?: string; anchor_text?: string; title?: string }
interface BriefDetail extends BriefSummary {
  secondary_keywords: string[]; outline: OutlineItem[];
  questions_to_answer: string[]; differentiation_notes: string;
  avoid_topics: string[]; internal_links_from: ILink[]; internal_links_to: ILink[];
  opening_hook?: string; cta_suggestion?: string; faq_questions?: string[];
  geo_requirements?: { answer_first_paragraph?: string; schema_types?: string[] };
  content_type?: string; confidence?: number; updated_at: string;
}

// ─── Constants ──────────────────────────────────────
const RISK: Record<string, { l: string; c: string }> = {
  low: { l: 'Low Risk', c: 'text-[#22c55e] bg-[#22c55e]/10' },
  medium: { l: 'Med Risk', c: 'text-[#eab308] bg-[#eab308]/10' },
  high: { l: 'High Risk', c: 'text-[#ef4444] bg-[#ef4444]/10' },
};
const STAT: Record<string, { l: string; i: typeof Clock; c: string }> = {
  draft: { l: 'Draft', i: FileText, c: 'text-[#94a3b8] bg-[#94a3b8]/10' },
  in_progress: { l: 'In Progress', i: Clock, c: 'text-[#3b82f6] bg-[#3b82f6]/10' },
  completed: { l: 'Published', i: CheckCircle, c: 'text-[#22c55e] bg-[#22c55e]/10' },
};
const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return '\u2014';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '\u2014' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};
const SUGGESTIONS = ['content marketing for SaaS', 'link building strategies', 'on-page SEO checklist', 'how to do keyword research'];

// ─── Helpers ────────────────────────────────────────
function Sec({ label, icon: I, children }: { label: string; icon?: typeof Target; children: React.ReactNode }) {
  return (<div><p className="text-xs font-semibold uppercase tracking-wider text-[#64748b] mb-2 flex items-center gap-1.5">
    {I && <I size={12} />}{label}</p>{children}</div>);
}
function Tags({ items, cls }: { items: string[]; cls: string }) {
  return (<div className="flex flex-wrap gap-1.5">
    {items.map((t, i) => <span key={i} className={`text-xs px-2 py-1 rounded-md ${cls}`}>{t}</span>)}</div>);
}
function Badge({ c, children }: { c: string; children: React.ReactNode }) {
  return <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded inline-flex items-center gap-1 ${c}`}>{children}</span>;
}

// ─── Detail Panel ───────────────────────────────────
function DetailPanel({ d, siteId, token }: { d: BriefDetail; siteId: string; token: string | null }) {
  const [refineInput, setRefineInput] = useState('');
  const [userNotes, setUserNotes] = useState('');
  const [refining, setRefining] = useState(false);
  const [rd, setRd] = useState<BriefDetail | null>(null);
  const dt = rd ?? d;
  const lc = (dt.internal_links_from?.length ?? 0) + (dt.internal_links_to?.length ?? 0);

  const handleRefine = async () => {
    if (!refineInput.trim() || refining) return;
    setRefining(true);
    try {
      const res = await apiFetch<Record<string, string>>(`/sites/${siteId}/intelligence/briefs`, {
        method: 'POST', token: token ?? undefined,
        body: JSON.stringify({ topic: `${dt.target_keyword} - ${refineInput.trim()}` }),
      });
      const nid = res?.brief_id ?? res?.id;
      if (nid) setRd(await apiFetch<BriefDetail>(`/sites/${siteId}/intelligence/briefs/${nid}`, { token: token ?? undefined }));
      setRefineInput('');
    } catch { /* silent */ } finally { setRefining(false); }
  };

  const oh = (s: OutlineItem) => s.heading ?? s.text ?? '';
  const os = (s: OutlineItem) => s.subheadings ?? s.bullets ?? [];

  return (
    <div className="border-t border-brand-border px-5 pb-5 space-y-4 pt-4">
      {(dt.confidence != null || dt.content_type) && (
        <div className="flex items-center gap-3 text-xs text-[#94a3b8]">
          {dt.content_type && <Badge c="bg-[#8b5cf6]/10 text-[#8b5cf6]">{dt.content_type}</Badge>}
          {dt.confidence != null && <span className="flex items-center gap-1">
            <ShieldCheck size={12} className="text-[#22c55e]" />Confidence: {Math.round(dt.confidence * 100)}%</span>}
        </div>
      )}
      {dt.opening_hook && (
        <Sec label="Opening Hook" icon={Zap}>
          <p className="text-sm text-[#e2e8f0] italic bg-[#0f172a] rounded-lg p-3 border border-[#1e293b]">&ldquo;{dt.opening_hook}&rdquo;</p>
        </Sec>
      )}
      {dt.secondary_keywords?.length > 0 && <Sec label="Secondary Keywords" icon={Target}><Tags items={dt.secondary_keywords} cls="bg-[#1e293b] text-[#94a3b8]" /></Sec>}
      {dt.suggested_titles?.length > 0 && (
        <Sec label={`Suggested Titles (${dt.suggested_titles.length})`} icon={BookOpen}>
          <ul className="space-y-1">{dt.suggested_titles.map((t, i) => <li key={i} className="text-sm text-[#e2e8f0]">{i + 1}. {t}</li>)}</ul>
        </Sec>
      )}
      {dt.content_angle && <Sec label="Content Angle"><p className="text-sm text-[#94a3b8]">{dt.content_angle}</p></Sec>}
      {dt.outline?.length > 0 && (
        <Sec label={`Outline (${dt.outline.length} sections)`} icon={FileText}>
          <div className="space-y-2">{dt.outline.map((s, i) => (
            <div key={i} className="rounded-lg bg-[#0f172a] p-3 border border-[#1e293b]">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-[#e2e8f0]">
                  {s.level && <span className="text-[10px] uppercase text-[#64748b] mr-2">{s.level}</span>}{oh(s)}
                </p>
                {s.estimated_words != null && <span className="text-[10px] text-[#64748b]">~{s.estimated_words}w</span>}
              </div>
              {os(s).length > 0 && <ul className="mt-1 ml-4 space-y-0.5">{os(s).map((sub, j) => <li key={j} className="text-xs text-[#94a3b8] list-disc">{sub}</li>)}</ul>}
              {s.notes && <p className="text-xs text-[#64748b] mt-1 italic">{s.notes}</p>}
            </div>
          ))}</div>
        </Sec>
      )}
      {dt.questions_to_answer?.length > 0 && (
        <Sec label="Questions to Answer" icon={HelpCircle}>
          <ul className="space-y-1">{dt.questions_to_answer.map((q, i) => (
            <li key={i} className="text-sm text-[#94a3b8] flex items-start gap-2"><span className="text-[#3b82f6] font-bold mt-0.5">?</span>{q}</li>
          ))}</ul>
        </Sec>
      )}
      {dt.faq_questions && dt.faq_questions.length > 0 && (
        <Sec label="FAQ Questions (AI Citability)">
          <ul className="space-y-1">{dt.faq_questions.map((q, i) => (
            <li key={i} className="text-sm text-[#94a3b8] flex items-start gap-2"><MessageSquare size={12} className="text-[#8b5cf6] mt-1 flex-shrink-0" />{q}</li>
          ))}</ul>
        </Sec>
      )}
      {dt.differentiation_notes && <Sec label="Differentiation Notes"><p className="text-sm text-[#94a3b8]">{dt.differentiation_notes}</p></Sec>}
      {dt.avoid_topics?.length > 0 && <Sec label="Topics to Avoid"><Tags items={dt.avoid_topics} cls="bg-[#ef4444]/10 text-[#ef4444]" /></Sec>}
      {lc > 0 && (
        <Sec label={`Internal Links (${lc})`} icon={Link2}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[{ links: dt.internal_links_from, label: 'Link from (existing)' }, { links: dt.internal_links_to, label: 'Link to (targets)' }]
              .filter(g => g.links?.length > 0).map(g => (
              <div key={g.label}><p className="text-[10px] uppercase text-[#64748b] mb-1">{g.label}</p>
                <ul className="space-y-1">{g.links.map((lk, i) => (
                  <li key={i} className="text-xs text-[#94a3b8]">
                    <span className="text-[#3b82f6]">{lk.anchor ?? lk.anchor_text ?? lk.title ?? 'link'}</span>
                    {lk.url && <span className="text-[#64748b] ml-1 truncate">{lk.url}</span>}
                  </li>
                ))}</ul></div>
            ))}
          </div>
        </Sec>
      )}
      {dt.cta_suggestion && <Sec label="Suggested CTA"><p className="text-sm text-[#94a3b8]">{dt.cta_suggestion}</p></Sec>}
      {dt.geo_requirements && (
        <Sec label="AI Readiness (GEO)" icon={ShieldCheck}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-[#94a3b8]">
            {dt.geo_requirements.answer_first_paragraph && (
              <div className="bg-[#0f172a] rounded-lg p-2 border border-[#1e293b]">
                <p className="text-[10px] uppercase text-[#64748b] mb-0.5">TL;DR Opening</p>{dt.geo_requirements.answer_first_paragraph}</div>
            )}
            {dt.geo_requirements.schema_types && (
              <div className="bg-[#0f172a] rounded-lg p-2 border border-[#1e293b]">
                <p className="text-[10px] uppercase text-[#64748b] mb-0.5">Schema Types</p>{dt.geo_requirements.schema_types.join(', ')}</div>
            )}
          </div>
        </Sec>
      )}
      <div className="flex items-center gap-4 text-xs text-[#64748b] pt-2 border-t border-[#1e293b]">
        <span>Target: {dt.recommended_word_count?.toLocaleString()} words</span>
        {dt.updated_at && <span>Updated: {fmtDate(dt.updated_at)}</span>}
      </div>
      {/* Refine */}
      <div className="pt-2">
        <p className="text-xs text-[#64748b] mb-1.5">Refine this idea &mdash; tell the AI a different angle or ask to go deeper</p>
        <div className="flex gap-2">
          <input type="text" value={refineInput} onChange={e => setRefineInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void handleRefine(); } }}
            disabled={refining} placeholder="e.g. 'focus on beginner audience' or 'add comparison angle'"
            className="flex-1 rounded-lg bg-brand-bg border border-brand-border text-xs text-brand-text placeholder-[#475569] px-3 py-2 focus:outline-none focus:border-[#8b5cf6] focus:ring-1 focus:ring-[#8b5cf6]/30 transition-colors"
            aria-label="Refine this content idea" />
          <button onClick={() => void handleRefine()} disabled={!refineInput.trim() || refining}
            className="text-xs font-medium px-3 py-2 rounded-lg bg-[#8b5cf6] text-white hover:bg-[#7c3aed] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
            aria-label="Refine idea">
            {refining ? <Spinner size="sm" className="text-white" /> : <Sparkles size={12} />}Refine
          </button>
        </div>
      </div>
      {/* User notes */}
      <div>
        <p className="text-xs text-[#64748b] mb-1.5 flex items-center gap-1"><StickyNote size={11} />Your notes</p>
        <textarea value={userNotes} onChange={e => setUserNotes(e.target.value)} rows={2}
          placeholder="Jot down your own angle, audience notes, or talking points..."
          className="w-full rounded-lg bg-brand-bg border border-brand-border text-xs text-brand-text placeholder-[#475569] px-3 py-2 focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30 transition-colors resize-none"
          aria-label="Your notes for this brief" />
      </div>
    </div>
  );
}

// ─── Brief Card ─────────────────────────────────────
function BriefCard({ brief: b, siteId, token, onDelete, autoExpand }: {
  brief: BriefSummary; siteId: string; token: string | null;
  onDelete: (id: string) => void; autoExpand?: boolean;
}) {
  const [expanded, setExpanded] = useState(autoExpand ?? false);
  const [detail, setDetail] = useState<BriefDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const risk = RISK[b.cannibalization_risk] ?? RISK.low;
  const st = STAT[b.status] ?? STAT.draft;
  const StI = st.i;
  const tc = b.suggested_titles?.length ?? 0;

  useEffect(() => {
    if (autoExpand && !detail && siteId && token) {
      setLoadingDetail(true);
      apiFetch<BriefDetail>(`/sites/${siteId}/intelligence/briefs/${b.id}`, { token })
        .then(setDetail).catch(() => {}).finally(() => setLoadingDetail(false));
    }
  }, [autoExpand, b.id, detail, siteId, token]);

  useEffect(() => { if (autoExpand && ref.current) ref.current.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, [autoExpand]);

  const toggle = async () => {
    if (expanded) { setExpanded(false); return; }
    setExpanded(true);
    if (!detail) {
      setLoadingDetail(true);
      try { setDetail(await apiFetch<BriefDetail>(`/sites/${siteId}/intelligence/briefs/${b.id}`, { token: token ?? undefined })); }
      catch { /* no detail */ } finally { setLoadingDetail(false); }
    }
  };
  const doDelete = async () => {
    setDeleting(true);
    try { await apiFetch<void>(`/sites/${siteId}/intelligence/briefs/${b.id}`, { method: 'DELETE', token: token ?? undefined }); onDelete(b.id); }
    catch { setConfirmDel(false); } finally { setDeleting(false); }
  };

  return (
    <div ref={ref} className={`rounded-xl border bg-brand-surface overflow-hidden transition-all duration-200 ${autoExpand ? 'border-[#3b82f6]/40 ring-1 ring-[#3b82f6]/20' : 'border-brand-border hover:border-[#334155]'}`}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-brand-text truncate mb-1.5">{b.target_keyword}</h3>
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <Badge c={risk.c}>{risk.l}</Badge>
              <Badge c={st.c}><StI size={10} />{st.l}</Badge>
            </div>
            {b.content_angle && <p className="text-sm text-brand-text-muted line-clamp-2 mb-2">{b.content_angle}</p>}
            <div className="flex items-center gap-3 flex-wrap text-xs text-brand-text-muted">
              <span>{b.recommended_word_count?.toLocaleString()} words</span>
              {tc > 0 && <span>{tc} title idea{tc !== 1 ? 's' : ''}</span>}
              <span>{fmtDate(b.created_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            {confirmDel ? (<>
              <button onClick={() => void doDelete()} disabled={deleting}
                className="text-xs font-medium px-2.5 py-1.5 rounded-md bg-[#ef4444] text-white hover:bg-[#dc2626] transition-colors disabled:opacity-50"
                aria-label="Confirm delete brief">{deleting ? 'Deleting...' : 'Yes, delete'}</button>
              <button onClick={() => setConfirmDel(false)} className="text-xs font-medium px-2.5 py-1.5 rounded-md text-brand-text-muted hover:text-brand-text transition-colors" aria-label="Cancel delete">Cancel</button>
            </>) : (
              <button onClick={() => setConfirmDel(true)} className="p-2 rounded-lg text-brand-text-muted hover:text-[#ef4444] hover:bg-[#ef4444]/10 transition-colors" aria-label="Delete brief" title="Delete"><Trash2 size={16} /></button>
            )}
          </div>
        </div>
        <button onClick={() => void toggle()} className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
          aria-label={expanded ? 'Hide details' : 'View details'}>
          {expanded ? 'Hide Details' : 'View Full Brief'}{expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      {expanded && (loadingDetail
        ? <div className="border-t border-brand-border px-5 py-6 flex items-center justify-center"><Spinner size="sm" /><span className="ml-2 text-sm text-brand-text-muted">Loading full brief...</span></div>
        : detail ? <DetailPanel d={detail} siteId={siteId} token={token} />
        : <div className="border-t border-brand-border px-5 py-4 text-sm text-brand-text-muted">Could not load brief details. Try collapsing and expanding again.</div>
      )}
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────
export default function BriefsPage() {
  const { currentSite } = useSite();
  const { session, token: authToken } = useAuth();
  const token = session?.access_token ?? authToken;
  const [briefs, setBriefs] = useState<BriefSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [topic, setTopic] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [newId, setNewId] = useState<string | null>(null);
  const siteId = currentSite?.id ?? null;

  const fetchBriefs = useCallback(async () => {
    if (!siteId || !token) return;
    setLoading(true);
    try { setBriefs(await apiFetch<BriefSummary[]>(`/sites/${siteId}/intelligence/briefs`, { token })); }
    catch { /* silent */ } finally { setLoading(false); }
  }, [siteId, token]);

  useEffect(() => { void fetchBriefs(); }, [fetchBriefs]);

  const handleGenerate = async () => {
    if (!siteId || !token || !topic.trim() || generating) return;
    setGenerating(true); setError(null); setNewId(null);
    try {
      const res = await apiFetch<Record<string, string>>(`/sites/${siteId}/intelligence/briefs`, {
        method: 'POST', body: JSON.stringify({ topic: topic.trim() }), token,
      });
      const cid = res?.brief_id ?? res?.id ?? null;
      setTopic(''); await fetchBriefs(); if (cid) setNewId(cid);
    } catch (err) {
      setError(err instanceof Error && err.message.includes('429')
        ? 'Rate limit reached. Please wait a minute before generating another idea.'
        : err instanceof Error ? err.message : 'Failed to generate content idea');
    } finally { setGenerating(false); }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-2">
      <div className="flex items-center gap-3">
        <Lightbulb size={24} className="text-[#3b82f6]" />
        <div>
          <h1 className="text-xl font-bold text-brand-text">Content Ideas Workshop</h1>
          <p className="text-sm text-brand-text-muted">Collaborate with AI to find content gaps, get detailed briefs, and refine ideas</p>
        </div>
      </div>

      <Card className="!p-0 overflow-hidden">
        <div className="bg-gradient-to-r from-[#3b82f6]/10 to-[#8b5cf6]/10 px-5 py-3 border-b border-brand-border">
          <div className="flex items-center gap-2"><Sparkles size={16} className="text-[#3b82f6]" />
            <h2 className="text-sm font-semibold text-brand-text">What should you write next?</h2></div>
          <p className="text-xs text-brand-text-muted mt-1">Enter a topic or keyword. The AI checks your clusters, rankings, and existing content to build a brief that fills real gaps.</p>
        </div>
        <div className="p-5 space-y-3">
          <div className="flex gap-3 items-start">
            <div className="flex-1">
              <input type="text" value={topic} onChange={e => setTopic(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleGenerate(); } }}
                disabled={generating} placeholder="Describe a topic, keyword, or question your audience asks..."
                className="w-full rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text placeholder-[#64748b] px-4 py-2.5 focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30 transition-colors"
                aria-label="Topic or keyword for content idea" />
              {error && <div className="flex items-center gap-1.5 mt-2 text-xs text-[#ef4444]"><AlertTriangle size={12} />{error}</div>}
            </div>
            <button onClick={() => void handleGenerate()} disabled={!topic.trim() || generating}
              className="flex-shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#3b82f6] text-white text-sm font-medium hover:bg-[#2563eb] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Generate content idea">
              {generating ? <><Spinner size="sm" className="text-white" />Generating...</> : <><Wand2 size={16} />Generate</>}
            </button>
          </div>
          {!generating && !topic && (
            <div className="flex flex-wrap gap-2"><span className="text-xs text-[#64748b]">Try:</span>
              {SUGGESTIONS.map(s => <button key={s} onClick={() => setTopic(s)} className="text-xs px-2.5 py-1 rounded-full bg-brand-bg border border-brand-border text-brand-text-muted hover:text-brand-text hover:border-[#3b82f6] transition-colors" aria-label={`Use suggestion: ${s}`}>{s}</button>)}
            </div>
          )}
          {generating && (
            <div className="flex items-center gap-2 text-xs text-brand-text-muted animate-pulse">
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>Analyzing clusters, checking cannibalization, building your brief...
            </div>
          )}
        </div>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-16"><Spinner size="lg" /></div>
      ) : briefs.length === 0 ? (
        <Card className="!p-10 text-center">
          <Lightbulb size={40} className="text-[#3b82f6] mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-semibold text-brand-text mb-2">No content ideas yet</h3>
          <p className="text-sm text-brand-text-muted max-w-md mx-auto">Enter a topic above and hit Generate. The AI will analyze your content ecosystem, check for cannibalization risks, and create a detailed brief with outline, links, and keyword targets.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">{briefs.length} content idea{briefs.length !== 1 ? 's' : ''}</p>
          {briefs.map(b => (
            <BriefCard key={b.id} brief={b} siteId={siteId!} token={token} autoExpand={b.id === newId}
              onDelete={id => { setBriefs(prev => prev.filter(x => x.id !== id)); if (id === newId) setNewId(null); }} />
          ))}
        </div>
      )}
    </div>
  );
}
