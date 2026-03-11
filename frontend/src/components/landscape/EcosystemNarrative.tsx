'use client';

import { TreePine, Droplets, Sun, Sprout, Flower2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { useClusterNarrative } from '@/lib/hooks/useApi';
import type { EcosystemState } from '@/lib/constants';

const STATE_CONFIG: Record<
  EcosystemState,
  { icon: typeof TreePine; color: string; glowColor: string; label: string }
> = {
  forest: { icon: TreePine, color: 'text-emerald-400', glowColor: '#22c55e', label: 'Forest' },
  swamp: { icon: Droplets, color: 'text-amber-400', glowColor: '#f59e0b', label: 'Swamp' },
  desert: { icon: Sun, color: 'text-orange-400', glowColor: '#f97316', label: 'Desert' },
  seedbed: { icon: Sprout, color: 'text-lime-400', glowColor: '#84cc16', label: 'Seedbed' },
  meadow: { icon: Flower2, color: 'text-green-400', glowColor: '#4ade80', label: 'Meadow' },
};

interface EcosystemNarrativeProps {
  siteId: string;
  clusterId: string;
  ecosystemState: EcosystemState | null;
  clusterLabel: string | null;
}

export function EcosystemNarrative({
  siteId,
  clusterId,
  ecosystemState,
  clusterLabel,
}: EcosystemNarrativeProps) {
  const { data: narrative, isLoading, error } = useClusterNarrative(siteId, clusterId);

  const state = ecosystemState ?? 'meadow';
  const config = STATE_CONFIG[state];
  const Icon = config.icon;

  if (isLoading) {
    return (
      <Card>
        <div className="flex items-center justify-center py-4">
          <Spinner size="sm" />
          <span className="ml-2 text-sm text-brand-text-muted">Loading narrative...</span>
        </div>
      </Card>
    );
  }

  if (error || !narrative) {
    return null; // Silently hide if no narrative available
  }

  return (
    <Card glow glowColor={config.glowColor}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 shrink-0 ${config.color}`}>
          <Icon size={20} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">
              Ecosystem Voice
            </span>
            <span className={`text-xs font-medium ${config.color}`}>
              {config.label}
            </span>
            {clusterLabel && (
              <span className="text-xs text-brand-text-muted">
                · {clusterLabel}
              </span>
            )}
          </div>
          <blockquote className="text-sm text-brand-text leading-relaxed italic border-l-2 border-brand-border pl-3">
            {narrative.narrative_text}
          </blockquote>
          <p className="mt-2 text-xs text-brand-text-muted">
            Generated {new Date(narrative.generated_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </Card>
  );
}
