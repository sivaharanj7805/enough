'use client';

import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, X, ExternalLink, BarChart2, Leaf, Sparkles } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useClusters, useCannibalizationPairs } from '@/lib/hooks/useApi';
import { EcosystemCanvas, type CannPair } from '@/components/landscape/EcosystemCanvas';
import { Spinner } from '@/components/ui/Spinner';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useEcosystemVisuals } from '@/lib/hooks/useApi';
import { EcosystemNarrative } from '@/components/landscape/EcosystemNarrative';
import { EcosystemOverlay } from '@/components/landscape/EcosystemOverlay';
import { OnboardingTour } from '@/components/landscape/OnboardingTour';
import { CreatureLegend } from '@/components/landscape/CreatureLegend';
import { ROLE_COLORS, ROLE_LABELS, TREND_ICONS, TREND_COLORS } from '@/lib/constants';
import type { PostHealth, ClusterDetail, CannibalizationPair, Recommendation } from '@/lib/types';
import type { EcosystemState } from '@/lib/constants';
import type { CreatureType } from '@/components/landscape/VegetationRenderer';

const CREATURE_LABELS: Record<NonNullable<CreatureType>, { emoji: string; label: string; color: string; recType: string[] }> = {
  bloomling: {
    emoji: '🌸',
    label: 'Bloomling — Growth Opportunity',
    color: 'text-green-400',
    recType: ['growth', 'interlink'],
  },
  rustmite: {
    emoji: '🦀',
    label: 'Rustmite — Content Decay',
    color: 'text-orange-400',
    recType: ['expand', 'optimize'],
  },
  fogling: {
    emoji: '👻',
    label: 'Fogling — Orphaned Post',
    color: 'text-slate-400',
    recType: ['interlink', 'optimize'],
  },
};

