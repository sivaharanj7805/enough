'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useConsolidationPlans, useSubscription } from '@/lib/hooks/useApi';
import { QuickWinBanner } from '@/components/consolidation/QuickWinBanner';
import { PlanCard } from '@/components/consolidation/PlanCard';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { Lock, ArrowRight, BarChart3 } from 'lucide-react';

export default function ConsolidationPage() {
  const { currentSite } = useSite();
  const { data: plans, isLoading, error } = useConsolidationPlans(currentSite?.id ?? null);
  const { data: subscription } = useSubscription();

  const isGrowthTier = subscription?.tier === 'growth';

  // Track which plans are "completed" (heuristic: plans with 0 merge candidates)
  const completedPlanIds = useMemo(() => {
    if (!plans) return new Set<string>();
    return new Set(
      plans
        .filter((p) => p.merge_candidates_count === 0 && p.dead_weight_count === 0)
        .map((p) => p.cluster_id)
    );
  }, [plans]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-brand-text-muted">Failed to load consolidation plans</p>
          <p className="text-xs text-red-400 mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!plans || plans.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-lg font-medium text-brand-text">No Consolidation Plans</p>
          <p className="text-sm text-brand-text-muted mt-1">
            Your ecosystem is healthy -- no consolidation opportunities detected.
          </p>
        </div>
      </div>
    );
  }

  const quickWin = plans.find((p) => p.is_quick_win);
  const otherPlans = plans.filter((p) => !p.is_quick_win);

  return (
    <div className="space-y-6">
      {quickWin && <QuickWinBanner plan={quickWin} />}

      {/* Tier-based Gating Banner */}
      {isGrowthTier && (
        <Card className="!p-4 border-amber-500/30 bg-amber-500/5">
          <div className="flex items-center gap-4">
            <div className="rounded-lg bg-amber-500/10 p-3 shrink-0">
              <Lock size={20} className="text-amber-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-brand-text">
                Upgrade to Scale for AI-Powered Draft Generation
              </p>
              <p className="text-xs text-brand-text-muted mt-1">
                Growth tier users can view consolidation plans, but generating AI drafts requires the Scale tier.
              </p>
            </div>
            <Link
              href="/settings/billing"
              className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600 transition-colors shrink-0"
            >
              Upgrade to Scale
              <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {otherPlans.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-brand-text-muted mb-4">
            All Consolidation Opportunities
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {otherPlans.map((plan) => (
              <div key={plan.cluster_id} className="relative">
                <PlanCard plan={plan} />
                {/* Impact Tracking Link for completed plans */}
                {completedPlanIds.has(plan.cluster_id) && (
                  <div className="mt-2 px-1">
                    <Link
                      href={`/impact/${plan.cluster_id}`}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-accent hover:text-brand-accent-hover transition-colors"
                    >
                      <BarChart3 size={12} />
                      View Impact
                      <ArrowRight size={12} />
                    </Link>
                  </div>
                )}
                {/* Tier gating overlay for Generate Draft */}
                {isGrowthTier && (
                  <div className="absolute bottom-12 left-4 right-4">
                    <div className="flex items-center gap-1.5 text-xs text-amber-400">
                      <Lock size={10} />
                      <span>Scale tier required for draft generation</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
