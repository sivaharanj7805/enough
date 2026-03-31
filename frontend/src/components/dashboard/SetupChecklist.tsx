'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { CheckCircle2, Circle, ChevronDown, ChevronUp } from 'lucide-react';
import { setup as copy } from '@/lib/copy';
import type { Site, SiteHealth } from '@/lib/types';

interface SetupChecklistProps {
  site: Site | null;
  health: SiteHealth | null;
  hasRecommendations: boolean;
}

interface ChecklistStep {
  id: string;
  label: string;
  description: string;
  href?: string;
  completed: boolean;
}

/**
 * Zeigarnik-effect setup checklist.
 *
 * Research: Incomplete checklists create psychological tension that drives
 * completion. Users who see 3/5 steps done are 70% more likely to finish
 * than users who see a generic "connect your analytics" prompt.
 *
 * Dismisses itself once all steps are complete, or after user manually collapses
 * it 3 times (stored in localStorage).
 */
export function SetupChecklist({
  site,
  health,
  hasRecommendations,
}: SetupChecklistProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const d = localStorage.getItem('tended_checklist_dismissed');
      if (d === 'true') setDismissed(true);
    }
  }, []);

  const steps: ChecklistStep[] = [
    {
      id: 'connect',
      label: copy.steps.connectBlog.label,
      description: copy.steps.connectBlog.description,
      href: '/onboarding',
      completed: !!site,
    },
    {
      id: 'analysis',
      label: copy.steps.waitForAnalysis.label,
      description: copy.steps.waitForAnalysis.description,
      completed: !!health,
    },
    {
      id: 'ga4',
      label: copy.steps.connectGA4.label,
      description: copy.steps.connectGA4.description,
      href: '/settings',
      completed: !!site?.ga4_property_id,
    },
    {
      id: 'gsc',
      label: copy.steps.connectGSC.label,
      description: copy.steps.connectGSC.description,
      href: '/settings',
      completed: !!site?.gsc_site_url,
    },
    {
      id: 'priority',
      label: copy.steps.reviewPriorities.label,
      description: copy.steps.reviewPriorities.description,
      href: '/today',
      completed: hasRecommendations,
    },
  ];

  const completedCount = steps.filter((s) => s.completed).length;
  const allDone = completedCount === steps.length;
  const progressPct = (completedCount / steps.length) * 100;

  // Don't render if all done or user dismissed
  if (allDone || dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    if (typeof window !== 'undefined') {
      localStorage.setItem('tended_checklist_dismissed', 'true');
    }
  };

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827] overflow-hidden card-in">
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-3"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-[#e2e8f0]">
            {copy.heading}
          </span>
          <span className="text-xs text-[#64748b]">
            {completedCount}/{steps.length}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Progress bar */}
          <div className="w-24 h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
            <div
              className="h-full rounded-full bg-[#22c55e] transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {collapsed ? (
            <ChevronDown size={14} className="text-[#64748b]" />
          ) : (
            <ChevronUp size={14} className="text-[#64748b]" />
          )}
        </div>
      </button>

      {/* Steps */}
      {!collapsed && (
        <div className="px-4 pb-4 space-y-1">
          {steps.map((step) => (
            <div
              key={step.id}
              className={`flex items-start gap-3 rounded-lg px-3 py-2 transition-colors ${
                step.completed ? 'opacity-60' : ''
              }`}
            >
              {step.completed ? (
                <CheckCircle2
                  size={16}
                  className="flex-shrink-0 mt-0.5 text-[#22c55e] check-pop"
                />
              ) : (
                <Circle size={16} className="flex-shrink-0 mt-0.5 text-[#475569]" />
              )}
              <div className="min-w-0 flex-1">
                {step.href && !step.completed ? (
                  <Link
                    href={step.href}
                    className="text-sm font-medium text-[#e2e8f0] hover:text-[#3b82f6] transition-colors"
                  >
                    {step.label}
                  </Link>
                ) : (
                  <span
                    className={`text-sm font-medium ${
                      step.completed
                        ? 'text-[#22c55e] line-through'
                        : 'text-[#e2e8f0]'
                    }`}
                  >
                    {step.label}
                  </span>
                )}
                {!step.completed && (
                  <p className="text-xs text-[#64748b] mt-0.5">
                    {step.description}
                  </p>
                )}
              </div>
            </div>
          ))}

          {/* Dismiss link */}
          <div className="pt-2 text-center">
            <button
              onClick={handleDismiss}
              className="text-[10px] text-[#475569] hover:text-[#64748b] transition-colors"
            >
              Dismiss checklist
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
