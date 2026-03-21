'use client';

import { Loader2, CheckCircle } from 'lucide-react';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { pipeline as copy } from '@/lib/copy';
import type { PipelineStatus } from '@/lib/types';

const STAGES = [
  { key: 'clustering', ...copy.stages.crawling },
  { key: 'cannibalization', ...copy.stages.embedding },
  { key: 'health_scoring', ...copy.stages.analyzing },
  { key: 'recommendations', ...copy.stages.clustering },
  { key: 'completed', ...copy.stages.completed },
] as const;

/**
 * Shows pipeline progress inline on the Today page.
 * Polls every 8s while running, reveals partial results as stages complete.
 *
 * Research: Progressive disclosure during loading reduces perceived wait time
 * by up to 40% and prevents abandonment.
 */
export function PipelineProgress({ siteId }: { siteId: string }) {
  const { data: status } = useSWRFetch<PipelineStatus>(
    `/sites/${siteId}/intelligence/pipeline-status`,
    { refreshInterval: 8000 }
  );

  if (!status || status.status === 'idle' || status.status === 'completed') {
    return null;
  }

  if (status.status === 'failed') {
    // Map raw error text to user-friendly messages
    const rawError = (status.error ?? '').toLowerCase();
    let friendlyError = 'Something went wrong. Try re-running the analysis.';

    if (rawError.includes('sitemap') || rawError.includes('404')) {
      friendlyError = "We couldn't find a sitemap at your domain. Try entering your sitemap URL directly in Settings > Integrations.";
    } else if (rawError.includes('robots.txt') || rawError.includes('blocked') || rawError.includes('403')) {
      friendlyError = "Your site's robots.txt or server is blocking our crawler. Allow the Enough user-agent or whitelist our IP.";
    } else if (rawError.includes('timeout') || rawError.includes('connection') || rawError.includes('ECONNREFUSED')) {
      friendlyError = "We couldn't connect to your site. Check if it's online and accessible, then try again.";
    } else if (rawError.includes('javascript') || rawError.includes('spa') || rawError.includes('no posts')) {
      friendlyError = "No posts found. If your site uses JavaScript rendering, try providing a direct sitemap URL.";
    } else if (rawError.includes('ssl') || rawError.includes('certificate')) {
      friendlyError = "SSL certificate issue. Make sure your site's HTTPS certificate is valid.";
    }

    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3">
        <p className="text-sm text-red-400 font-medium">Analysis failed</p>
        <p className="text-xs text-[#94a3b8] mt-1">
          {friendlyError}
        </p>
      </div>
    );
  }

  const completedSteps = new Set(status.steps_completed ?? []);
  const currentStep = status.current_step;

  return (
    <div className="rounded-xl border border-[#22c55e]/20 bg-[#22c55e]/5 p-4 card-in">
      <div className="flex items-center gap-2 mb-3">
        <Loader2 size={14} className="animate-spin text-[#22c55e]" />
        <span className="text-xs font-semibold uppercase tracking-widest text-[#22c55e]">
          Analysis running
        </span>
      </div>

      <div className="space-y-2">
        {STAGES.map((stage) => {
          const isDone = completedSteps.has(stage.key);
          const isActive = stage.key === currentStep;
          const isPending = !isDone && !isActive;

          return (
            <div
              key={stage.key}
              className={`flex items-start gap-3 rounded-lg px-3 py-2 transition-all ${
                isActive
                  ? 'bg-[#22c55e]/10'
                  : isDone
                    ? 'opacity-70'
                    : 'opacity-30'
              }`}
            >
              <span className="flex-shrink-0 mt-0.5">
                {isDone ? (
                  <CheckCircle size={14} className="text-[#22c55e]" />
                ) : isActive ? (
                  <Loader2 size={14} className="animate-spin text-[#22c55e]" />
                ) : (
                  <div className="w-3.5 h-3.5 rounded-full border border-[#475569]" />
                )}
              </span>
              <div className="min-w-0">
                <span
                  className={`text-sm font-medium ${
                    isDone
                      ? 'text-[#22c55e]'
                      : isActive
                        ? 'text-[#e2e8f0]'
                        : 'text-[#475569]'
                  }`}
                >
                  {stage.label}
                </span>
                {isActive && (
                  <p className="text-xs text-[#64748b] mt-0.5">
                    {stage.description}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-[#475569] mt-3">{copy.canClose}</p>
    </div>
  );
}
