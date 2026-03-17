'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  Map,
  Network,
  Sparkles,
  BarChart3,
  Calendar,
  Wrench,
  TrendingUp,
  User,
  CreditCard,
  ChevronLeft,
  ChevronRight,
  LogOut,
  LayoutDashboard,
  FileText,
  Layers,
  AlertTriangle,
  CheckSquare,
} from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';
import { SiteSelector } from './SiteSelector';

const NAV_ITEMS = [
  { href: '/overview', label: 'Overview', icon: LayoutDashboard },
  { href: '/posts', label: 'Posts', icon: FileText },
  { href: '/clusters', label: 'Clusters', icon: Layers },
  { href: '/issues', label: 'Issues', icon: AlertTriangle },
  { href: '/actions', label: 'Action Queue', icon: CheckSquare },
  { href: '/landscape', label: 'Landscape', icon: Map },
  { href: '/cannibalization', label: 'Cannibalization', icon: Network },
  { href: '/oracle', label: 'Oracle', icon: Sparkles },
  { href: '/dashboard', label: 'Analytics', icon: BarChart3 },
  { href: '/calendar', label: 'Calendar', icon: Calendar },
  { href: '/impact', label: 'Impact', icon: TrendingUp },
  { href: '/consolidation', label: 'Consolidation', icon: Wrench },
];

const BOTTOM_NAV_ITEMS = [
  { href: '/profile', label: 'Profile', icon: User },
  { href: '/billing', label: 'Billing', icon: CreditCard },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <aside
      className={clsx(
        'flex flex-col border-r border-brand-border bg-brand-surface transition-all duration-200',
        collapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between px-4 border-b border-brand-border">
        {!collapsed && (
          <Link href="/landscape" className="text-xl font-bold text-brand-accent">
            Enough
          </Link>
        )}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="rounded-lg p-1.5 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 p-3">
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
              <item.icon size={20} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom Nav */}
      <div className="border-t border-brand-border p-3 space-y-1">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
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
      </div>

      {/* Site Selector */}
      <div className="border-t border-brand-border p-3">
        {!collapsed && <SiteSelector />}
      </div>

      {/* User */}
      <div className="border-t border-brand-border p-3">
        <button
          onClick={() => void signOut()}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text transition-colors"
        >
          <LogOut size={18} />
          {!collapsed && (
            <span className="truncate">
              {user?.email ?? 'Sign out'}
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
