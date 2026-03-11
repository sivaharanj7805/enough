/**
 * RegionRenderer — Draws a single cluster region on the landscape canvas.
 * Includes ground plane, vegetation, labels, and health badge.
 */

import * as d3 from 'd3';
import { ECOSYSTEM_COLORS, type EcosystemState } from '@/lib/constants';
import { drawVegetation, type VegetationConfig } from './VegetationRenderer';
import type { PostHealth } from '@/lib/types';

export interface RegionData {
  id: string;
  label: string;
  ecosystemState: EcosystemState;
  healthScore: number;
  posts: PostHealth[];
  x: number;
  y: number;
  radius: number;
}

function scoreColor(score: number): string {
  if (score >= 70) return '#22c55e';
  if (score >= 40) return '#eab308';
  return '#ef4444';
}

/**
 * Checks if a post was published within the last 30 days.
 */
function isNewPost(_post: PostHealth): boolean {
  // PostHealth doesn't have published_at directly; we approximate via trend
  // In a real impl we'd check the date. For now, we don't flag as new.
  return false;
}

/**
 * Draws ground texture based on ecosystem state.
 */
function drawGround(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  state: EcosystemState,
  radius: number
): void {
  const colors = ECOSYSTEM_COLORS[state];

  // Main ground shape — organic blob using rounded rect
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 0)
    .attr('rx', radius)
    .attr('ry', radius * 0.7)
    .attr('fill', colors.bg)
    .attr('stroke', colors.border)
    .attr('stroke-width', 1.5)
    .attr('opacity', 0.85);

  // Texture overlays based on state
  if (state === 'swamp') {
    // Murky patches
    for (let i = 0; i < 5; i++) {
      const angle = (i / 5) * Math.PI * 2;
      const dist = radius * 0.4 * Math.random();
      g.append('ellipse')
        .attr('cx', Math.cos(angle) * dist)
        .attr('cy', Math.sin(angle) * dist * 0.7)
        .attr('rx', 10 + Math.random() * 15)
        .attr('ry', 6 + Math.random() * 10)
        .attr('fill', '#1a2e0f')
        .attr('opacity', 0.4 + Math.random() * 0.2);
    }
  } else if (state === 'desert') {
    // Crack lines
    for (let i = 0; i < 4; i++) {
      const startAngle = Math.random() * Math.PI * 2;
      const len = radius * 0.3 + Math.random() * radius * 0.3;
      const x1 = Math.cos(startAngle) * radius * 0.1;
      const y1 = Math.sin(startAngle) * radius * 0.1 * 0.7;
      const x2 = Math.cos(startAngle) * len;
      const y2 = Math.sin(startAngle) * len * 0.7;
      g.append('line')
        .attr('x1', x1)
        .attr('y1', y1)
        .attr('x2', x2)
        .attr('y2', y2)
        .attr('stroke', '#a6896a')
        .attr('stroke-width', 0.5)
        .attr('opacity', 0.6);
    }
  } else if (state === 'forest') {
    // Lush ground patches
    for (let i = 0; i < 4; i++) {
      const angle = (i / 4) * Math.PI * 2 + Math.random() * 0.5;
      const dist = radius * 0.3 * Math.random();
      g.append('ellipse')
        .attr('cx', Math.cos(angle) * dist)
        .attr('cy', Math.sin(angle) * dist * 0.7)
        .attr('rx', 8 + Math.random() * 12)
        .attr('ry', 5 + Math.random() * 8)
        .attr('fill', '#14532d')
        .attr('opacity', 0.3);
    }
  } else if (state === 'seedbed') {
    // Soft soil dots
    for (let i = 0; i < 8; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * radius * 0.6;
      g.append('circle')
        .attr('cx', Math.cos(angle) * dist)
        .attr('cy', Math.sin(angle) * dist * 0.7)
        .attr('r', 2 + Math.random() * 3)
        .attr('fill', '#166534')
        .attr('opacity', 0.25);
    }
  }
}

/**
 * Render a complete cluster region with ground, vegetation, and labels.
 */
export function renderRegion(
  parent: d3.Selection<SVGGElement, unknown, null, undefined>,
  region: RegionData,
  onHoverPost: (post: PostHealth | null, x: number, y: number) => void,
  onClickPost: (post: PostHealth) => void,
  onClickRegion: (regionId: string) => void,
): d3.Selection<SVGGElement, unknown, null, undefined> {
  const g = parent.append('g')
    .attr('transform', `translate(${region.x},${region.y})`)
    .attr('class', 'region');

  // Ground plane
  drawGround(g, region.ecosystemState, region.radius);

  // Click region to zoom
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 0)
    .attr('rx', region.radius)
    .attr('ry', region.radius * 0.7)
    .attr('fill', 'transparent')
    .attr('cursor', 'pointer')
    .on('click', () => onClickRegion(region.id));

  // Place vegetation for each post
  const maxTraffic = Math.max(...region.posts.map((p) => p.traffic_90d), 1);
  const postCount = region.posts.length;

  region.posts.forEach((post, i) => {
    // Arrange posts in a spiral-ish pattern within the region
    const angle = (i / Math.max(postCount, 1)) * Math.PI * 2;
    const dist = region.radius * 0.3 + (i % 3) * region.radius * 0.15;
    const px = Math.cos(angle) * dist;
    const py = Math.sin(angle) * dist * 0.7;

    const vegGroup = g.append('g')
      .attr('transform', `translate(${px},${py})`)
      .attr('cursor', 'pointer')
      .on('mouseenter', function (event: MouseEvent) {
        const rect = (event.target as SVGElement).closest('svg')?.getBoundingClientRect();
        if (rect) {
          onHoverPost(post, event.clientX - rect.left, event.clientY - rect.top);
        }
      })
      .on('mouseleave', () => onHoverPost(null, 0, 0))
      .on('click', (event: MouseEvent) => {
        event.stopPropagation();
        onClickPost(post);
      });

    const config: VegetationConfig = {
      role: post.role,
      traffic: post.traffic_90d,
      maxTraffic,
      isNew: isNewPost(post),
    };

    drawVegetation(vegGroup, config);
  });

  // Label above region
  g.append('text')
    .attr('x', 0)
    .attr('y', -region.radius * 0.7 - 12)
    .attr('text-anchor', 'middle')
    .attr('fill', '#e2e8f0')
    .attr('font-size', '12px')
    .attr('font-weight', '600')
    .text(region.label);

  // Health score badge
  const badgeX = region.radius * 0.7;
  const badgeY = -region.radius * 0.5;
  const badgeG = g.append('g')
    .attr('transform', `translate(${badgeX},${badgeY})`);

  badgeG.append('rect')
    .attr('x', -16)
    .attr('y', -10)
    .attr('width', 32)
    .attr('height', 20)
    .attr('rx', 10)
    .attr('fill', '#111827')
    .attr('stroke', scoreColor(region.healthScore))
    .attr('stroke-width', 1.5);

  badgeG.append('text')
    .attr('x', 0)
    .attr('y', 4)
    .attr('text-anchor', 'middle')
    .attr('fill', scoreColor(region.healthScore))
    .attr('font-size', '10px')
    .attr('font-weight', '700')
    .text(region.healthScore.toString());

  return g;
}