export default function LandscapePage() {
  const { currentSite } = useSite();
  const searchParams = useSearchParams();
  const initialCluster = searchParams.get('cluster');

  const { data: clusters, isLoading, error } = useClusters(currentSite?.id ?? null);
  const [zoomedClusterId, setZoomedClusterId] = useState<string | null>(initialCluster);
  const [selectedPost, setSelectedPost] = useState<PostHealth | null>(null);
  const [activeCreature, setActiveCreature] = useState<CreatureType>(null);
  const [viewMode, setViewMode] = useState<'ecosystem' | 'data'>('ecosystem');

  const { data: ecosystemVisuals } = useEcosystemVisuals(currentSite?.id ?? null);
  const { data: cannPairsRaw } = useCannibalizationPairs(currentSite?.id ?? null);

  const clusterIds = clusters?.map((c) => c.id) ?? [];
  const { data: clusterDetails, isLoading: detailsLoading } = useSWRFetch<ClusterDetail[]>(
    currentSite && clusterIds.length > 0
      ? `/sites/${currentSite.id}/intelligence/clusters/details`
      : null
  );

  // Fetch recs for selected post when a creature is clicked
  const { data: postRecs } = useSWRFetch<{ recommendations: Recommendation[] }>(
    currentSite && selectedPost && activeCreature
      ? `/sites/${currentSite.id}/intelligence/recommendations?post_id=${selectedPost.post_id}&limit=3`
      : null
  );

  const effectiveClusters: ClusterDetail[] = useMemo(() => {
    if (clusterDetails) return clusterDetails;
    if (!clusters) return [];
    return clusters.map((c) => ({ ...c, posts: [] }));
  }, [clusterDetails, clusters]);

  // Map cann pairs to lightweight format for canvas
  const cannPairs: CannPair[] = useMemo(() => {
    if (!cannPairsRaw) return [];
    return cannPairsRaw.map((p: CannibalizationPair) => ({
      post_a_id: p.post_a.post_id,
      post_b_id: p.post_b.post_id,
      cosine_similarity: p.overlap_score,
    }));
  }, [cannPairsRaw]);

  const handleSelectPost = useCallback((post: PostHealth | null) => {
    setSelectedPost(post);
    if (!post) setActiveCreature(null);
  }, []);

  const handleZoomToCluster = useCallback((clusterId: string | null) => {
    setZoomedClusterId(clusterId);
  }, []);

  const handleClickCreature = useCallback((post: PostHealth, creature: CreatureType) => {
    setSelectedPost(post);
    setActiveCreature(creature);
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
            Connect a site and run the ecosystem analysis to see your content landscape.
          </p>
        </div>
      </div>
    );
  }

  const creatureMeta = activeCreature ? CREATURE_LABELS[activeCreature] : null;
  const filteredRecs = postRecs?.recommendations?.filter((r) =>
    creatureMeta ? creatureMeta.recType.includes(r.recommendation_type) : true
  ) ?? [];

  return (
    <div className="flex h-full -m-6">
      {/* Main canvas */}
      <div className="flex-1 relative">
        {/* View toggle */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex rounded-lg border border-brand-border bg-brand-surface/95 backdrop-blur-sm p-0.5">
          <button
            onClick={() => setViewMode('ecosystem')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              viewMode === 'ecosystem'
                ? 'bg-brand-accent text-black'
                : 'text-brand-text-muted hover:text-brand-text'
            }`}
          >
            <Leaf size={12} /> Ecosystem
          </button>
          <button
            onClick={() => setViewMode('data')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              viewMode === 'data'
                ? 'bg-brand-accent text-black'
                : 'text-brand-text-muted hover:text-brand-text'
            }`}
          >
            <BarChart2 size={12} /> Data View
          </button>
        </div>

        {/* Back button when zoomed */}
        {zoomedClusterId && viewMode === 'ecosystem' && (
          <button
            onClick={() => setZoomedClusterId(null)}
            className="absolute top-4 left-4 z-10 flex items-center gap-2 rounded-lg border border-brand-border bg-brand-surface/95 backdrop-blur-sm px-3 py-2 text-sm text-brand-text hover:bg-brand-surface-hover transition-colors"
          >
            <ArrowLeft size={16} />
            Back to full landscape
          </button>
        )}

        {/* Ecosystem narrative when zoomed */}
        {zoomedClusterId && viewMode === 'ecosystem' && currentSite && (() => {
          const cluster = clusters?.find((c) => c.id === zoomedClusterId);
          return cluster ? (
            <div className="absolute bottom-16 left-4 right-4 z-10 max-w-lg">
              <EcosystemNarrative
                siteId={currentSite.id}
                clusterId={zoomedClusterId}
                ecosystemState={cluster.ecosystem_state as EcosystemState | null}
                clusterLabel={cluster.label}
              />
            </div>
          ) : null;
        })()}

        {/* Ecosystem canvas */}
        {viewMode === 'ecosystem' && (
          <>
            <EcosystemCanvas
              clusters={effectiveClusters}
              onSelectPost={handleSelectPost}
              onZoomToCluster={handleZoomToCluster}
              zoomedClusterId={zoomedClusterId}
              cannPairs={cannPairs}
              onClickCreature={handleClickCreature}
            />

            {ecosystemVisuals && effectiveClusters.length > 0 && (
              <EcosystemOverlay
                visuals={ecosystemVisuals}
                clusters={effectiveClusters}
              />
            )}

            {/* Creature legend */}
            <CreatureLegend />

            {/* Onboarding tour (first visit only) */}
            <OnboardingTour />
          </>
        )}

        {/* Data view — cluster grid */}
        {viewMode === 'data' && (
          <div className="h-full overflow-y-auto p-6 pt-14">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {clusters.map((c) => (
                <Card
                  key={c.id}
                  className="cursor-pointer hover:border-brand-border-hover transition-colors"
                  onClick={() => { setViewMode('ecosystem'); setZoomedClusterId(c.id); }}
                >
                  <div className="flex items-start justify-between mb-2">
                    <p className="text-sm font-semibold text-brand-text line-clamp-2">{c.label}</p>
                    <span
                      className="text-xs font-bold ml-2 shrink-0"
                      style={{ color: (c.health_score ?? 0) >= 60 ? '#22c55e' : (c.health_score ?? 0) >= 40 ? '#eab308' : '#ef4444' }}
                    >
                      {Math.round(c.health_score ?? 0)}
                    </span>
                  </div>
                  <p className="text-xs text-brand-text-muted">{c.post_count} posts</p>
                  <p className="text-xs text-brand-text-muted capitalize mt-0.5">{c.ecosystem_state?.replace('_', ' ')}</p>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Post detail panel */}
      {selectedPost && (
        <div className="w-80 border-l border-brand-border bg-brand-surface p-5 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-brand-text">Post Details</h3>
            <button
              onClick={() => { setSelectedPost(null); setActiveCreature(null); }}
              className="rounded-lg p-1 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
            >
              <X size={16} />
            </button>
          </div>

          {/* Creature context banner */}
          {activeCreature && creatureMeta && (
            <div className="mb-4 rounded-lg bg-brand-surface-hover border border-brand-border px-3 py-2">
              <p className={`text-xs font-semibold ${creatureMeta.color}`}>
                {creatureMeta.emoji} {creatureMeta.label}
              </p>
              <p className="text-xs text-brand-text-muted mt-0.5">
                {activeCreature === 'bloomling' && 'This post has traffic momentum — push it to rank higher.'}
                {activeCreature === 'rustmite' && 'Declining rankings detected. Content needs updating.'}
                {activeCreature === 'fogling' && 'No posts link here. Google can\'t reliably find it.'}
              </p>
            </div>
          )}

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
                <p className="text-xs text-brand-text-muted">Link Score</p>
                <p className="text-lg font-bold text-brand-text">{((selectedPost.internal_link_score ?? 0) * 100).toFixed(0)}</p>
              </Card>
              <Card className="!p-3">
                <p className="text-xs text-brand-text-muted">Ranking</p>
                <p className="text-lg font-bold text-brand-text">{((selectedPost.ranking_strength ?? 0) * 100).toFixed(0)}</p>
              </Card>
            </div>

            {/* Relevant recs from creature click */}
            {activeCreature && filteredRecs.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-brand-text mb-2 flex items-center gap-1">
                  <Sparkles size={11} className="text-purple-400" />
                  Recommended Actions
                </p>
                <div className="space-y-2">
                  {filteredRecs.slice(0, 3).map((rec) => (
                    <div
                      key={rec.id}
                      className="rounded-lg bg-brand-surface-hover border border-brand-border px-3 py-2"
                    >
                      <p className="text-xs font-medium text-brand-text">{rec.title}</p>
                      {rec.summary && (
                        <p className="text-xs text-brand-text-muted mt-0.5 line-clamp-2">{rec.summary}</p>
                      )}
                      <span className="inline-block mt-1 text-xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                        {rec.recommendation_type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
