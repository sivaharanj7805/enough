'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, ChevronDown, RefreshCw, Loader2 } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

/* ─── Route → label map for breadcrumbs ──────── */

const SEGMENT_LABELS: Record<string, string> = {
  today: 'Today',
  landscape: 'Landscape',
  clusters: 'Clusters',
  posts: 'Posts',
  actions: 'Recommendations',
  issues: 'Issues',
  cannibalization: 'Cannibalization',
  consolidation: 'Consolidation',
  oracle: 'Oracle',
  overview: 'Analytics',
  settings: 'Integrations',
  billing: 'Billing',
};

function buildBreadcrumbs(pathname: string) {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [{ label: 'Today', href: '/today' }];

  return segments.map((seg, idx) => {
    const href = '/' + segments.slice(0, idx + 1).join('/');
    const label = SEGMENT_LABELS[seg] ?? seg.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    return { label, href };
  });
}

/* ─── Helpers ────────────────────────────────── */

function isStale(dateStr: string | null | undefined, days: number): boolean {
  if (!dateStr) return true;
  const diff = Date.now() - new Date(dateStr).getTime();
  return diff > days * 24 * 60 * 60 * 1000;
}

/* ─── Site selector dropdown ─────────────────── */

function SiteSelector() {
  const { sites, currentSite, selectSite } = useSite();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (!currentSite) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-[#9CA3AF] hover:bg-[#1E1F2B] hover:text-white transition-colors duration-150"
      >
        <span className="max-w-[180px] truncate">{currentSite.name}</span>
        <ChevronDown size={14} className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 min-w-[200px] rounded-lg border border-[#23262F] bg-[#0F1117] py-1 shadow-xl">
          {sites.map((site) => (
            <button
              key={site.id}
              onClick={() => {
                selectSite(site.id);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2 text-sm transition-colors duration-150 ${site.id === currentSite.id
                  ? 'text-[#3B82F6] bg-[#3B82F6]/10'
                  : 'text-[#9CA3AF] hover:bg-[#1E1F2B] hover:text-white'
                }`}
            >
              {site.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Header ─────────────────────────────────── */

export function Header() {
  const pathname = usePathname();
  const { currentSite } = useSite();
  const { token } = useAuth();
  const [reanalyzing, setReanalyzing] = useState(false);

  const breadcrumbs = useMemo(() => buildBreadcrumbs(pathname), [pathname]);

  const showReanalyze = isStale(currentSite?.last_crawl_at, 7);

  const handleReanalyze = async () => {
    if (!currentSite?.id || !token) return;
    setReanalyzing(true);
    try {
      await apiFetch(`/sites/${currentSite.id}/pipeline`, { method: 'POST', token });
    } catch (err) {
      console.error('Re-analysis failed:', err);
    } finally {
      setReanalyzing(false);
    }
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-[#23262F] px-6">
      {/* Left: Breadcrumbs */}
      <nav className="flex items-center gap-1 text-sm" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, idx) => {
          const isLast = idx === breadcrumbs.length - 1;
          return (
            <span key={crumb.href} className="flex items-center gap-1">
              {idx > 0 && <ChevronRight size={14} className="text-[#5F6571]" />}
              {isLast ? (
                <span className="font-medium text-white">{crumb.label}</span>
              ) : (
                <Link
                  href={crumb.href}
                  className="text-[#9CA3AF] hover:text-white transition-colors duration-150"
                >
                  {crumb.label}
                </Link>
              )}
            </span>
          );
        })}
      </nav>

      {/* Right: Site selector + Re-analyze */}
      <div className="flex items-center gap-3">
        <SiteSelector />

        {showReanalyze && (
          <button
            onClick={() => void handleReanalyze()}
            disabled={reanalyzing}
            className="flex items-center gap-1.5 rounded-md border border-[#3B82F6] px-3 py-1.5 text-sm font-medium text-[#3B82F6] hover:bg-[#3B82F6]/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {reanalyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            <span>{reanalyzing ? 'Re-analyzing...' : 'Re-analyze'}</span>
          </button>
        )}
      </div>
    </header>
  );
}
