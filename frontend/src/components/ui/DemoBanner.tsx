'use client';

import { useState } from 'react';
import { X } from 'lucide-react';

interface DemoBannerProps {
  /** Only render the banner when true */
  isDemoData: boolean;
}

/**
 * Yellow/amber banner shown at the top of a page when the user is viewing
 * demo data (Close.com's blog). Dismissible via the X button.
 *
 * Usage:
 *   <DemoBanner isDemoData={site.isDemo} />
 */
export function DemoBanner({ isDemoData }: DemoBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (!isDemoData || dismissed) return null;

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5 bg-[#78350f]/20 border-b border-[#92400e]/30">
      <p className="text-sm text-[#fbbf24]">
        This is demo data from Close.com&apos;s blog (958 posts). Your analysis
        is running and will replace this in ~18 minutes.
      </p>
      <button
        onClick={() => setDismissed(true)}
        className="flex-shrink-0 p-1 rounded hover:bg-[#92400e]/30 transition-colors"
        aria-label="Dismiss demo banner"
      >
        <X size={16} className="text-[#fbbf24]" />
      </button>
    </div>
  );
}
