'use client';

import { useRef, useEffect, useCallback, useMemo, useState } from 'react';
import { ECOSYSTEM_COLORS, type EcosystemState } from '@/lib/constants';
import type { ClusterDetail } from '@/lib/types';

interface MinimapProps {
  clusters: ClusterDetail[];
  canvasWidth: number;
  canvasHeight: number;
  viewportTransform: { x: number; y: number; k: number } | null;
  onNavigate: (x: number, y: number) => void;
}

const MINIMAP_W = 150;
const MINIMAP_H = 100;

interface MinimapRegion {
  id: string;
  x: number;
  y: number;
  radius: number;
  color: string;
}

export function Minimap({ clusters, canvasWidth, canvasHeight, viewportTransform, onNavigate }: MinimapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovering, setHovering] = useState(false);

  // Compute simplified region positions (approximate grid layout)
  const regions: MinimapRegion[] = useMemo(() => {
    if (clusters.length === 0) return [];

    const maxPosts = Math.max(...clusters.map(c => c.posts.length), 1);
    const cols = Math.ceil(Math.sqrt(clusters.length));
    const cw = canvasWidth || 800;
    const ch = canvasHeight || 600;

    return clusters.map((c, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      const spacing = Math.min(cw, ch) / (cols + 1);
      const postRatio = c.posts.length / maxPosts;
      const radius = 4 + postRatio * 8;

      const state = (c.ecosystem_state as EcosystemState) ?? 'meadow';
      const color = ECOSYSTEM_COLORS[state]?.border ?? '#4d8b4d';

      return {
        id: c.id,
        x: spacing * (col + 1),
        y: spacing * (row + 1),
        radius,
        color,
      };
    });
  }, [clusters, canvasWidth, canvasHeight]);

  // Scale factors from canvas coords to minimap coords
  const scaleX = MINIMAP_W / (canvasWidth || 800);
  const scaleY = MINIMAP_H / (canvasHeight || 600);

  // Draw minimap
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, MINIMAP_W, MINIMAP_H);

    // Background
    ctx.fillStyle = '#0a0f1a';
    ctx.beginPath();
    ctx.roundRect(0, 0, MINIMAP_W, MINIMAP_H, 8);
    ctx.fill();

    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(0.5, 0.5, MINIMAP_W - 1, MINIMAP_H - 1, 8);
    ctx.stroke();

    // Draw regions as colored circles
    regions.forEach((r) => {
      const mx = r.x * scaleX;
      const my = r.y * scaleY;
      const mr = Math.max(2, r.radius * scaleX);

      ctx.beginPath();
      ctx.arc(mx, my, mr, 0, Math.PI * 2);
      ctx.fillStyle = r.color;
      ctx.globalAlpha = 0.7;
      ctx.fill();
      ctx.globalAlpha = 1;
    });

    // Draw viewport rectangle
    if (viewportTransform) {
      const vt = viewportTransform;
      const cw = canvasWidth || 800;
      const ch = canvasHeight || 600;

      // The viewport in canvas space
      const vx = -vt.x / vt.k;
      const vy = -vt.y / vt.k;
      const vw = cw / vt.k;
      const vh = ch / vt.k;

      // Map to minimap space
      const rx = vx * scaleX;
      const ry = vy * scaleY;
      const rw = vw * scaleX;
      const rh = vh * scaleY;

      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.rect(
        Math.max(0, rx),
        Math.max(0, ry),
        Math.min(rw, MINIMAP_W - Math.max(0, rx)),
        Math.min(rh, MINIMAP_H - Math.max(0, ry))
      );
      ctx.stroke();

      // Subtle fill
      ctx.fillStyle = 'rgba(59, 130, 246, 0.08)';
      ctx.fill();
    }
  }, [regions, viewportTransform, scaleX, scaleY, canvasWidth, canvasHeight]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Convert minimap coords to canvas coords
    const cx = mx / scaleX;
    const cy = my / scaleY;

    onNavigate(cx, cy);
  }, [scaleX, scaleY, onNavigate]);

  if (clusters.length === 0) return null;

  return (
    <div
      className={`absolute bottom-4 right-4 z-10 transition-opacity duration-200 ${
        hovering ? 'opacity-100' : 'opacity-60'
      }`}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <canvas
        ref={canvasRef}
        width={MINIMAP_W}
        height={MINIMAP_H}
        onClick={handleClick}
        className="cursor-crosshair rounded-lg shadow-lg"
        aria-label="Ecosystem minimap — click to navigate"
      />
    </div>
  );
}
