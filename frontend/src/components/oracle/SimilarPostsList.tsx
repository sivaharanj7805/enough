'use client';

import { ExternalLink } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { SimilarPost } from '@/lib/types';

interface SimilarPostsListProps {
  posts: SimilarPost[];
}

export function SimilarPostsList({ posts }: SimilarPostsListProps) {
  if (posts.length === 0) return null;

  return (
    <Card>
      <h3 className="text-sm font-semibold text-brand-text mb-4">
        Similar Existing Posts ({posts.length})
      </h3>
      <div className="space-y-2">
        {posts.map((post) => (
          <div
            key={post.post_id}
            className="flex items-center gap-4 rounded-lg border border-brand-border p-3 hover:bg-brand-surface-hover transition-colors"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-brand-text truncate">{post.title}</p>
              <a
                href={post.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-0.5 flex items-center gap-1 text-xs text-brand-accent hover:underline"
              >
                <ExternalLink size={10} />
                <span className="truncate">{post.url}</span>
              </a>
            </div>
            <div className="text-right shrink-0 space-y-1">
              {post.similarity_score !== null && (
                <div className="text-xs text-brand-text-muted">
                  Similarity:{' '}
                  <span className="font-mono text-brand-text">
                    {(post.similarity_score * 100).toFixed(0)}%
                  </span>
                </div>
              )}
              {post.avg_position !== null && (
                <div className="text-xs text-brand-text-muted">
                  Avg pos: <span className="font-mono text-brand-text">#{post.avg_position.toFixed(1)}</span>
                </div>
              )}
              {post.total_clicks !== null && (
                <div className="text-xs text-brand-text-muted">
                  Clicks: <span className="font-mono text-brand-text">{post.total_clicks.toLocaleString()}</span>
                </div>
              )}
              <div className="text-xs text-brand-text-muted capitalize">
                Source: {post.source}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
