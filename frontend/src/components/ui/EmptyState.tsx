import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  /** Monochrome illustration icon — rendered large and muted */
  icon?: LucideIcon;
  /** Clear headline */
  title: string;
  /** Helpful subtext explaining the state */
  description: string;
  /** Primary CTA label */
  actionLabel?: string;
  /** Primary CTA link (renders an anchor) */
  actionHref?: string;
  /** Primary CTA click handler (renders a button when no href) */
  onAction?: () => void;
  /** Secondary action label */
  secondaryLabel?: string;
  /** Secondary action link */
  secondaryHref?: string;
  /** Secondary action click handler (renders a button when no href) */
  onSecondaryAction?: () => void;
  /** Show demo data banner */
  showDemoBanner?: boolean;
  className?: string;
}

/**
 * Reusable empty state for pages with no data.
 *
 * Research: empty states that show value (demo data, clear next step) retain
 * 75% more users than blank screens with "no data" messages.
 *
 * Usage:
 *   <EmptyState
 *     icon={Search}
 *     title="No posts analyzed yet"
 *     description="Posts will appear here once the crawl completes."
 *     actionLabel="Start analysis"
 *     actionHref="/onboarding"
 *     secondaryLabel="Learn more"
 *     onSecondaryAction={() => openDocs()}
 *   />
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
  onSecondaryAction,
  showDemoBanner,
  className,
}: EmptyStateProps) {
  return (
    <div className={`text-center py-16 px-6 ${className ?? ''}`}>
      {/* Monochrome illustration — large, muted icon */}
      {Icon && (
        <div className="mx-auto mb-6 w-20 h-20 rounded-2xl bg-[#1e293b]/60 flex items-center justify-center">
          <Icon size={40} className="text-[#475569]" strokeWidth={1.5} />
        </div>
      )}

      {/* Clear headline */}
      <h3 className="text-lg font-semibold text-[#e2e8f0] mb-2">{title}</h3>

      {/* Helpful subtext */}
      <p className="text-sm text-[#64748b] max-w-md mx-auto mb-8 leading-relaxed">
        {description}
      </p>

      <div className="flex flex-col items-center gap-3">
        {/* Primary CTA — link variant */}
        {actionLabel && actionHref && (
          <Link
            href={actionHref}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
          >
            {actionLabel} <ArrowRight size={14} />
          </Link>
        )}

        {/* Primary CTA — button variant */}
        {actionLabel && onAction && !actionHref && (
          <button
            onClick={onAction}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
          >
            {actionLabel} <ArrowRight size={14} />
          </button>
        )}

        {/* Secondary action — link variant */}
        {secondaryLabel && secondaryHref && (
          <Link
            href={secondaryHref}
            className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors"
          >
            {secondaryLabel}
          </Link>
        )}

        {/* Secondary action — button variant */}
        {secondaryLabel && onSecondaryAction && !secondaryHref && (
          <button
            onClick={onSecondaryAction}
            className="text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors"
          >
            {secondaryLabel}
          </button>
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
