'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/ProgressBar';
import type { ConsolidationPlan } from '@/lib/types';

interface PlanCardProps {
  plan: ConsolidationPlan;
}

export function PlanCard({ plan }: PlanCardProps) {
  return (
    <Card className="hover:border-brand-border-hover transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-sm font-semibold text-brand-text">{plan.cluster_label}</h3>
        <span className="text-xs text-brand-text-muted">
          Priority: {plan.priority_score.toFixed(0)}
        </span>
      </div>

      <ProgressBar value={plan.priority_score} color="#22c55e" className="mb-3" />

      <div className="space-y-1.5 text-sm">
        <p className="text-brand-text-muted">
          Pillar: <span className="text-brand-text">{plan.pillar_post_title}</span>
        </p>
        <p className="text-brand-text-muted">
          {plan.merge_count} posts to merge · {plan.redirect_count} to redirect
        </p>
        <p className="text-brand-accent text-xs font-medium">
          Est. +{plan.estimated_traffic_recovery.toLocaleString()} traffic recovery
        </p>
      </div>

      <Link
        href={`/consolidation/${plan.cluster_id}`}
        className="mt-4 flex items-center gap-1 text-sm font-medium text-brand-accent hover:underline"
      >
        View Plan
        <ArrowRight size={14} />
      </Link>
    </Card>
  );
}
