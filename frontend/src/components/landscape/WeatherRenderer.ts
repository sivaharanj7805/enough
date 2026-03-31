/**
 * WeatherRenderer — Per-cluster weather effects: sun glow, clouds, rain, lightning, fog.
 */

import type { WeatherData, ClusterPositions } from '@/lib/types/phase6';

function drawSunny(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number, time: number
): void {
  // Golden radial glow filling the entire cluster area
  const pulse = 0.8 + Math.sin(time * 0.001) * 0.2;
  const grad = ctx.createRadialGradient(x, y, 0, x, y, radius * 1.2);
  grad.addColorStop(0, `rgba(250, 204, 21, ${0.2 * pulse})`);
  grad.addColorStop(0.4, `rgba(250, 204, 21, ${0.1 * pulse})`);
  grad.addColorStop(0.8, `rgba(250, 204, 21, ${0.03 * pulse})`);
  grad.addColorStop(1, 'rgba(250, 204, 21, 0)');

  ctx.save();
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.ellipse(x, y, radius * 1.2, radius * 0.85, 0, 0, Math.PI * 2);
  ctx.fill();

  // Sun rays (longer, more visible)
  const rayCount = 8;
  for (let i = 0; i < rayCount; i++) {
    const angle = (i / rayCount) * Math.PI * 2 + time * 0.0002;
    const innerR = radius * 0.2;
    const outerR = radius * 0.6 * pulse;
    ctx.beginPath();
    ctx.moveTo(
      x + Math.cos(angle) * innerR,
      y + Math.sin(angle) * innerR * 0.7
    );
    ctx.lineTo(
      x + Math.cos(angle) * outerR,
      y + Math.sin(angle) * outerR * 0.7
    );
    ctx.strokeStyle = `rgba(250, 204, 21, ${0.25 * pulse})`;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.stroke();
  }
  ctx.restore();
}

function drawClouds(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number, time: number
): void {
  const cloudCount = 3;
  for (let i = 0; i < cloudCount; i++) {
    const drift = Math.sin(time * 0.0003 + i * 2) * radius * 0.3;
    const cx = x + drift + (i - 1) * radius * 0.3;
    const cy = y - radius * 0.6 - i * 8;

    ctx.save();
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = '#9ca3af';
    ctx.beginPath();
    ctx.ellipse(cx, cy, radius * 0.2, radius * 0.08, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(cx + radius * 0.1, cy - 4, radius * 0.12, radius * 0.06, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

function drawRain(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number, time: number
): void {
  // Draw clouds first
  drawClouds(ctx, x, y, radius, time);

  // Rain drops — wider, more visible
  const dropCount = 16;
  for (let i = 0; i < dropCount; i++) {
    const seed = Math.sin(i * 47.3) * 10000;
    const dx = (seed - Math.floor(seed)) * radius * 1.2 - radius * 0.6;
    const fallCycle = ((time * 0.003 + i * 0.3) % 1);
    const dy = -radius * 0.4 + fallCycle * radius * 0.8;

    ctx.save();
    // Rain drop
    ctx.beginPath();
    ctx.moveTo(x + dx, y + dy);
    ctx.lineTo(x + dx - 0.5, y + dy + 8);
    ctx.strokeStyle = '#60a5fa';
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.7;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Splash circle at bottom of cycle
    if (fallCycle > 0.9) {
      const splashAlpha = (1 - fallCycle) * 10; // fade out 0.9→1
      ctx.beginPath();
      ctx.arc(x + dx, y + dy + 8, 3 * (1 - splashAlpha), 0, Math.PI * 2);
      ctx.strokeStyle = '#93c5fd';
      ctx.lineWidth = 0.8;
      ctx.globalAlpha = splashAlpha * 0.6;
      ctx.stroke();
    }

    ctx.restore();
  }
}

function drawStorm(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number, time: number
): void {
  // Heavy rain
  drawRain(ctx, x, y, radius, time);

  // Lightning flash (occasional)
  const flashCycle = Math.floor(time / 2000) % 7;
  if (flashCycle === 0) {
    const flashIntensity = Math.max(0, 1 - (time % 2000) / 200);
    if (flashIntensity > 0) {
      ctx.save();
      ctx.globalAlpha = flashIntensity * 0.3;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.ellipse(x, y, radius * 1.2, radius * 0.85, 0, 0, Math.PI * 2);
      ctx.fill();

      // Lightning bolt with branching forks
      if (flashIntensity > 0.5) {
        // Main bolt
        ctx.beginPath();
        ctx.moveTo(x + 5, y - radius * 0.6);
        ctx.lineTo(x - 3, y - radius * 0.3);
        ctx.lineTo(x + 3, y - radius * 0.25);
        ctx.lineTo(x - 5, y);
        ctx.strokeStyle = '#fde047';
        ctx.lineWidth = 2.5;
        ctx.globalAlpha = flashIntensity;
        ctx.stroke();

        // White glow around bolt
        ctx.lineWidth = 6;
        ctx.globalAlpha = flashIntensity * 0.3;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();

        // Branching fork 1
        ctx.beginPath();
        ctx.moveTo(x - 3, y - radius * 0.3);
        ctx.lineTo(x - 12, y - radius * 0.15);
        ctx.strokeStyle = '#fde047';
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = flashIntensity * 0.7;
        ctx.stroke();

        // Branching fork 2
        ctx.beginPath();
        ctx.moveTo(x + 3, y - radius * 0.25);
        ctx.lineTo(x + 10, y - radius * 0.1);
        ctx.strokeStyle = '#fde047';
        ctx.lineWidth = 1;
        ctx.globalAlpha = flashIntensity * 0.5;
        ctx.stroke();
      }
      ctx.restore();
    }
  }
}

function drawFog(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number, time: number
): void {
  const layers = 4;
  for (let i = 0; i < layers; i++) {
    const drift = Math.sin(time * 0.0002 + i * 1.5) * radius * 0.15;
    const ly = y - radius * 0.2 + i * radius * 0.15;

    ctx.save();
    const grad = ctx.createRadialGradient(x + drift, ly, 0, x + drift, ly, radius * 0.9);
    grad.addColorStop(0, 'rgba(148, 163, 184, 0.2)');
    grad.addColorStop(0.6, 'rgba(148, 163, 184, 0.08)');
    grad.addColorStop(1, 'rgba(148, 163, 184, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(x + drift, ly, radius * 0.9, radius * 0.25, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

export function draw(
  ctx: CanvasRenderingContext2D,
  weather: Record<string, WeatherData>,
  clusters: ClusterPositions,
  time: number
): void {
  for (const [clusterId, data] of Object.entries(weather)) {
    const cluster = clusters[clusterId];
    if (!cluster) continue;

    switch (data.state) {
      case 'sunny':
        drawSunny(ctx, cluster.x, cluster.y, cluster.radius, time);
        break;
      case 'cloudy':
        drawClouds(ctx, cluster.x, cluster.y, cluster.radius, time);
        break;
      case 'rain':
        drawRain(ctx, cluster.x, cluster.y, cluster.radius, time);
        break;
      case 'storm':
        drawStorm(ctx, cluster.x, cluster.y, cluster.radius, time);
        break;
      case 'fog':
        drawFog(ctx, cluster.x, cluster.y, cluster.radius, time);
        break;
    }
  }
}
