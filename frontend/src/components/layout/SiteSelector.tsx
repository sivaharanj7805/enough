'use client';

import { useSite } from '@/lib/hooks/useSite';
import { Globe } from 'lucide-react';

export function SiteSelector() {
  const { sites, currentSite, selectSite } = useSite();

  if (sites.length === 0) return null;

  return (
    <div className="space-y-1">
      <label className="flex items-center gap-2 text-xs font-medium text-brand-text-muted">
        <Globe size={14} />
        Site
      </label>
      <select
        value={currentSite?.id ?? ''}
        onChange={(e) => selectSite(e.target.value)}
        className="w-full rounded-lg border border-brand-border bg-brand-bg px-2 py-1.5 text-xs text-brand-text focus:border-brand-accent focus:outline-none"
      >
        {sites.map((site) => (
          <option key={site.id} value={site.id}>
            {site.name}
          </option>
        ))}
      </select>
    </div>
  );
}
