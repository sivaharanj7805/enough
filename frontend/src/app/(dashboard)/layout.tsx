'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { useSubscription } from '@/lib/hooks/useApi';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { Spinner } from '@/components/ui/Spinner';
import { OraclePanel } from '@/components/oracle/OraclePanel';
import { Sparkles } from 'lucide-react';

// Only billing is accessible without a paid subscription (so they can actually pay)
const UNPAID_PAGES = ['/billing'];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [oracleOpen, setOracleOpen] = useState(false);
  const { data: subscription, isLoading: subLoading } = useSubscription();

  // Allow access if Supabase user exists OR if a manual token is stored (backend JWT / demo mode)
  const isAuthenticated = !!user || !!token;

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isAuthenticated, loading, router]);

  // Hard redirect: no subscription → go to billing. No soft wall, no teaser.
  const tier = subscription?.tier ?? 'free';
  const isPaid = tier === 'growth' || tier === 'scale';
  const isUnpaidPage = UNPAID_PAGES.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  useEffect(() => {
    if (!subLoading && isAuthenticated && !isPaid && !isUnpaidPage) {
      router.replace('/billing');
    }
  }, [subLoading, isAuthenticated, isPaid, isUnpaidPage, router]);

  if (loading || subLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  // Still waiting for redirect — don't flash dashboard content
  if (!isPaid && !isUnpaidPage) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto bg-brand-bg p-6">
          {children}
        </main>
      </div>

      {/* Persistent Oracle FAB — only for paying users */}
      {isPaid && (
        <button
          onClick={() => setOracleOpen(true)}
          className="fixed bottom-6 right-6 z-30 flex items-center gap-2 px-4 py-3 rounded-full
                     bg-[#3b82f6] text-white font-semibold text-sm shadow-lg
                     hover:bg-[#2563eb] transition-all duration-200 hover:shadow-[#3b82f6]/20
                     hover:shadow-xl hover:scale-105"
          title="Ask Oracle anything"
        >
          <Sparkles size={16} />
          <span>Ask Oracle</span>
        </button>
      )}

      {/* Oracle slide-in panel */}
      <OraclePanel open={oracleOpen} onClose={() => setOracleOpen(false)} />
    </div>
  );
}
