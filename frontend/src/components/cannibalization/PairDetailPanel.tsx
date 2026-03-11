'use client';

import { X, ExternalLink } from 'lucide-react';
import { SeverityBadge } from './SeverityBadge';
import { Badge } from '@/components/ui/Badge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import type { CannibalizationPair } from '@/lib/types';
import { SEVERITY_COLORS } from '@/lib/constants';

interface PairDetailPanelProps {
  pair: CannibalizationPair;
  onClose: () => void;
}

export function PairDetailPanel({ pair, onClose }: PairDetailPanelProps) {
  const queries = pair.overlapping_queries ?? [];

  return (
    <div className="w-96 border-l border-brand-border bg-brand-surface p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-semibold text-brand-text">Pair Details</h3>
        <button
          onClick={onClose}
          className="rounded-lg p-1 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
        >
          <X size={18} />
        </button>
      </div>

      {/* Severity + Score */}
      <div className="flex items-center gap-3 mb-4">
        <SeverityBadge severity={pair.severity} />
        <div className="flex-1">
          <ProgressBar
            value={pair.overlap_score * 100}
            color={SEVERITY_COLORS[pair.severity]}
          />
        </div>
        <span className="text-sm font-mono text-brand-text">
          {(pair.overlap_score * 100).toFixed(0)}%
        </span>
      </div>

      {/* Posts — using nested post_a / post_b objects from backend */}
      <div className="space-y-3 mb-6">
        {[
          { post: pair.post_a, label: 'Post A' },
          { post: pair.post_b, label: 'Post B' },
        ].map(({ post, label }) => (
          <div key={label} className="rounded-lg border border-brand-border p-3">
            <p className="text-xs text-brand-text-muted mb-1">{label}</p>
            <p className="text-sm font-medium text-brand-text truncate">{post.title}</p>
            <a
              href={post.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 flex items-center gap-1 text-xs text-brand-accent hover:underline"
            >
              <ExternalLink size={12} />
              {post.url}
            </a>
            <div className="mt-2 flex gap-2 text-xs text-brand-text-muted">
              <span>Score: {Math.round(post.composite_score ?? 0)}</span>
              <span>·</span>
              <span>Role: {post.role ?? 'unknown'}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Overlapping queries */}
      {queries.length > 0 && (
        <div className="mb-6">
          <h4 className="text-xs font-semibold text-brand-text-muted mb-2">
            Overlapping Queries ({queries.length})
          </h4>
          <div className="flex flex-wrap gap-1">
            {queries.map((q) => (
              <Badge key={q}>{q}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Recommendation based on severity */}
      <div className="rounded-lg bg-brand-accent/5 border border-brand-accent/20 p-3">
        <h4 className="text-xs font-semibold text-brand-accent mb-1">Recommendation</h4>
        <p className="text-sm text-brand-text">
          {pair.severity === 'critical' || pair.severity === 'high'
            ? `Merge "${pair.post_b.title}" into "${pair.post_a.title}" and set up a 301 redirect.`
            : `Differentiate these posts by adjusting the target keyword of the weaker one.`}
        </p>
      </div>
    </div>
  );
}
