'use client';

import { useSite } from '@/lib/hooks/useSite';
import { useConsolidationPlans } from '@/lib/hooks/useApi';
import { QuickWinBanner } from '@/components/consolidation/QuickWinBanner';
import { PlanCard } from '@/components/consolidation/PlanCard';
import { Spinner } from '@/components/ui/Spinner';

export default function ConsolidationPage() {
  const { currentSite } = useSite();
  const { data: plans, isLoading, error } = useConsolidationPlans(currentSite?.id ?? null);

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
          <p className="text-2xl mb-2">🔧</p>
          <p className="text-lg font-medium text-brand-text">No Consolidation Plans</p>
          <p className="text-sm text-brand-text-muted mt-1">
            Your ecosystem is healthy — no consolidation opportunities detected.
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

      {otherPlans.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-brand-text-muted mb-4">
            All Consolidation Opportunities
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {otherPlans.map((plan) => (
              <PlanCard key={plan.id} plan={plan} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
