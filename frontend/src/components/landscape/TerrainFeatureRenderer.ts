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
    const size = 12 + seededRandom(i * 71) * 6; // 12-18px

    ctx.save();
    ctx.globalAlpha = 0.85;

    // Boulder body with 3D gradient (highlight top-left, shadow bottom-right)
    const bGrad = ctx.createLinearGradient(bx - size, by - size, bx + size, by + size);
    bGrad.addColorStop(0, '#78716c');
    bGrad.addColorStop(0.5, '#57534e');
    bGrad.addColorStop(1, '#292524');
    ctx.fillStyle = bGrad;
    ctx.beginPath();
    ctx.ellipse(bx, by, size, size * 0.65, seededRandom(i * 11) * 0.5, 0, Math.PI * 2);
    ctx.fill();

    // Highlight spot (top-left)
    ctx.fillStyle = '#a8a29e';
    ctx.beginPath();
    ctx.ellipse(bx - size * 0.25, by - size * 0.2, size * 0.3, size * 0.2, -0.3, 0, Math.PI * 2);
    ctx.globalAlpha = 0.4;
    ctx.fill();

    // Crack lines
    ctx.strokeStyle = '#1c1917';
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.moveTo(bx - size * 0.4, by - size * 0.1);
    ctx.lineTo(bx + size * 0.1, by + size * 0.05);
    ctx.lineTo(bx + size * 0.3, by + size * 0.15);
    ctx.stroke();

    ctx.restore();
  }
}

function drawErosion(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number
): void {
  const segments = Math.min(count * 3, 12);

  ctx.save();

  for (let i = 0; i < segments; i++) {
    const angle = (i / segments) * Math.PI * 2;
    const nextAngle = ((i + 1) / segments) * Math.PI * 2;

    const r1 = radius * (0.92 + seededRandom(i * 23) * 0.18);
    const r2 = radius * (0.92 + seededRandom(i * 41 + 5) * 0.18);

    const x1 = x + Math.cos(angle) * r1;
    const y1 = y + Math.sin(angle) * r1 * 0.7;
    const x2 = x + Math.cos(nextAngle) * r2;
    const y2 = y + Math.sin(nextAngle) * r2 * 0.7;

    // Brownish erosion stain along the line
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = '#92400e';
    ctx.lineWidth = 3;
    ctx.globalAlpha = 0.35;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Darker center line
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = '#78716c';
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.6;
    ctx.stroke();

    // Debris particles (bigger)
    if (seededRandom(i * 67) > 0.4) {
      const px = (x1 + x2) / 2 + (seededRandom(i * 89) - 0.5) * 8;
      const py = (y1 + y2) / 2 + seededRandom(i * 97) * 5;
      ctx.fillStyle = '#a8a29e';
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.arc(px, py, 1.5 + seededRandom(i * 103), 0, Math.PI * 2);
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
    const wobble = Math.sin(time * 0.002 + i * 1.7) * 1.5;
    const size = 5 + seededRandom(i * 59) * 4; // 10-14px effective

    ctx.save();
    ctx.globalAlpha = 0.85;

    // Stem
    ctx.strokeStyle = '#d6d3d1';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(mx, my);
    ctx.lineTo(mx + wobble, my - size * 2);
    ctx.stroke();

    // Cap — red dome
    ctx.fillStyle = '#dc2626';
    ctx.beginPath();
    ctx.ellipse(mx + wobble, my - size * 2, size * 1.8, size, 0, Math.PI, 0);
    ctx.fill();

    // Cap highlight
    ctx.fillStyle = '#ef4444';
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.ellipse(mx + wobble - size * 0.3, my - size * 2.3, size * 0.7, size * 0.35, -0.2, 0, Math.PI * 2);
    ctx.fill();

    // White spots on cap (3 spots)
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = 0.7;
    const spots = [
      { dx: -size * 0.5, dy: -size * 2.4, r: size * 0.2 },
      { dx: size * 0.4, dy: -size * 2.2, r: size * 0.15 },
      { dx: 0, dy: -size * 2.6, r: size * 0.18 },
    ];
    spots.forEach((s) => {
      ctx.beginPath();
      ctx.arc(mx + wobble + s.dx, my + s.dy, s.r, 0, Math.PI * 2);
      ctx.fill();
    });

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
