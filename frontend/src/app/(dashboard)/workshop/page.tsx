'use client';

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Send, Star, X, Hammer, Sparkles, ArrowRight, Loader2 } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { useClusters, useRecommendations, usePostDetail } from '@/lib/hooks/useApi';
import { apiUrl } from '@/lib/api';
import type { Cluster, Recommendation } from '@/lib/types';

interface ChatMessage { id: string; role: 'user' | 'ai'; content: string; timestamp: number }
interface IdeaCard { id: string; title: string; cluster: string; clusterColor: string; reason: string; effort: string; starred: boolean; dismissed: boolean }

function hColor(s: number | null) { return s == null ? '#6b7280' : s >= 70 ? '#22c55e' : s >= 40 ? '#eab308' : '#ef4444'; }
function hBg(s: number | null) { return s == null ? 'rgba(107,114,128,0.15)' : s >= 70 ? 'rgba(34,197,94,0.12)' : s >= 40 ? 'rgba(234,179,8,0.12)' : 'rgba(239,68,68,0.12)'; }

const PROMPTS = [
  'What are my biggest content gaps?',
  'Which cluster should I invest in next?',
  'What post should I update first?',
  'Give me 5 ideas for [cluster name]',
];
const CLUSTER_COLORS = ['#3B82F6', '#8b5cf6', '#22c55e', '#f97316', '#ec4899', '#06b6d4'];
let idCtr = 0;

function parseIdeas(text: string, clusters: Cluster[]): IdeaCard[] {
  const ideas: IdeaCard[] = [];
  for (const line of text.split('\n').filter((l) => l.trim())) {
    const m = line.match(/^(?:\d+[\.\)]\s*|-\s+)\*?\*?(.+?)\*?\*?(?:\s*[-:]\s*)(.+)$/);
    if (!m) continue;
    const title = m[1].replace(/\*\*/g, '').trim();
    const reason = m[2].replace(/\*\*/g, '').trim();
    const mc = clusters.find((c) => c.label && reason.toLowerCase().includes(c.label.toLowerCase()));
    idCtr++;
    ideas.push({
      id: `idea-${Date.now()}-${idCtr}`, title, reason, effort: '',
      cluster: mc?.label ?? 'General', starred: false, dismissed: false,
      clusterColor: CLUSTER_COLORS[(mc ? clusters.indexOf(mc) : ideas.length) % CLUSTER_COLORS.length],
    });
  }
  return ideas;
}

/* ─── Cluster strip ──────────────────────────────── */

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
              style={{ width: Math.max(72, Math.round((c.post_count / max) * 180)), backgroundColor: active ? hBg(c.health_score) : 'rgba(30,41,59,0.5)', borderColor: active ? hColor(c.health_score) : '#1e293b' }}
              className="shrink-0 rounded-lg border px-3 py-2 text-left transition-all hover:border-[#334155]"
              aria-label={`Focus on cluster ${c.label ?? 'Unnamed'}`}>
              <p className="text-[11px] font-medium truncate" style={{ color: active ? hColor(c.health_score) : '#e2e8f0' }}>{c.label ?? 'Unnamed'}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-[#64748b]">{c.post_count} posts</span>
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: hColor(c.health_score) }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Idea card ──────────────────────────────────── */

