'use client';

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { useRecommendations } from '@/lib/hooks/useApi';
import { apiFetch } from '@/lib/api';
import { EMPTY_STATES, recType as REC_TYPE_LABELS } from '@/lib/copy';
import type { Recommendation } from '@/lib/types';
import {
  CheckCircle, ChevronLeft, ChevronRight, Send, Loader2,
  ExternalLink, Sparkles, Clock, AlertTriangle,
} from 'lucide-react';

const PRIORITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-400', high: 'bg-orange-500/15 text-orange-400',
  medium: 'bg-yellow-500/15 text-yellow-400', low: 'bg-zinc-500/15 text-zinc-400',
};
const SUGGESTED_PROMPTS = ['How do I do this?', 'Show me an example', 'What should I prioritize?', 'Why does this matter for SEO?'];

interface PatchStep { title: string; instruction: string; detail: string; checklist: string[] }

function buildSteps(rec: Recommendation): PatchStep[] {
  const t = rec.recommendation_type;
  const a = rec.specific_actions ?? [];
  if (t === 'expand') return [
    { title: 'Review the current post', instruction: 'Open the post and read through it. Note word count, structure, and coverage.', detail: a[0] ?? rec.summary, checklist: ['Read the full post', 'Note missing subtopics'] },
    { title: 'Identify what to add', instruction: 'Review AI guidance. Identify gaps compared to competing content.', detail: a[1] ?? 'Look for thin sections, missing subtopics, and outdated information.', checklist: ['List 2-3 sections to add', 'Check competitor coverage'] },
    { title: 'Write the new content', instruction: 'Draft the new sections. Aim for depth over length.', detail: a[2] ?? 'Focus on unique insights and original data when possible.', checklist: ['Draft new sections', 'Add internal links', 'Include relevant examples'] },
    { title: 'Update the post', instruction: 'Publish the updated content. Verify formatting and links.', detail: a[3] ?? 'Update the modified date and check all links work.', checklist: ['Publish changes', 'Verify formatting', 'Check all links'] },
    { title: 'Verify and mark complete', instruction: 'Confirm the changes are live and the post looks correct.', detail: 'Once satisfied, mark this recommendation as complete.', checklist: ['Preview live page', 'Check mobile view'] },
  ];
  if (t === 'merge') return [
    { title: 'Review both posts', instruction: 'Open both competing posts side by side. Identify the stronger one.', detail: a[0] ?? rec.summary, checklist: ['Read both posts fully', 'Compare traffic and rankings'] },
    { title: 'Decide which to keep', instruction: 'Pick the post with better rankings, backlinks, or traffic as the target.', detail: a[1] ?? 'The post with more backlinks and higher authority is usually the better target.', checklist: ['Check backlink profiles', 'Compare search positions'] },
    { title: 'Combine the best content', instruction: 'Merge the best sections from both posts into the target.', detail: a[2] ?? 'Keep the best paragraphs, examples, and data from each post.', checklist: ['Copy unique content to target', 'Remove duplicate sections', 'Update internal links'] },
    { title: 'Set up 301 redirect', instruction: 'Redirect the removed post to the merged target.', detail: a[3] ?? 'A 301 redirect passes link equity to the target URL.', checklist: ['Configure 301 redirect', 'Test the redirect', 'Update sitemap'] },
    { title: 'Verify', instruction: 'Confirm the redirect works and the merged post looks correct.', detail: 'Check that the old URL redirects properly and no broken links remain.', checklist: ['Test redirect in browser', 'Check for broken links'] },
  ];
  if (t === 'seo_fix') return [
    { title: 'Review the issue', instruction: 'Understand what the SEO issue is and why it matters.', detail: a[0] ?? rec.summary, checklist: ['Read the issue description', 'Check current state'] },
    { title: 'Apply the fix', instruction: 'Make the required change to resolve the issue.', detail: a[1] ?? 'Follow the specific guidance provided.', checklist: a.length > 1 ? a.slice(1) : ['Apply the fix', 'Save changes'] },
    { title: 'Verify', instruction: 'Confirm the fix is live and working correctly.', detail: 'Check the page source or use a testing tool to verify.', checklist: ['Preview the page', 'Verify in page source'] },
  ];
  const steps: PatchStep[] = a.map((action, i) => ({ title: `Step ${i + 1}`, instruction: action, detail: '', checklist: [] }));
  if (steps.length === 0) steps.push(
    { title: 'Review', instruction: rec.summary, detail: '', checklist: [] },
    { title: 'Apply and verify', instruction: 'Make the recommended change and verify it is live.', detail: '', checklist: [] },
  );
  return steps;
}

