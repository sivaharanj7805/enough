'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useConsolidationDetail } from '@/lib/hooks/useApi';
import { RedirectMap } from '@/components/consolidation/RedirectMap';
import { DraftViewer } from '@/components/consolidation/DraftViewer';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ROLE_COLORS } from '@/lib/constants';

export default function ConsolidationDetailPage() {
  const params = useParams();
  const clusterId = typeof params.clusterId === 'string' ? params.clusterId : null;
  const { currentSite } = useSite();
  const { data: detail, isLoading, error } = useConsolidationDetail(
    currentSite?.id ?? null,
    clusterId
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load consolidation detail</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="space-y-6">
      <Link
        href="/consolidation"
        className="inline-flex items-center gap-2 text-sm text-brand-text-muted hover:text-brand-text transition-colors"
      >
        <ArrowLeft size={16} />
        Back to Plans
      </Link>

      <div>
        <h2 className="text-xl font-bold text-brand-text">{detail.cluster_label}</h2>
        <p className="text-sm text-brand-text-muted mt-1">
          Est. +{detail.estimated_traffic_recovery.toLocaleString()} traffic recovery ·{' '}
          ~{detail.estimated_effort_hours}h effort
        </p>
      </div>

      {/* Section 1 — Plan overview */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Pillar post */}
        <Card glow glowColor="#22c55e">
          <h3 className="text-xs font-semibold text-brand-accent uppercase tracking-wide mb-3">
            Pillar Post (Keep & Enhance)
          </h3>
          <p className="text-sm font-semibold text-brand-text">{detail.pillar_post.title}</p>
          <a
            href={detail.pillar_post.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 flex items-center gap-1 text-xs text-brand-accent hover:underline"
          >
            <ExternalLink size={12} />
            {detail.pillar_post.url}
          </a>
          <div className="mt-3 flex gap-3 text-xs text-brand-text-muted">
            <span>Health: <span className="text-brand-text font-mono">{detail.pillar_post.health_score}</span></span>
            <span>Traffic: <span className="text-brand-text font-mono">{detail.pillar_post.traffic_90d.toLocaleString()}</span></span>
          </div>
        </Card>

        {/* Metrics */}
        <Card>
          <h3 className="text-xs font-semibold text-brand-text-muted uppercase tracking-wide mb-3">
            Estimated Metrics
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-2xl font-bold text-brand-accent">+{detail.estimated_traffic_recovery.toLocaleString()}</p>
              <p className="text-xs text-brand-text-muted">Traffic Recovery</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-brand-text">{detail.estimated_effort_hours}h</p>
              <p className="text-xs text-brand-text-muted">Effort</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-brand-text">{detail.merge_count}</p>
              <p className="text-xs text-brand-text-muted">Posts to Merge</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-brand-text">{detail.redirect_count}</p>
              <p className="text-xs text-brand-text-muted">Redirects</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Merge candidates */}
      {detail.merge_candidates.length > 0 && (
        <Card>
          <h3 className="text-sm font-semibold text-brand-text mb-4">
            Merge Candidates ({detail.merge_candidates.length})
          </h3>
          <div className="space-y-2">
            {detail.merge_candidates.map((mc) => (
              <div
                key={mc.post_id}
                className="flex items-center gap-3 rounded-lg border border-brand-border p-3"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-brand-text truncate">{mc.title}</p>
                  <p className="text-xs text-brand-text-muted truncate">{mc.url}</p>
                </div>
                <Badge color={ROLE_COLORS.competitor}>
                  {(mc.similarity_score * 100).toFixed(0)}% similar
                </Badge>
                <span className="text-xs text-brand-text-muted shrink-0">
                  {mc.word_count.toLocaleString()} words
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Dead weight */}
      {detail.dead_weight.length > 0 && (
        <Card>
          <h3 className="text-sm font-semibold text-brand-text mb-4">
            Dead Weight ({detail.dead_weight.length})
          </h3>
          <div className="space-y-2">
            {detail.dead_weight.map((dw) => (
              <div
                key={dw.post_id}
                className="flex items-center gap-3 rounded-lg border border-brand-border/50 p-3 opacity-60"
              >
                <Badge color={ROLE_COLORS.dead_weight}>Dead</Badge>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-brand-text truncate">{dw.title}</p>
                  <p className="text-xs text-brand-text-muted truncate">{dw.url}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Section 2 — Redirect Map */}
      <RedirectMap
        entries={detail.redirect_map}
        isWordPress={currentSite?.cms_type === 'wordpress'}
      />

      {/* Section 3 — AI Draft */}
      {currentSite && clusterId && (
        <DraftViewer siteId={currentSite.id} clusterId={clusterId} />
      )}
    </div>
  );
}
