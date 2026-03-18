'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { Spinner } from '@/components/ui/Spinner';
import { OraclePanel } from '@/components/oracle/OraclePanel';
import { Sparkles } from 'lucide-react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [oracleOpen, setOracleOpen] = useState(false);

  // Allow access if Supabase user exists OR if a manual token is stored (backend JWT / demo mode)
  const isAuthenticated = !!user || !!token;

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isAuthenticated, loading, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto bg-brand-bg p-6">
          {children}
        </main>
      </div>

      {/* Persistent Oracle FAB — always visible */}
      <button
        onClick={() => setOracleOpen(true)}
        className="fixed bottom-6 right-6 z-30 flex items-center gap-2 px-4 py-3 rounded-full
                   bg-[#22c55e] text-[#0a0f1a] font-semibold text-sm shadow-lg
                   hover:bg-[#16a34a] transition-all duration-200 hover:shadow-[#22c55e]/20
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
