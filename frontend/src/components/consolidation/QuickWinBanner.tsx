'use client';

import Link from 'next/link';
import { Zap, ArrowRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { ConsolidationPlan } from '@/lib/types';

interface QuickWinBannerProps {
  plan: ConsolidationPlan;
}

export function QuickWinBanner({ plan }: QuickWinBannerProps) {
  return (
    <Card glow glowColor="#22c55e">
      <div className="flex items-center gap-4">
        <div className="rounded-lg bg-brand-accent/10 p-3">
          <Zap size={24} className="text-brand-accent" />
        </div>
        <div className="flex-1">
          <p className="text-xs font-medium text-brand-accent uppercase tracking-wide">
            This Week&apos;s Quick Win
          </p>
          <h3 className="text-lg font-semibold text-brand-text mt-1">
            Consolidate: {plan.cluster_label}
          </h3>
          <p className="text-sm text-brand-text-muted mt-1">
            {plan.merge_candidates_count} posts to merge · {plan.dead_weight_count} to remove ·{' '}
            Est. +{plan.estimated_traffic_recovery.toLocaleString()} traffic recovery
          </p>
        </div>
        <Link
          href={`/consolidation/${plan.cluster_id}`}
          className="flex items-center gap-2 rounded-lg bg-brand-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-accent-hover transition-colors"
        >
          Start Consolidation
          <ArrowRight size={16} />
        </Link>
      </div>
    </Card>
  );
}
