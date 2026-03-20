'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { supabase } from '@/lib/supabase';
import Link from 'next/link';
import { ArrowRight, Loader2, CheckCircle2 } from 'lucide-react';

const BENEFITS = [
  'See which posts are hurting your rankings',
  'Find content cannibalizing itself',
  'Get a prioritised fix list — not 700 vague suggestions',
  'AI readiness scores for every post',
];

type PasswordStrength = 'too_short' | 'weak' | 'fair' | 'strong';

function getPasswordStrength(password: string): PasswordStrength {
  if (password.length < 8) return 'too_short';

  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const hasMixedCaseAndNumbers = hasUpper && hasLower && hasNumber;

  if (password.length >= 12 && hasMixedCaseAndNumbers && hasSpecial) return 'strong';
  if (password.length >= 12 || hasMixedCaseAndNumbers) return 'fair';
  return 'weak';
}

const STRENGTH_CONFIG: Record<PasswordStrength, { color: string; bg: string; label: string; width: string }> = {
  too_short: { color: '#ef4444', bg: '#ef444440', label: 'Too short', width: '25%' },
  weak:      { color: '#f97316', bg: '#f9731640', label: 'Weak', width: '50%' },
  fair:      { color: '#eab308', bg: '#eab30840', label: 'Fair', width: '75%' },
  strong:    { color: '#22c55e', bg: '#22c55e40', label: 'Strong', width: '100%' },
};

function PasswordStrengthBar({ password }: { password: string }) {
  const strength = useMemo(() => getPasswordStrength(password), [password]);
  const config = STRENGTH_CONFIG[strength];

  if (!password) return null;

  return (
    <div className="mt-2">
      <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: config.bg }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: config.width, backgroundColor: config.color }}
        />
      </div>
      <p className="text-xs mt-1" style={{ color: config.color }}>
        {config.label}
      </p>
    </div>
  );
}

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
          <span className="text-[#3b82f6]">you don&apos;t know about yet.</span>
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
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [generalError, setGeneralError] = useState('');

  useEffect(() => {
    if (token) router.replace('/onboarding');
  }, [token, router]);

  async function handleGoogleSignup() {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin + '/today' },
    });
    if (error) {
      setGeneralError(error.message);
    }
  }

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setEmailError('');
    setPasswordError('');
    setGeneralError('');

    let hasError = false;

    if (!email.trim()) {
      setEmailError('Email is required');
      hasError = true;
    }

    if (password.length < 8) {
      setPasswordError('Password must be at least 8 characters');
      hasError = true;
    }

    if (hasError) return;

    setStatus('loading');
    try {
      await signUp(email, password, '');
      setStatus('done');
    } catch (err) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Something went wrong — try again';
      // Attempt to show inline errors for known cases
      if (message.toLowerCase().includes('email')) {
        setEmailError(message);
      } else if (message.toLowerCase().includes('password')) {
        setPasswordError(message);
      } else {
        setGeneralError(message);
      }
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

              {/* Google OAuth Button */}
              <button
                type="button"
                onClick={() => void handleGoogleSignup()}
                className="w-full py-3 rounded-xl border border-[#1e293b] bg-[#111827]
                           text-sm text-[#e2e8f0] font-medium
                           hover:border-[#334155] hover:bg-[#1e293b] transition-all
                           flex items-center justify-center gap-3"
              >
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                Sign up with Google
              </button>

              <div className="my-6 flex items-center gap-3">
                <div className="flex-1 h-px bg-[#1e293b]" />
                <span className="text-xs text-[#334155]">or continue with email</span>
                <div className="flex-1 h-px bg-[#1e293b]" />
              </div>

              <form onSubmit={(e) => void handleSignup(e)} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-[#94a3b8] mb-2 uppercase tracking-wider">
                    Work email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => { setEmail(e.target.value); setEmailError(''); }}
                    required
                    autoFocus
                    placeholder="you@company.com"
                    className={`w-full px-4 py-3 rounded-xl bg-[#111827] border
                               text-[#e2e8f0] placeholder-[#334155] text-sm
                               focus:outline-none focus:ring-1 transition-all ${
                                 emailError
                                   ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                                   : 'border-[#1e293b] focus:border-[#3b82f6] focus:ring-[#3b82f6]/30'
                               }`}
                  />
                  {emailError && (
                    <p className="text-xs text-red-400 mt-1.5">{emailError}</p>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#94a3b8] mb-2 uppercase tracking-wider">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={e => { setPassword(e.target.value); setPasswordError(''); }}
                    required
                    placeholder="8+ characters"
                    className={`w-full px-4 py-3 rounded-xl bg-[#111827] border
                               text-[#e2e8f0] placeholder-[#334155] text-sm
                               focus:outline-none focus:ring-1 transition-all ${
                                 passwordError
                                   ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                                   : 'border-[#1e293b] focus:border-[#3b82f6] focus:ring-[#3b82f6]/30'
                               }`}
                  />
                  {passwordError && (
                    <p className="text-xs text-red-400 mt-1.5">{passwordError}</p>
                  )}
                  <PasswordStrengthBar password={password} />
                  <p className="text-xs text-[#334155] mt-1.5">You can always reset this via email.</p>
                </div>

                {generalError && (
                  <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 rounded-xl px-4 py-3 border border-red-400/20">
                    <span className="flex-shrink-0">⚠️</span>
                    <span>{generalError}</span>
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
