'use client';

import { Card } from '@/components/ui/Card';
import { TREND_ICONS, TREND_COLORS, type Trend } from '@/lib/constants';

interface HealthScoreCardProps {
  title: string;
  value: number;
  suffix?: string;
  trend: Trend;
  description?: string;
}

function scoreColor(value: number): string {
  if (value >= 70) return '#22c55e';
  if (value >= 40) return '#eab308';
  return '#ef4444';
}

export function HealthScoreCard({ title, value, suffix = '', trend, description }: HealthScoreCardProps) {
  const color = scoreColor(value);

  return (
    <Card>
      <p className="text-sm font-medium text-brand-text-muted">{title}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-4xl font-bold" style={{ color }}>
          {value}
        </span>
        {suffix && <span className="text-lg text-brand-text-muted">{suffix}</span>}
        <span
          className="ml-auto text-sm font-medium"
          style={{ color: TREND_COLORS[trend] }}
        >
          {TREND_ICONS[trend]}
        </span>
      </div>
      {description && (
        <p className="mt-2 text-xs text-brand-text-muted">{description}</p>
      )}
    </Card>
  );
}
