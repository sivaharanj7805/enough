/**
 * VegetationRenderer — SVG vegetation shapes + creature overlays for the landscape.
 * Trees represent posts (Pillar Oak, Supporter Birch, Competitor Vine, Dead Weight Stump).
 * Creatures represent active problems (Bloomlings, Rustmites, Foglings, Tanglevines).
 */

import type { PostRole } from '@/lib/constants';

export interface VegetationConfig {
  role: PostRole;
  traffic: number;
  maxTraffic: number;
  isNew: boolean;
}

/**
 * Scale factor: 0.3 → 1.0 based on traffic relative to max.
 */
function trafficScale(traffic: number, maxTraffic: number): number {
  if (maxTraffic <= 0) return 0.5;
  return 0.3 + (traffic / maxTraffic) * 0.7;
}

/**
 * Draw a tree (pillar post). Tall trunk + full canopy.
 * Returns SVG path string for appending into a <g> element.
 */
export function drawTree(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const trunkH = 30 * scale;
  const trunkW = 6 * scale;
  const canopyR = 18 * scale;

  // Shadow
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 2)
    .attr('rx', canopyR * 0.8)
    .attr('ry', 4 * scale)
    .attr('fill', 'rgba(0,0,0,0.3)');

  // Trunk
  g.append('rect')
    .attr('x', -trunkW / 2)
    .attr('y', -trunkH)
    .attr('width', trunkW)
    .attr('height', trunkH)
    .attr('rx', 2)
    .attr('fill', '#5c3d2e');

  // Trunk detail
  g.append('line')
    .attr('x1', -1)
    .attr('y1', -trunkH * 0.3)
    .attr('x2', -1)
    .attr('y2', -trunkH * 0.7)
    .attr('stroke', '#4a2f22')
    .attr('stroke-width', 1);

  // Canopy layers (3 overlapping circles for organic feel)
  const canopyColors = ['#166534', '#15803d', '#22c55e'];
  const offsets = [
    { dx: -canopyR * 0.3, dy: -trunkH - canopyR * 0.5, r: canopyR * 0.85 },
    { dx: canopyR * 0.3, dy: -trunkH - canopyR * 0.4, r: canopyR * 0.8 },
    { dx: 0, dy: -trunkH - canopyR * 0.9, r: canopyR },
  ];

  offsets.forEach((o, i) => {
    g.append('circle')
      .attr('cx', o.dx)
      .attr('cy', o.dy)
      .attr('r', o.r)
      .attr('fill', canopyColors[i])
      .attr('opacity', 0.9);
  });

  // Highlight dot
  g.append('circle')
    .attr('cx', canopyR * 0.2)
    .attr('cy', -trunkH - canopyR * 1.1)
    .attr('r', canopyR * 0.15)
    .attr('fill', '#4ade80')
    .attr('opacity', 0.6);
}

/**
 * Draw a bush (supporter post). Rounded green shape.
 */
export function drawBush(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const w = 20 * scale;
  const h = 14 * scale;

  // Shadow
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 2)
    .attr('rx', w * 0.7)
    .attr('ry', 3 * scale)
    .attr('fill', 'rgba(0,0,0,0.25)');

  // Bush body (overlapping ellipses)
  const bushParts = [
    { dx: -w * 0.3, dy: -h * 0.4, rx: w * 0.55, ry: h * 0.5, color: '#1d4ed8' },
    { dx: w * 0.3, dy: -h * 0.3, rx: w * 0.5, ry: h * 0.45, color: '#2563eb' },
    { dx: 0, dy: -h * 0.6, rx: w * 0.6, ry: h * 0.55, color: '#3b82f6' },
  ];

  bushParts.forEach((p) => {
    g.append('ellipse')
      .attr('cx', p.dx)
      .attr('cy', p.dy)
      .attr('rx', p.rx)
      .attr('ry', p.ry)
      .attr('fill', p.color)
      .attr('opacity', 0.85);
  });

  // Subtle stem
  g.append('line')
    .attr('x1', 0)
    .attr('y1', 0)
    .attr('x2', 0)
    .attr('y2', -h * 0.3)
    .attr('stroke', '#5c3d2e')
    .attr('stroke-width', 2 * scale);
}

