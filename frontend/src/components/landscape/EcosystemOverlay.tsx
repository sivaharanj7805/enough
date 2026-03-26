'use client';

import { useEffect, useRef } from 'react';
import type { EcosystemVisualsResponse, ClusterPositions } from '@/lib/types/phase6';
import * as RiverRenderer from './RiverRenderer';
import * as GrassRenderer from './GrassRenderer';
import * as WeatherRenderer from './WeatherRenderer';
import * as AnimalRenderer from './AnimalRenderer';
import * as TerrainFeatureRenderer from './TerrainFeatureRenderer';

interface EcosystemOverlayProps {
  visuals: EcosystemVisualsResponse;
  positions: ClusterPositions;
}

export function EcosystemOverlay({ visuals, positions }: EcosystemOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const positionsRef = useRef<ClusterPositions>(positions);
  positionsRef.current = positions;

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

      const clusterPositions = positionsRef.current;

      // Render layers in order (back to front)
      // 1. Fog weather (behind everything)
      // 2. Rivers + water particles
      RiverRenderer.draw(ctx, visuals.rivers, clusterPositions, timestamp);

      // 3. Grass around cluster edges
      GrassRenderer.draw(ctx, visuals.grass, clusterPositions, timestamp);

      // 4. Terrain features (boulders, erosion, mushrooms)
      TerrainFeatureRenderer.draw(ctx, visuals.terrain_features, clusterPositions, timestamp);

      // 5. Ground animals (foxes, deer)
      AnimalRenderer.draw(ctx, visuals.animals, clusterPositions, timestamp);

      // 6. Weather effects (clouds, rain, sun above)
      WeatherRenderer.draw(ctx, visuals.weather, clusterPositions, timestamp);

      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      resizeObserver.disconnect();
    };
  }, [visuals]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-[5]"
      style={{ mixBlendMode: 'normal' }}
    />
  );
}
