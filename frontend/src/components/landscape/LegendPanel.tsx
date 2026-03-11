'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { ECOSYSTEM_COLORS, type EcosystemState } from '@/lib/constants';

const VEGETATION_LEGEND = [
  { label: 'Pillar (Tree)', color: '#22c55e', desc: 'Core content, high traffic' },
  { label: 'Supporter (Bush)', color: '#3b82f6', desc: 'Supporting content' },
  { label: 'Competitor (Vine)', color: '#f97316', desc: 'Cannibalizing content' },
  { label: 'Dead Weight (Stump)', color: '#6b7280', desc: 'No traffic, no value' },
  { label: 'New (Seedling)', color: '#86efac', desc: 'Published ≤30 days ago' },
];

export function LegendPanel() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute bottom-4 right-4 z-10 w-64 rounded-xl border border-brand-border bg-brand-surface/95 backdrop-blur-sm shadow-xl">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between px-4 py-3 text-xs font-semibold text-brand-text-muted uppercase tracking-wide"
      >
        Legend
        {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-4">
          {/* Vegetation */}
          <div>
            <p className="text-xs font-medium text-brand-text-muted mb-2">Vegetation</p>
            <div className="space-y-1.5">
              {VEGETATION_LEGEND.map((item) => (
                <div key={item.label} className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-sm shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-xs text-brand-text">{item.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Ground colors */}
          <div>
            <p className="text-xs font-medium text-brand-text-muted mb-2">Ground State</p>
            <div className="space-y-1.5">
              {(Object.entries(ECOSYSTEM_COLORS) as [EcosystemState, typeof ECOSYSTEM_COLORS[EcosystemState]][]).map(
                ([key, val]) => (
                  <div key={key} className="flex items-center gap-2">
                    <div
                      className="h-3 w-3 rounded-sm shrink-0"
                      style={{ backgroundColor: val.bg }}
                    />
                    <span className="text-xs text-brand-text">{val.label}</span>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