/**
 * Draw a vine tangle (competitor/cannibalizing post).
 */
export function drawVine(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const size = 16 * scale;

  // Shadow
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 2)
    .attr('rx', size * 0.6)
    .attr('ry', 3 * scale)
    .attr('fill', 'rgba(0,0,0,0.2)');

  // Tangled vine paths
  const vineColor = '#c2410c';
  const vineColor2 = '#f97316';

  // Main tangle
  g.append('path')
    .attr('d', `M${-size * 0.5},0 Q${-size * 0.3},${-size * 0.8} ${size * 0.1},${-size * 0.6} T${size * 0.5},${-size * 0.3}`)
    .attr('fill', 'none')
    .attr('stroke', vineColor)
    .attr('stroke-width', 3 * scale)
    .attr('stroke-linecap', 'round');

  g.append('path')
    .attr('d', `M${-size * 0.3},${-size * 0.1} Q${size * 0.2},${-size * 1} ${size * 0.4},${-size * 0.5} T${size * 0.2},0`)
    .attr('fill', 'none')
    .attr('stroke', vineColor2)
    .attr('stroke-width', 2.5 * scale)
    .attr('stroke-linecap', 'round');

  g.append('path')
    .attr('d', `M${-size * 0.1},0 Q${-size * 0.5},${-size * 0.5} ${0},${-size * 0.9} T${size * 0.3},${-size * 0.2}`)
    .attr('fill', 'none')
    .attr('stroke', '#ea580c')
    .attr('stroke-width', 2 * scale)
    .attr('stroke-linecap', 'round');

  // Leaf blobs
  [
    { x: -size * 0.4, y: -size * 0.5 },
    { x: size * 0.3, y: -size * 0.4 },
    { x: 0, y: -size * 0.8 },
  ].forEach((p) => {
    g.append('circle')
      .attr('cx', p.x)
      .attr('cy', p.y)
      .attr('r', 3 * scale)
      .attr('fill', '#854d0e')
      .attr('opacity', 0.7);
  });
}

/**
 * Draw a stump (dead weight post). Grey, lifeless.
 */
export function drawStump(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const w = 10 * scale;
  const h = 10 * scale;

  // Cracked ground
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', 2)
    .attr('rx', w * 1.2)
    .attr('ry', 4 * scale)
    .attr('fill', '#374151')
    .attr('opacity', 0.4);

  // Cracks
  g.append('path')
    .attr('d', `M${-w},2 L${-w * 0.3},0 L${w * 0.5},3`)
    .attr('fill', 'none')
    .attr('stroke', '#1f2937')
    .attr('stroke-width', 0.5);

  // Stump body
  g.append('rect')
    .attr('x', -w / 2)
    .attr('y', -h)
    .attr('width', w)
    .attr('height', h)
    .attr('rx', 2)
    .attr('fill', '#4b5563');

  // Stump top (ellipse)
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', -h)
    .attr('rx', w / 2 + 1)
    .attr('ry', 3 * scale)
    .attr('fill', '#6b7280');

  // Ring detail
  g.append('ellipse')
    .attr('cx', 0)
    .attr('cy', -h)
    .attr('rx', w * 0.25)
    .attr('ry', 1.5 * scale)
    .attr('fill', 'none')
    .attr('stroke', '#9ca3af')
    .attr('stroke-width', 0.5);
}

/**
 * Draw a seedling (new post ≤30 days).
 */
