'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  Home,
  Network,
  FileText,
  Zap,
  GitCompare,
  Sparkles,
  BarChart3,
  Plug,
  CreditCard,
  Menu,
  X,
  Compass,
  ChevronLeft,
  Hammer,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';

/* ─── Navigation structure ─────────────────────── */

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

interface NavSection {
  header: string;
  items: NavItem[];
}

type NavEntry = NavItem | NavSection;

const NAV: NavEntry[] = [
  { href: '/today', label: 'Today', icon: Home },
  {
    header: 'Explore',
    items: [
      { href: '/clusters', label: 'Clusters', icon: Network },
      { href: '/posts', label: 'Posts', icon: FileText },
    ],
  },
  {
    header: 'Actions',
    items: [
      { href: '/actions', label: 'Recommendations', icon: Zap },
      { href: '/patcher', label: 'Patcher', icon: Hammer },
      { href: '/pioneer', label: 'Pioneer', icon: Compass },
      { href: '/cannibalization', label: 'Cannibalization', icon: GitCompare },
    ],
  },
  { href: '/oracle', label: 'Oracle', icon: Sparkles },
  { href: '/overview', label: 'Analytics', icon: BarChart3 },
  {
    header: 'Settings',
    items: [
      { href: '/settings', label: 'Integrations', icon: Plug },
      { href: '/billing', label: 'Billing', icon: CreditCard },
    ],
  },
];

/* ─── Mobile bottom nav items ──────────────────── */

const MOBILE_NAV: NavItem[] = [
  { href: '/today', label: 'Today', icon: Home },
  { href: '/clusters', label: 'Explore', icon: Compass },
  { href: '/actions', label: 'Actions', icon: Zap },
  { href: '/oracle', label: 'Oracle', icon: Sparkles },
];

/* ─── Helpers ──────────────────────────────────── */

function isSection(entry: NavEntry): entry is NavSection {
  return 'header' in entry;
}

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/* ─── Sidebar (desktop) ───────────────────────── */

function DesktopSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { user } = useAuth();

  const width = collapsed ? 'w-16' : 'w-60';

  const renderItem = (item: NavItem, indented = false) => {
    const active = isActive(pathname, item.href);
    return (
      <Link
        key={item.href}
        href={item.href}
        title={collapsed ? item.label : undefined}
        className={clsx(
          'group relative flex items-center rounded-md py-2 text-sm font-medium transition-colors duration-150',
          collapsed ? 'justify-center px-0' : 'gap-3 px-3',
          indented && !collapsed && 'pl-6',
          active
            ? 'text-white'
            : 'text-[#9CA3AF] hover:bg-[#1E1F2B] hover:text-white',
        )}
      >
        {/* Active indicator bar */}
        {active && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r bg-[#3B82F6]" />
        )}
        <item.icon size={20} className="flex-shrink-0" />
        {!collapsed && <span className="text-xs leading-snug">{item.label}</span>}
      </Link>
    );
  };

  return (
    <aside
      className={clsx(
        'hidden md:flex flex-col bg-[#0F1117] overflow-hidden transition-[width] duration-200',
        width,
      )}
    >
      {/* Top: Logo + collapse */}
      <div className={clsx('flex h-14 items-center', collapsed ? 'justify-center px-0' : 'justify-between px-4')}>
        {!collapsed && (
          <Link
            href="/today"
            className="text-lg font-bold tracking-widest text-white"
          >
            TENDED
          </Link>
        )}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="rounded-md p-1.5 text-[#9CA3AF] hover:bg-[#1E1F2B] hover:text-white transition-colors duration-150"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <Menu size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAV.map((entry, idx) => {
          if (isSection(entry)) {
            return (
              <div key={entry.header}>
                {!collapsed && (
                  <p className="mt-6 mb-2 px-3 text-[11px] font-medium uppercase tracking-wider text-[#5F6571]">
                    {entry.header}
                  </p>
                )}
                {collapsed && <div className="mt-4" />}
                {entry.items.map((item) => renderItem(item, true))}
              </div>
            );
          }
          return renderItem(entry);
        })}
      </nav>

      {/* User area */}
      <div className={clsx('border-t border-[#23262F]', collapsed ? 'p-2' : 'p-3')}>
        <div className={clsx('flex items-center', collapsed ? 'justify-center' : 'gap-3')}>
          {/* Avatar placeholder */}
          <div className="h-8 w-8 flex-shrink-0 rounded-full bg-[#23262F] flex items-center justify-center text-xs font-medium text-[#9CA3AF]">
            {user?.email?.[0]?.toUpperCase() ?? '?'}
          </div>
          {!collapsed && (
            <span className="truncate text-sm text-[#9CA3AF] max-w-[160px]">
              {user?.email ?? ''}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}

/* ─── Mobile bottom nav + sheet ────────────────── */

function MobileBottomNav() {
  const pathname = usePathname();
  const [sheetOpen, setSheetOpen] = useState(false);

  const toggleSheet = useCallback(() => setSheetOpen((v) => !v), []);

  /* All items that are NOT in the bottom nav (for the "More" sheet) */
  const allItems: NavItem[] = [];
  NAV.forEach((entry) => {
    if (isSection(entry)) {
      entry.items.forEach((item) => allItems.push(item));
    } else {
      allItems.push(entry);
    }
  });
  const mobileHrefs = new Set(MOBILE_NAV.map((i) => i.href));
  const moreItems = allItems.filter((i) => !mobileHrefs.has(i.href));

  return (
    <>
      {/* Bottom bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex md:hidden items-center justify-around border-t border-[#23262F] bg-[#0F1117] pb-[env(safe-area-inset-bottom)]">
        {MOBILE_NAV.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex min-h-[44px] min-w-[44px] flex-col items-center justify-center gap-0.5 px-1 py-1.5',
                active ? 'text-[#3B82F6]' : 'text-[#9CA3AF]',
              )}
            >
              <item.icon size={20} />
              <span className="text-[10px]">{item.label}</span>
            </Link>
          );
        })}

        {/* More button */}
        <button
          onClick={toggleSheet}
          className={clsx(
            'flex min-h-[44px] min-w-[44px] flex-col items-center justify-center gap-0.5 px-1 py-1.5',
            sheetOpen ? 'text-[#3B82F6]' : 'text-[#9CA3AF]',
          )}
        >
          <Menu size={20} />
          <span className="text-[10px]">More</span>
        </button>
      </nav>

      {/* Slide-up sheet */}
      {sheetOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-50 bg-black/50 md:hidden"
            onClick={toggleSheet}
          />

          {/* Sheet */}
          <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden animate-slide-up rounded-t-2xl bg-[#0F1117] px-4 pb-8 pt-4 max-h-[70vh] overflow-y-auto">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-sm font-semibold text-white">
                Navigation
              </span>
              <button
                onClick={toggleSheet}
                className="rounded-md p-1.5 text-[#9CA3AF] hover:text-white"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-1">
              {moreItems.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={toggleSheet}
                    className={clsx(
                      'flex items-center gap-3 rounded-md px-3 py-3 text-sm font-medium transition-colors duration-150',
                      active
                        ? 'text-[#3B82F6]'
                        : 'text-[#9CA3AF] hover:bg-[#1E1F2B] hover:text-white',
                    )}
                  >
                    <item.icon size={20} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </>
      )}
    </>
  );
}

/* ─── Exported Sidebar ─────────────────────────── */

export function Sidebar() {
  return (
    <>
      <DesktopSidebar />
      <MobileBottomNav />
    </>
  );
}
