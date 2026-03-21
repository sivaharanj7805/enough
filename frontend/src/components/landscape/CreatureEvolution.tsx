'use client';

import { useMemo } from 'react';
import type { PostHealth } from '@/lib/types';
import type { CreatureType } from './VegetationRenderer';

export type CreatureLevel = 1 | 2 | 3;

export interface CreatureEvolutionData {
  creature: NonNullable<CreatureType>;
  level: CreatureLevel;
  label: string;
  description: string;
  scale: number;
  glowRadius: number;
  glowOpacity: number;
  hasParticles: boolean;
}

/**
 * Determine the bloomling evolution level based on traffic growth patterns.
 */
function getBloomlingLevel(post: PostHealth): CreatureLevel {
  const traffic = post.traffic_contribution ?? 0;
  const score = post.composite_score ?? 0;
  if (traffic > 0.05 && score >= 80) return 3;
  if (traffic > 0.02 && score >= 65) return 2;
  return 1;
}

/**
 * Determine the rustmite evolution level based on decay severity.
 */
function getRustmiteLevel(post: PostHealth): CreatureLevel {
  const score = post.composite_score ?? 0;
  const linkScore = post.internal_link_score ?? 0;
  if (score < 20 && linkScore < 0.01) return 3;
  if (score < 35) return 2;
  return 1;
}

/**
 * Determine the fogling evolution level based on orphan severity.
 */
function getFoglingLevel(post: PostHealth): CreatureLevel {
  const score = post.composite_score ?? 0;
  const linkScore = post.internal_link_score ?? 0;
  const traffic = post.traffic_contribution ?? 0;
  if (linkScore < 0.01 && traffic < 0.001 && score < 20) return 3;
  if (linkScore < 0.01 && (traffic < 0.005 || score < 30)) return 2;
  return 1;
}

const LEVEL_LABELS: Record<NonNullable<CreatureType>, Record<CreatureLevel, { label: string; desc: string }>> = {
  bloomling: {
    1: { label: 'Budding Bloomling', desc: 'Early growth detected — this post is gaining traction.' },
    2: { label: 'Thriving Bloomling', desc: 'Strong traffic growth (20-50%) — keep nurturing this content.' },
    3: { label: 'Radiant Bloomling', desc: 'Outstanding growth (50%+) — this is your star performer!' },
  },
  rustmite: {
    1: { label: 'Minor Rustmite', desc: 'Early decay signs — content freshness is declining.' },
    2: { label: 'Active Rustmite', desc: 'Moderate decay — rankings are slipping, update needed.' },
    3: { label: 'Critical Rustmite', desc: 'Severe decay — content is critically outdated and losing all traffic.' },
  },
  fogling: {
    1: { label: 'Faint Fogling', desc: 'This post has few internal links pointing to it.' },
    2: { label: 'Drifting Fogling', desc: 'Orphaned post with declining metrics — needs interlinking.' },
    3: { label: 'Lost Fogling', desc: 'Completely orphaned — zero links, no traffic, invisible to search engines.' },
  },
};

/**
 * Compute creature evolution data for a given post and creature type.
 */
export function getCreatureEvolution(
  post: PostHealth,
  creature: NonNullable<CreatureType>
): CreatureEvolutionData {
  let level: CreatureLevel;

  switch (creature) {
    case 'bloomling':
      level = getBloomlingLevel(post);
      break;
    case 'rustmite':
      level = getRustmiteLevel(post);
      break;
    case 'fogling':
      level = getFoglingLevel(post);
      break;
  }

  const levelInfo = LEVEL_LABELS[creature][level];

  return {
    creature,
    level,
    label: levelInfo.label,
    description: levelInfo.desc,
    scale: level === 1 ? 0.7 : level === 2 ? 1.0 : 1.4,
    glowRadius: level === 1 ? 0 : level === 2 ? 8 : 16,
    glowOpacity: level === 1 ? 0 : level === 2 ? 0.15 : 0.35,
    hasParticles: level === 3,
  };
}

/**
 * Get SVG visual modifications for a creature level.
 * Returns D3-compatible attributes for drawing.
 */
export function getCreatureLevelVisuals(evolution: CreatureEvolutionData) {
  const CREATURE_GLOW_COLORS: Record<NonNullable<CreatureType>, string> = {
    bloomling: '#22c55e',
    rustmite: '#f97316',
    fogling: '#94a3b8',
  };

  return {
    scale: evolution.scale,
    glowColor: CREATURE_GLOW_COLORS[evolution.creature],
    glowRadius: evolution.glowRadius,
    glowOpacity: evolution.glowOpacity,
    hasParticles: evolution.hasParticles,
    particleCount: evolution.hasParticles ? 5 : 0,
  };
}

/**
 * CreatureEvolutionTooltip — shows creature level info when hovering.
 */
export function CreatureEvolutionTooltip({
  post,
  creature,
  x,
  y,
}: {
  post: PostHealth;
  creature: NonNullable<CreatureType>;
  x: number;
  y: number;
}) {
  const evolution = useMemo(() => getCreatureEvolution(post, creature), [post, creature]);

  const levelStars = Array.from({ length: 3 }, (_, i) => (
    <span
      key={i}
      className={`inline-block w-1.5 h-1.5 rounded-full ${
        i < evolution.level ? 'bg-current' : 'bg-[#334155]'
      }`}
    />
  ));

  const creatureColors: Record<NonNullable<CreatureType>, string> = {
    bloomling: 'text-green-400',
    rustmite: 'text-orange-400',
    fogling: 'text-slate-400',
  };

  return (
    <div
      className="absolute z-50 pointer-events-none"
      style={{ left: x + 12, top: y - 8, maxWidth: 220 }}
    >
      <div className="rounded-lg bg-[#1e293b] border border-[#334155] p-3 shadow-lg">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-semibold ${creatureColors[creature]}`}>
            {evolution.label}
          </span>
          <div className={`flex gap-0.5 ${creatureColors[creature]}`}>
            {levelStars}
          </div>
        </div>
        <p className="text-[11px] text-[#94a3b8] leading-snug">{evolution.description}</p>
      </div>
    </div>
  );
}
