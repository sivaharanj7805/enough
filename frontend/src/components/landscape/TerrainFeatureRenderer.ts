/**
 * TerrainFeatureRenderer — Boulders (broken links), erosion (thin content), mushrooms (near-duplicates).
 */

import type { TerrainFeature, ClusterPositions } from '@/lib/types/phase6';

function seededRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function drawBoulders(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number
): void {
  for (let i = 0; i < count; i++) {
    const angle = seededRandom(i * 37 + 7) * Math.PI * 2;
    const dist = radius * (0.3 + seededRandom(i * 53) * 0.5);
    const bx = x + Math.cos(angle) * dist;
    const by = y + Math.sin(angle) * dist * 0.7;
    const size = 4 + seededRandom(i * 71) * 4;

    ctx.save();
    ctx.globalAlpha = 0.5;

    // Boulder shape — irregular ellipse
    ctx.fillStyle = '#57534e';
    ctx.beginPath();
    ctx.ellipse(bx, by, size, size * 0.65, seededRandom(i * 11) * 0.5, 0, Math.PI * 2);
    ctx.fill();

    // Highlight
    ctx.fillStyle = '#78716c';
    ctx.beginPath();
    ctx.ellipse(bx - size * 0.2, by - size * 0.2, size * 0.4, size * 0.3, 0, 0, Math.PI * 2);
    ctx.globalAlpha = 0.3;
    ctx.fill();

    // Crack line
    ctx.strokeStyle = '#292524';
    ctx.lineWidth = 0.6;
    ctx.globalAlpha = 0.4;
    ctx.beginPath();
    ctx.moveTo(bx - size * 0.3, by);
    ctx.lineTo(bx + size * 0.2, by + size * 0.1);
    ctx.stroke();

    ctx.restore();
  }
}

function drawErosion(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number
): void {
  // Crumbling edge effect — jagged segments around the perimeter
  const segments = Math.min(count * 3, 12);

  ctx.save();
  ctx.globalAlpha = 0.4;
  ctx.strokeStyle = '#78716c';
  ctx.lineWidth = 1;

  for (let i = 0; i < segments; i++) {
    const angle = (i / segments) * Math.PI * 2;
    const nextAngle = ((i + 1) / segments) * Math.PI * 2;

    const r1 = radius * (0.95 + seededRandom(i * 23) * 0.15);
    const r2 = radius * (0.95 + seededRandom(i * 41 + 5) * 0.15);

    const x1 = x + Math.cos(angle) * r1;
    const y1 = y + Math.sin(angle) * r1 * 0.7;
    const x2 = x + Math.cos(nextAngle) * r2;
    const y2 = y + Math.sin(nextAngle) * r2 * 0.7;

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Debris particles
    if (seededRandom(i * 67) > 0.5) {
      const px = (x1 + x2) / 2 + (seededRandom(i * 89) - 0.5) * 6;
      const py = (y1 + y2) / 2 + seededRandom(i * 97) * 4;
      ctx.fillStyle = '#a8a29e';
      ctx.beginPath();
      ctx.arc(px, py, 1, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}

function drawMushrooms(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    const angle = seededRandom(i * 29 + 13) * Math.PI * 2;
    const dist = radius * (0.2 + seededRandom(i * 43) * 0.6);
    const mx = x + Math.cos(angle) * dist;
    const my = y + Math.sin(angle) * dist * 0.7;

    // Wobble animation
    const wobble = Math.sin(time * 0.002 + i * 1.7) * 0.5;
    const size = 2 + seededRandom(i * 59) * 2;

    ctx.save();
    ctx.globalAlpha = 0.6;

    // Stem
    ctx.strokeStyle = '#d6d3d1';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(mx, my);
    ctx.lineTo(mx + wobble, my - size * 2);
    ctx.stroke();

    // Cap — red with spots
    ctx.fillStyle = '#dc2626';
    ctx.beginPath();
    ctx.ellipse(mx + wobble, my - size * 2, size * 1.5, size * 0.8, 0, Math.PI, 0);
    ctx.fill();

    // White spots on cap
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.arc(mx + wobble - 1, my - size * 2.2, 0.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(mx + wobble + 1.2, my - size * 2, 0.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }
}

export function draw(
  ctx: CanvasRenderingContext2D,
  terrainFeatures: Record<string, TerrainFeature[]>,
  clusters: ClusterPositions,
  time: number
): void {
  for (const [clusterId, features] of Object.entries(terrainFeatures)) {
    const cluster = clusters[clusterId];
    if (!cluster) continue;

    for (const feature of features) {
      switch (feature.type) {
        case 'boulders':
          drawBoulders(ctx, cluster.x, cluster.y, cluster.radius, feature.count);
          break;
        case 'erosion':
          drawErosion(ctx, cluster.x, cluster.y, cluster.radius, feature.count);
          break;
        case 'mushrooms':
          drawMushrooms(ctx, cluster.x, cluster.y, cluster.radius, feature.count, time);
          break;
      }
    }
  }
}
