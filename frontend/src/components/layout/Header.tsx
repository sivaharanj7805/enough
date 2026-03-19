'use client';

import { usePathname } from 'next/navigation';

const PAGE_TITLES: Record<string, string> = {
  '/landscape': 'Landscape',
  '/cannibalization': 'Content Overlap',
  '/oracle': 'Pre-Publish Oracle',
  '/dashboard': 'Health Dashboard',
  '/consolidation': 'Consolidation Plans',
};

export function Header() {
  const pathname = usePathname();
  const title = Object.entries(PAGE_TITLES).find(([path]) =>
    pathname === path || pathname.startsWith(`${path}/`)
  )?.[1] ?? 'Enough';

  return (
    <header className="flex h-14 items-center border-b border-brand-border bg-brand-surface px-6">
      <h1 className="text-lg font-semibold text-brand-text">{title}</h1>
    </header>
  );
}
