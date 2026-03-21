'use client';

import { useEffect, useRef, useMemo } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useCalendar } from '@/lib/hooks/useApi';
import type { ClusterDetail } from '@/lib/types';
import type { EcosystemState } from '@/lib/constants';

interface ContentPlannerOverlayProps {
  clusters: ClusterDetail[];
  visible: boolean;
}

interface RegionPosition {
  id: string;
  label: string | null;
  ecosystemState: EcosystemState | null;
  x: number;
  y: number;
  radius: number;
}

/**
 * Compute approximate region positions (same layout as EcosystemCanvas).
 * This mirrors the force layout used in the canvas for overlay alignment.
 */
function computeRegionPositions(clusters: ClusterDetail[], width: number, height: number): RegionPosition[] {
  const minRadius = 60;
  const maxRadius = 180;
  const maxPosts = Math.max(...clusters.map(c => c.posts.length), 1);

  const regions = clusters.map((c, i) => {
    const postRatio = c.posts.length / maxPosts;
    const radius = minRadius + postRatio * (maxRadius - minRadius);
    // Approximate positions using a grid layout (simpler than force sim)
    const cols = Math.ceil(Math.sqrt(clusters.length));
    const row = Math.floor(i / cols);
    const col = i % cols;
    const spacing = Math.min(width, height) / (cols + 1);

    return {
      id: c.id,
      label: c.label,
      ecosystemState: c.ecosystem_state as EcosystemState | null,
      x: spacing * (col + 1),
      y: spacing * (row + 1),
      radius,
    };
  });

  return regions;
}

export function ContentPlannerOverlay({ clusters, visible }: ContentPlannerOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const { currentSite } = useSite();
  const { data: calendar } = useCalendar(currentSite?.id ?? null);

  const calendarRecs = useMemo(() => {
    if (!calendar?.recommendations) return new Map<string, string[]>();
    const map = new Map<string, string[]>();
    for (const rec of calendar.recommendations) {
      const existing = map.get(rec.cluster_id) ?? [];
      existing.push(rec.recommendation_text);
      map.set(rec.cluster_id, existing);
    }
    return map;
  }, [calendar]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !visible) {
      cancelAnimationFrame(animRef.current);
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    canvas.width = parent.clientWidth;
    canvas.height = parent.clientHeight;

    const regions = computeRegionPositions(clusters, canvas.width, canvas.height);
    let time = 0;

    const draw = () => {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Semi-transparent dark overlay
      ctx.fillStyle = 'rgba(10, 15, 26, 0.3)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      time += 0.02;

      regions.forEach((region) => {
        const state = region.ecosystemState;

        if (state === 'seedbed') {
          // Pulsing green circle — growth opportunity
          const pulse = 0.7 + Math.sin(time * 2) * 0.3;
          ctx.beginPath();
          ctx.arc(region.x, region.y, region.radius * 0.8, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(34, 197, 94, ${0.3 * pulse})`;
          ctx.lineWidth = 3;
          ctx.setLineDash([8, 4]);
          ctx.stroke();
          ctx.setLineDash([]);

          // Inner glow
          const grad = ctx.createRadialGradient(
            region.x, region.y, 0,
            region.x, region.y, region.radius * 0.6
          );
          grad.addColorStop(0, `rgba(34, 197, 94, ${0.08 * pulse})`);
          grad.addColorStop(1, 'rgba(34, 197, 94, 0)');
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(region.x, region.y, region.radius * 0.6, 0, Math.PI * 2);
          ctx.fill();

          // Label
          ctx.font = 'bold 10px system-ui, -apple-system, sans-serif';
          ctx.fillStyle = '#22c55e';
          ctx.textAlign = 'center';
          ctx.fillText('PLANT HERE', region.x, region.y - region.radius * 0.5);
        } else if (state === 'swamp') {
          // Warning amber zone
          const pulse = 0.6 + Math.sin(time * 1.5) * 0.4;
          ctx.beginPath();
          ctx.arc(region.x, region.y, region.radius * 0.8, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(245, 158, 11, ${0.3 * pulse})`;
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 4]);
          ctx.stroke();
          ctx.setLineDash([]);

          // Warning fill
          const grad = ctx.createRadialGradient(
            region.x, region.y, 0,
            region.x, region.y, region.radius * 0.6
          );
          grad.addColorStop(0, `rgba(245, 158, 11, ${0.06 * pulse})`);
          grad.addColorStop(1, 'rgba(245, 158, 11, 0)');
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(region.x, region.y, region.radius * 0.6, 0, Math.PI * 2);
          ctx.fill();

          ctx.font = 'bold 10px system-ui, -apple-system, sans-serif';
          ctx.fillStyle = '#f59e0b';
          ctx.textAlign = 'center';
          ctx.fillText('CONSOLIDATE FIRST', region.x, region.y - region.radius * 0.5);
        }

        // Show calendar suggestions floating near clusters
        const suggestions = calendarRecs.get(region.id);
        if (suggestions && suggestions.length > 0) {
          const text = suggestions[0].slice(0, 50) + (suggestions[0].length > 50 ? '...' : '');
          const floatY = region.y + region.radius * 0.3 + Math.sin(time + parseInt(region.id, 36) * 0.1) * 4;

          // Suggestion pill
          ctx.font = '10px system-ui, -apple-system, sans-serif';
          const metrics = ctx.measureText(text);
          const pillW = metrics.width + 16;
          const pillH = 22;
          const pillX = region.x - pillW / 2;

          ctx.fillStyle = 'rgba(30, 41, 59, 0.9)';
          ctx.beginPath();
          ctx.roundRect(pillX, floatY - pillH / 2, pillW, pillH, 6);
          ctx.fill();

          ctx.strokeStyle = 'rgba(59, 130, 246, 0.3)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(pillX, floatY - pillH / 2, pillW, pillH, 6);
          ctx.stroke();

          ctx.fillStyle = '#94a3b8';
          ctx.textAlign = 'center';
          ctx.fillText(text, region.x, floatY + 3);
        }
      });

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(animRef.current);
  }, [clusters, visible, calendarRecs]);

  if (!visible) return null;

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-[6]"
      aria-label="Content planner overlay showing growth opportunities and consolidation zones"
    />
  );
}
