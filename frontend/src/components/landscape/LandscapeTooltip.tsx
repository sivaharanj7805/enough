'use client';

import { ROLE_LABELS, TREND_ICONS, TREND_COLORS, type PostRole, type Trend } from '@/lib/constants';

interface TooltipData {
  title: string;
  url: string;
  traffic: number;
  healthScore: number;
  role: PostRole;
  trend: Trend;
}

interface LandscapeTooltipProps {
  data: TooltipData;
  x: number;
  y: number;
}

export function LandscapeTooltip({ data, x, y }: LandscapeTooltipProps) {
  return (
    <div
      className="landscape-tooltip"
      style={{
        left: x + 15,
        top: y - 10,
      }}
    >
      <div className="rounded-xl border border-brand-border bg-brand-surface/95 backdrop-blur-sm p-3 shadow-2xl max-w-xs">
        <p className="text-sm font-semibold text-brand-text truncate">{data.title}</p>
        <p className="text-xs text-brand-text-muted truncate mt-0.5">{data.url}</p>

        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
          <div className="text-xs text-brand-text-muted">
            Role: <span className="text-brand-text">{ROLE_LABELS[data.role]}</span>
          </div>
          <div className="text-xs text-brand-text-muted">
            Health: <span className="text-brand-text font-mono">{data.healthScore}</span>
          </div>
          <div className="text-xs text-brand-text-muted">
            Traffic: <span className="text-brand-text font-mono">{data.traffic.toLocaleString()}</span>
          </div>
          <div className="text-xs text-brand-text-muted">
            Trend:{' '}
            <span className="font-medium" style={{ color: TREND_COLORS[data.trend] }}>
              {TREND_ICONS[data.trend]}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
