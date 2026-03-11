'use client';

import { Card } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { TREND_ICONS, TREND_COLORS, type Trend } from '@/lib/constants';

interface EfficiencyRatioProps {
  ratio: number;
  trend: Trend;
}

export function EfficiencyRatio({ ratio, trend }: EfficiencyRatioProps) {
  const color = ratio >= 50 ? '#22c55e' : ratio >= 30 ? '#eab308' : '#ef4444';

  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-brand-text-muted">Content Efficiency</p>
        <span
          className="text-sm font-medium"
          style={{ color: TREND_COLORS[trend] }}
        >
          {TREND_ICONS[trend]}
        </span>
      </div>
      <div className="mt-2">
        <span className="text-4xl font-bold" style={{ color }}>
          {ratio}
        </span>
        <span className="text-lg text-brand-text-muted">%</span>
      </div>
      <div className="mt-3">
        <ProgressBar value={ratio} color={color} />
        <div className="mt-1 flex justify-between text-xs text-brand-text-muted">
          <span>0%</span>
          <span className="text-brand-accent">Target: 50%</span>
          <span>100%</span>
        </div>
      </div>
    </Card>
  );
}
