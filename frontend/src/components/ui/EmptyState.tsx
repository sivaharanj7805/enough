import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  /** Primary CTA */
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  /** Secondary CTA */
  secondaryLabel?: string;
  secondaryHref?: string;
  /** Show demo data banner */
  showDemoBanner?: boolean;
  className?: string;
}

/**
 * Reusable empty state for pages with no data.
 *
 * Research: empty states that show value (demo data, clear next step) retain
 * 75% more users than blank screens with "no data" messages.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
  secondaryLabel,
  secondaryHref,
  showDemoBanner,
  className,
}: EmptyStateProps) {
  return (
    <div className={`text-center py-12 px-6 ${className ?? ''}`}>
      {Icon && (
        <div className="mx-auto mb-4 w-12 h-12 rounded-xl bg-[#1e293b] flex items-center justify-center">
          <Icon size={24} className="text-[#64748b]" />
        </div>
      )}
      <h3 className="text-lg font-semibold text-[#e2e8f0] mb-2">{title}</h3>
      <p className="text-sm text-[#64748b] max-w-md mx-auto mb-6">{description}</p>

      <div className="flex flex-col items-center gap-3">
        {actionLabel && actionHref && (
          <Link
            href={actionHref}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
          >
            {actionLabel} <ArrowRight size={14} />
          </Link>
        )}
        {actionLabel && onAction && !actionHref && (
          <button
            onClick={onAction}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
          >
            {actionLabel} <ArrowRight size={14} />
          </button>
        )}
        {secondaryLabel && secondaryHref && (
          <Link
            href={secondaryHref}
            className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors"
          >
            {secondaryLabel}
          </Link>
        )}
      </div>

      {showDemoBanner && (
        <div className="mt-8 mx-auto max-w-sm">
          <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#3b82f6]/5 border border-[#3b82f6]/20">
            <p className="text-xs text-[#94a3b8]">
              See a live example with Close.com data
            </p>
            <Link
              href="/onboarding"
              className="flex-shrink-0 text-xs font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors ml-3"
            >
              Try demo
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
