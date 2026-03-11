'use client';

import type { ImpactSnapshotResponse } from '@/lib/types/phase5';
import { CheckCircle2, Circle } from 'lucide-react';

interface ImpactTimelineProps {
  snapshots: ImpactSnapshotResponse[];
  daysSince: number;
}

const MILESTONES = [
  { key: '30d', label: '30 Days', days: 30 },
  { key: '60d', label: '60 Days', days: 60 },
  { key: '90d', label: '90 Days', days: 90 },
] as const;

export function ImpactTimeline({ snapshots, daysSince }: ImpactTimelineProps) {
  const snapshotMap = new Map(
    snapshots
      .filter((s) => s.milestone !== null)
      .map((s) => [s.milestone, s])
  );

  return (
    <div className="relative">
      {/* Progress bar background */}
      <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-brand-border" />

      <div className="space-y-8">
        {/* Start */}
        <div className="flex items-start gap-4">
          <div className="relative z-10 flex h-8 w-8 items-center justify-center rounded-full bg-brand-accent">
            <CheckCircle2 size={16} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-medium text-brand-text">Consolidation Started</div>
            <div className="text-xs text-brand-text-muted">Day 0 — Baseline captured</div>
          </div>
        </div>

        {/* Milestones */}
        {MILESTONES.map((milestone) => {
          const snapshot = snapshotMap.get(milestone.key);
          const reached = daysSince >= milestone.days;
          const isNext = !reached && daysSince < milestone.days;

          return (
            <div key={milestone.key} className="flex items-start gap-4">
              <div
                className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full ${
                  snapshot
                    ? 'bg-brand-accent'
                    : reached
                    ? 'bg-brand-accent/50'
                    : isNext
                    ? 'bg-brand-surface-hover border-2 border-brand-accent/50'
                    : 'bg-brand-surface-hover border border-brand-border'
                }`}
              >
                {snapshot ? (
                  <CheckCircle2 size={16} className="text-white" />
                ) : (
                  <Circle size={16} className={reached ? 'text-white' : 'text-brand-text-muted'} />
                )}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-brand-text">{milestone.label}</div>
                {snapshot ? (
                  <div className="mt-1 rounded-lg bg-brand-surface p-3 border border-brand-border">
                    <div className="grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-brand-text-muted">Traffic</span>
                        <div className="font-medium text-brand-text">{snapshot.traffic.toLocaleString()}</div>
                      </div>
                      <div>
                        <span className="text-brand-text-muted">Avg Position</span>
                        <div className="font-medium text-brand-text">
                          {snapshot.avg_position?.toFixed(1) ?? '—'}
                        </div>
                      </div>
                      <div>
                        <span className="text-brand-text-muted">Redirects OK</span>
                        <div className="font-medium text-brand-text">{snapshot.redirects_working}</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-brand-text-muted">
                    {reached ? 'Reached — no snapshot recorded' : `${milestone.days - daysSince} days remaining`}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
