'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import Link from 'next/link';
import { ArrowRight, Loader2, CheckCircle2 } from 'lucide-react';

const BENEFITS = [
  'See which posts are hurting your rankings',
  'Find content cannibalizing itself',
  'Get a prioritised fix list — not 700 vague suggestions',
  'AI readiness scores for every post',
];

function LeftPanel() {
  return (
    <div className="hidden lg:flex flex-col justify-between h-full p-12 bg-[#0d1526] border-r border-[#1e293b]">
      <div>
        <span className="text-2xl font-bold tracking-widest text-[#3b82f6]">ENOUGH</span>
        <p className="text-xs text-[#475569] mt-1 tracking-wider uppercase">Content Ecosystem Intelligence</p>
      </div>

      <div>
        <h2 className="text-3xl font-bold text-[#e2e8f0] leading-tight mb-3">
          Your blog has problems<br />
          <span className="text-[#3b82f6]">you don't know about yet.</span>
        </h2>
        <p className="text-[#64748b] text-sm leading-relaxed mb-8">
          Enough crawls your entire content library, maps every cluster, detects every conflict,
          and tells you the three things to fix this week.
        </p>

        <div className="space-y-3">
          {BENEFITS.map((b) => (
            <div key={b} className="flex items-start gap-3">
              <CheckCircle2 size={16} className="text-[#22c55e] flex-shrink-0 mt-0.5" />
              <span className="text-sm text-[#94a3b8]">{b}</span>
            </div>
          ))}
        </div>

        {/* Proof point */}
        <div className="mt-8 p-4 rounded-xl bg-[#111827] border border-[#1e293b]">
          <p className="text-sm text-[#e2e8f0] font-medium leading-snug">
            &ldquo;We analysed Close.com&apos;s 958-post blog and found zero schema markup across
            every single post — a concrete fix their team could ship in a day.&rdquo;
          </p>
          <p className="text-xs text-[#475569] mt-2">
            From a real Enough analysis · Jan 2026
          </p>
        </div>
      </div>

      <p className="text-xs text-[#334155]">
        Free to start · no credit card · read-only access only
      </p>
    </div>
  );
}

export default function SignupPage() {
  const router = useRouter();
  const { token, signUp } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (token) router.replace('/onboarding');
  }, [token, router]);

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setStatus('loading');
    try {
      await signUp(email, password, '');
      setStatus('done');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Something went wrong — try again');
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex">
      {/* Left — value panel */}
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
          {status === 'done' ? (
            <div className="text-center py-8 px-4 rounded-2xl bg-[#111827] border border-[#1e293b]">
              <div className="text-5xl mb-4">🎉</div>
              <p className="text-[#e2e8f0] font-bold text-xl">You&apos;re in.</p>
              <p className="text-[#64748b] text-sm mt-2 leading-relaxed">
                We sent a confirmation link to<br />
                <span className="text-[#3b82f6] font-medium">{email}</span>
              </p>
              <p className="text-[#475569] text-xs mt-3">Click the link to activate your account.</p>
              <Link
                href="/login"
                className="mt-6 inline-flex items-center gap-2 text-sm text-[#3b82f6] hover:underline"
              >
                Go to sign in →
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-8">
                <h1 className="text-2xl font-bold text-[#e2e8f0]">Start your free audit</h1>
                <p className="text-[#64748b] text-sm mt-1">
                  Takes 2 minutes to set up. Analysis is free.
                </p>
              </div>

              <form onSubmit={(e) => void handleSignup(e)} className="space-y-4">
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

                <div>
                  <label className="block text-xs font-semibold text-[#94a3b8] mb-2 uppercase tracking-wider">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    placeholder="8+ characters"
                    className="w-full px-4 py-3 rounded-xl bg-[#111827] border border-[#1e293b]
                               text-[#e2e8f0] placeholder-[#334155] text-sm
                               focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30
                               transition-all"
                  />
                  <p className="text-xs text-[#334155] mt-1.5">You can always reset this via email.</p>
                </div>

                {error && (
                  <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 rounded-xl px-4 py-3 border border-red-400/20">
                    <span className="flex-shrink-0">⚠️</span>
                    <span>{error}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={status === 'loading' || !email.trim() || !password.trim()}
                  className="w-full py-3 rounded-xl bg-[#3b82f6] text-white font-semibold
                             text-sm hover:bg-[#2563eb] transition-all
                             disabled:opacity-50 disabled:cursor-not-allowed
                             flex items-center justify-center gap-2 shadow-lg shadow-[#3b82f6]/20"
                >
                  {status === 'loading' ? (
                    <><Loader2 size={16} className="animate-spin" /> Creating account…</>
                  ) : (
                    <>Analyse my blog free <ArrowRight size={15} /></>
                  )}
                </button>

                <p className="text-center text-xs text-[#334155]">
                  No credit card required
                </p>
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
                Try without an account first
              </Link>

              <p className="text-center text-xs text-[#334155] mt-6">
                Already have an account?{' '}
                <Link href="/login" className="text-[#3b82f6] hover:underline font-medium">
                  Sign in →
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