function IdeaCardView({ idea, onStar, onDismiss }: { idea: IdeaCard; onStar: () => void; onDismiss: () => void }) {
  if (idea.dismissed) return null;
  return (
    <div className={`rounded-xl border bg-[#0F1117] p-4 transition-all ${idea.starred ? 'border-[#eab308]/40 ring-1 ring-[#eab308]/20' : 'border-[#1e293b]'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[#e2e8f0] leading-snug">{idea.title}</p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: idea.clusterColor + '18', color: idea.clusterColor }}>{idea.cluster}</span>
            {idea.effort && <span className="text-[10px] text-[#475569]">{idea.effort}</span>}
          </div>
          <p className="text-xs text-[#64748b] mt-2 leading-relaxed">{idea.reason}</p>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <button onClick={onStar} className="p-1.5 rounded-lg hover:bg-[#1e293b] transition-colors" aria-label={idea.starred ? 'Unstar idea' : 'Star idea'}>
            <Star size={14} className={idea.starred ? 'text-[#eab308] fill-[#eab308]' : 'text-[#475569]'} />
          </button>
          <button onClick={onDismiss} className="p-1.5 rounded-lg hover:bg-[#1e293b] transition-colors" aria-label="Dismiss idea">
            <X size={14} className="text-[#475569]" />
          </button>
        </div>
      </div>
      <button className="mt-3 flex items-center gap-1 text-xs font-medium text-[#3B82F6] hover:text-[#60A5FA] transition-colors" aria-label="Develop this idea">
        Develop this <ArrowRight size={12} />
      </button>
    </div>
  );
}

/* ─── Main page ──────────────────────────────────── */

export default function WorkshopPage() {
  const { currentSite } = useSite();
  const { session, token: authToken } = useAuth();
  const searchParams = useSearchParams();
  const siteId = currentSite?.id ?? null;
  const postId = searchParams.get('postId');
  const recId = searchParams.get('recId');

  const { data: clusters } = useClusters(siteId);
  const { data: recsData } = useRecommendations(siteId);
  const { data: linkedPost } = usePostDetail(siteId, postId);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [ideas, setIdeas] = useState<IdeaCard[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState('');
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const ctxSent = useRef(false);
  const accessToken = session?.access_token ?? authToken;
  const clusterList = clusters ?? [];

  const sortedIdeas = useMemo(() => [...ideas].filter((i) => !i.dismissed).sort((a, b) => (a.starred === b.starred ? 0 : a.starred ? -1 : 1)), [ideas]);
  const linkedRec: Recommendation | undefined = useMemo(() => recsData?.recommendations?.find((r) => r.id === recId), [recsData, recId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, streaming]);
  useEffect(() => { inputRef.current?.focus(); }, []);

  // Auto-populate from Actions page context
  useEffect(() => {
    if (ctxSent.current || !siteId || !postId || !linkedPost) return;
    ctxSent.current = true;
    const q = linkedRec
      ? `I'm looking at "${linkedPost.title}" (${linkedPost.url}). The recommendation is: ${linkedRec.title}. ${linkedRec.summary} What should I do to improve this post?`
      : `I'm looking at "${linkedPost.title}" (${linkedPost.url}). What ideas do you have for this post?`;
    void handleSubmit(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, postId, linkedPost, linkedRec]);

  const handleSubmit = useCallback(async (question: string) => {
    if (!currentSite || !question.trim() || loading) return;
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: 'user', content: question.trim(), timestamp: Date.now() }]);
    setInput(''); setLoading(true); setStreaming('');

    let ctxPrefix = '';
    if (activeClusterId && clusters) {
      const cl = clusters.find((c) => c.id === activeClusterId);
      if (cl) ctxPrefix = `[Context: cluster "${cl.label}", ${cl.post_count} posts, health ${cl.health_score ?? 'N/A'}] `;
    }

    try {
      const res = await fetch(apiUrl(`/sites/${currentSite.id}/intelligence/oracle`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
        body: JSON.stringify({ draft_text: ctxPrefix + question.trim() }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);

      let finalContent = '';
      if (res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let full = '';
        // eslint-disable-next-line no-constant-condition
        while (true) { const { done, value } = await reader.read(); if (done) break; full += decoder.decode(value, { stream: true }); setStreaming(full); }
        finalContent = full;
        try {
          const p = JSON.parse(full);
          if (p.reasoning) {
            const parts = [p.reasoning];
            if (p.recommendation) parts.push(`\n\nRecommendation: ${p.recommendation}`);
            if (p.similar_posts?.length) { parts.push('\n\nRelated posts:'); p.similar_posts.forEach((sp: { title: string }) => parts.push(`- ${sp.title}`)); }
            finalContent = parts.join('\n');
          } else if (p.answer) finalContent = p.answer;
        } catch { /* raw text */ }
      } else {
        const data = await res.json();
        finalContent = data.reasoning || data.answer || JSON.stringify(data);
      }

      setMessages((prev) => [...prev, { id: `ai-${Date.now()}`, role: 'ai', content: finalContent, timestamp: Date.now() }]);
      if (clusters) { const ni = parseIdeas(finalContent, clusters); if (ni.length > 0) setIdeas((prev) => [...ni, ...prev]); }
    } catch (err) {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'ai', content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}. Please try again.`, timestamp: Date.now() }]);
    } finally { setLoading(false); setStreaming(''); }
  }, [currentSite, loading, accessToken, activeClusterId, clusters]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSubmit(input); } };
  const handleClusterSelect = useCallback((c: Cluster) => { setActiveClusterId((prev) => (prev === c.id ? null : c.id)); }, []);
  const handleStar = useCallback((id: string) => { setIdeas((prev) => prev.map((i) => (i.id === id ? { ...i, starred: !i.starred } : i))); }, []);
  const handleDismiss = useCallback((id: string) => { setIdeas((prev) => prev.map((i) => (i.id === id ? { ...i, dismissed: true } : i))); }, []);
  const handlePromptClick = useCallback((prompt: string) => {
    let text = prompt;
    if (activeClusterId && clusters) { const cl = clusters.find((c) => c.id === activeClusterId); if (cl?.label) text = text.replace('[cluster name]', cl.label); }
    void handleSubmit(text);
  }, [activeClusterId, clusters, handleSubmit]);

  const isEmpty = messages.length === 0 && !loading;
  const dataCtx = useMemo(() => {
    const p: string[] = [];
    if (clusterList.length > 0) p.push(`${clusterList.length} clusters`);
    const tp = clusterList.reduce((s, c) => s + c.post_count, 0);
    if (tp > 0) p.push(`${tp} posts`);
    if ((recsData?.total ?? 0) > 0) p.push(`${recsData!.total} recommendations`);
    return p.length > 0 ? `Based on your ${p.join(' and ')}` : '';
  }, [clusterList, recsData]);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 flex-shrink-0">
        <Hammer size={20} className="text-[#3B82F6]" />
        <div>
          <h1 className="text-lg font-semibold text-[#e2e8f0]">Workshop</h1>
          <p className="text-[11px] text-[#475569]">{dataCtx || 'Discover content ideas with AI'}</p>
        </div>
        {linkedPost && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[11px] text-[#475569]">Working on:</span>
            <Link href={`/posts/${postId}`} className="text-xs text-[#3B82F6] hover:text-[#60A5FA] truncate max-w-[200px]">{linkedPost.title}</Link>
          </div>
        )}
      </div>

      {clusterList.length > 0 && <ClusterStrip clusters={clusterList} activeId={activeClusterId} onSelect={handleClusterSelect} />}

      {/* Split layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left — Ideas workspace */}
        <div className="w-[60%] border-r border-[#1e293b] flex flex-col min-h-0">
          <div className="px-4 py-2 border-b border-[#1e293b] flex items-center justify-between flex-shrink-0">
            <span className="text-xs font-medium uppercase tracking-wider text-[#475569]">Ideas</span>
            {sortedIdeas.length > 0 && <span className="text-[10px] text-[#475569] tabular-nums">{sortedIdeas.length} idea{sortedIdeas.length !== 1 ? 's' : ''}</span>}
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {sortedIdeas.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                <Sparkles size={28} className="text-[#334155]" />
                <p className="text-sm font-medium text-[#94a3b8]">No ideas yet</p>
                <p className="text-xs text-[#475569] mt-1 max-w-[280px]">Ask the AI panel a question, or click a cluster to get started</p>
              </div>
            )}
            {sortedIdeas.map((idea) => <IdeaCardView key={idea.id} idea={idea} onStar={() => handleStar(idea.id)} onDismiss={() => handleDismiss(idea.id)} />)}
          </div>
        </div>

        {/* Right — AI chat */}
        <div className="w-[40%] flex flex-col min-h-0">
          <div className="px-4 py-2 border-b border-[#1e293b] flex-shrink-0">
            <span className="text-xs font-medium uppercase tracking-wider text-[#475569]">AI Assistant</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {isEmpty && (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <Sparkles size={24} className="text-[#3B82F6]" />
                <p className="text-sm text-[#64748b] text-center max-w-[260px]">Ask me about your content strategy, gaps, or what to write next</p>
                <div className="flex flex-col gap-2 w-full max-w-[300px]">
                  {PROMPTS.map((p) => (
                    <button key={p} onClick={() => handlePromptClick(p)}
                      className="text-xs text-left px-3 py-2.5 rounded-lg bg-[#1e293b] text-[#94a3b8] hover:bg-[#3B82F6]/10 hover:text-[#3B82F6] transition-colors border border-[#334155] hover:border-[#3B82F6]/30">
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={msg.role === 'user' ? 'bg-[#3B82F6] text-white rounded-2xl rounded-tr-sm px-3.5 py-2 max-w-[85%]' : 'bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-3.5 py-2 max-w-[85%] text-[#e2e8f0]'}>
                  <div className="text-[13px] leading-relaxed whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}
            {loading && streaming && (
              <div className="flex justify-start">
                <div className="bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-3.5 py-2 max-w-[85%] text-[#e2e8f0]">
                  <div className="text-[13px] leading-relaxed whitespace-pre-wrap">{streaming}</div>
                </div>
              </div>
            )}
            {loading && !streaming && (
              <div className="flex justify-start">
                <div className="bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-3.5 py-3">
                  <div className="flex items-center gap-1.5">
                    {[0, 1, 2].map((i) => <div key={i} className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce" style={{ animationDelay: `${i * 0.15}s`, animationDuration: '0.6s' }} />)}
                    <span className="text-xs text-[#475569] ml-1">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          {/* Input */}
          <div className="flex-shrink-0 border-t border-[#1e293b] p-3">
            <div className="flex gap-2 items-center">
              <input ref={inputRef} type="text" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} disabled={loading} aria-label="Message input"
                placeholder={activeClusterId && clusters ? `Ask about "${clusters.find((c) => c.id === activeClusterId)?.label ?? 'cluster'}"...` : 'Ask anything about your content...'}
                className="flex-1 rounded-xl bg-[#0a0f1a] border border-[#1e293b] text-sm text-[#e2e8f0] placeholder-[#334155] px-3.5 py-2.5 focus:outline-none focus:border-[#3B82F6] transition-colors" />
              <button onClick={() => void handleSubmit(input)} disabled={!input.trim() || loading} aria-label="Send message"
                className="flex-shrink-0 p-2.5 rounded-xl bg-[#3B82F6] text-white hover:bg-[#2563eb] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
