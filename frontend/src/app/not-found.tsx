import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center px-4">
      <div className="text-center max-w-sm">
        <div className="text-8xl font-black text-[#1e293b] mb-2 select-none">404</div>
        <h1 className="text-xl font-bold text-[#e2e8f0] mb-2">Page not found</h1>
        <p className="text-sm text-[#64748b] mb-8">
          This page doesn&apos;t exist — or it moved. Your dashboard is still right where you left it.
        </p>
        <Link
          href="/today"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3b82f6] text-white
                     font-semibold text-sm hover:bg-[#2563eb] transition-colors"
        >
          <ArrowLeft size={14} /> Go to dashboard
        </Link>
        <div className="mt-4">
          <Link href="/" className="text-xs text-[#334155] hover:text-[#64748b] transition-colors">
            ← Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}
