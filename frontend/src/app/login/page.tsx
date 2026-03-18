'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import Link from 'next/link';
import { ArrowRight, Loader2 } from 'lucide-react';

// Left panel — social proof + value
function LeftPanel() {
  return (
    <div className="hidden lg:flex flex-col justify-between h-full p-12 bg-[#0d1526] border-r border-[#1e293b]">
      {/* Logo */}
      <div>
        <span className="text-2xl font-bold tracking-widest text-[#3b82f6]">ENOUGH</span>
        <p className="text-xs text-[#475569] mt-1 tracking-wider uppercase">Content Ecosystem Intelligence</p>
      </div>

      {/* Core value prop */}
      <div>
        <h2 className="text-3xl font-bold text-[#e2e8f0] leading-tight mb-4">
          Stop publishing more.<br />
          <span className="text-[#3b82f6]">Start publishing smarter.</span>
        </h2>
        <p className="text-[#64748b] text-base leading-relaxed">
          Enough analyses your entire content library, finds what&apos;s working and what&apos;s hurting you,
          and tells you exactly what to fix — in priority order.
        </p>

        {/* Stats */}
        <div className="mt-8 grid grid-cols-2 gap-4">
          {[
            { n: '958', label: 'Posts analysed on Close.com', color: '#e2e8f0' },
            { n: '200+', label: 'Cannibalization pairs detected', color: '#f97316' },
            { n: '3.0%', label: 'Posts AI-ready (huge opportunity)', color: '#eab308' },
            { n: '0',    label: 'Schema markup across 958 posts', color: '#ef4444' },
          ].map(({ n, label, color }) => (
            <div key={label} className="bg-[#111827] rounded-xl p-4 border border-[#1e293b]">
              <div className="text-2xl font-bold" style={{ color }}>{n}</div>
              <div className="text-xs text-[#64748b] mt-1 leading-tight">{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tagline */}
      <p className="text-xs text-[#334155]">
        Read-only · never modifies your content · cancel anytime
      </p>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { token, signIn, signInWithMagicLink } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'magic' | 'password'>('magic');
  const [status, setStatus] = useState<'idle' | 'loading' | 'sent' | 'error'>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (token) router.replace('/today');
  }, [token, router]);

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    setStatus('loading');
    setError('');
    try {
      await signInWithMagicLink(email);
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Something went wrong — try again');
    }
  }

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setStatus('loading');
    setError('');
    try {
      await signIn(email, password);
      router.replace('/today');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Incorrect email or password');
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex">
      {/* Left — value panel (desktop only) */}
      <div className="lg:w-[480px] xl:w-[520px] flex-shrink-0">
        <LeftPanel />
      </div>

      {/* Right — form */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12">
        {/* Mobile logo */}
        <div className="lg:hidden text-center mb-10">
          <span className="text-2xl font-bold tracking-widest text-[#3b82f6]">ENOUGH</span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-[#e2e8f0]">Welcome back</h1>
            <p className="text-[#64748b] text-sm mt-1">
              Your content insights are waiting.
            </p>
          </div>

          {status === 'sent' ? (
            <div className="text-center py-8 px-4 rounded-2xl bg-[#111827] border border-[#1e293b]">
              <div className="text-5xl mb-4">📬</div>
              <p className="text-[#e2e8f0] font-semibold text-lg">Check your email</p>
              <p className="text-[#64748b] text-sm mt-2 leading-relaxed">
                We sent a sign-in link to<br />
                <span className="text-[#3b82f6] font-medium">{email}</span>
              </p>
              <p className="text-[#475569] text-xs mt-4">Didn&apos;t get it? Check your spam folder.</p>
              <button
                onClick={() => setStatus('idle')}
                className="mt-4 text-sm text-[#64748b] hover:text-[#94a3b8] transition-colors underline"
              >
                Try a different email
              </button>
            </div>
          ) : (
            <>
              {/* Mode toggle */}
              <div className="flex rounded-xl bg-[#111827] border border-[#1e293b] p-1 mb-6">
                {(['magic', 'password'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => { setMode(m); setStatus('idle'); setError(''); }}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                      mode === m
                        ? 'bg-[#1e293b] text-[#e2e8f0] shadow-sm'
                        : 'text-[#64748b] hover:text-[#94a3b8]'
                    }`}
                  >
                    {m === 'magic' ? '✉️ Magic link' : '🔑 Password'}
                  </button>
                ))}
              </div>

              <form
                onSubmit={mode === 'magic'
                  ? (e) => void handleMagicLink(e)
                  : (e) => void handlePassword(e)}
                className="space-y-4"
              >
                <div>
                  <label className="block text-xs font-semibold text-[#94a3b8] mb-2 uppercase tracking-wider">
                    Work email
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
                               focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30
                               transition-all"
                  />
                </div>

                {mode === 'password' && (
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <label className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
                        Password
                      </label>
                      <Link href="/forgot-password" className="text-xs text-[#3b82f6] hover:underline">
                        Forgot password?
                      </Link>
                    </div>
                    <input
                      type="password"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      required
                      placeholder="••••••••"
                      className="w-full px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b]
                                 text-[#e2e8f0] placeholder-[#334155] text-sm
                                 focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30
                                 transition-all"
                    />
                  </div>
                )}

                {error && (
                  <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 rounded-xl px-4 py-3 border border-red-400/20">
                    <span className="flex-shrink-0 mt-0.5">⚠️</span>
                    <span>{error}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={status === 'loading' || !email.trim()}
                  className="w-full py-3 rounded-xl bg-[#3b82f6] text-white font-semibold
                             text-sm hover:bg-[#2563eb] transition-all
                             disabled:opacity-50 disabled:cursor-not-allowed
                             flex items-center justify-center gap-2 shadow-lg shadow-[#3b82f6]/20"
                >
                  {status === 'loading' ? (
                    <><Loader2 size={16} className="animate-spin" /> Sending…</>
                  ) : mode === 'magic' ? (
                    <>Send sign-in link <ArrowRight size={15} /></>
                  ) : (
                    <>Sign in <ArrowRight size={15} /></>
                  )}
                </button>
              </form>

              <div className="mt-6 flex items-center gap-3">
                <div className="flex-1 h-px bg-[#1e293b]" />
                <span className="text-xs text-[#334155]">or</span>
                <div className="flex-1 h-px bg-[#1e293b]" />
              </div>

              <Link
                href="/onboarding"
                className="mt-4 flex items-center justify-center gap-2 w-full py-3 rounded-xl
                           border border-[#1e293b] text-sm text-[#64748b]
                           hover:border-[#334155] hover:text-[#94a3b8] transition-all"
              >
                Try without an account
              </Link>
            </>
          )}

          <p className="text-center text-xs text-[#334155] mt-8">
            No account?{' '}
            <Link href="/signup" className="text-[#3b82f6] hover:underline font-medium">
              Start for free →
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
