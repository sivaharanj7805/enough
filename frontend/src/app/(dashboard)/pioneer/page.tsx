'use client';

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import {
  ArrowRight, RotateCcw, ChevronDown, ChevronRight, Download,
  Send, Plus, Trash2, GripVertical, Check, Minus,
} from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useClusters } from '@/lib/hooks/useApi';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { pioneer as copy } from '@/lib/copy';
import type { Cluster } from '@/lib/types';

type Phase = 'idea' | 'briefing' | 'build';
type SectionKey = 'title' | 'angle' | 'outline' | 'data' | 'links' | 'preflight';
type SectionStatus = 'empty' | 'in_progress' | 'complete';
interface OutlineItem { id: string; text: string }
interface LinkSuggestion { postTitle: string; reason: string; checked: boolean }
interface BuildState {
  title: string; angle: string; outline: OutlineItem[];
  data: string; linksTo: LinkSuggestion[]; linksFrom: LinkSuggestion[];
}

function hColor(s: number | null): string {
  if (s == null) return '#6b7280';
  return s >= 70 ? '#22c55e' : s >= 40 ? '#eab308' : '#ef4444';
}
function overlapSignal(clusters: Cluster[], idea: string): 'green' | 'amber' | 'red' {
  const lower = idea.toLowerCase();
  const m = clusters.filter((c) => c.label && lower.includes(c.label.toLowerCase().split(' ')[0]));
  if (m.length === 0) return 'green';
  return (m[0].post_count ?? 0) > 10 ? 'red' : (m[0].post_count ?? 0) > 4 ? 'amber' : 'green';
}
function findBestCluster(clusters: Cluster[], idea: string): Cluster | null {
  const lower = idea.toLowerCase();
  return clusters.find((c) => c.label && lower.includes(c.label.toLowerCase().split(' ')[0])) ?? clusters[0] ?? null;
}

const STATUS_DOT: Record<SectionStatus, string> = { empty: 'bg-[#374151]', in_progress: 'bg-[#eab308]', complete: 'bg-[#22c55e]' };
const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: 'title', label: copy.sectionTitle }, { key: 'angle', label: copy.sectionAngle },
  { key: 'outline', label: copy.sectionOutline }, { key: 'data', label: copy.sectionData },
  { key: 'links', label: copy.sectionLinks }, { key: 'preflight', label: copy.sectionPreflight },
];
let olId = 0;
function mkId(): string { return `ol-${Date.now()}-${++olId}`; }

/* ── Cluster Map Strip ─────────────────────────── */

