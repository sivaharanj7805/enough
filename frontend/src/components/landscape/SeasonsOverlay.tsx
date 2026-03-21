'use client';

import { useEffect, useRef, useMemo } from 'react';
import { Flower2, Sun, Leaf, Snowflake } from 'lucide-react';
import { useSiteHealth } from '@/lib/hooks/useApi';
import { useSite } from '@/lib/hooks/useSite';

export type Season = 'spring' | 'summer' | 'autumn' | 'winter';

const SEASON_CONFIG: Record<Season, {
  label: string;
  icon: typeof Flower2;
  tint: string;
  particleColor: string;
  badgeBg: string;
  badgeText: string;
}> = {
  spring: {
    label: 'Spring',
    icon: Flower2,
    tint: 'rgba(250, 204, 21, 0.06)',
    particleColor: '#fde047',
    badgeBg: 'bg-yellow-500/10 border-yellow-500/20',
    badgeText: 'text-yellow-400',
  },
  summer: {
    label: 'Summer',
    icon: Sun,
    tint: 'rgba(34, 197, 94, 0.05)',
    particleColor: '#4ade80',
    badgeBg: 'bg-green-500/10 border-green-500/20',
    badgeText: 'text-green-400',
  },
  autumn: {
    label: 'Autumn',
    icon: Leaf,
    tint: 'rgba(245, 158, 11, 0.07)',
    particleColor: '#f59e0b',
    badgeBg: 'bg-amber-500/10 border-amber-500/20',
    badgeText: 'text-amber-400',
  },
  winter: {
    label: 'Winter',
    icon: Snowflake,
    tint: 'rgba(96, 165, 250, 0.06)',
    particleColor: '#93c5fd',
    badgeBg: 'bg-blue-500/10 border-blue-500/20',
    badgeText: 'text-blue-400',
  },
};

export function determineSeason(healthScore: number, trend30d: number | null): Season {
  const delta = trend30d ?? 0;

  if (delta > 5) return 'spring';
  if (delta >= 0 && healthScore > 70) return 'summer';
  if (delta < -10 || healthScore < 30) return 'winter';
  if (delta < 0) return 'autumn';

  return 'summer';
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
  rotation: number;
  rotationSpeed: number;
}

function createParticles(season: Season, width: number, height: number): Particle[] {
  const count = season === 'winter' ? 40 : season === 'autumn' ? 25 : season === 'spring' ? 20 : 10;
  return Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * (season === 'winter' ? 0.8 : 0.3),
    vy: season === 'autumn' ? 0.3 + Math.random() * 0.5 : season === 'winter' ? 0.4 + Math.random() * 0.3 : (Math.random() - 0.5) * 0.2,
    size: season === 'winter' ? 2 + Math.random() * 3 : season === 'autumn' ? 4 + Math.random() * 4 : 2 + Math.random() * 2,
    opacity: 0.3 + Math.random() * 0.5,
    rotation: Math.random() * 360,
    rotationSpeed: (Math.random() - 0.5) * 2,
  }));
}

export function SeasonsOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const particlesRef = useRef<Particle[]>([]);
  const { currentSite } = useSite();
  const { data: health } = useSiteHealth(currentSite?.id ?? null);

  const season = useMemo(() => {
    if (!health) return 'summer' as Season;
    const trend30d = health.trends?.['30d'] ?? null;
    return determineSeason(health.content_health_score, trend30d);
  }, [health]);

  const config = SEASON_CONFIG[season];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
      particlesRef.current = createParticles(season, canvas.width, canvas.height);
    };

    resize();
    window.addEventListener('resize', resize);

    const draw = () => {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Tint overlay
      ctx.fillStyle = config.tint;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Summer sun glow
      if (season === 'summer') {
        const sunGrad = ctx.createRadialGradient(
          canvas.width - 60, 60, 5,
          canvas.width - 60, 60, 120
        );
        sunGrad.addColorStop(0, 'rgba(250, 204, 21, 0.08)');
        sunGrad.addColorStop(1, 'rgba(250, 204, 21, 0)');
        ctx.fillStyle = sunGrad;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }

      // Draw particles
      particlesRef.current.forEach((p) => {
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.globalAlpha = p.opacity;

        if (season === 'winter') {
          // Snowflakes — simple star
          ctx.fillStyle = config.particleColor;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const angle = (i / 6) * Math.PI * 2;
            ctx.moveTo(0, 0);
            ctx.lineTo(Math.cos(angle) * p.size, Math.sin(angle) * p.size);
          }
          ctx.strokeStyle = config.particleColor;
          ctx.lineWidth = 0.5;
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(0, 0, p.size * 0.3, 0, Math.PI * 2);
          ctx.fill();
        } else if (season === 'autumn') {
          // Falling leaves — ellipse
          ctx.fillStyle = Math.random() > 0.5 ? '#f59e0b' : '#ea580c';
          ctx.beginPath();
          ctx.ellipse(0, 0, p.size, p.size * 0.6, 0, 0, Math.PI * 2);
          ctx.fill();
        } else if (season === 'spring') {
          // Pollen dots
          ctx.fillStyle = config.particleColor;
          ctx.beginPath();
          ctx.arc(0, 0, p.size, 0, Math.PI * 2);
          ctx.fill();
        } else {
          // Summer sparkles
          ctx.fillStyle = config.particleColor;
          ctx.beginPath();
          ctx.arc(0, 0, p.size * 0.5, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.restore();

        // Update position
        p.x += p.vx;
        p.y += p.vy;
        p.rotation += p.rotationSpeed;

        // Wrap around
        if (p.y > canvas.height + 10) { p.y = -10; p.x = Math.random() * canvas.width; }
        if (p.y < -10) { p.y = canvas.height + 10; }
        if (p.x > canvas.width + 10) p.x = -10;
        if (p.x < -10) p.x = canvas.width + 10;
      });

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [season, config]);

  const Icon = config.icon;

  return (
    <>
      {/* Particle overlay canvas */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none z-[5]"
        aria-hidden="true"
      />

      {/* Season indicator badge */}
      <div
        className={`absolute top-4 right-4 z-10 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border backdrop-blur-sm ${config.badgeBg}`}
      >
        <Icon size={12} className={config.badgeText} />
        <span className={`text-xs font-medium ${config.badgeText}`}>{config.label}</span>
      </div>
    </>
  );
}
