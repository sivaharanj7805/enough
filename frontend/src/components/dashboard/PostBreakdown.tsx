'use client';

import { Card } from '@/components/ui/Card';

interface PostBreakdownProps {
  active: number;
  passive: number;
  cannibal: number;
  dead: number;
}

const SEGMENTS = [
  { key: 'active', label: 'Active', color: '#22c55e' },
  { key: 'passive', label: 'Passive', color: '#3b82f6' },
  { key: 'cannibal', label: 'Cannibalistic', color: '#f97316' },
  { key: 'dead', label: 'Dead', color: '#ef4444' },
] as const;

export function PostBreakdown({ active, passive, cannibal, dead }: PostBreakdownProps) {
  const total = active + passive + cannibal + dead;
  const values: Record<string, number> = { active, passive, cannibal, dead };

  return (
    <Card>
      <p className="text-sm font-medium text-brand-text-muted mb-4">Post Breakdown</p>

      {/* Stacked bar */}
      <div className="h-6 flex rounded-full overflow-hidden">
        {SEGMENTS.map((seg) => {
          const pct = total > 0 ? (values[seg.key] / total) * 100 : 0;
          if (pct === 0) return null;
          return (
            <div
              key={seg.key}
              className="transition-all duration-500"
              style={{ width: `${pct}%`, backgroundColor: seg.color }}
            />
          );
        })}
      </div>

      {/* Labels */}
      <div className="mt-4 grid grid-cols-4 gap-4">
        {SEGMENTS.map((seg) => (
          <div key={seg.key} className="text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <div
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: seg.color }}
              />
              <span className="text-xs text-brand-text-muted">{seg.label}</span>
            </div>
            <span className="text-lg font-semibold text-brand-text">{values[seg.key]}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