function ClusterStrip({ clusters, activeId, onSelect }: { clusters: Cluster[]; activeId: string | null; onSelect: (c: Cluster) => void }) {
  const max = Math.max(1, ...clusters.map((c) => c.post_count));
  return (
    <div className="flex-shrink-0 border-b border-[#1e293b] bg-[#0a0f1a]/80">
      <div className="flex items-center gap-2 px-4 py-2 overflow-x-auto">
        <span className="text-[10px] font-medium uppercase tracking-wider text-[#475569] shrink-0">Clusters</span>
        {clusters.map((c) => {
          const active = activeId === c.id;
          return (
            <button key={c.id} onClick={() => onSelect(c)}
              style={{ width: Math.max(64, Math.round((c.post_count / max) * 160)), backgroundColor: active ? `${hColor(c.health_score)}18` : 'rgba(30,41,59,0.5)', borderColor: active ? hColor(c.health_score) : '#1e293b' }}
              className="shrink-0 rounded-lg border px-2 py-1.5 text-left transition-all hover:border-[#334155]"
              aria-label={`Select cluster ${c.label ?? 'Unnamed'}`}>
              <p className="text-[10px] font-medium text-brand-text truncate">{c.label ?? 'Unnamed'}</p>
              <p className="text-[9px] text-brand-text-muted">{c.post_count} posts</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Phase 1: Idea Input ───────────────────────── */

function IdeaInput({ onSubmit }: { onSubmit: (v: string) => void }) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const submit = useCallback(() => { if (value.trim()) onSubmit(value.trim()); }, [value, onSubmit]);
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-xl space-y-4 text-center">
        <input ref={ref} type="text" value={value} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          placeholder={copy.inputPlaceholder} aria-label={copy.inputPlaceholder}
          className="w-full rounded-xl border border-[#1e293b] bg-[#0f172a] px-5 py-4 text-lg text-brand-text placeholder:text-[#475569] focus:border-[#3b82f6] focus:outline-none focus:ring-1 focus:ring-[#3b82f6] transition-colors" />
        <p className="text-sm text-brand-text-muted">{copy.inputHint}</p>
      </div>
    </div>
  );
}

/* ── Phase 2: Briefing ─────────────────────────── */

function BriefingPanel({ idea, cluster, signal, onProceed, onRethink }: {
  idea: string; cluster: Cluster | null; signal: 'green' | 'amber' | 'red';
  onProceed: () => void; onRethink: () => void;
}) {
  const projected = cluster?.health_score != null ? Math.min(100, (cluster.health_score ?? 0) + Math.round(Math.random() * 8 + 2)) : null;
  const signalCfg = { green: { c: '#22c55e', l: 'Low risk', d: 'No existing posts closely match this topic.' }, amber: { c: '#eab308', l: 'Some overlap', d: 'Some posts touch this topic. Angle carefully to avoid overlap.' }, red: { c: '#ef4444', l: 'High overlap', d: 'Multiple posts already cover this area. Consider updating instead.' } };
  const s = signalCfg[signal];
  return (
    <div className="animate-in slide-in-from-right-4 duration-300 w-full max-w-md space-y-4">
      <h2 className="text-lg font-semibold text-brand-text">{copy.briefingTitle}</h2>
      <Card className="!p-4 space-y-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-1">{copy.clusterFit}</p>
          {cluster ? (
            <p className="text-sm text-brand-text">Maps to <span className="font-semibold" style={{ color: hColor(cluster.health_score) }}>{cluster.label ?? 'Unnamed'}</span> ({cluster.post_count} posts, health {Math.round(cluster.health_score ?? 0)})</p>
          ) : <p className="text-sm text-brand-text">New territory — this could seed a new cluster</p>}
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-1">{copy.overlapRisk}</p>
          <span className="inline-flex items-center gap-1.5 text-sm">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.c }} />
            <span style={{ color: s.c }}>{s.l}</span>
          </span>
          <p className="text-xs text-brand-text-muted mt-1">{s.d}</p>
        </div>
        {cluster?.health_score != null && projected != null && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-1">{copy.clusterImpact}</p>
            <p className="text-sm text-brand-text">
              If this post scores well, cluster health could move from{' '}
              <span className="font-semibold" style={{ color: hColor(cluster.health_score) }}>{Math.round(cluster.health_score ?? 0)}</span>{' to '}
              <span className="font-semibold" style={{ color: hColor(projected) }}>{projected}</span>
            </p>
          </div>
        )}
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-1">{copy.siteKnows}</p>
          <p className="text-xs text-brand-text-muted italic">{cluster ? `${cluster.post_count} posts in this cluster cover related topics. Your site has existing authority here.` : 'No existing coverage detected for this topic.'}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-brand-text-muted mb-1">{copy.siteDoesntKnow}</p>
          <p className="text-xs text-brand-text-muted italic">This idea could fill a gap by addressing &ldquo;{idea}&rdquo; from a fresh angle{cluster ? ` within the ${cluster.label ?? 'Unnamed'} cluster` : ''}.</p>
        </div>
      </Card>
      <div className="flex items-center gap-3">
        <button onClick={onProceed} className="flex items-center gap-2 rounded-lg bg-[#3b82f6] px-4 py-2 text-sm font-medium text-white hover:bg-[#2563eb] transition-colors" aria-label={copy.proceed}>{copy.proceed} <ArrowRight size={14} /></button>
        <button onClick={onRethink} className="flex items-center gap-2 rounded-lg border border-[#1e293b] px-4 py-2 text-sm font-medium text-brand-text-muted hover:text-brand-text hover:border-[#334155] transition-colors" aria-label={copy.rethink}><RotateCcw size={14} /> {copy.rethink}</button>
      </div>
    </div>
  );
}

/* ── Phase 3: Build Canvas ─────────────────────── */

function BuildCanvas({ idea, cluster, clusters, onExport }: {
  idea: string; cluster: Cluster | null; clusters: Cluster[]; onExport: (s: BuildState) => void;
}) {
  const [activeSection, setActive] = useState<SectionKey>('title');
  const [openSet, setOpenSet] = useState<Set<SectionKey>>(() => new Set<SectionKey>(['title']));
  const [askInput, setAskInput] = useState('');
  const [bs, setBs] = useState<BuildState>({
    title: '', angle: '', outline: [{ id: mkId(), text: '' }], data: '',
    linksTo: cluster ? [
      { postTitle: `Best practices for ${cluster.label ?? 'this topic'}`, reason: 'Contextual link in intro', checked: true },
      { postTitle: `${cluster.label ?? 'Topic'} beginner guide`, reason: 'Background reference', checked: false },
    ] : [],
    linksFrom: cluster ? [{ postTitle: `${cluster.label ?? 'Topic'} tools comparison`, reason: 'Related resource', checked: true }] : [],
  });

  const toggle = useCallback((k: SectionKey) => {
    setOpenSet((p) => { const n = new Set(p); if (n.has(k)) { n.delete(k); } else { n.add(k); } return n; });
    setActive(k);
  }, []);

  const status = useCallback((k: SectionKey): SectionStatus => {
    switch (k) {
      case 'title': return bs.title.length > 10 ? 'complete' : bs.title.length > 0 ? 'in_progress' : 'empty';
      case 'angle': return bs.angle.length > 30 ? 'complete' : bs.angle.length > 0 ? 'in_progress' : 'empty';
      case 'outline': { const f = bs.outline.filter((o) => o.text.trim()).length; return f >= 3 ? 'complete' : f > 0 ? 'in_progress' : 'empty'; }
      case 'data': return bs.data.length > 20 ? 'complete' : bs.data.length > 0 ? 'in_progress' : 'empty';
      case 'links': return (bs.linksTo.some((l) => l.checked) || bs.linksFrom.some((l) => l.checked)) ? 'complete' : 'empty';
      case 'preflight': return status('title') === 'complete' && status('outline') === 'complete' ? 'complete' : 'in_progress';
    }
  }, [bs]);

  const wordEst = useMemo(() => Math.max(800, bs.outline.filter((o) => o.text.trim()).length * 350), [bs.outline]);
  const qH2 = useMemo(() => bs.outline.filter((o) => o.text.trim().endsWith('?')).length, [bs.outline]);

  const toggleLink = useCallback((dir: 'to' | 'from', i: number) => {
    setBs((p) => { const k = dir === 'to' ? 'linksTo' : 'linksFrom'; const u = [...p[k]]; u[i] = { ...u[i], checked: !u[i].checked }; return { ...p, [k]: u }; });
  }, []);

  const aiCtx = useMemo((): { heading: string; items: string[] } => {
    const c = cluster;
    switch (activeSection) {
      case 'title': return { heading: 'Title analysis', items: [`Character count: ${bs.title.length}/60 recommended`, bs.title.length > 60 ? 'Title may be truncated in search results' : 'Length looks good for search', c ? `Pattern: ${c.post_count > 5 ? 'Listicle and how-to titles perform best here' : 'Room for authoritative guides'}` : 'No cluster data for comparison'] };
      case 'angle': return { heading: 'Angle analysis', items: [bs.angle.length > 0 ? 'Angle defined — checking differentiation' : 'Define your unique angle to stand out', c ? `${c.post_count} existing posts — differentiation is key` : 'New territory, strong angles build authority fast', 'Contrarian or data-backed angles earn more citations'] };
      case 'outline': return { heading: 'Structure analysis', items: [`${bs.outline.filter((o) => o.text.trim()).length} headings defined`, `${qH2} question-format H2s (aim for 2+)`, `Estimated word count: ~${wordEst}`, bs.outline.length < 4 ? 'Consider adding more sections for depth' : 'Good structural depth'] };
      case 'data': return { heading: 'Evidence check', items: [bs.data.length > 0 ? 'Data plan started' : 'Add statistics, examples, or original data', 'Posts with original data get 2x more backlinks', c ? `Look for data patterns across ${c.post_count} posts in this cluster` : 'Original research creates differentiation'] };
      case 'links': return { heading: 'Link analysis', items: [`${bs.linksTo.filter((l) => l.checked).length} inbound links selected`, `${bs.linksFrom.filter((l) => l.checked).length} outbound links selected`, 'Internal links strengthen cluster cohesion and distribute authority'] };
      case 'preflight': return { heading: 'Launch readiness', items: [status('title') === 'complete' ? 'Title: ready' : 'Title: needs work', status('angle') === 'complete' ? 'Angle: ready' : 'Angle: needs work', status('outline') === 'complete' ? 'Outline: ready' : 'Outline: needs work', `Word count target: ~${wordEst}`] };
    }
  }, [activeSection, bs, cluster, qH2, wordEst, status]);

  const inputCls = 'w-full rounded-lg border border-[#1e293b] bg-[#0f172a] px-3 py-2 text-sm text-brand-text placeholder:text-[#475569] focus:border-[#3b82f6] focus:outline-none transition-colors';

  return (
    <div className="flex-1 flex overflow-hidden animate-in fade-in duration-300">
      {/* Workspace 65% */}
      <div className="flex-[65] overflow-y-auto px-6 py-4 space-y-1 border-r border-[#1e293b]">
        <h2 className="text-lg font-semibold text-brand-text mb-3">{copy.buildTitle}</h2>
        {SECTIONS.map(({ key, label }) => (
          <div key={key} className="border-b border-[#1e293b]/50 last:border-b-0">
            <button onClick={() => toggle(key)} className="w-full flex items-center gap-3 py-2 text-left" aria-label={`${openSet.has(key) ? 'Collapse' : 'Expand'} ${label}`}>
              <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${STATUS_DOT[status(key)]}`} />
              <span className="text-sm font-semibold text-brand-text flex-1">{label}</span>
              {openSet.has(key) ? <ChevronDown size={14} className="text-brand-text-muted" /> : <ChevronRight size={14} className="text-brand-text-muted" />}
            </button>
            {openSet.has(key) && (
              <div className="pb-4 pl-5" onClick={() => setActive(key)}>
                {key === 'title' && <input type="text" value={bs.title} onChange={(e) => setBs((p) => ({ ...p, title: e.target.value }))} onFocus={() => setActive('title')} placeholder="Enter your post title" aria-label="Post title" className={inputCls} />}
                {key === 'angle' && <textarea value={bs.angle} onChange={(e) => setBs((p) => ({ ...p, angle: e.target.value }))} onFocus={() => setActive('angle')} placeholder="What makes your perspective unique?" aria-label="Content angle" rows={3} className={`${inputCls} resize-none`} />}
                {key === 'outline' && (
                  <div className="space-y-2">
                    {bs.outline.map((item, i) => (
                      <div key={item.id} className="flex items-center gap-2">
                        <GripVertical size={12} className="text-[#475569] shrink-0" />
                        <span className="text-[10px] text-[#475569] shrink-0 w-6">H2</span>
                        <input type="text" value={item.text} onChange={(e) => setBs((p) => ({ ...p, outline: p.outline.map((o) => o.id === item.id ? { ...o, text: e.target.value } : o) }))} onFocus={() => setActive('outline')} placeholder={`Heading ${i + 1}`} aria-label={`Outline heading ${i + 1}`} className="flex-1 rounded border border-[#1e293b] bg-[#0f172a] px-2 py-1.5 text-sm text-brand-text placeholder:text-[#475569] focus:border-[#3b82f6] focus:outline-none transition-colors" />
                        {bs.outline.length > 1 && <button onClick={() => setBs((p) => ({ ...p, outline: p.outline.filter((o) => o.id !== item.id) }))} className="text-[#475569] hover:text-red-400 transition-colors" aria-label="Remove heading"><Trash2 size={12} /></button>}
                      </div>
                    ))}
                    <button onClick={() => setBs((p) => ({ ...p, outline: [...p.outline, { id: mkId(), text: '' }] }))} className="flex items-center gap-1 text-xs text-[#3b82f6] hover:text-[#60a5fa] transition-colors" aria-label="Add outline heading"><Plus size={12} /> Add heading</button>
                  </div>
                )}
                {key === 'data' && <textarea value={bs.data} onChange={(e) => setBs((p) => ({ ...p, data: e.target.value }))} onFocus={() => setActive('data')} placeholder="Statistics, examples, original research to include..." aria-label="Data and evidence plan" rows={3} className={`${inputCls} resize-none`} />}
                {key === 'links' && (
                  <div className="space-y-3">
                    {(['to', 'from'] as const).map((dir) => {
                      const links = dir === 'to' ? bs.linksTo : bs.linksFrom;
                      return (
                        <div key={dir}>
                          <p className="text-xs font-medium text-brand-text-muted mb-1.5">{dir === 'to' ? copy.linkTo : copy.linkFrom}</p>
                          {links.length === 0 ? <p className="text-xs text-[#475569] italic">No link suggestions available</p> : links.map((link, i) => (
                            <label key={i} className="flex items-start gap-2 py-1 cursor-pointer">
                              <input type="checkbox" checked={link.checked} onChange={() => toggleLink(dir, i)} className="mt-0.5 accent-[#3b82f6]" />
                              <span className="text-xs text-brand-text">{link.postTitle} <span className="text-brand-text-muted">— {link.reason}</span></span>
                            </label>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}
                {key === 'preflight' && (
                  <div className="space-y-1.5">
                    {[
                      { done: status('title') === 'complete', text: `Target word count: ~${wordEst}` },
                      { done: qH2 >= 2, text: `Question-format H2s: ${qH2} of 2+ target` },
                      { done: bs.outline.some((o) => o.text.toLowerCase().includes('faq')), text: 'FAQ section included' },
                      { done: bs.data.length > 20, text: 'Data/evidence plan defined' },
                      { done: overlapSignal(clusters, idea) !== 'red', text: 'Overlap safety check passed' },
                    ].map((ck, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        {ck.done ? <Check size={12} className="text-[#22c55e]" /> : <Minus size={12} className="text-[#475569]" />}
                        <span className={ck.done ? 'text-brand-text' : 'text-brand-text-muted'}>{ck.text}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        <div className="pt-4">
          <button onClick={() => onExport(bs)} className="flex items-center gap-2 rounded-lg bg-[#3b82f6] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#2563eb] transition-colors" aria-label={copy.exportBrief}><Download size={14} /> {copy.exportBrief}</button>
        </div>
      </div>
      {/* AI Context Panel 35% */}
      <div className="flex-[35] flex flex-col bg-[#0a0f1a]/60 overflow-hidden">
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[#475569]">{copy.aiPanelTitle}</h3>
          <Card className="!p-3 !bg-[#0f172a]/80 space-y-2">
            <p className="text-xs font-semibold text-brand-text">{aiCtx.heading}</p>
            {aiCtx.items.map((item, i) => <p key={i} className="text-xs text-brand-text-muted leading-relaxed">{item}</p>)}
          </Card>
          {cluster && (
            <Card className="!p-3 !bg-[#0f172a]/80 space-y-1">
              <p className="text-xs font-semibold text-brand-text">Cluster context</p>
              <p className="text-xs text-brand-text-muted"><span className="font-medium" style={{ color: hColor(cluster.health_score) }}>{cluster.label ?? 'Unnamed'}</span> &middot; {cluster.post_count} posts &middot; health {Math.round(cluster.health_score ?? 0)}</p>
              {cluster.description && <p className="text-xs text-brand-text-muted">{cluster.description}</p>}
            </Card>
          )}
        </div>
        <div className="border-t border-[#1e293b] px-4 py-3">
          <div className="flex items-center gap-2">
            <input type="text" value={askInput} onChange={(e) => setAskInput(e.target.value)} placeholder={copy.askPlaceholder} aria-label={copy.askPlaceholder} className="flex-1 rounded-lg border border-[#1e293b] bg-[#0f172a] px-3 py-1.5 text-xs text-brand-text placeholder:text-[#475569] focus:border-[#3b82f6] focus:outline-none transition-colors" />
            <button className="rounded-lg bg-[#1e293b] p-1.5 text-[#475569] hover:text-brand-text transition-colors" aria-label="Send question"><Send size={12} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Export Markdown ────────────────────────────── */

function exportMarkdown(idea: string, cluster: Cluster | null, st: BuildState) {
  const now = new Date().toISOString().split('T')[0];
  const wEst = Math.max(800, st.outline.filter((o) => o.text.trim()).length * 350);
  const qCount = st.outline.filter((o) => o.text.trim().endsWith('?')).length;
  const lines = [
    `# Content Brief: ${st.title || idea}`,
    `Cluster: ${cluster?.label ?? 'New'} | Est. length: ${wEst} words | Created: ${now}`,
    '', '## Angle', st.angle || '_Not defined_',
    '', '## Outline', ...st.outline.filter((o) => o.text.trim()).map((o) => `- H2: ${o.text}`),
    '', '## Data Plan', st.data || '_Not defined_',
    '', '## Internal Links', '### Link TO this post from:',
    ...(st.linksTo.filter((l) => l.checked).map((l) => `- ${l.postTitle} \u2014 ${l.reason}`)),
    ...(st.linksTo.filter((l) => l.checked).length === 0 ? ['_None selected_'] : []),
    '### Link FROM this post to:',
    ...(st.linksFrom.filter((l) => l.checked).map((l) => `- ${l.postTitle} \u2014 ${l.reason}`)),
    ...(st.linksFrom.filter((l) => l.checked).length === 0 ? ['_None selected_'] : []),
    '', '## Pre-Flight',
    `- [${st.title.length > 10 ? 'x' : ' '}] Target word count: ${wEst}`,
    `- [${qCount >= 2 ? 'x' : ' '}] Question-format H2s: ${qCount} of 2+`,
    `- [${st.outline.some((o) => o.text.toLowerCase().includes('faq')) ? 'x' : ' '}] FAQ section included`,
    `- [${st.data.length > 20 ? 'x' : ' '}] Data/evidence plan defined`,
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url;
  a.download = `brief-${(st.title || idea).toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)}.md`;
  a.click(); URL.revokeObjectURL(url);
}

/* ── Main Page ─────────────────────────────────── */

export default function PioneerPage() {
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const { data: clusters, isLoading } = useClusters(siteId);

  const [phase, setPhase] = useState<Phase>('idea');
  const [idea, setIdea] = useState('');
  const [selCluster, setSelCluster] = useState<Cluster | null>(null);

  const sorted = useMemo(() => [...(clusters ?? [])].sort((a, b) => b.post_count - a.post_count), [clusters]);
  const bestCluster = useMemo(() => (idea && sorted.length > 0 ? findBestCluster(sorted, idea) : null), [idea, sorted]);
  const signal = useMemo(() => (idea && sorted.length > 0 ? overlapSignal(sorted, idea) : 'green' as const), [idea, sorted]);

  const onIdeaSubmit = useCallback((t: string) => { setIdea(t); setPhase('briefing'); setSelCluster(findBestCluster(sorted, t)); }, [sorted]);
  const onProceed = useCallback(() => setPhase('build'), []);
  const onRethink = useCallback(() => { setPhase('idea'); setIdea(''); }, []);
  const onExport = useCallback((st: BuildState) => { exportMarkdown(idea, selCluster, st); }, [idea, selCluster]);

  if (isLoading) return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] max-w-7xl mx-auto">
      <div className="px-6 pt-4 pb-2">
        <h1 className="text-2xl font-bold text-brand-text">{copy.pageTitle}</h1>
        <p className="text-sm text-brand-text-muted">{copy.pageSubtitle}</p>
      </div>
      {sorted.length > 0 && <ClusterStrip clusters={sorted} activeId={selCluster?.id ?? null} onSelect={setSelCluster} />}
      {sorted.length === 0 && !isLoading && <div className="px-6 py-2"><p className="text-xs text-[#475569]">{copy.noClusterData}</p></div>}
      {phase === 'idea' && <IdeaInput onSubmit={onIdeaSubmit} />}
      {phase === 'briefing' && (
        <div className="flex-1 flex items-center justify-center px-6 overflow-y-auto">
          <BriefingPanel idea={idea} cluster={bestCluster} signal={signal} onProceed={onProceed} onRethink={onRethink} />
        </div>
      )}
      {phase === 'build' && <BuildCanvas idea={idea} cluster={selCluster} clusters={sorted} onExport={onExport} />}
    </div>
  );
}
