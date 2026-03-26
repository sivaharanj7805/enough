/**
 * RiverRenderer — Animated bezier curve rivers between clusters with water flow particles.
 */

import type { RiverData, ClusterPositions } from '@/lib/types/phase6';

const QUALITY_COLORS: Record<string, { water: string; particle: string }> = {
  sparkling: { water: '#38bdf8', particle: '#ffffff' },
  clear: { water: '#3b82f6', particle: '#93c5fd' },
  murky: { water: '#78716c', particle: '#a8a29e' },
  toxic: { water: '#4ade80', particle: '#86efac' },
};

function bezierPoint(
  x0: number, y0: number,
  cx: number, cy: number,
  x1: number, y1: number,
  t: number
): [number, number] {
  const u = 1 - t;
  const x = u * u * x0 + 2 * u * t * cx + t * t * x1;
  const y = u * u * y0 + 2 * u * t * cy + t * t * y1;
  return [x, y];
}

export function draw(
  ctx: CanvasRenderingContext2D,
  rivers: RiverData[],
  clusters: ClusterPositions,
  time: number
): void {
  for (const river of rivers) {
    const from = clusters[river.from_cluster_id];
    const to = clusters[river.to_cluster_id];
    if (!from || !to) continue;

    const colors = QUALITY_COLORS[river.quality] || QUALITY_COLORS.clear;

    // Control point for bezier (perpendicular offset for curve)
    const mx = (from.x + to.x) / 2;
    const my = (from.y + to.y) / 2;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const offset = dist * 0.15;
    const cx = mx + (-dy / dist) * offset;
    const cy = my + (dx / dist) * offset;

    // Draw river path — minimum 3px width, higher alpha
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.quadraticCurveTo(cx, cy, to.x, to.y);
    ctx.strokeStyle = colors.water;
    ctx.lineWidth = Math.max(river.width * 1.5, 3);
    ctx.globalAlpha = 0.85;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Dry riverbed for single-link trickles
    if (river.total_links === 1) {
      ctx.setLineDash([4, 6]);
      ctx.strokeStyle = '#6b7280';
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.3;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.restore();

    // Water flow particles — elongated teardrops
    const particleCount = Math.min(river.total_links, 8);
    for (let i = 0; i < particleCount; i++) {
      const t = ((time * 0.0003 * (1 + i * 0.1)) + i / particleCount) % 1;
      const [px, py] = bezierPoint(from.x, from.y, cx, cy, to.x, to.y, t);

      // Compute direction for teardrop orientation
      const dt = 0.02;
      const t2 = Math.min(1, t + dt);
      const [px2, py2] = bezierPoint(from.x, from.y, cx, cy, to.x, to.y, t2);
      const dirAngle = Math.atan2(py2 - py, px2 - px);

      ctx.save();
      ctx.translate(px, py);
      ctx.rotate(dirAngle);
      // Elongated teardrop shape
      ctx.beginPath();
      ctx.moveTo(-4, 0);
      ctx.quadraticCurveTo(-1, -2, 3, 0);
      ctx.quadraticCurveTo(-1, 2, -4, 0);
      ctx.fillStyle = colors.particle;
      ctx.globalAlpha = 0.85;
      ctx.fill();
      ctx.restore();
    }

    // Waterfall effect for one-directional flow
    if (river.bidirectional_ratio < 0.2 && river.total_links >= 3) {
      const midT = 0.5;
      const [wx, wy] = bezierPoint(from.x, from.y, cx, cy, to.x, to.y, midT);
      ctx.save();
      ctx.beginPath();
      ctx.arc(wx, wy, river.width * 2, 0, Math.PI * 2);
      ctx.fillStyle = colors.water;
      ctx.globalAlpha = 0.15 + Math.sin(time * 0.003) * 0.05;
      ctx.fill();
      ctx.restore();
    }
  }
}
