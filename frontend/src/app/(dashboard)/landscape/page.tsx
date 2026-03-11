'use client';

import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, X, ExternalLink } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useClusters } from '@/lib/hooks/useApi';
import { EcosystemCanvas } from '@/components/landscape/EcosystemCanvas';
import { Spinner } from '@/components/ui/Spinner';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { ROLE_COLORS, ROLE_LABELS, TREND_ICONS, TREND_COLORS } from '@/lib/constants';
import type { PostHealth, ClusterDetail } from '@/lib/types';

export default function LandscapePage() {
  const { currentSite } = useSite();
  const searchParams = useSearchParams();
  const initialCluster = searchParams.get('cluster');

  const { data: clusters, isLoading, error } = useClusters(currentSite?.id ?? null);
  const [zoomedClusterId, setZoomedClusterId] = useState<string | null>(initialCluster);
  const [selectedPost, setSelectedPost] = useState<PostHealth | null>(null);

  // Fetch all cluster details
  const clusterIds = clusters?.map((c) => c.id) ?? [];
  const { data: clusterDetails, isLoading: detailsLoading } = useSWRFetch<ClusterDetail[]>(
    currentSite && clusterIds.length > 0
      ? `/sites/${currentSite.id}/intelligence/clusters/details`
      : null
  );

  // Fallback: if batch endpoint doesn't exist, use individual cluster data
  const effectiveClusters: ClusterDetail[] = useMemo(() => {
    if (clusterDetails) return clusterDetails;
    if (!clusters) return [];
    // Create mock details from cluster list (posts will be empty until detail loads)
    return clusters.map((c) => ({
      ...c,
      posts: [],
    }));
  }, [clusterDetails, clusters]);

  const handleSelectPost = useCallback((post: PostHealth | null) => {
    setSelectedPost(post);
  }, []);

  const handleZoomToCluster = useCallback((clusterId: string | null) => {
    setZoomedClusterId(clusterId);
  }, []);

  if (isLoading || detailsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Spinner size="lg" />
          <p className="mt-4 text-sm text-brand-text-muted">Loading your ecosystem...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load landscape data</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!clusters || clusters.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <p className="text-4xl mb-4">🗺️</p>
          <h2 className="text-xl font-bold text-brand-text">Your Landscape Awaits</h2>
          <p className="text-sm text-brand-text-muted mt-2">
            Connect a site and run the ecosystem analysis to see your content landscape come to life.
            Each cluster becomes a region. Each post becomes vegetation. The health of your content
            ecosystem, visualized as a living world.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full -m-6">
      {/* Main canvas */}
      <div className="flex-1 relative">
        {/* Zoom controls */}
        {zoomedClusterId && (
          <button
            onClick={() => setZoomedClusterId(null)}
            className="absolute top-4 left-4 z-10 flex items-center gap-2 rounded-lg border border-brand-border bg-brand-surface/95 backdrop-blur-sm px-3 py-2 text-sm text-brand-text hover:bg-brand-surface-hover transition-colors"
          >
            <ArrowLeft size={16} />
            Back to full landscape
          </button>
        )}

        <EcosystemCanvas
          clusters={effectiveClusters}
          onSelectPost={handleSelectPost}
          onZoomToCluster={handleZoomToCluster}
          zoomedClusterId={zoomedClusterId}
        />
      </div>

      {/* Post detail panel */}
      {selectedPost && (
        <div className="w-80 border-l border-brand-border bg-brand-surface p-5 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">Post Details</h3>
            <button
              onClick={() => setSelectedPost(null)}
              className="rounded-lg p-1 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
            >
              <X size={16} />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-sm font-semibold text-brand-text">{selectedPost.title}</p>
              <a
                href={selectedPost.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 flex items-center gap-1 text-xs text-brand-accent hover:underline"
              >
                <ExternalLink size={10} />
                {selectedPost.url}
              </a>
            </div>

            <div className="flex gap-2">
              <Badge color={ROLE_COLORS[selectedPost.role ?? 'dead_weight']}>
                {ROLE_LABELS[selectedPost.role ?? 'dead_weight']}
              </Badge>
              <span
                className="text-sm font-medium"
                style={{ color: TREND_COLORS[selectedPost.trend ?? 'stable'] }}
              >
                {TREND_ICONS[selectedPost.trend ?? 'stable']}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Card className="!p-3">
                <p className="text-xs text-brand-text-muted">Health</p>
                <p className="text-lg font-bold text-brand-text">{Math.round(selectedPost.composite_score ?? 0)}</p>
              </Card>
              <Card className="!p-3">
                <p className="text-xs text-brand-text-muted">Traffic Share</p>
                <p className="text-lg font-bold text-brand-text">{((selectedPost.traffic_contribution ?? 0) * 100).toFixed(1)}%</p>
              </Card>
              <Card className="!p-3">
                <p className="text-xs text-brand-text-muted">Ranking</p>
                <p className="text-lg font-bold text-brand-text">{((selectedPost.ranking_strength ?? 0) * 100).toFixed(0)}</p>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
