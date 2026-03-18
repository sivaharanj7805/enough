'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { renderRegion, type RegionData } from './RegionRenderer';
import { LandscapeTooltip } from './LandscapeTooltip';
import { LegendPanel } from './LegendPanel';
import type { ClusterDetail } from '@/lib/types';
import type { PostHealth } from '@/lib/types';
import type { EcosystemState, PostRole, Trend } from '@/lib/constants';
import type { CreatureType } from './VegetationRenderer';

export interface CannPair {
  post_a_id: string;
  post_b_id: string;
  cosine_similarity: number;
}

interface EcosystemCanvasProps {
  clusters: ClusterDetail[];
  onSelectPost: (post: PostHealth | null) => void;
  onZoomToCluster: (clusterId: string | null) => void;
  zoomedClusterId: string | null;
  cannPairs?: CannPair[];
  onClickCreature?: (post: PostHealth, creature: CreatureType) => void;
}

interface TooltipData {
  title: string;
  url: string;
  traffic: number;
  healthScore: number;
  role: PostRole;
  trend: Trend;
}

interface TooltipState {
  data: TooltipData;
  x: number;
  y: number;
}

export function EcosystemCanvas({
  clusters,
  onSelectPost,
  onZoomToCluster,
  zoomedClusterId,
  cannPairs = [],
  onClickCreature,
}: EcosystemCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const handleHoverPost = useCallback((post: PostHealth | null, x: number, y: number) => {
    if (!post) {
      setTooltip(null);
      return;
    }
    setTooltip({
      data: {
        title: post.title,
        url: post.url,
        traffic: Math.round((post.traffic_contribution ?? 0) * 10000),
        healthScore: Math.round(post.composite_score ?? 0),
        role: post.role ?? 'dead_weight',
        trend: post.trend ?? 'stable',
      },
      x,
      y,
    });
  }, []);

  const handleClickPost = useCallback((post: PostHealth) => {
    onSelectPost(post);
  }, [onSelectPost]);

  const handleClickCreature = useCallback((post: PostHealth, creature: CreatureType) => {
    onSelectPost(post);
    if (onClickCreature) onClickCreature(post, creature);
  }, [onSelectPost, onClickCreature]);

  const handleClickRegion = useCallback((regionId: string) => {
    onZoomToCluster(regionId);
  }, [onZoomToCluster]);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || clusters.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    svg.attr('width', width).attr('height', height);

    // Background
    svg.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', '#0a0f1a');

    // Subtle grid
    const gridSpacing = 40;
    const gridG = svg.append('g').attr('class', 'grid');
    for (let x = 0; x < width; x += gridSpacing) {
      gridG.append('line')
        .attr('x1', x).attr('y1', 0)
        .attr('x2', x).attr('y2', height)
        .attr('stroke', '#111827')
        .attr('stroke-width', 0.5);
    }
    for (let y = 0; y < height; y += gridSpacing) {
      gridG.append('line')
        .attr('x1', 0).attr('y1', y)
        .attr('x2', width).attr('y2', y)
        .attr('stroke', '#111827')
        .attr('stroke-width', 0.5);
    }

    // Main group for zoom/pan
    const g = svg.append('g').attr('class', 'landscape');

    // Zoom behavior
    const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 8])
      .on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        g.attr('transform', event.transform.toString());
      });
    svg.call(zoomBehavior);

    // Build region data with force layout for positioning
    const minRadius = 60;
    const maxRadius = 180;
    const maxPosts = Math.max(...clusters.map((c) => c.posts.length), 1);

    const regions: RegionData[] = clusters.map((cluster) => {
      const postRatio = cluster.posts.length / maxPosts;
      const radius = minRadius + postRatio * (maxRadius - minRadius);

      return {
        id: cluster.id,
        label: cluster.label,
        ecosystemState: cluster.ecosystem_state as EcosystemState,
        healthScore: cluster.health_score ?? 0,
        posts: cluster.posts,
        x: width / 2 + (Math.random() - 0.5) * width * 0.5,
        y: height / 2 + (Math.random() - 0.5) * height * 0.5,
        radius,
      };
    });

    // Force simulation to prevent overlap
    interface ForceNode extends d3.SimulationNodeDatum {
      id: string;
      radius: number;
    }

    const forceNodes: ForceNode[] = regions.map((r) => ({
      id: r.id,
      x: r.x,
      y: r.y,
      radius: r.radius,
    }));

    const simulation = d3.forceSimulation(forceNodes)
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('collision', d3.forceCollide<ForceNode>().radius((d) => d.radius + 30))
      .stop();

    // Run simulation synchronously
    for (let i = 0; i < 200; i++) {
      simulation.tick();
    }

    // Update region positions from simulation
    forceNodes.forEach((node, i) => {
      regions[i].x = node.x ?? regions[i].x;
      regions[i].y = node.y ?? regions[i].y;
    });

    // Render regions
    const postPositions = new Map<string, { x: number; y: number }>();

    regions.forEach((region) => {
      renderRegion(g, region, handleHoverPost, handleClickPost, handleClickRegion, handleClickCreature);

      // Record absolute positions for Tanglevine connections
      const postCount = region.posts.length;
      region.posts.forEach((post, i) => {
        const angle = (i / Math.max(postCount, 1)) * Math.PI * 2;
        const dist = region.radius * 0.3 + (i % 3) * region.radius * 0.15;
        const px = region.x + Math.cos(angle) * dist;
        const py = region.y + Math.sin(angle) * dist * 0.7;
        postPositions.set(post.id ?? post.post_id, { x: px, y: py });
      });
    });

    // Draw Tanglevines — animated vine paths between cannibalizing post pairs
    if (cannPairs.length > 0) {
      const vineGroup = g.append('g').attr('class', 'tanglevines');

      cannPairs.slice(0, 30).forEach((pair) => {
        const posA = postPositions.get(pair.post_a_id);
        const posB = postPositions.get(pair.post_b_id);
        if (!posA || !posB) return;

        const mx = (posA.x + posB.x) / 2 + (Math.random() - 0.5) * 40;
        const my = (posA.y + posB.y) / 2 - 25;
        const intensity = Math.min(1, (pair.cosine_similarity - 0.75) / 0.2);
        const color = intensity > 0.7 ? '#ef4444' : intensity > 0.4 ? '#f97316' : '#eab308';
        const opacity = 0.25 + intensity * 0.4;

        vineGroup.append('path')
          .attr('d', `M${posA.x},${posA.y} Q${mx},${my} ${posB.x},${posB.y}`)
          .attr('fill', 'none')
          .attr('stroke', color)
          .attr('stroke-width', 1 + intensity * 1.5)
          .attr('stroke-dasharray', '4 3')
          .attr('opacity', opacity)
          .attr('class', 'tanglevine')
          .attr('stroke-linecap', 'round');

        // Small vine knot at midpoint
        vineGroup.append('circle')
          .attr('cx', mx).attr('cy', my)
          .attr('r', 2 + intensity * 2)
          .attr('fill', color)
          .attr('opacity', opacity * 0.8);
      });
    }

    // If zoomed to a cluster, zoom into it
    if (zoomedClusterId) {
      const target = regions.find((r) => r.id === zoomedClusterId);
      if (target) {
        const scale = Math.min(width, height) / (target.radius * 3);
        const tx = width / 2 - target.x * scale;
        const ty = height / 2 - target.y * scale;
        svg.transition().duration(750).call(
          zoomBehavior.transform,
          d3.zoomIdentity.translate(tx, ty).scale(scale)
        );
      }
    }

    return () => {
      // Remove zoom handler from SVG element itself (not just child nodes)
      svg.on('.zoom', null);
      svg.selectAll('*').remove();
    };
  }, [clusters, zoomedClusterId, handleHoverPost, handleClickPost, handleClickRegion, handleClickCreature, cannPairs]);

  return (
    <div ref={containerRef} className="relative h-full w-full landscape-canvas">
      <svg
        ref={svgRef}
        className="h-full w-full"
        role="img"
        aria-label="Content ecosystem landscape — interactive visualization of your content clusters"
      />

      {tooltip && (
        <LandscapeTooltip
          data={tooltip.data}
          x={tooltip.x}
          y={tooltip.y}
        />
      )}

      <LegendPanel />
    </div>
  );
}
