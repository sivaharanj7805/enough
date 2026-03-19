'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { useSubscription } from '@/lib/hooks/useApi';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { Spinner } from '@/components/ui/Spinner';
import { OraclePanel } from '@/components/oracle/OraclePanel';
import { Sparkles, ArrowRight } from 'lucide-react';
import Link from 'next/link';

// Pages accessible without a paid subscription (billing + settings to manage account)
const FREE_PAGES = ['/billing', '/settings'];

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

  if (loading || subLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  // Payment wall: if user has no active paid subscription and is not on a free page, show upgrade prompt
  const tier = subscription?.tier ?? 'free';
  const isPaid = tier === 'growth' || tier === 'scale';
  const isFreePage = FREE_PAGES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const showPaywall = !isPaid && !isFreePage;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto bg-brand-bg p-6">
          {showPaywall ? (
            <div className="max-w-lg mx-auto text-center py-20">
              <div className="text-5xl mb-6">🔒</div>
              <h2 className="text-2xl font-bold text-[#e2e8f0] mb-3">
                Upgrade to access your dashboard
              </h2>
              <p className="text-sm text-[#94a3b8] mb-8 leading-relaxed">
                Enough is a paid tool built for content strategists who are serious about
                growing their organic traffic. Start your Growth plan to unlock your full
                content analysis, the Oracle, and prioritized recommendations.
              </p>
              <Link
                href="/billing"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors"
              >
                View plans — starting at $99/mo <ArrowRight size={16} />
              </Link>
              <p className="mt-4 text-xs text-[#475569]">
                Cancel anytime. No long-term contracts.
              </p>
            </div>
          ) : (
            children
          )}
        </main>
      </div>

      {/* Persistent Oracle FAB — always visible */}
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

      {/* Oracle slide-in panel */}
      <OraclePanel open={oracleOpen} onClose={() => setOracleOpen(false)} />
    </div>
  );
}
