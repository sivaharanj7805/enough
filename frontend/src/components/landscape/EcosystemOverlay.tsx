'use client';

import { useEffect, useRef, useCallback } from 'react';
import type { EcosystemVisualsResponse, ClusterPositions } from '@/lib/types/phase6';
import type { ClusterDetail } from '@/lib/types';

interface EcosystemOverlayProps {
  visuals: EcosystemVisualsResponse;
  clusters: ClusterDetail[];
}

export function EcosystemOverlay({ visuals, clusters }: EcosystemOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  // Build cluster positions from the cluster data
  // Uses a deterministic layout matching the SVG force layout
  const getClusterPositions = useCallback((): ClusterPositions => {
    if (clusters.length === 0) return {};

    const canvas = canvasRef.current;
    if (!canvas) return {};

    const width = canvas.width;
    const height = canvas.height;
    const maxPosts = Math.max(...clusters.map((c) => c.posts.length), 1);
    const minRadius = 60;
    const maxRadius = 180;

    const positions: ClusterPositions = {};

    // Simple deterministic layout: distribute clusters in a grid-like pattern
    const cols = Math.ceil(Math.sqrt(clusters.length));
    const rows = Math.ceil(clusters.length / cols);
    const cellW = width / (cols + 1);
    const cellH = height / (rows + 1);

    clusters.forEach((cluster, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const postRatio = cluster.posts.length / maxPosts;
      const radius = minRadius + postRatio * (maxRadius - minRadius);

      positions[cluster.id] = {
        id: cluster.id,
        x: cellW * (col + 1),
        y: cellH * (row + 1),
        radius,
      };
    });

    return positions;
  }, [clusters]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    // Match canvas size to parent
    const resize = () => {
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    };
    resize();

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(parent);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const animate = (timestamp: number) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const clusterPositions = getClusterPositions();

      // Render layers removed (renderers deleted)

      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      resizeObserver.disconnect();
    };
  }, [visuals, getClusterPositions]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-[5]"
      style={{ mixBlendMode: 'screen' }}
    />
  );
}
