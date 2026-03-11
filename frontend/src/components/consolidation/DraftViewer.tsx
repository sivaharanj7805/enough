'use client';

import { useState, useCallback } from 'react';
import { Copy, Download, FileText, Check } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import type { ConsolidationDraft } from '@/lib/types';

interface DraftViewerProps {
  siteId: string;
  clusterId: string;
}

export function DraftViewer({ siteId, clusterId }: DraftViewerProps) {
  const { session } = useAuth();
  const [draft, setDraft] = useState<ConsolidationDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const generateDraft = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch<ConsolidationDraft>(
        `/sites/${siteId}/intelligence/consolidation/${clusterId}/draft`,
        {
          method: 'POST',
          token: session?.access_token,
        }
      );
      setDraft(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate draft');
    } finally {
      setLoading(false);
    }
  }, [siteId, clusterId, session?.access_token]);

  async function copyToClipboard() {
    if (!draft) return;
    await navigator.clipboard.writeText(draft.content_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadMarkdown() {
    if (!draft) return;
    const blob = new Blob([draft.content_markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${draft.title.toLowerCase().replace(/\s+/g, '-')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!draft) {
    return (
      <Card>
        <div className="text-center space-y-4 py-6">
          <FileText size={40} className="mx-auto text-brand-text-muted" />
          <div>
            <h3 className="text-sm font-semibold text-brand-text">AI Draft Generator</h3>
            <p className="text-xs text-brand-text-muted mt-1">
              Claude will write a consolidated post from the merge candidates
            </p>
          </div>

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <Button onClick={() => void generateDraft()} loading={loading}>
            Generate Consolidated Draft
          </Button>

          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-brand-text-muted">
              <Spinner size="sm" />
              Claude is writing your consolidated post...
            </div>
          )}
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-brand-text">{draft.title}</h3>
          <p className="text-xs text-brand-text-muted">
            {draft.word_count.toLocaleString()} words · Generated {new Date(draft.generated_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => void copyToClipboard()}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied!' : 'Copy'}
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadMarkdown}>
            <Download size={14} />
            Download .md
          </Button>
        </div>
      </div>

      <div className="prose prose-invert prose-sm max-w-none rounded-lg bg-brand-bg p-4 border border-brand-border overflow-y-auto max-h-[600px]">
        <pre className="whitespace-pre-wrap text-sm text-brand-text font-sans leading-relaxed">
          {draft.content_markdown}
        </pre>
      </div>

      <p className="mt-3 text-xs text-brand-text-muted italic">
        ⚠️ Review and edit this draft before publishing. AI-generated content should always be human-verified.
      </p>
    </Card>
  );
}
