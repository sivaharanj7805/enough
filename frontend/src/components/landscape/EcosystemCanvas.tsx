'use client';

/**
 * EcosystemCanvas — PixiJS WebGL-based ecosystem visualization.
 * D3 handles force layout math. PixiJS handles all rendering (GPU-accelerated).
 * All overlay effects (grass, terrain, weather, rivers, animals) render in-stage.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { LandscapeTooltip } from './LandscapeTooltip';
import { LegendPanel } from './LegendPanel';
import type { ClusterDetail, PostHealth } from '@/lib/types';
import type { ClusterPositions, EcosystemVisualsResponse } from '@/lib/types/phase6';
import { ECOSYSTEM_COLORS, type EcosystemState, type PostRole, type Trend } from '@/lib/constants';

export interface CannPair {
  post_a_id: string;
  post_b_id: string;
  cosine_similarity: number;
}

type CreatureType = string;

interface EcosystemCanvasProps {
  clusters: ClusterDetail[];
  onSelectPost: (post: PostHealth | null) => void;
  onZoomToCluster: (clusterId: string | null) => void;
  zoomedClusterId: string | null;
  cannPairs?: CannPair[];
  visuals?: EcosystemVisualsResponse | null;
  onClickCreature?: (post: PostHealth, creature: CreatureType) => void;
  onPositionsComputed?: (positions: ClusterPositions) => void;
  onViewportChange?: (transform: { x: number; y: number; k: number }) => void;
  navigateRef?: React.MutableRefObject<((x: number, y: number) => void) | null>;
}

interface TooltipData {
  title: string;
  url: string;
  traffic: number;
  healthScore: number;
  role: PostRole;
  trend: Trend;
}

interface TooltipState {
  data: TooltipData;
  x: number;
  y: number;
}

// ── Utilities (no pixi dependency) ──────────────────────────

function seededRandom(seed: string): () => number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = Math.imul(31, h) + seed.charCodeAt(i) | 0;
  return () => {
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
    h = Math.imul(h ^ (h >>> 13), 0x45d9f3b);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  };
}

function scoreColor(score: number): string {
  if (score >= 70) return '#22c55e';
  if (score >= 40) return '#eab308';
  return '#ef4444';
}

function trafficScale(traffic: number, maxTraffic: number): number {
  if (maxTraffic <= 0) return 0.5;
  return 0.3 + (traffic / maxTraffic) * 0.7;
}

// ── Component ───────────────────────────────────────────────

export function EcosystemCanvas({
  clusters,
  onSelectPost,
  onZoomToCluster,
  zoomedClusterId,
  cannPairs = [],
  visuals,
  onClickCreature,
  onPositionsComputed,
  onViewportChange,
  navigateRef,
}: EcosystemCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const handleHoverPost = useCallback((post: PostHealth | null, screenX: number, screenY: number) => {
    if (!post) { setTooltip(null); return; }
    setTooltip({
      data: {
        title: post.title,
        url: post.url,
        traffic: Math.round((post.traffic_contribution ?? 0) * 10000),
        healthScore: Math.round(post.composite_score ?? 0),
        role: post.role ?? 'dead_weight',
        trend: post.trend ?? 'stable',
      },
      x: screenX,
      y: screenY,
    });
  }, []);

  // ── Main PixiJS rendering effect ──────────────────────────
  useEffect(() => {
    if (!containerRef.current || clusters.length === 0) return;

    let destroyed = false;
    let pixiApp: any = null;

    (async () => {
      const PIXI = await import('pixi.js');
      if (destroyed) return;

      const container = containerRef.current!;
      const width = container.clientWidth;
      const height = container.clientHeight;

      // ── App init ──
      const app = new PIXI.Application();
      await app.init({
        background: '#020617',
        width,
        height,
        antialias: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        autoDensity: true,
      });
      if (destroyed) return;
      container.appendChild(app.canvas as HTMLCanvasElement);
      pixiApp = app;

      // ── Scene graph ──
      const world = new PIXI.Container();
      app.stage.addChild(world);
      const updaters: ((t: number) => void)[] = [];

      // ── D3 force layout ──
      // Seed with UMAP centroids for deterministic, topologically meaningful layout.
      // Falls back to random positions if no UMAP data available (legacy / first run).
      interface ForceNode extends d3.SimulationNodeDatum { id: string; radius: number; }
      const minRadius = 70;
      const maxRadius = 200;
      const maxPosts = Math.max(...clusters.map(c => c.posts.length), 1);

      // Scale UMAP centroids to canvas viewport
      const hasUmapPositions = clusters.some(c => c.center_x != null && c.center_y != null);
      let umapToCanvas: (cx: number | null, cy: number | null) => [number, number];

      if (hasUmapPositions) {
        const xs = clusters.filter(c => c.center_x != null).map(c => c.center_x!);
        const ys = clusters.filter(c => c.center_y != null).map(c => c.center_y!);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const rangeX = maxX - minX || 1;
        const rangeY = maxY - minY || 1;
        const pad = 0.15;
        umapToCanvas = (cx, cy) => [
          width * pad + (((cx ?? 0) - minX) / rangeX) * width * (1 - 2 * pad),
          height * pad + (((cy ?? 0) - minY) / rangeY) * height * (1 - 2 * pad),
        ];
      } else {
        umapToCanvas = () => [
          width / 2 + (Math.random() - 0.5) * width * 0.5,
          height / 2 + (Math.random() - 0.5) * height * 0.5,
        ];
      }

      const regions = clusters.map(cluster => {
        const postRatio = cluster.posts.length / maxPosts;
        const radius = minRadius + postRatio * (maxRadius - minRadius);
        const [ix, iy] = umapToCanvas(cluster.center_x, cluster.center_y);
        return {
          id: cluster.id,
          label: cluster.label,
          ecosystemState: (cluster.ecosystem_state ?? 'desert') as EcosystemState,
          healthScore: cluster.health_score ?? 0,
          posts: cluster.posts,
          x: ix,
          y: iy,
          radius,
        };
      });

      const forceNodes: ForceNode[] = regions.map(r => ({ id: r.id, x: r.x, y: r.y, radius: r.radius }));
      const sim = d3.forceSimulation(forceNodes)
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('collision', d3.forceCollide<ForceNode>().radius(d => d.radius + 30))
        .stop();
      for (let i = 0; i < 200; i++) sim.tick();
      forceNodes.forEach((n, i) => { regions[i].x = n.x ?? regions[i].x; regions[i].y = n.y ?? regions[i].y; });

      // Report positions
      const clusterPositions: ClusterPositions = {};
      regions.forEach(r => { clusterPositions[r.id] = { id: r.id, x: r.x, y: r.y, radius: r.radius }; });
      if (onPositionsComputed) onPositionsComputed(clusterPositions);

      // ── Background vignette ──
      const bg = new PIXI.Graphics();
      bg.rect(0, 0, width * 2, height * 2);
      bg.fill({ color: '#0a0f1a' });
      // Vignette center glow
      bg.circle(width / 2, height / 2, Math.max(width, height) * 0.5);
      bg.fill({ color: '#0f172a', alpha: 0.6 });
      world.addChild(bg);

      // ── Cluster glows ──
      const glowLayer = new PIXI.Container();
      regions.forEach(r => {
        const glow = new PIXI.Graphics();
        glow.ellipse(r.x, r.y, r.radius * 1.3, r.radius * 0.9);
        glow.fill({ color: ECOSYSTEM_COLORS[r.ecosystemState]?.bg ?? '#1e293b', alpha: 0.25 });
        glow.filters = [new PIXI.BlurFilter({ strength: 25 })];
        glowLayer.addChild(glow);
      });
      world.addChild(glowLayer);

      // ── Vegetation helpers ──

      function drawTree(s: number) {
        const c = new PIXI.Container();
        const sc = 0.7 + s * 0.7;
        const th = 45 * sc, tw = 8 * sc, cr = 24 * sc;

        // Shadow
        const sh = new PIXI.Graphics();
        sh.ellipse(0, 4, cr * 0.9, 6 * sc);
        sh.fill({ color: '#000000', alpha: 0.2 });
        c.addChild(sh);

        // Trunk
        const trunk = new PIXI.Graphics();
        trunk.poly([{ x: -tw / 2, y: 0 }, { x: -tw * 0.3, y: -th }, { x: tw * 0.3, y: -th }, { x: tw / 2, y: 0 }]);
        trunk.fill({ color: '#5c3d2e' });
        // Bark lines
        trunk.moveTo(-tw * 0.1, -th * 0.3); trunk.lineTo(-tw * 0.15, -th * 0.6);
        trunk.stroke({ color: '#3b1f12', width: 1 * sc, cap: 'round' });
        trunk.moveTo(tw * 0.05, -th * 0.5); trunk.lineTo(tw * 0.1, -th * 0.75);
        trunk.stroke({ color: '#3b1f12', width: 0.8 * sc, cap: 'round' });
        c.addChild(trunk);

        // Branches
        const br = new PIXI.Graphics();
        br.moveTo(-tw * 0.2, -th * 0.5); br.lineTo(-tw, -th * 0.65);
        br.stroke({ color: '#4a2f22', width: 2 * sc, cap: 'round' });
        br.moveTo(tw * 0.15, -th * 0.7); br.lineTo(tw * 0.8, -th * 0.82);
        br.stroke({ color: '#4a2f22', width: 1.5 * sc, cap: 'round' });
        c.addChild(br);

        // Canopy layers (dark to light, large to small)
        const can = new PIXI.Graphics();
        can.ellipse(-cr * 0.3, -th - cr * 0.3, cr, cr * 0.8);
        can.fill({ color: '#14532d', alpha: 0.9 });
        can.ellipse(cr * 0.3, -th - cr * 0.2, cr * 0.9, cr * 0.7);
        can.fill({ color: '#166534', alpha: 0.9 });
        can.ellipse(0, -th - cr * 0.7, cr * 0.95, cr * 0.8);
        can.fill({ color: '#15803d', alpha: 0.85 });
        can.ellipse(-cr * 0.1, -th - cr * 0.9, cr * 0.6, cr * 0.5);
        can.fill({ color: '#22c55e', alpha: 0.7 });
        can.ellipse(cr * 0.12, -th - cr, cr * 0.3, cr * 0.22);
        can.fill({ color: '#4ade80', alpha: 0.45 });
        c.addChild(can);
        return c;
      }

      function drawBush(s: number) {
        const c = new PIXI.Container();
        const sc = 0.6 + s * 0.6;
        const w = 22 * sc, h = 16 * sc;
        const g = new PIXI.Graphics();
        g.ellipse(0, 3, w * 0.6, 4 * sc);
        g.fill({ color: '#000000', alpha: 0.2 });
        g.moveTo(0, 0); g.lineTo(0, -h * 0.3);
        g.stroke({ color: '#5c3d2e', width: 2 * sc });
        g.ellipse(-w * 0.3, -h * 0.4, w * 0.5, h * 0.5);
        g.fill({ color: '#166534', alpha: 0.85 });
        g.ellipse(w * 0.25, -h * 0.35, w * 0.45, h * 0.5);
        g.fill({ color: '#15803d', alpha: 0.85 });
        g.ellipse(0, -h * 0.65, w * 0.5, h * 0.5);
        g.fill({ color: '#22c55e', alpha: 0.8 });
        g.ellipse(w * 0.05, -h * 0.75, w * 0.2, h * 0.2);
        g.fill({ color: '#4ade80', alpha: 0.4 });
        c.addChild(g);
        return c;
      }

      function drawVine(s: number) {
        const c = new PIXI.Container();
        const sc = 0.6 + s * 0.6;
        const sz = 18 * sc;
        const g = new PIXI.Graphics();
        g.ellipse(0, 3, sz * 0.5, 3 * sc);
        g.fill({ color: '#000000', alpha: 0.15 });
        // Vine paths
        g.moveTo(-sz * 0.5, 0);
        g.quadraticCurveTo(-sz * 0.3, -sz * 0.8, sz * 0.1, -sz * 0.6);
        g.quadraticCurveTo(sz * 0.3, -sz * 0.45, sz * 0.5, -sz * 0.3);
        g.stroke({ color: '#22c55e', width: 3 * sc, cap: 'round' });
        g.moveTo(-sz * 0.3, -sz * 0.1);
        g.quadraticCurveTo(sz * 0.2, -sz, sz * 0.4, -sz * 0.5);
        g.stroke({ color: '#f97316', width: 2.5 * sc, cap: 'round' });
        g.moveTo(-sz * 0.1, 0);
        g.quadraticCurveTo(-sz * 0.5, -sz * 0.5, 0, -sz * 0.9);
        g.stroke({ color: '#ea580c', width: 2 * sc, cap: 'round' });
        // Leaves
        [[-sz * 0.4, -sz * 0.5], [sz * 0.3, -sz * 0.4], [0, -sz * 0.8], [-sz * 0.15, -sz * 0.3]].forEach(([lx, ly]) => {
          g.ellipse(lx, ly, 4 * sc, 2.5 * sc);
          g.fill({ color: '#854d0e', alpha: 0.7 });
        });
        c.addChild(g);
        return c;
      }

      function drawStump(s: number) {
        const c = new PIXI.Container();
        const sc = 0.6 + s * 0.5;
        const w = 12 * sc, h = 12 * sc;
        const g = new PIXI.Graphics();
        g.ellipse(0, 3, w * 1.2, 4 * sc);
        g.fill({ color: '#374151', alpha: 0.35 });
        g.rect(-w / 2, -h, w, h);
        g.fill({ color: '#4b5563' });
        for (let i = 1; i <= 3; i++) {
          g.moveTo(-w * 0.4, -h + h * (i / 4)); g.lineTo(w * 0.4, -h + h * (i / 4));
          g.stroke({ color: '#374151', width: 0.6, alpha: 0.6 });
        }
        g.ellipse(-w * 0.3, -h * 0.4, w * 0.25, h * 0.3);
        g.fill({ color: '#166534', alpha: 0.25 });
        g.ellipse(0, -h, w / 2 + 1, 3 * sc);
        g.fill({ color: '#6b7280' });
        g.ellipse(0, -h, w * 0.3, 1.8 * sc);
        g.stroke({ color: '#9ca3af', width: 0.5 });
        c.addChild(g);
        return c;
      }

      function drawSeedling(s: number) {
        const c = new PIXI.Container();
        const sc = 0.6 + s * 0.5;
        const sh = Math.max(18, 16 * sc);
        const g = new PIXI.Graphics();
        g.ellipse(0, 3, 6 * sc, 3 * sc);
        g.fill({ color: '#3f2c1a', alpha: 0.5 });
        g.moveTo(0, 0); g.lineTo(0, -sh);
        g.stroke({ color: '#4ade80', width: 2.5 * sc, cap: 'round' });
        g.moveTo(0, -sh * 0.6);
        g.quadraticCurveTo(-10 * sc, -sh * 0.9, -3 * sc, -sh * 0.5);
        g.fill({ color: '#86efac', alpha: 0.85 });
        g.moveTo(0, -sh * 0.7);
        g.quadraticCurveTo(10 * sc, -sh, 3 * sc, -sh * 0.6);
        g.fill({ color: '#4ade80', alpha: 0.85 });
        g.circle(0, -sh - 2 * sc, 2.5 * sc);
        g.fill({ color: '#bbf7d0' });
        c.addChild(g);
        return c;
      }

      // ── Creature helpers ──

      function drawBloomling(s: number) {
        const c = new PIXI.Container();
        const r = 7 * s;
        const g = new PIXI.Graphics();
        g.ellipse(0, r + 1, r * 0.7, 2 * s);
        g.fill({ color: '#000000', alpha: 0.15 });
        for (let i = 0; i < 5; i++) {
          const a = (i / 5) * Math.PI * 2 - Math.PI / 2;
          g.circle(Math.cos(a) * (r + 3 * s), -r + Math.sin(a) * (r + 3 * s), 3.5 * s);
          g.fill({ color: '#4ade80', alpha: 0.8 });
        }
        g.circle(0, -r, r);
        g.fill({ color: '#86efac' });
        g.circle(0, -r, r);
        g.stroke({ color: '#22c55e', width: 1.2 });
        g.circle(-r * 0.3, -r - 1, 1.3 * s);
        g.fill({ color: '#14532d' });
        g.circle(r * 0.3, -r - 1, 1.3 * s);
        g.fill({ color: '#14532d' });
        g.moveTo(-r * 0.3, -r + 2);
        g.quadraticCurveTo(0, -r + 4, r * 0.3, -r + 2);
        g.stroke({ color: '#14532d', width: 1 });
        c.addChild(g);
        return c;
      }

      function drawRustmite(s: number) {
        const c = new PIXI.Container();
        const g = new PIXI.Graphics();
        g.ellipse(0, 2, 10 * s, 2.5 * s);
        g.fill({ color: '#000000', alpha: 0.15 });
        [[-1, -0.5], [-1, 0], [-1, 0.5], [1, -0.5], [1, 0], [1, 0.5]].forEach(([side, off]) => {
          g.moveTo(side * 5 * s, -4 * s + off * 5 * s);
          g.lineTo(side * 8 * s, -4 * s + off * 5 * s + 3 * s * side * -0.3);
          g.stroke({ color: '#c2410c', width: 1.2 * s, cap: 'round' });
        });
        g.ellipse(0, -4 * s, 6.5 * s, 4 * s);
        g.fill({ color: '#ea580c' });
        g.ellipse(0, -4 * s, 6.5 * s, 4 * s);
        g.stroke({ color: '#9a3412', width: 0.7 });
        g.moveTo(-5 * s, -4 * s); g.lineTo(5 * s, -4 * s);
        g.stroke({ color: '#7c2d12', width: 0.6, alpha: 0.5 });
        g.circle(-2.5 * s, -6.5 * s, 1.5 * s);
        g.fill({ color: '#fef08a' });
        g.circle(2.5 * s, -6.5 * s, 1.5 * s);
        g.fill({ color: '#fef08a' });
        g.circle(-6.5 * s, -7.5 * s, 2.5 * s);
        g.fill({ color: '#c2410c' });
        g.circle(6.5 * s, -7.5 * s, 2.5 * s);
        g.fill({ color: '#c2410c' });
        c.addChild(g);
        return c;
      }

      function drawFogling(s: number) {
        const c = new PIXI.Container();
        const w = 10 * s, h = 16 * s;
        const g = new PIXI.Graphics();
        g.ellipse(0, -h * 0.5, w * 1.5, h * 0.8);
        g.fill({ color: '#94a3b8', alpha: 0.06 });
        g.moveTo(-w, -h * 0.1);
        g.quadraticCurveTo(-w, -h * 1.1, 0, -h * 1.15);
        g.quadraticCurveTo(w, -h * 1.1, w, -h * 0.1);
        g.quadraticCurveTo(w * 0.5, h * 0.15, w * 0.2, -h * 0.05);
        g.quadraticCurveTo(0, h * 0.2, -w * 0.2, -h * 0.05);
        g.quadraticCurveTo(-w * 0.6, h * 0.15, -w, -h * 0.1);
        g.fill({ color: '#94a3b8', alpha: 0.3 });
        g.stroke({ color: '#cbd5e1', width: 0.8, alpha: 0.35 });
        g.circle(-w * 0.3, -h * 0.75, 2 * s);
        g.fill({ color: '#1e293b', alpha: 0.6 });
        g.circle(w * 0.3, -h * 0.75, 2 * s);
        g.fill({ color: '#1e293b', alpha: 0.6 });
        c.addChild(g);
        c.alpha = 0.4;
        return c;
      }

      // ── Render regions ──
      const regionLayer = new PIXI.Container();
      const postPositions = new Map<string, { x: number; y: number }>();
      const creatureAnimations: { container: any; type: string; baseY: number; index: number }[] = [];

      regions.forEach(region => {
        const rc = new PIXI.Container();
        rc.x = region.x;
        rc.y = region.y;

        const colors = ECOSYSTEM_COLORS[region.ecosystemState];
        const rand = seededRandom(region.id);

        // Ground ellipse
        const ground = new PIXI.Graphics();
        ground.ellipse(0, 0, region.radius, region.radius * 0.7);
        ground.fill({ color: colors?.bg ?? '#1e293b', alpha: 0.85 });
        ground.ellipse(0, 0, region.radius, region.radius * 0.7);
        ground.stroke({ color: colors?.border ?? '#334155', width: 1.5 });
        ground.eventMode = 'static';
        ground.cursor = 'pointer';
        ground.on('pointertap', () => onZoomToCluster(region.id));
        rc.addChild(ground);

        // Ground textures
        const tex = new PIXI.Graphics();
        if (region.ecosystemState === 'swamp') {
          for (let i = 0; i < 6; i++) {
            const a = (i / 6) * Math.PI * 2;
            const d = region.radius * 0.4 * rand();
            tex.ellipse(Math.cos(a) * d, Math.sin(a) * d * 0.7, 12 + rand() * 18, 7 + rand() * 12);
            tex.fill({ color: '#1a2e0f', alpha: 0.35 + rand() * 0.2 });
          }
        } else if (region.ecosystemState === 'desert') {
          for (let i = 0; i < 5; i++) {
            const a = rand() * Math.PI * 2;
            const len = region.radius * (0.2 + rand() * 0.4);
            tex.moveTo(Math.cos(a) * region.radius * 0.1, Math.sin(a) * region.radius * 0.07);
            tex.lineTo(Math.cos(a) * len, Math.sin(a) * len * 0.7);
            tex.stroke({ color: '#a6896a', width: 0.6, alpha: 0.5 });
          }
        } else if (region.ecosystemState === 'forest') {
          for (let i = 0; i < 5; i++) {
            const a = (i / 5) * Math.PI * 2 + rand() * 0.5;
            const d = region.radius * 0.3 * rand();
            tex.ellipse(Math.cos(a) * d, Math.sin(a) * d * 0.7, 10 + rand() * 15, 6 + rand() * 10);
            tex.fill({ color: '#14532d', alpha: 0.25 });
          }
        } else if (region.ecosystemState === 'seedbed') {
          for (let i = 0; i < 10; i++) {
            const a = rand() * Math.PI * 2;
            const d = rand() * region.radius * 0.6;
            tex.circle(Math.cos(a) * d, Math.sin(a) * d * 0.7, 2 + rand() * 3);
            tex.fill({ color: '#166534', alpha: 0.2 });
          }
        }
        rc.addChild(tex);

        // Vegetation for each post
        // Use UMAP 2D positions when available (topologically meaningful placement),
        // falling back to angular layout for posts without positions.
        const maxTraffic = Math.max(...region.posts.map(p => p.traffic_contribution ?? 0), 0.01);
        const postCount = region.posts.length;

        // Pre-compute UMAP-to-local mapping for posts with positions
        const postsWithUmap = region.posts.filter(p => p.x_pos != null && p.y_pos != null);
        let umapToLocal: ((xp: number, yp: number) => [number, number]) | null = null;
        if (postsWithUmap.length >= 2) {
          const uxs = postsWithUmap.map(p => p.x_pos!);
          const uys = postsWithUmap.map(p => p.y_pos!);
          const uMinX = Math.min(...uxs), uMaxX = Math.max(...uxs);
          const uMinY = Math.min(...uys), uMaxY = Math.max(...uys);
          const uRangeX = uMaxX - uMinX || 1;
          const uRangeY = uMaxY - uMinY || 1;
          const usableRadius = region.radius * 0.6;
          umapToLocal = (xp, yp) => [
            ((xp - uMinX) / uRangeX - 0.5) * 2 * usableRadius,
            ((yp - uMinY) / uRangeY - 0.5) * 2 * usableRadius * 0.7,
          ];
        }

        region.posts.forEach((post, i) => {
          let px: number, py: number;
          if (umapToLocal && post.x_pos != null && post.y_pos != null) {
            [px, py] = umapToLocal(post.x_pos, post.y_pos);
          } else {
            const angle = (i / Math.max(postCount, 1)) * Math.PI * 2;
            const dist = region.radius * 0.3 + (i % 3) * region.radius * 0.15;
            px = Math.cos(angle) * dist;
            py = Math.sin(angle) * dist * 0.7;
          }
          const scale = trafficScale(post.traffic_contribution ?? 0, maxTraffic);

          let veg;
          switch (post.role ?? 'dead_weight') {
            case 'pillar': veg = drawTree(scale); break;
            case 'supporter': veg = drawBush(scale); break;
            case 'competitor': veg = drawVine(scale); break;
            default: veg = drawStump(scale); break;
          }
          veg.x = px;
          veg.y = py;

          // Interaction
          veg.eventMode = 'static';
          veg.cursor = 'pointer';
          veg.on('pointerover', (e: any) => {
            const rect = container.getBoundingClientRect();
            handleHoverPost(post, e.global.x / (app.renderer.resolution) + rect.left - rect.left, e.global.y / (app.renderer.resolution));
          });
          veg.on('pointerout', () => handleHoverPost(null, 0, 0));
          veg.on('pointertap', (e: any) => { e.stopPropagation(); onSelectPost(post); });
          rc.addChild(veg);

          // Record absolute position
          postPositions.set(post.id ?? post.post_id, { x: region.x + px, y: region.y + py });

          // Creature
          let creatureType: string | null = null;
          if (post.role === 'pillar' && (post.trend === 'growing' || post.trend === 'stable')) creatureType = 'bloomling';
          else if (post.trend === 'declining') creatureType = 'rustmite';
          else if ((post.internal_link_score ?? 0) < 0.1 && post.role !== 'pillar') creatureType = 'fogling';

          if (creatureType) {
            const cs = 0.5 + scale * 0.5;
            let creature;
            if (creatureType === 'bloomling') creature = drawBloomling(cs);
            else if (creatureType === 'rustmite') creature = drawRustmite(cs);
            else creature = drawFogling(cs);
            creature.x = px + 16 * cs;
            creature.y = py - 6 * cs;
            creature.eventMode = 'static';
            creature.cursor = 'pointer';
            creature.on('pointertap', (e: any) => { e.stopPropagation(); onSelectPost(post); if (onClickCreature) onClickCreature(post, creatureType!); });
            rc.addChild(creature);
            creatureAnimations.push({ container: creature, type: creatureType, baseY: creature.y, index: i });
          }
        });

        // Label
        const label = new PIXI.Text({
          text: region.label ?? 'Unlabeled',
          style: { fontSize: 12, fill: '#e2e8f0', fontWeight: '600', fontFamily: 'Inter, system-ui, sans-serif' },
        });
        label.anchor.set(0.5, 1);
        label.y = -region.radius * 0.7 - 14;
        rc.addChild(label);

        // Health badge
        const badgeC = new PIXI.Container();
        const badgeBg = new PIXI.Graphics();
        badgeBg.roundRect(-18, -12, 36, 22, 11);
        badgeBg.fill({ color: '#111827' });
        badgeBg.roundRect(-18, -12, 36, 22, 11);
        badgeBg.stroke({ color: scoreColor(region.healthScore), width: 1.5 });
        badgeC.addChild(badgeBg);
        const badgeText = new PIXI.Text({
          text: Math.round(region.healthScore).toString(),
          style: { fontSize: 10, fill: scoreColor(region.healthScore), fontWeight: '700', fontFamily: 'Inter, system-ui, sans-serif' },
        });
        badgeText.anchor.set(0.5, 0.5);
        badgeText.y = -1;
        badgeC.addChild(badgeText);
        badgeC.x = region.radius * 0.7;
        badgeC.y = -region.radius * 0.5;
        rc.addChild(badgeC);

        regionLayer.addChild(rc);
      });
      world.addChild(regionLayer);

      // ── Tanglevines ──
      if (cannPairs.length > 0) {
        const vineLayer = new PIXI.Graphics();
        cannPairs.slice(0, 30).forEach(pair => {
          const posA = postPositions.get(pair.post_a_id);
          const posB = postPositions.get(pair.post_b_id);
          if (!posA || !posB) return;
          const mx = (posA.x + posB.x) / 2 + (Math.random() - 0.5) * 40;
          const my = (posA.y + posB.y) / 2 - 25;
          const intensity = Math.min(1, (pair.cosine_similarity - 0.75) / 0.2);
          const color = intensity > 0.7 ? '#ef4444' : intensity > 0.4 ? '#f97316' : '#eab308';
          vineLayer.moveTo(posA.x, posA.y);
          vineLayer.quadraticCurveTo(mx, my, posB.x, posB.y);
          vineLayer.stroke({ color, width: 1 + intensity * 1.5, alpha: 0.25 + intensity * 0.4, cap: 'round' });
          vineLayer.circle(mx, my, 2 + intensity * 2);
          vineLayer.fill({ color, alpha: (0.25 + intensity * 0.4) * 0.8 });
        });
        world.addChild(vineLayer);
      }

      // ── Overlay effects (grass, rivers, weather, terrain, animals) ──
      if (visuals) {
        // Rivers
        const riverG = new PIXI.Graphics();
        const riverParticles: { fromX: number; fromY: number; cx: number; cy: number; toX: number; toY: number; color: string; i: number; count: number }[] = [];
        const qualityColors: Record<string, string> = { sparkling: '#38bdf8', clear: '#3b82f6', murky: '#78716c', toxic: '#4ade80' };

        (visuals.rivers ?? []).forEach(river => {
          const from = clusterPositions[river.from_cluster_id];
          const to = clusterPositions[river.to_cluster_id];
          if (!from || !to) return;
          const color = qualityColors[river.quality] ?? '#3b82f6';
          const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;
          const dx = to.x - from.x, dy = to.y - from.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const cx = mx + (-dy / dist) * dist * 0.15, cy = my + (dx / dist) * dist * 0.15;
          riverG.moveTo(from.x, from.y); riverG.quadraticCurveTo(cx, cy, to.x, to.y);
          riverG.stroke({ color, width: Math.max(river.width * 1.5, 3), alpha: 0.8, cap: 'round' });
          for (let i = 0; i < Math.min(river.total_links, 8); i++) {
            riverParticles.push({ fromX: from.x, fromY: from.y, cx, cy, toX: to.x, toY: to.y, color, i, count: Math.min(river.total_links, 8) });
          }
        });
        world.addChild(riverG);

        // River particles animation
        const rpContainer = new PIXI.Container();
        const rpGraphics = new PIXI.Graphics();
        rpContainer.addChild(rpGraphics);
        world.addChild(rpContainer);
        updaters.push((time) => {
          rpGraphics.clear();
          riverParticles.forEach(rp => {
            const t = ((time * 0.0003 * (1 + rp.i * 0.1)) + rp.i / rp.count) % 1;
            const u = 1 - t;
            const px = u * u * rp.fromX + 2 * u * t * rp.cx + t * t * rp.toX;
            const py = u * u * rp.fromY + 2 * u * t * rp.cy + t * t * rp.toY;
            rpGraphics.circle(px, py, 3);
            rpGraphics.fill({ color: '#ffffff', alpha: 0.7 });
          });
        });

        // Grass
        for (const [clusterId, grassData] of Object.entries(visuals.grass ?? {})) {
          const cl = clusterPositions[clusterId];
          if (!cl) continue;
          const configs: Record<string, { h: number; c: string; tc: string; sway: number }> = {
            fresh: { h: 10, c: '#22c55e', tc: '#4ade80', sway: 2 },
            maintained: { h: 14, c: '#16a34a', tc: '#22c55e', sway: 3 },
            overgrown: { h: 22, c: '#a3a23a', tc: '#ca8a04', sway: 5 },
            dead: { h: 5, c: '#78716c', tc: '#a8a29e', sway: 0 },
          };
          const cfg = configs[grassData.state] ?? configs.maintained;
          const grassG = new PIXI.Graphics();
          const clumpCount = 40;
          const grassUpdater = (time: number) => {
            grassG.clear();
            for (let i = 0; i < clumpCount; i++) {
              const a = (i / clumpCount) * Math.PI * 2;
              const edge = 0.82 + ((Math.sin(i * 17.3) * 43758.5453) % 1 + 1) % 1 * 0.3;
              const bx = cl.x + Math.cos(a) * cl.radius * edge;
              const by = cl.y + Math.sin(a) * cl.radius * 0.7 * edge;
              const blades = 3 + (i % 3);
              for (let b = 0; b < blades; b++) {
                const spread = (b / blades - 0.5) * 0.8;
                const sway = cfg.sway * Math.sin(time * 0.002 + i * 0.7 + b * 0.4);
                const bh = cfg.h * (0.7 + ((Math.sin(i * 31.1 + b * 13.7) * 43758.5) % 1 + 1) % 1 * 0.6);
                grassG.moveTo(bx, by);
                grassG.quadraticCurveTo(bx + sway * 0.5 + spread * 5, by - bh * 0.6, bx + sway + spread * 8, by - bh);
                grassG.stroke({ color: cfg.c, width: 2, alpha: 0.85, cap: 'round' });
              }
            }
          };
          world.addChild(grassG);
          updaters.push(grassUpdater);
        }

        // Weather
        for (const [clusterId, weatherData] of Object.entries(visuals.weather ?? {})) {
          const cl = clusterPositions[clusterId];
          if (!cl) continue;
          if (weatherData.state === 'sunny') {
            const sunG = new PIXI.Graphics();
            updaters.push((time) => {
              sunG.clear();
              const pulse = 0.8 + Math.sin(time * 0.001) * 0.2;
              sunG.circle(cl.x, cl.y, cl.radius * 0.8);
              sunG.fill({ color: '#fbbf24', alpha: 0.08 * pulse });
              sunG.circle(cl.x, cl.y, cl.radius * 0.4);
              sunG.fill({ color: '#fbbf24', alpha: 0.12 * pulse });
              for (let i = 0; i < 8; i++) {
                const a = (i / 8) * Math.PI * 2 + time * 0.0002;
                sunG.moveTo(cl.x + Math.cos(a) * cl.radius * 0.2, cl.y + Math.sin(a) * cl.radius * 0.14);
                sunG.lineTo(cl.x + Math.cos(a) * cl.radius * 0.55 * pulse, cl.y + Math.sin(a) * cl.radius * 0.4 * pulse);
                sunG.stroke({ color: '#fbbf24', width: 2, alpha: 0.2 * pulse, cap: 'round' });
              }
            });
            world.addChild(sunG);
          } else if (weatherData.state === 'rain' || weatherData.state === 'storm') {
            const rainG = new PIXI.Graphics();
            updaters.push((time) => {
              rainG.clear();
              for (let i = 0; i < 18; i++) {
                const seed = ((Math.sin(i * 47.3) * 10000) % 1 + 1) % 1;
                const dx = seed * cl.radius * 1.2 - cl.radius * 0.6;
                const fall = ((time * 0.003 + i * 0.3) % 1);
                const dy = -cl.radius * 0.4 + fall * cl.radius * 0.8;
                rainG.moveTo(cl.x + dx, cl.y + dy);
                rainG.lineTo(cl.x + dx - 0.5, cl.y + dy + 8);
                rainG.stroke({ color: '#60a5fa', width: 1.5, alpha: 0.6, cap: 'round' });
                if (fall > 0.9) {
                  const sa = (1 - fall) * 10;
                  rainG.circle(cl.x + dx, cl.y + dy + 8, 3 * (1 - sa));
                  rainG.stroke({ color: '#93c5fd', width: 0.8, alpha: sa * 0.5 });
                }
              }
            });
            world.addChild(rainG);
          } else if (weatherData.state === 'fog') {
            const fogG = new PIXI.Graphics();
            updaters.push((time) => {
              fogG.clear();
              for (let i = 0; i < 4; i++) {
                const drift = Math.sin(time * 0.0002 + i * 1.5) * cl.radius * 0.15;
                fogG.ellipse(cl.x + drift, cl.y - cl.radius * 0.2 + i * cl.radius * 0.15, cl.radius * 0.8, cl.radius * 0.2);
                fogG.fill({ color: '#94a3b8', alpha: 0.08 - i * 0.015 });
              }
            });
            world.addChild(fogG);
          }
        }

        // Terrain features
        for (const [clusterId, features] of Object.entries(visuals.terrain_features ?? {})) {
          const cl = clusterPositions[clusterId];
          if (!cl) continue;
          for (const feature of features) {
            if (feature.type === 'mushrooms') {
              const mushG = new PIXI.Graphics();
              updaters.push((time) => {
                mushG.clear();
                for (let i = 0; i < feature.count; i++) {
                  const a = ((Math.sin(i * 29.1 + 13) * 43758.5) % 1 + 1) % 1 * Math.PI * 2;
                  const d = cl.radius * (0.2 + ((Math.sin(i * 43.2) * 43758.5) % 1 + 1) % 1 * 0.6);
                  const mx = cl.x + Math.cos(a) * d;
                  const my = cl.y + Math.sin(a) * d * 0.7;
                  const sz = 6 + ((Math.sin(i * 59.1) * 43758.5) % 1 + 1) % 1 * 4;
                  const wobble = Math.sin(time * 0.002 + i * 1.7) * 1.5;
                  mushG.moveTo(mx, my); mushG.lineTo(mx + wobble, my - sz * 2);
                  mushG.stroke({ color: '#d6d3d1', width: 2.5, cap: 'round' });
                  mushG.ellipse(mx + wobble, my - sz * 2, sz * 1.8, sz);
                  mushG.fill({ color: '#dc2626', alpha: 0.85 });
                  [[- sz * 0.5, -sz * 2.4, sz * 0.2], [sz * 0.4, -sz * 2.2, sz * 0.15], [0, -sz * 2.6, sz * 0.18]].forEach(([dx2, dy2, r2]) => {
                    mushG.circle(mx + wobble + dx2, my + dy2, r2);
                    mushG.fill({ color: '#ffffff', alpha: 0.65 });
                  });
                }
              });
              world.addChild(mushG);
            } else if (feature.type === 'boulders') {
              const bG = new PIXI.Graphics();
              for (let i = 0; i < feature.count; i++) {
                const a = ((Math.sin(i * 37.1 + 7) * 43758.5) % 1 + 1) % 1 * Math.PI * 2;
                const d = cl.radius * (0.3 + ((Math.sin(i * 53.2) * 43758.5) % 1 + 1) % 1 * 0.5);
                const bx = cl.x + Math.cos(a) * d, by = cl.y + Math.sin(a) * d * 0.7;
                const sz = 14 + ((Math.sin(i * 71.3) * 43758.5) % 1 + 1) % 1 * 6;
                bG.ellipse(bx, by, sz, sz * 0.65);
                bG.fill({ color: '#57534e', alpha: 0.8 });
                bG.ellipse(bx - sz * 0.2, by - sz * 0.15, sz * 0.3, sz * 0.2);
                bG.fill({ color: '#a8a29e', alpha: 0.3 });
              }
              world.addChild(bG);
            }
          }
        }

        // Animals
        for (const [clusterId, animalList] of Object.entries(visuals.animals ?? {})) {
          const cl = clusterPositions[clusterId];
          if (!cl) continue;
          for (const animal of animalList) {
            const aG = new PIXI.Graphics();
            if (animal.type === 'birds') {
              updaters.push((time) => {
                aG.clear();
                for (let i = 0; i < animal.count; i++) {
                  const a = (i / animal.count) * Math.PI * 2 + time * 0.0005;
                  const orbit = cl.radius * 1.1 + i * 8;
                  const bx = cl.x + Math.cos(a) * orbit;
                  const by = cl.y - cl.radius * 0.7 + Math.sin(a * 0.5) * 10 - i * 6;
                  const flap = Math.sin(time * 0.005 + i * 2) * 3;
                  aG.moveTo(bx - 5, by + flap); aG.lineTo(bx, by); aG.lineTo(bx + 5, by + flap);
                  aG.stroke({ color: '#1e293b', width: 1.3, alpha: 0.6 });
                }
              });
            } else if (animal.type === 'bees') {
              updaters.push((time) => {
                aG.clear();
                for (let i = 0; i < animal.count; i++) {
                  const t = time * 0.002 + i * 5;
                  const bx = cl.x + Math.sin(t * 1.3) * cl.radius * 0.4 + Math.cos(t * 0.7 + i) * cl.radius * 0.2;
                  const by = cl.y + Math.cos(t * 0.9) * cl.radius * 0.25 - cl.radius * 0.2;
                  aG.circle(bx, by, 2.5);
                  aG.fill({ color: '#fbbf24', alpha: 0.7 });
                  aG.circle(bx, by, 5);
                  aG.fill({ color: '#fbbf24', alpha: 0.08 });
                }
              });
            } else if (animal.type === 'foxes') {
              updaters.push((time) => {
                aG.clear();
                for (let i = 0; i < animal.count; i++) {
                  const ba = (i / animal.count) * Math.PI * 2 + Math.PI * 0.25;
                  const prowl = Math.sin(time * 0.001 + i * 3) * cl.radius * 0.1;
                  const fx = cl.x + Math.cos(ba) * (cl.radius * 0.85 + prowl);
                  const fy = cl.y + Math.sin(ba) * cl.radius * 0.6;
                  aG.poly([{ x: fx - 5, y: fy + 3 }, { x: fx, y: fy - 5 }, { x: fx + 5, y: fy + 3 }]);
                  aG.fill({ color: '#ea580c', alpha: 0.6 });
                  aG.moveTo(fx - 5, fy + 1); aG.quadraticCurveTo(fx - 9, fy - 2, fx - 7, fy + 5);
                  aG.stroke({ color: '#ea580c', width: 1.5, alpha: 0.6 });
                }
              });
            } else if (animal.type === 'deer') {
              updaters.push((time) => {
                aG.clear();
                for (let i = 0; i < animal.count; i++) {
                  const a = (i / animal.count) * Math.PI * 2 + Math.PI * 0.6;
                  const dx = cl.x + Math.cos(a) * cl.radius * 0.5;
                  const dy = cl.y + Math.sin(a) * cl.radius * 0.35;
                  const headDip = Math.sin(time * 0.0015 + i * 2) * 3;
                  aG.ellipse(dx, dy, 6, 4);
                  aG.fill({ color: '#92400e', alpha: 0.55 });
                  aG.moveTo(dx + 4, dy - 2); aG.lineTo(dx + 6, dy - 6 + headDip);
                  aG.stroke({ color: '#92400e', width: 1.5, alpha: 0.55 });
                  aG.circle(dx + 6, dy - 7 + headDip, 2.5);
                  aG.fill({ color: '#92400e', alpha: 0.55 });
                }
              });
            }
            world.addChild(aG);
          }
        }
      }

      // ── Creature animations ──
      updaters.push((time) => {
        creatureAnimations.forEach(ca => {
          if (ca.type === 'bloomling') {
            ca.container.y = ca.baseY + Math.sin(time * 0.003 + ca.index * 0.3) * 3;
          } else if (ca.type === 'rustmite') {
            ca.container.rotation = Math.sin(time * 0.004 + ca.index * 0.5) * 0.07;
          } else if (ca.type === 'fogling') {
            ca.container.y = ca.baseY + Math.sin(time * 0.002 + ca.index * 0.4) * 5;
            ca.container.alpha = 0.25 + Math.sin(time * 0.002 + ca.index * 0.4) * 0.1;
          }
        });
      });

      // ── D3 zoom ──
      const zoomBehavior = d3.zoom<HTMLDivElement, unknown>()
        .scaleExtent([0.2, 8])
        .on('zoom', (event: d3.D3ZoomEvent<HTMLDivElement, unknown>) => {
          world.x = event.transform.x;
          world.y = event.transform.y;
          world.scale.set(event.transform.k);
          if (onViewportChange) onViewportChange({ x: event.transform.x, y: event.transform.y, k: event.transform.k });
        });
      d3.select(container).call(zoomBehavior as any);

      if (navigateRef) {
        navigateRef.current = (worldX, worldY) => {
          d3.select(container).transition().duration(500).call(
            zoomBehavior.transform as any,
            d3.zoomIdentity.translate(width / 2 - worldX, height / 2 - worldY).scale(1),
          );
        };
      }

      // Auto-zoom to selected cluster
      if (zoomedClusterId) {
        const target = regions.find(r => r.id === zoomedClusterId);
        if (target) {
          const scale = Math.min(width, height) / (target.radius * 3);
          d3.select(container).transition().duration(750).call(
            zoomBehavior.transform as any,
            d3.zoomIdentity.translate(width / 2 - target.x * scale, height / 2 - target.y * scale).scale(scale),
          );
        }
      }

      // ── Animation ticker (throttled for performance) ──
      let lastFrame = 0;
      app.ticker.add(() => {
        const time = performance.now();
        // Cap at 30fps for large scenes (50+ clusters)
        if (regions.length > 50 && time - lastFrame < 33) return;
        lastFrame = time;
        for (const update of updaters) update(time);
      });

    })();

    return () => {
      destroyed = true;
      if (pixiApp) {
        const canvas = pixiApp.canvas;
        pixiApp.destroy(true, { children: true });
        if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
        pixiApp = null;
      }
    };
  }, [clusters, zoomedClusterId, cannPairs, visuals, handleHoverPost, onSelectPost, onZoomToCluster, onClickCreature, onPositionsComputed, onViewportChange, navigateRef]);

  return (
    <div ref={containerRef} className="relative h-full w-full landscape-canvas" style={{ touchAction: 'none' }}>
      {tooltip && <LandscapeTooltip data={tooltip.data} x={tooltip.x} y={tooltip.y} />}
      <LegendPanel />
    </div>
  );
}