function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${PRIORITY_COLORS[priority] ?? PRIORITY_COLORS.low}`}>
      {priority === 'critical' && <AlertTriangle size={11} />}
      {priority}
    </span>
  );
}

function RecCard({ rec, onClick }: { rec: Recommendation; onClick: () => void }) {
  const typeLabel = REC_TYPE_LABELS[rec.recommendation_type] ?? rec.recommendation_type;
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl border border-brand-border bg-brand-surface p-5 hover:border-brand-border-hover hover:bg-brand-surface-hover transition-colors"
      aria-label={`Start fixing: ${rec.title}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <PriorityBadge priority={rec.priority} />
        <span className="text-[11px] text-brand-text-muted">{typeLabel}</span>
        {rec.estimated_effort_hours != null && (
          <span className="ml-auto flex items-center gap-1 text-[11px] text-brand-text-muted">
            <Clock size={11} /> {rec.estimated_effort_hours}h
          </span>
        )}
      </div>
      <p className="text-sm font-medium text-brand-text mb-1">{rec.title}</p>
      <p className="text-xs text-brand-text-muted line-clamp-2 leading-relaxed">{rec.summary}</p>
    </button>
  );
}

function AIPanel({ siteId, step, rec }: { siteId: string; step: PatchStep; rec: Recommendation }) {
  const { session } = useAuth();
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'ai'; text: string }>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => { setMessages([]); }, [step.title]);

  const ask = useCallback(async (question: string) => {
    if (!question.trim() || loading) return;
    const q = question.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setLoading(true);
    try {
      const context = `Recommendation: ${rec.title}. Current step: ${step.title}. ${step.instruction}`;
      const res = await apiFetch<{ recommendation: string }>(`/sites/${siteId}/intelligence/oracle`, {
        method: 'POST', token: session?.access_token,
        body: JSON.stringify({ draft_text: `${context}\n\nUser question: ${q}` }),
      });
      setMessages((prev) => [...prev, { role: 'ai', text: res.recommendation }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'ai', text: 'Sorry, I could not get an answer right now. Try again.' }]);
    } finally { setLoading(false); }
  }, [loading, siteId, session?.access_token, rec.title, step.title, step.instruction]);

  return (
    <div className="flex flex-col h-full border-l border-brand-border bg-[#0F1117]">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-brand-border">
        <Sparkles size={16} className="text-brand-accent" />
        <span className="text-sm font-semibold text-brand-text">AI Assistant</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <div className="rounded-lg bg-brand-accent/5 border border-brand-accent/10 px-3 py-2">
          <p className="text-xs text-brand-text-muted leading-relaxed">
            Asking about: <span className="text-brand-text font-medium">{step.title}</span>
          </p>
        </div>
        {messages.length === 0 && (
          <div className="space-y-2 pt-2">
            {SUGGESTED_PROMPTS.map((prompt) => (
              <button key={prompt} onClick={() => ask(prompt)} className="block w-full text-left rounded-lg border border-brand-border px-3 py-2 text-xs text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text transition-colors" aria-label={prompt}>
                {prompt}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`rounded-lg px-3 py-2 text-sm leading-relaxed ${m.role === 'user' ? 'bg-brand-accent/10 text-brand-text ml-6' : 'bg-brand-surface text-brand-text-muted mr-2'}`}>
            {m.text}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-brand-text-muted px-3">
            <Loader2 size={14} className="animate-spin" /> Thinking...
          </div>
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="flex items-center gap-2 border-t border-brand-border px-3 py-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question about this step..." className="flex-1 rounded-lg bg-brand-surface border border-brand-border px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted/50 focus:outline-none focus:border-brand-accent" aria-label="Ask the AI assistant" />
        <button type="submit" disabled={loading || !input.trim()} className="rounded-lg bg-brand-accent p-2 text-white disabled:opacity-40 hover:bg-brand-accent/80 transition-colors" aria-label="Send question">
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}

export default function PatcherPage() {
  const params = useSearchParams();
  const { currentSite } = useSite();
  const siteId = currentSite?.id ?? null;
  const { data } = useRecommendations(siteId, { status: 'pending' });
  const [selectedId, setSelectedId] = useState<string | null>(params.get('recId'));
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  const topRecs = useMemo(() => {
    if (!data?.recommendations) return [];
    return [...data.recommendations]
      .sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9))
      .slice(0, 3);
  }, [data]);

  const activeRec = useMemo(() => {
    if (!selectedId || !data?.recommendations) return null;
    return data.recommendations.find((r) => r.id === selectedId) ?? null;
  }, [selectedId, data]);

  const steps = useMemo(() => (activeRec ? buildSteps(activeRec) : []), [activeRec]);
  const step = steps[currentStep] ?? null;
  const allComplete = steps.length > 0 && completedSteps.size === steps.length;

  const markStepComplete = useCallback(() => {
    setCompletedSteps((prev) => { const next = new Set(prev); next.add(currentStep); return next; });
    if (currentStep < steps.length - 1) setCurrentStep((s) => s + 1);
  }, [currentStep, steps.length]);

  const selectRec = useCallback((id: string) => {
    setSelectedId(id); setCurrentStep(0); setCompletedSteps(new Set());
  }, []);

  // Picker view
  if (!selectedId || !activeRec) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12">
        <h1 className="text-xl font-bold text-brand-text mb-1">Patcher</h1>
        <p className="text-sm text-brand-text-muted mb-8">{EMPTY_STATES.patcher.description}</p>
        {topRecs.length === 0 ? (
          <div className="rounded-xl border border-brand-border bg-brand-surface p-8 text-center">
            <p className="text-sm font-medium text-brand-text mb-1">{EMPTY_STATES.patcher.emptyTitle}</p>
            <p className="text-xs text-brand-text-muted">{EMPTY_STATES.patcher.emptyDescription}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {topRecs.map((rec) => <RecCard key={rec.id} rec={rec} onClick={() => selectRec(rec.id)} />)}
          </div>
        )}
      </div>
    );
  }

  // Workflow view
  const typeLabel = REC_TYPE_LABELS[activeRec.recommendation_type] ?? activeRec.recommendation_type;
  return (
    <div className="flex h-full">
      <div className="flex flex-1 min-w-0" style={{ flex: '0 0 65%' }}>
        {/* Vertical step indicator */}
        <div className="flex flex-col items-center gap-1 px-3 pt-6 pb-4 border-r border-brand-border">
          {steps.map((_, i) => (
            <button key={i} onClick={() => setCurrentStep(i)} className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold transition-colors ${completedSteps.has(i) ? 'bg-green-500/20 text-green-400' : i === currentStep ? 'bg-brand-accent/20 text-brand-accent ring-2 ring-brand-accent/40' : 'bg-brand-surface-hover text-brand-text-muted'}`} aria-label={`Go to step ${i + 1}`}>
              {completedSteps.has(i) ? <CheckCircle size={14} /> : i + 1}
            </button>
          ))}
        </div>
        {/* Main content */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          <div>
            <button onClick={() => { setSelectedId(null); setCurrentStep(0); setCompletedSteps(new Set()); }} className="flex items-center gap-1 text-xs text-brand-text-muted hover:text-brand-text mb-3 transition-colors" aria-label="Back to picker">
              <ChevronLeft size={14} /> Back
            </button>
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <PriorityBadge priority={activeRec.priority} />
              <span className="text-xs text-brand-text-muted">{typeLabel}</span>
            </div>
            <h1 className="text-lg font-bold text-brand-text">{activeRec.title}</h1>
            {activeRec.post_id && (
              <Link href={`/posts/${activeRec.post_id}`} className="inline-flex items-center gap-1 text-xs text-brand-accent hover:underline mt-1">
                View post <ExternalLink size={11} />
              </Link>
            )}
          </div>
          {/* Progress bar */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-brand-text">Step {currentStep + 1} of {steps.length}</span>
              <span className="text-[11px] text-brand-text-muted">{completedSteps.size}/{steps.length} complete</span>
            </div>
            <div className="h-1.5 rounded-full bg-brand-surface-hover overflow-hidden">
              <div className="h-full rounded-full bg-brand-accent transition-all duration-300" style={{ width: `${(completedSteps.size / steps.length) * 100}%` }} />
            </div>
          </div>
          {/* All-done banner */}
          {allComplete && (
            <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-5 text-center">
              <CheckCircle size={28} className="mx-auto text-green-400 mb-2" />
              <p className="text-sm font-semibold text-brand-text mb-1">{EMPTY_STATES.patcher.allDone}</p>
              <p className="text-xs text-brand-text-muted">{EMPTY_STATES.patcher.allDoneSub}</p>
            </div>
          )}
          {/* Current step card */}
          {step && !allComplete && (
            <div className="rounded-xl border border-brand-border bg-brand-surface p-6 space-y-4">
              <div>
                <span className="text-[11px] font-semibold text-brand-accent uppercase tracking-wider">Step {currentStep + 1}</span>
                <h2 className="text-base font-semibold text-brand-text mt-1">{step.title}</h2>
              </div>
              <p className="text-sm text-brand-text-muted leading-relaxed">{step.instruction}</p>
              {step.detail && (
                <div className="rounded-lg bg-brand-accent/5 border border-brand-accent/10 px-4 py-3">
                  <p className="text-sm text-brand-text leading-relaxed">{step.detail}</p>
                </div>
              )}
              {step.checklist.length > 0 && (
                <ul className="space-y-2">
                  {step.checklist.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-brand-text-muted">
                      <span className="mt-0.5 h-4 w-4 rounded border border-brand-border flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              )}
              <button onClick={markStepComplete} className="flex items-center gap-2 rounded-lg bg-brand-accent px-4 py-2 text-sm font-medium text-white hover:bg-brand-accent/80 transition-colors" aria-label="Mark step complete">
                <CheckCircle size={14} /> Mark step complete
              </button>
            </div>
          )}
          {/* Navigation */}
          <div className="flex items-center justify-between pt-2">
            <button onClick={() => setCurrentStep((s) => Math.max(0, s - 1))} disabled={currentStep === 0} className="flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-brand-text-muted hover:text-brand-text disabled:opacity-30 transition-colors" aria-label="Previous step">
              <ChevronLeft size={14} /> Previous
            </button>
            <button onClick={() => setCurrentStep((s) => Math.min(steps.length - 1, s + 1))} disabled={currentStep === steps.length - 1} className="flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-brand-text-muted hover:text-brand-text disabled:opacity-30 transition-colors" aria-label="Next step">
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
      {/* Right: AI panel (35%) */}
      {step && siteId && (
        <div className="hidden lg:flex" style={{ flex: '0 0 35%' }}>
          <AIPanel siteId={siteId} step={step} rec={activeRec} />
        </div>
      )}
    </div>
  );
}
