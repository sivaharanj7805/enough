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

      {/* Posts */}
      <div className="space-y-3 mb-6">
        {[
          { title: pair.post_a_title, url: pair.post_a_url, label: 'Post A' },
          { title: pair.post_b_title, url: pair.post_b_url, label: 'Post B' },
        ].map((post) => (
          <div key={post.label} className="rounded-lg border border-brand-border p-3">
            <p className="text-xs text-brand-text-muted mb-1">{post.label}</p>
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
          </div>
        ))}
      </div>

      {/* Overlapping queries */}
      <div className="mb-6">
        <h4 className="text-xs font-semibold text-brand-text-muted mb-2">
          Overlapping Queries ({pair.overlapping_queries.length})
        </h4>
        <div className="flex flex-wrap gap-1">
          {pair.overlapping_queries.map((q) => (
            <Badge key={q}>{q}</Badge>
          ))}
        </div>
      </div>

      {/* Recommendation */}
      <div className="rounded-lg bg-brand-accent/5 border border-brand-accent/20 p-3">
        <h4 className="text-xs font-semibold text-brand-accent mb-1">Recommendation</h4>
        <p className="text-sm text-brand-text">{pair.recommendation}</p>
      </div>
    </div>
  );
}
