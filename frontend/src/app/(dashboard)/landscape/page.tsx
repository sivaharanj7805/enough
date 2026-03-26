'use client';

import { useState, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, X, ExternalLink, BarChart2, Leaf, Sparkles, MapPin, Volume2, VolumeX } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useClusters, useCannibalizationPairs } from '@/lib/hooks/useApi';
import { EcosystemCanvas, type CannPair } from '@/components/landscape/EcosystemCanvas';
import { Spinner } from '@/components/ui/Spinner';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useEcosystemVisuals } from '@/lib/hooks/useApi';
import { EcosystemNarrative } from '@/components/landscape/EcosystemNarrative';
import { OnboardingTour } from '@/components/landscape/OnboardingTour';
import { CreatureLegend } from '@/components/landscape/CreatureLegend';
import { ContentPlannerOverlay } from '@/components/landscape/ContentPlannerOverlay';
import { Minimap } from '@/components/landscape/Minimap';
import { useEcosystemSounds } from '@/lib/hooks/useEcosystemSounds';
import { useEasterEggs } from '@/lib/hooks/useEasterEggs';
import { ROLE_COLORS, ROLE_LABELS, TREND_ICONS, TREND_COLORS } from '@/lib/constants';
import type { PostHealth, ClusterDetail, CannibalizationPair, Recommendation } from '@/lib/types';
import type { EcosystemState } from '@/lib/constants';
import type { ClusterPositions } from '@/lib/types/phase6';
type CreatureType = string | null;

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
  const [plannerVisible, setPlannerVisible] = useState(false);
  const [clusterPositions, setClusterPositions] = useState<ClusterPositions>({});
  const [viewportTransform, setViewportTransform] = useState<{ x: number; y: number; k: number } | null>(null);
  const navigateRef = useRef<((x: number, y: number) => void) | null>(null);
  const sounds = useEcosystemSounds();
  useEasterEggs();

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

  const handlePositionsComputed = useCallback((positions: ClusterPositions) => {
    setClusterPositions(positions);
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
        {/* View toggle + toolbar */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2">
          <div className="flex rounded-lg border border-brand-border bg-brand-surface/95 backdrop-blur-sm p-0.5">
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

          {/* Content Planner toggle */}
          <button
            onClick={() => setPlannerVisible(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors backdrop-blur-sm ${
              plannerVisible
                ? 'bg-green-500/20 border-green-500/30 text-green-400'
                : 'bg-brand-surface/95 border-brand-border text-brand-text-muted hover:text-brand-text'
            }`}
            title="Toggle content planner overlay"
          >
            <MapPin size={12} /> Planner
          </button>

          {/* Sound toggle */}
          <button
            onClick={sounds.toggle}
            className={`flex items-center gap-1 px-2 py-1.5 rounded-lg border text-xs font-medium transition-colors backdrop-blur-sm ${
              sounds.enabled
                ? 'bg-blue-500/20 border-blue-500/30 text-blue-400'
                : 'bg-brand-surface/95 border-brand-border text-brand-text-muted hover:text-brand-text'
            }`}
            title={sounds.enabled ? 'Disable sounds' : 'Enable sounds'}
          >
            {sounds.enabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
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
              visuals={ecosystemVisuals}
              onClickCreature={handleClickCreature}
              onPositionsComputed={handlePositionsComputed}
              onViewportChange={setViewportTransform}
              navigateRef={navigateRef}
            />

            {/* Content planner overlay */}
            <ContentPlannerOverlay
              clusters={effectiveClusters}
              visible={plannerVisible}
            />

            {/* Minimap with live viewport tracking */}
            <Minimap
              clusters={effectiveClusters}
              canvasWidth={800}
              canvasHeight={600}
              viewportTransform={viewportTransform}
              onNavigate={(cx, cy) => navigateRef.current?.(cx, cy)}
            />

            {/* Creature legend */}
            <CreatureLegend />

            {/* Onboarding tour (first visit only) */}
            <OnboardingTour />
          </>
        )}

        {/* Data view — enriched cluster grid (UX-6) */}
        {viewMode === 'data' && (
          <div className="h-full overflow-y-auto p-6 pt-14">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {effectiveClusters.map((c) => {
                const score = Math.round(c.health_score ?? 0);
                const scoreColor = score >= 60 ? '#22c55e' : score >= 40 ? '#eab308' : '#ef4444';
                const circumference = 2 * Math.PI * 20;
                const filled = (score / 100) * circumference;

                // Role distribution from posts
                const roleCounts: Record<string, number> = { pillar: 0, supporter: 0, competitor: 0, dead_weight: 0 };
                (c.posts ?? []).forEach((p) => {
                  const r = p.role ?? 'dead_weight';
                  roleCounts[r] = (roleCounts[r] || 0) + 1;
                });
                const totalPosts = (c.posts ?? []).length || c.post_count || 1;

                // Ecosystem state styling
                const stateConfig: Record<string, { icon: string; color: string; bg: string }> = {
                  forest: { icon: '🌲', color: 'text-green-400', bg: 'bg-green-500/15' },
                  meadow: { icon: '🌻', color: 'text-lime-400', bg: 'bg-lime-500/15' },
                  seedbed: { icon: '🌱', color: 'text-emerald-400', bg: 'bg-emerald-500/15' },
                  swamp: { icon: '🪴', color: 'text-amber-400', bg: 'bg-amber-500/15' },
                  desert: { icon: '🏜️', color: 'text-orange-400', bg: 'bg-orange-500/15' },
                };
                const state = c.ecosystem_state ?? 'desert';
                const sc = stateConfig[state] ?? stateConfig.desert;

                return (
                  <Card
                    key={c.id}
                    className="cursor-pointer hover:border-brand-border-hover transition-colors"
                    onClick={() => { setViewMode('ecosystem'); setZoomedClusterId(c.id); }}
                  >
                    {/* Top row: label + health ring */}
                    <div className="flex items-start gap-3 mb-3">
                      {/* Health score ring */}
                      <div className="shrink-0 relative w-12 h-12">
                        <svg width="48" height="48" viewBox="0 0 48 48">
                          <circle cx="24" cy="24" r="20" fill="none" stroke="#1e293b" strokeWidth="3" />
                          <circle
                            cx="24" cy="24" r="20" fill="none"
                            stroke={scoreColor} strokeWidth="3"
                            strokeDasharray={`${filled} ${circumference}`}
                            strokeLinecap="round"
                            transform="rotate(-90 24 24)"
                          />
                        </svg>
                        <span className="absolute inset-0 flex items-center justify-center text-xs font-bold" style={{ color: scoreColor }}>
                          {score}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-brand-text line-clamp-2">{c.label}</p>
                        <p className="text-xs text-brand-text-muted mt-0.5">{c.post_count} posts</p>
                      </div>
                    </div>

                    {/* Ecosystem state badge */}
                    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded ${sc.bg} ${sc.color}`}>
                      {sc.icon} {state.charAt(0).toUpperCase() + state.slice(1)}
                    </span>

                    {/* Role distribution mini bar */}
                    <div className="mt-3">
                      <div className="flex items-center gap-1 h-2 rounded-full overflow-hidden bg-brand-surface-hover">
                        {(['pillar', 'supporter', 'competitor', 'dead_weight'] as const).map((role) => {
                          const pct = (roleCounts[role] / totalPosts) * 100;
                          if (pct === 0) return null;
                          return (
                            <div
                              key={role}
                              style={{ width: `${pct}%`, backgroundColor: ROLE_COLORS[role] }}
                              className="h-full"
                              title={`${ROLE_LABELS[role]}: ${roleCounts[role]}`}
                            />
                          );
                        })}
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5">
                        {(['pillar', 'supporter', 'competitor', 'dead_weight'] as const).map((role) => {
                          if (!roleCounts[role]) return null;
                          return (
                            <span key={role} className="flex items-center gap-1 text-[10px] text-brand-text-muted">
                              <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: ROLE_COLORS[role] }} />
                              {roleCounts[role]} {ROLE_LABELS[role]}
                            </span>
                          );
                        })}
                      </div>
                    </div>

                    {/* Clustering confidence badge */}
                    <div className="flex items-center gap-2 mt-2">
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                          c.silhouette_score != null && c.silhouette_score >= 0.5
                            ? 'bg-green-500/15 text-green-400'
                            : c.silhouette_score != null && c.silhouette_score >= 0.2
                              ? 'bg-yellow-500/15 text-yellow-400'
                              : 'bg-gray-500/15 text-gray-400'
                        }`}
                      >
                        {c.silhouette_score != null && c.silhouette_score >= 0.5
                          ? 'High confidence'
                          : c.silhouette_score != null && c.silhouette_score >= 0.2
                            ? 'Mixed'
                            : 'Low confidence'}
                      </span>
                    </div>
                  </Card>
                );
              })}
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
