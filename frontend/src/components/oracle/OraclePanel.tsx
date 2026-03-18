'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Sparkles, X, Send, RotateCcw, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { VerdictDisplay } from './VerdictDisplay';
import { SimilarPostsList } from './SimilarPostsList';
import type { OracleVerdict } from '@/lib/types';

// Suggested prompts to guide new users
const SUGGESTIONS = [
  'What should I fix first?',
  'Which posts are cannibalizing each other?',
  'What content is missing from my clusters?',
  'Show me my weakest posts',
  'How do I improve my AI citability score?',
];

interface OraclePanelProps {
  open: boolean;
  onClose: () => void;
}

export function OraclePanel({ open, onClose }: OraclePanelProps) {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState<OracleVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [open]);

  const handleSubmit = useCallback(async (content: string) => {
    if (!currentSite || !content.trim()) return;
    setLoading(true);
    setError(null);
    setVerdict(null);

    try {
      const result = await apiFetch<OracleVerdict>(
        `/sites/${currentSite.id}/intelligence/oracle`,
        {
          method: 'POST',
          token: session?.access_token,
          body: JSON.stringify({ draft_text: content, target_keyword: null }),
        }
      );
      setVerdict(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Oracle analysis failed');
    } finally {
      setLoading(false);
    }
  }, [currentSite, session?.access_token]);

  function handleReset() {
    setVerdict(null);
    setError(null);
    setInput('');
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(input);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className={clsx(
          'fixed inset-0 bg-black/40 z-40 transition-opacity duration-200',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={clsx(
          'fixed top-0 right-0 h-full w-full max-w-lg bg-[#111827] border-l border-[#1e293b] z-50',
          'flex flex-col shadow-2xl transition-transform duration-300',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e293b]">
          <div className="flex items-center gap-2.5">
            <Sparkles size={18} className="text-[#22c55e]" />
            <div>
              <p className="text-sm font-semibold text-[#e2e8f0]">Oracle</p>
              <p className="text-xs text-[#64748b]">Ask anything about your content</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {verdict && (
              <button
                onClick={handleReset}
                className="p-1.5 rounded-lg text-[#64748b] hover:text-[#e2e8f0] hover:bg-[#1e293b] transition-colors"
                title="New question"
              >
                <RotateCcw size={15} />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-[#64748b] hover:text-[#e2e8f0] hover:bg-[#1e293b] transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {!verdict && !loading && !error && (
            <>
              <p className="text-xs text-[#64748b]">Suggested questions:</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput(s);
                      void handleSubmit(s);
                    }}
                    className="text-xs px-3 py-1.5 rounded-full bg-[#1e293b] text-[#94a3b8]
                               hover:bg-[#22c55e]/10 hover:text-[#22c55e] transition-colors border border-[#334155]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </>
          )}

          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 size={24} className="text-[#22c55e] animate-spin" />
              <p className="text-sm text-[#64748b]">Analyzing your content ecosystem…</p>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400">
              {error}
            </div>
          )}

          {verdict && !loading && (
            <div className="space-y-4">
              <VerdictDisplay verdict={verdict} />
              {verdict.similar_posts && verdict.similar_posts.length > 0 && (
                <SimilarPostsList posts={verdict.similar_posts} />
              )}
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-[#1e293b] p-4">
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything — 'what should I fix first?' or paste a draft post…"
              rows={2}
              className="flex-1 resize-none rounded-xl bg-[#0a0f1a] border border-[#1e293b] text-sm
                         text-[#e2e8f0] placeholder-[#334155] px-3 py-2.5 focus:outline-none
                         focus:border-[#22c55e] transition-colors"
            />
            <button
              onClick={() => void handleSubmit(input)}
              disabled={!input.trim() || loading}
              className="flex-shrink-0 p-2.5 rounded-xl bg-[#22c55e] text-[#0a0f1a]
                         hover:bg-[#16a34a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={15} />
            </button>
          </div>
          <p className="text-[10px] text-[#334155] mt-2">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </>
  );
}
