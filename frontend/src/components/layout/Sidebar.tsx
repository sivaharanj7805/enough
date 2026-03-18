'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  Zap,
  Compass,
  Sparkles,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';
import { SiteSelector } from './SiteSelector';

const NAV_ITEMS = [
  {
    href: '/today',
    label: 'Today',
    icon: Zap,
    description: 'Your #1 priority',
  },
  {
    href: '/explore',
    label: 'Explore',
    icon: Compass,
    description: 'Deep dive',
  },
];

const BOTTOM_NAV_ITEMS = [
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <aside
      className={clsx(
        'flex flex-col border-r border-brand-border bg-brand-surface transition-all duration-200',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between px-4 border-b border-brand-border">
        {!collapsed && (
          <Link href="/today" className="text-xl font-bold tracking-widest text-brand-accent">
            ENOUGH
          </Link>
        )}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="rounded-lg p-1.5 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Site Selector */}
      <div className="border-b border-brand-border p-3">
        {!collapsed && <SiteSelector />}
      </div>

      {/* Primary Nav */}
      <nav className="flex-1 space-y-1 p-3 pt-4">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                active
                  ? 'bg-brand-accent/10 text-brand-accent'
                  : 'text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text'
              )}
            >
              <item.icon size={20} className="flex-shrink-0" />
              {!collapsed && (
                <div>
                  <div>{item.label}</div>
                  <div className="text-xs font-normal opacity-60">{item.description}</div>
                </div>
              )}
            </Link>
          );
        })}

        {/* Oracle — visual separator, prominent position */}
        <div className="pt-2">
          {!collapsed && (
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-brand-text-muted/50">
              AI
            </p>
          )}
          <Link
            href="/oracle"
            className={clsx(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              pathname === '/oracle' || pathname.startsWith('/oracle/')
                ? 'bg-brand-accent/10 text-brand-accent'
                : 'text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text'
            )}
          >
            <Sparkles size={20} className="flex-shrink-0" />
            {!collapsed && (
              <div>
                <div>Oracle</div>
                <div className="text-xs font-normal opacity-60">Ask anything</div>
              </div>
            )}
          </Link>
        </div>
      </nav>

      {/* Bottom Nav */}
      <div className="border-t border-brand-border p-3 space-y-1">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-brand-accent/10 text-brand-accent'
                  : 'text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text'
              )}
            >
              <item.icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}

        {/* Sign out */}
        <button
          onClick={() => void signOut()}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text transition-colors"
        >
          <LogOut size={18} />
          {!collapsed && (
            <span className="truncate max-w-[140px]">
              {user?.email ?? 'Sign out'}
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
