'use client';

import { Card } from '@/components/ui/Card';
import type { ImpactCardResponse } from '@/lib/types/phase5';
import { ArrowUpRight, ArrowDownRight, Link2, FileStack } from 'lucide-react';

interface ImpactCardProps {
  card: ImpactCardResponse;
  onCopy?: () => void;
}

export function ImpactCard({ card, onCopy }: ImpactCardProps) {
  const isPositive = card.traffic_change >= 0;

  const handleCopy = () => {
    navigator.clipboard.writeText(card.summary);
    onCopy?.();
  };

  return (
    <Card className="relative overflow-hidden">
      {/* Accent bar */}
      <div
        className="absolute left-0 top-0 h-full w-1"
        style={{ backgroundColor: isPositive ? '#22c55e' : '#ef4444' }}
      />

      <div className="pl-4">
        <h3 className="text-lg font-semibold text-brand-text mb-2">
          {card.headline}
        </h3>

        <p className="text-sm text-brand-text-muted mb-4 truncate">
          {card.pillar_url}
        </p>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="flex items-center gap-2">
            {isPositive ? (
              <ArrowUpRight size={20} className="text-green-400" />
            ) : (
              <ArrowDownRight size={20} className="text-red-400" />
            )}
            <div>
              <div className="text-xs text-brand-text-muted">Traffic Change</div>
              <div className={`text-lg font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{card.traffic_change_pct.toFixed(1)}%
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <FileStack size={20} className="text-brand-text-muted" />
            <div>
              <div className="text-xs text-brand-text-muted">Posts Consolidated</div>
              <div className="text-lg font-bold text-brand-text">{card.posts_consolidated}</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link2 size={20} className="text-brand-text-muted" />
            <div>
              <div className="text-xs text-brand-text-muted">Redirects Working</div>
              <div className="text-lg font-bold text-brand-text">{card.redirects_working}</div>
            </div>
          </div>

          <div>
            <div className="text-xs text-brand-text-muted">Days Since</div>
            <div className="text-lg font-bold text-brand-text">{card.days_since}</div>
          </div>
        </div>

        <p className="text-sm text-brand-text-muted mb-4">{card.summary}</p>

        <div className="flex gap-2">
          <button
            onClick={handleCopy}
            className="text-xs px-3 py-1.5 rounded-lg bg-brand-surface-hover text-brand-text hover:bg-brand-border transition-colors"
          >
            Copy Summary
          </button>
        </div>
      </div>
    </Card>
  );
}
