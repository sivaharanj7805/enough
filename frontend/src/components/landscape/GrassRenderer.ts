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
    const clumpCount = Math.floor(48 * config.density); // Doubled density

    for (let i = 0; i < clumpCount; i++) {
      // Position clumps around the cluster edge
      const angle = (i / clumpCount) * Math.PI * 2;
      const edgeOffset = 0.82 + seededRandom(i * 17 + 3) * 0.3;
      const bx = cluster.x + Math.cos(angle) * cluster.radius * edgeOffset;
      const by = cluster.y + Math.sin(angle) * cluster.radius * 0.7 * edgeOffset;

      // Draw a clump of 3-5 blades radiating from shared base
      const bladesInClump = 3 + Math.floor(seededRandom(i * 43) * 3);
      for (let b = 0; b < bladesInClump; b++) {
        const spreadAngle = (b / bladesInClump - 0.5) * 0.8;
        const sway = config.swayAmplitude * Math.sin(time * config.swaySpeed + i * 0.7 + b * 0.4);
        const bladeHeight = config.height * (0.7 + seededRandom(i * 31 + b * 13) * 0.6);

        ctx.save();
        ctx.globalAlpha = 0.9;

        // Dark base → light tip gradient via two segments
        // Base segment (darker)
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.quadraticCurveTo(
          bx + sway * 0.3 + spreadAngle * 4,
          by - bladeHeight * 0.5,
          bx + sway * 0.6 + spreadAngle * 6,
          by - bladeHeight * 0.6
        );
        ctx.strokeStyle = config.color;
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.stroke();

        // Tip segment (lighter)
        ctx.beginPath();
        ctx.moveTo(bx + sway * 0.6 + spreadAngle * 6, by - bladeHeight * 0.6);
        ctx.quadraticCurveTo(
          bx + sway * 0.8 + spreadAngle * 7,
          by - bladeHeight * 0.85,
          bx + sway + spreadAngle * 8,
          by - bladeHeight
        );
        ctx.strokeStyle = config.tipColor;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.stroke();

        ctx.restore();
      }
    }
  }
}
