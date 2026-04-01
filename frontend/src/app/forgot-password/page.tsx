'use client';

import { useState } from 'react';
import { supabase } from '@/lib/supabase';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'sent' | 'error'>('idle');
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('loading');
    setError('');
    try {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent('/login')}`,
      });
      if (resetError) throw resetError;
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Something went wrong — try again');
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="text-2xl font-bold tracking-widest text-[#3b82f6]">TENDED</span>
        </div>

        <div>
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-sm text-[#64748b] hover:text-[#94a3b8] transition-colors mb-6"
          >
            <ArrowLeft size={14} /> Back to sign in
          </Link>

          {status === 'sent' ? (
            <div className="text-center py-8 px-4 rounded-2xl bg-[#111827] border border-[#1e293b]">
              <div className="text-5xl mb-4">📬</div>
              <p className="text-[#e2e8f0] font-semibold text-lg">Check your email</p>
              <p className="text-[#64748b] text-sm mt-2">
                We sent a sign-in link to <span className="text-[#3b82f6] font-medium">{email}</span>.
                Use it to access your account and update your password in Settings.
              </p>
              <button
                onClick={() => setStatus('idle')}
                className="mt-4 text-sm text-[#64748b] hover:text-[#94a3b8] transition-colors underline"
              >
                Try a different email
              </button>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-[#e2e8f0] mb-1">Reset password</h1>
              <p className="text-[#64748b] text-sm mb-6">
                Enter your email and we&apos;ll send you a sign-in link.
              </p>

              <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-[#94a3b8] mb-2 uppercase tracking-wider">
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    autoFocus
                    placeholder="you@company.com"
                    className="w-full px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b]
                               text-[#e2e8f0] placeholder-[#334155] text-sm
                               focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30 transition-all"
                  />
                </div>

                {error && (
                  <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 rounded-xl px-4 py-3 border border-red-400/20">
                    <span>⚠️</span><span>{error}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={status === 'loading' || !email.trim()}
                  className="w-full py-3 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm
                             hover:bg-[#2563eb] transition-all disabled:opacity-50 disabled:cursor-not-allowed
                             flex items-center justify-center gap-2"
                >
                  {status === 'loading' ? (
                    <><Loader2 size={16} className="animate-spin" /> Sending…</>
                  ) : 'Send reset link'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
