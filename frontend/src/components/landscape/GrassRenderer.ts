/**
 * GrassRenderer — Procedural grass blades at cluster edges, height/color/sway based on freshness.
 */

import type { GrassData, ClusterPositions } from '@/lib/types/phase6';

interface GrassConfig {
  height: number;
  color: string;
  tipColor: string;
  swayAmplitude: number;
  swaySpeed: number;
  density: number;
}

const STATE_CONFIG: Record<string, GrassConfig> = {
  fresh: {
    height: 8,
    color: '#22c55e',
    tipColor: '#4ade80',
    swayAmplitude: 2,
    swaySpeed: 0.002,
    density: 1.0,
  },
  maintained: {
    height: 12,
    color: '#16a34a',
    tipColor: '#22c55e',
    swayAmplitude: 3,
    swaySpeed: 0.0015,
    density: 0.8,
  },
  overgrown: {
    height: 20,
    color: '#a3a23a',
    tipColor: '#ca8a04',
    swayAmplitude: 5,
    swaySpeed: 0.001,
    density: 0.9,
  },
  dead: {
    height: 4,
    color: '#78716c',
    tipColor: '#a8a29e',
    swayAmplitude: 0,
    swaySpeed: 0,
    density: 0.4,
  },
};

// Deterministic pseudo-random from seed
function seededRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

export function draw(
  ctx: CanvasRenderingContext2D,
  grass: Record<string, GrassData>,
  clusters: ClusterPositions,
  time: number
): void {
  for (const [clusterId, data] of Object.entries(grass)) {
    const cluster = clusters[clusterId];
    if (!cluster) continue;

    const config = STATE_CONFIG[data.state] || STATE_CONFIG.maintained;
    const bladeCount = Math.floor(24 * config.density);

    for (let i = 0; i < bladeCount; i++) {
      // Position blades around the cluster edge
      const angle = (i / bladeCount) * Math.PI * 2;
      const edgeOffset = 0.85 + seededRandom(i * 17 + 3) * 0.25;
      const bx = cluster.x + Math.cos(angle) * cluster.radius * edgeOffset;
      const by = cluster.y + Math.sin(angle) * cluster.radius * 0.7 * edgeOffset;

      // Sway animation
      const sway = config.swayAmplitude * Math.sin(time * config.swaySpeed + i * 0.7);
      const bladeHeight = config.height * (0.7 + seededRandom(i * 31) * 0.6);

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.quadraticCurveTo(
        bx + sway * 0.5,
        by - bladeHeight * 0.6,
        bx + sway,
        by - bladeHeight
      );
      ctx.strokeStyle = config.color;
      ctx.lineWidth = 1.2;
      ctx.globalAlpha = 0.7;
      ctx.stroke();

      // Grass tip highlight
      if (data.state !== 'dead') {
        ctx.beginPath();
        ctx.arc(bx + sway, by - bladeHeight, 0.8, 0, Math.PI * 2);
        ctx.fillStyle = config.tipColor;
        ctx.globalAlpha = 0.5;
        ctx.fill();
      }

      ctx.restore();
    }
  }
}