export function drawSeedling(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const stemH = 14 * scale;

  // Ground dot
  g.append('circle')
    .attr('cx', 0)
    .attr('cy', 1)
    .attr('r', 3 * scale)
    .attr('fill', '#166534')
    .attr('opacity', 0.5);

  // Stem
  g.append('line')
    .attr('x1', 0)
    .attr('y1', 0)
    .attr('x2', 0)
    .attr('y2', -stemH)
    .attr('stroke', '#4ade80')
    .attr('stroke-width', 1.5 * scale)
    .attr('stroke-linecap', 'round');

  // Left leaf
  g.append('path')
    .attr('d', `M0,${-stemH * 0.6} Q${-8 * scale},${-stemH * 0.9} ${-3 * scale},${-stemH * 0.5}`)
    .attr('fill', '#86efac')
    .attr('opacity', 0.9);

  // Right leaf
  g.append('path')
    .attr('d', `M0,${-stemH * 0.7} Q${8 * scale},${-stemH * 1} ${3 * scale},${-stemH * 0.6}`)
    .attr('fill', '#4ade80')
    .attr('opacity', 0.9);

  // Tip
  g.append('circle')
    .attr('cx', 0)
    .attr('cy', -stemH - 2 * scale)
    .attr('r', 2 * scale)
    .attr('fill', '#bbf7d0');
}

/**
 * Draw the appropriate vegetation for a post.
 */
export function drawVegetation(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  config: VegetationConfig
): void {
  const scale = trafficScale(config.traffic, config.maxTraffic);

  if (config.isNew) {
    drawSeedling(g, scale);
    return;
  }

  switch (config.role) {
    case 'pillar':
      drawTree(g, scale);
      break;
    case 'supporter':
      drawBush(g, scale);
      break;
    case 'competitor':
      drawVine(g, scale);
      break;
    case 'dead_weight':
      drawStump(g, scale);
      break;
  }
}

// Re-export the type for D3 compatibility
export type D3Selection = d3.Selection<SVGGElement, unknown, null, undefined>;

// ── Creature type ─────────────────────────────────────────────────────────────
export type CreatureType = 'bloomling' | 'rustmite' | 'fogling' | null;

/**
 * Bloomling — round bouncy creature with flower petals. Near healthy high-traffic posts.
 * Clicking opens "growth opportunity" rec.
 */
export function drawBloomling(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const r = 5 * scale;
  const petalR = 2.5 * scale;
  const petalDist = r + petalR * 0.8;

  // Shadow
  g.append('ellipse')
    .attr('cx', 0).attr('cy', r + 1).attr('rx', r * 0.8).attr('ry', 2 * scale)
    .attr('fill', 'rgba(0,0,0,0.2)');

  // Petals (5 petals around body)
  for (let i = 0; i < 5; i++) {
    const angle = (i / 5) * Math.PI * 2 - Math.PI / 2;
    g.append('circle')
      .attr('cx', Math.cos(angle) * petalDist)
      .attr('cy', -r + Math.sin(angle) * petalDist)
      .attr('r', petalR)
      .attr('fill', '#4ade80')
      .attr('opacity', 0.85);
  }

  // Body
  g.append('circle')
    .attr('cx', 0).attr('cy', -r).attr('r', r)
    .attr('fill', '#86efac')
    .attr('stroke', '#22c55e')
    .attr('stroke-width', 1);

  // Eyes
  g.append('circle').attr('cx', -r * 0.3).attr('cy', -r - 0.5).attr('r', 1).attr('fill', '#14532d');
  g.append('circle').attr('cx', r * 0.3).attr('cy', -r - 0.5).attr('r', 1).attr('fill', '#14532d');

  // Smile
  g.append('path')
    .attr('d', `M${-r * 0.4},${-r + 1.5} Q0,${-r + 3} ${r * 0.4},${-r + 1.5}`)
    .attr('fill', 'none').attr('stroke', '#14532d').attr('stroke-width', 0.8);

  // Glow
  g.append('circle')
    .attr('cx', 0).attr('cy', -r).attr('r', r * 2)
    .attr('fill', 'none')
    .attr('stroke', '#22c55e')
    .attr('stroke-width', 0.5)
    .attr('opacity', 0.3);
}

