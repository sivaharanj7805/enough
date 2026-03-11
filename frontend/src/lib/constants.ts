export type EcosystemState = 'forest' | 'swamp' | 'desert' | 'seedbed' | 'meadow';
export type PostRole = 'pillar' | 'supporter' | 'competitor' | 'dead_weight';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type Trend = 'growing' | 'stable' | 'declining';

export const ECOSYSTEM_COLORS: Record<EcosystemState, { bg: string; border: string; label: string }> = {
  forest: { bg: '#1a4731', border: '#2d6b4f', label: 'Forest 🌲' },
  swamp: { bg: '#2d3a1f', border: '#4a5a2f', label: 'Swamp 🪴' },
  desert: { bg: '#8b7355', border: '#a6896a', label: 'Desert 🏜️' },
  seedbed: { bg: '#2d5a27', border: '#3d7a34', label: 'Seedbed 🌱' },
  meadow: { bg: '#3d6b3d', border: '#4d8b4d', label: 'Meadow 🌻' },
};

export const ROLE_COLORS: Record<PostRole, string> = {
  pillar: '#22c55e',
  supporter: '#3b82f6',
  competitor: '#f97316',
  dead_weight: '#6b7280',
};

export const ROLE_LABELS: Record<PostRole, string> = {
  pillar: 'Pillar',
  supporter: 'Supporter',
  competitor: 'Competitor',
  dead_weight: 'Dead Weight',
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#6b7280',
};

export const TREND_ICONS: Record<Trend, string> = {
  growing: '↑',
  stable: '→',
  declining: '↓',
};

export const TREND_COLORS: Record<Trend, string> = {
  growing: '#22c55e',
  stable: '#eab308',
  declining: '#ef4444',
};

export const NAV_ITEMS = [
  { href: '/landscape', label: 'Landscape', icon: 'Map' as const },
  { href: '/cannibalization', label: 'Cannibalization', icon: 'Network' as const },
  { href: '/oracle', label: 'Oracle', icon: 'Sparkles' as const },
  { href: '/dashboard', label: 'Dashboard', icon: 'BarChart3' as const },
  { href: '/consolidation', label: 'Consolidation', icon: 'Wrench' as const },
] as const;
