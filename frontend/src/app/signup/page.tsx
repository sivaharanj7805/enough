'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';

export default function SignupPage() {
  const router = useRouter();
  const { token, signUp } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (token) router.replace('/onboarding');
  }, [token, router]);

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
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
      setError(err instanceof Error ? err.message : 'Signup failed');
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <span className="text-3xl font-bold tracking-widest text-[#3b82f6]">ENOUGH</span>
          <p className="text-[#64748b] text-sm mt-1">Content Ecosystem Intelligence</p>
        </div>

        <div className="bg-[#111827] rounded-2xl border border-[#1e293b] p-8">
          {status === 'done' ? (
            <div className="text-center py-6">
              <div className="text-4xl mb-3">📬</div>
              <p className="text-[#e2e8f0] font-medium">Verify your email</p>
              <p className="text-[#64748b] text-sm mt-2">
                We sent a confirmation link to{' '}
                <span className="text-[#3b82f6]">{email}</span>.
                Click it to activate your account.
              </p>
              <a
                href="/login"
                className="mt-4 inline-block text-sm text-[#3b82f6] hover:underline"
              >
                Back to sign in →
              </a>
            </div>
          ) : (
            <>
              <h1 className="text-[#e2e8f0] text-xl font-semibold mb-1">Create account</h1>
              <p className="text-[#64748b] text-sm mb-6">Start your free content ecosystem audit</p>

              <form onSubmit={(e) => void handleSignup(e)} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    placeholder="you@company.com"
                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0f1a] border border-[#1e293b] text-[#e2e8f0]
                               placeholder-[#334155] text-sm focus:outline-none focus:border-[#3b82f6] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    placeholder="8+ characters"
                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0f1a] border border-[#1e293b] text-[#e2e8f0]
                               placeholder-[#334155] text-sm focus:outline-none focus:border-[#3b82f6] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">Confirm password</label>
                  <input
                    type="password"
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    required
                    placeholder="Same password again"
                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0f1a] border border-[#1e293b] text-[#e2e8f0]
                               placeholder-[#334155] text-sm focus:outline-none focus:border-[#3b82f6] transition-colors"
                  />
                </div>

                {error && (
                  <p className="text-red-400 text-xs bg-red-400/10 rounded-lg px-3 py-2">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={status === 'loading'}
                  className="w-full py-2.5 rounded-lg bg-[#3b82f6] text-white font-semibold text-sm
                             hover:bg-[#2563eb] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {status === 'loading' ? 'Creating account…' : 'Create account'}
                </button>
              </form>

              <p className="text-center text-xs text-[#334155] mt-6">
                Already have an account?{' '}
                <a href="/login" className="text-[#3b82f6] hover:underline">Sign in →</a>
              </p>
            </>
          )}
        </div>

        <p className="text-center text-[10px] text-[#1e293b] mt-6">
          By signing up you agree to our terms. No credit card required.
        </p>
      </div>
    </div>
  );
}