/**
 * Rustmite — small orange crab shape. Appears on posts with decay problems.
 * Clicking opens the decay/content-update rec.
 */
export function drawRustmite(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const s = scale * 0.9;

  // Shadow
  g.append('ellipse')
    .attr('cx', 0).attr('cy', 2).attr('rx', 8 * s).attr('ry', 2 * s)
    .attr('fill', 'rgba(0,0,0,0.2)');

  // Legs (3 on each side)
  const legColor = '#c2410c';
  [[-1, -0.5], [-1, 0], [-1, 0.5], [1, -0.5], [1, 0], [1, 0.5]].forEach(([side, offset]) => {
    const lx = side * 6 * s;
    const ly = -3 * s + offset * 4 * s;
    g.append('line')
      .attr('x1', side * 4 * s).attr('y1', ly)
      .attr('x2', lx).attr('y2', ly + 3 * s * side * -0.3)
      .attr('stroke', legColor).attr('stroke-width', 1 * s)
      .attr('stroke-linecap', 'round');
  });

  // Body
  g.append('ellipse')
    .attr('cx', 0).attr('cy', -3 * s).attr('rx', 5 * s).attr('ry', 3 * s)
    .attr('fill', '#ea580c').attr('stroke', '#9a3412').attr('stroke-width', 0.5);

  // Shell segments
  g.append('line')
    .attr('x1', -4 * s).attr('y1', -3 * s).attr('x2', 4 * s).attr('y2', -3 * s)
    .attr('stroke', '#7c2d12').attr('stroke-width', 0.5).attr('opacity', 0.5);

  // Eyes
  g.append('circle').attr('cx', -2 * s).attr('cy', -5 * s).attr('r', 1.2 * s).attr('fill', '#fef08a');
  g.append('circle').attr('cx', 2 * s).attr('cy', -5 * s).attr('r', 1.2 * s).attr('fill', '#fef08a');

  // Claws
  [[-5.5, -6.5], [5.5, -6.5]].forEach(([cx, cy]) => {
    g.append('circle')
      .attr('cx', cx * s).attr('cy', cy * s).attr('r', 2 * s)
      .attr('fill', '#c2410c').attr('stroke', '#7c2d12').attr('stroke-width', 0.5);
  });
}

/**
 * Fogling — ghost wisp shape. Near orphan/low-health posts with SEO issues.
 * Clicking opens the SEO optimization rec.
 */
export function drawFogling(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  scale: number
): void {
  const w = 8 * scale;
  const h = 13 * scale;

  // Glow aura
  g.append('ellipse')
    .attr('cx', 0).attr('cy', -h * 0.5).attr('rx', w * 1.5).attr('ry', h * 0.8)
    .attr('fill', 'rgba(148, 163, 184, 0.08)');

  // Ghost body — tapered at bottom, rounded top
  g.append('path')
    .attr('d', `
      M${-w},${-h * 0.1}
      Q${-w},${-h * 1.1} 0,${-h * 1.15}
      Q${w},${-h * 1.1} ${w},${-h * 0.1}
      Q${w * 0.6},${h * 0.15} ${w * 0.2},${-h * 0.05}
      Q0,${h * 0.2} ${-w * 0.2},${-h * 0.05}
      Q${-w * 0.6},${h * 0.15} ${-w},${-h * 0.1}
      Z
    `)
    .attr('fill', 'rgba(148,163,184,0.35)')
    .attr('stroke', 'rgba(203,213,225,0.4)')
    .attr('stroke-width', 0.8);

  // Eyes (hollow)
  g.append('circle').attr('cx', -w * 0.3).attr('cy', -h * 0.75).attr('r', 1.5 * scale).attr('fill', 'rgba(30,41,59,0.7)');
  g.append('circle').attr('cx', w * 0.3).attr('cy', -h * 0.75).attr('r', 1.5 * scale).attr('fill', 'rgba(30,41,59,0.7)');

  // Floating motion will be handled via CSS animation class
}
