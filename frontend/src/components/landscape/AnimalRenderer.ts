/**
 * AnimalRenderer — Animated creatures per cluster based on user behavior signals.
 * Birds circle above, foxes lurk at edges, deer graze, bees buzz, vultures soar.
 */

import type { AnimalData, ClusterPositions } from '@/lib/types/phase6';

function drawBirds(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 + time * 0.0005;
    const orbitR = radius * 1.1 + i * 8;
    const bx = x + Math.cos(angle) * orbitR;
    const by = y - radius * 0.7 + Math.sin(angle * 0.5) * 10 - i * 6;

    // V-shape bird silhouette
    const wingFlap = Math.sin(time * 0.005 + i * 2) * 3;
    ctx.save();
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1.2;
    ctx.globalAlpha = 0.7;
    ctx.beginPath();
    ctx.moveTo(bx - 4, by + wingFlap);
    ctx.lineTo(bx, by);
    ctx.lineTo(bx + 4, by + wingFlap);
    ctx.stroke();
    ctx.restore();
  }
}

function drawFoxes(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    const baseAngle = (i / count) * Math.PI * 2 + Math.PI * 0.25;
    const prowl = Math.sin(time * 0.001 + i * 3) * radius * 0.1;
    const fx = x + Math.cos(baseAngle) * (radius * 0.85 + prowl);
    const fy = y + Math.sin(baseAngle) * radius * 0.6;

    ctx.save();
    ctx.globalAlpha = 0.65;

    // Body — small orange triangle
    ctx.fillStyle = '#ea580c';
    ctx.beginPath();
    ctx.moveTo(fx - 4, fy + 2);
    ctx.lineTo(fx, fy - 4);
    ctx.lineTo(fx + 4, fy + 2);
    ctx.closePath();
    ctx.fill();

    // Tail
    ctx.beginPath();
    ctx.moveTo(fx - 4, fy + 1);
    ctx.quadraticCurveTo(fx - 8, fy - 2, fx - 6, fy + 4);
    ctx.strokeStyle = '#ea580c';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Eyes (glowing dots)
    ctx.fillStyle = '#fbbf24';
    ctx.globalAlpha = 0.5 + Math.sin(time * 0.003 + i) * 0.3;
    ctx.beginPath();
    ctx.arc(fx - 1.5, fy - 2, 0.7, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(fx + 1.5, fy - 2, 0.7, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }
}

function drawDeer(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 + Math.PI * 0.6;
    const dx = x + Math.cos(angle) * radius * 0.5;
    const dy = y + Math.sin(angle) * radius * 0.35;

    // Grazing animation: head dips
    const headDip = Math.sin(time * 0.0015 + i * 2) * 3;

    ctx.save();
    ctx.globalAlpha = 0.6;

    // Body
    ctx.fillStyle = '#92400e';
    ctx.beginPath();
    ctx.ellipse(dx, dy, 5, 3, 0, 0, Math.PI * 2);
    ctx.fill();

    // Neck + head
    ctx.beginPath();
    ctx.moveTo(dx + 3, dy - 2);
    ctx.lineTo(dx + 5, dy - 5 + headDip);
    ctx.strokeStyle = '#92400e';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Head
    ctx.beginPath();
    ctx.arc(dx + 5, dy - 6 + headDip, 2, 0, Math.PI * 2);
    ctx.fill();

    // Antlers
    ctx.strokeStyle = '#78350f';
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(dx + 5, dy - 8 + headDip);
    ctx.lineTo(dx + 3, dy - 12 + headDip);
    ctx.moveTo(dx + 5, dy - 8 + headDip);
    ctx.lineTo(dx + 7, dy - 12 + headDip);
    ctx.stroke();

    // Legs
    ctx.strokeStyle = '#92400e';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(dx - 3, dy + 2);
    ctx.lineTo(dx - 3, dy + 6);
    ctx.moveTo(dx + 2, dy + 2);
    ctx.lineTo(dx + 2, dy + 6);
    ctx.stroke();

    ctx.restore();
  }
}

function drawBees(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    // Zigzag random movement
    const t = time * 0.002 + i * 5;
    const bx = x + Math.sin(t * 1.3) * radius * 0.4 + Math.cos(t * 0.7 + i) * radius * 0.2;
    const by = y + Math.cos(t * 0.9) * radius * 0.25 - radius * 0.2;

    ctx.save();

    // Body
    ctx.fillStyle = '#fbbf24';
    ctx.globalAlpha = 0.7;
    ctx.beginPath();
    ctx.ellipse(bx, by, 2, 1.5, 0, 0, Math.PI * 2);
    ctx.fill();

    // Stripes
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 0.5;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.moveTo(bx - 0.5, by - 1.5);
    ctx.lineTo(bx - 0.5, by + 1.5);
    ctx.moveTo(bx + 0.5, by - 1.5);
    ctx.lineTo(bx + 0.5, by + 1.5);
    ctx.stroke();

    // Glow trail
    const grad = ctx.createRadialGradient(bx, by, 0, bx, by, 4);
    grad.addColorStop(0, 'rgba(251, 191, 36, 0.15)');
    grad.addColorStop(1, 'rgba(251, 191, 36, 0)');
    ctx.fillStyle = grad;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(bx, by, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }
}

function drawVultures(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  count: number, time: number
): void {
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 + time * 0.0003;
    const orbitR = radius * 1.3 + i * 12;
    const vx = x + Math.cos(angle) * orbitR;
    const vy = y - radius * 0.9 + Math.sin(angle * 0.3) * 15 - i * 10;

    // Larger, darker silhouette with tilted wings
    const tilt = Math.sin(time * 0.002 + i) * 0.15;

    ctx.save();
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(vx - 7, vy + 2 + tilt * 10);
    ctx.quadraticCurveTo(vx - 3, vy - 1, vx, vy);
    ctx.quadraticCurveTo(vx + 3, vy - 1, vx + 7, vy + 2 - tilt * 10);
    ctx.stroke();
    ctx.restore();
  }
}

export function draw(
  ctx: CanvasRenderingContext2D,
  animals: Record<string, AnimalData[]>,
  clusters: ClusterPositions,
  time: number
): void {
  for (const [clusterId, animalList] of Object.entries(animals)) {
    const cluster = clusters[clusterId];
    if (!cluster) continue;

    for (const animal of animalList) {
      switch (animal.type) {
        case 'birds':
          drawBirds(ctx, cluster.x, cluster.y, cluster.radius, animal.count, time);
          break;
        case 'foxes':
          drawFoxes(ctx, cluster.x, cluster.y, cluster.radius, animal.count, time);
          break;
        case 'deer':
          drawDeer(ctx, cluster.x, cluster.y, cluster.radius, animal.count, time);
          break;
        case 'bees':
          drawBees(ctx, cluster.x, cluster.y, cluster.radius, animal.count, time);
          break;
        case 'vultures':
          drawVultures(ctx, cluster.x, cluster.y, cluster.radius, animal.count, time);
          break;
      }
    }
  }
}
