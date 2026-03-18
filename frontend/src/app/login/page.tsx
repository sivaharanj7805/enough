'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';

export default function LoginPage() {
  const router = useRouter();
  const { token, signIn, signInWithMagicLink } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'magic' | 'password'>('magic');
  const [status, setStatus] = useState<'idle' | 'loading' | 'sent' | 'error'>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (token) router.replace('/dashboard');
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
      setError(err instanceof Error ? err.message : 'Failed to send magic link');
    }
  }

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setStatus('loading');
    setError('');
    try {
      await signIn(email, password);
      router.replace('/dashboard');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Invalid credentials');
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-10">
          <span className="text-3xl font-bold tracking-widest text-[#22c55e]">ENOUGH</span>
          <p className="text-[#64748b] text-sm mt-1">Content Ecosystem Intelligence</p>
        </div>

        <div className="bg-[#111827] rounded-2xl border border-[#1e293b] p-8">
          <h1 className="text-[#e2e8f0] text-xl font-semibold mb-1">Sign in</h1>
          <p className="text-[#64748b] text-sm mb-6">Access your content intelligence dashboard</p>

          {/* Mode toggle */}
          <div className="flex rounded-lg bg-[#0a0f1a] p-1 mb-6">
            {(['magic', 'password'] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setStatus('idle'); setError(''); }}
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                  mode === m
                    ? 'bg-[#1e293b] text-[#e2e8f0]'
                    : 'text-[#64748b] hover:text-[#94a3b8]'
                }`}
              >
                {m === 'magic' ? 'Magic Link' : 'Password'}
              </button>
            ))}
          </div>

          {status === 'sent' ? (
            <div className="text-center py-6">
              <div className="text-4xl mb-3">📬</div>
              <p className="text-[#e2e8f0] font-medium">Check your inbox</p>
              <p className="text-[#64748b] text-sm mt-1">
                We sent a magic link to{' '}
                <span className="text-[#22c55e]">{email}</span>
              </p>
              <button
                onClick={() => setStatus('idle')}
                className="mt-4 text-sm text-[#64748b] hover:text-[#94a3b8] underline"
              >
                Try a different email
              </button>
            </div>
          ) : (
            <form
              onSubmit={mode === 'magic' ? handleMagicLink : handlePassword}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  placeholder="you@company.com"
                  className="w-full px-3 py-2.5 rounded-lg bg-[#0a0f1a] border border-[#1e293b]
                             text-[#e2e8f0] placeholder-[#334155] text-sm
                             focus:outline-none focus:border-[#22c55e] transition-colors"
                />
              </div>

              {mode === 'password' && (
                <div>
                  <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    placeholder="••••••••"
                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0f1a] border border-[#1e293b]
                               text-[#e2e8f0] placeholder-[#334155] text-sm
                               focus:outline-none focus:border-[#22c55e] transition-colors"
                  />
                </div>
              )}

              {error && (
                <p className="text-red-400 text-xs bg-red-400/10 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={status === 'loading'}
                className="w-full py-2.5 rounded-lg bg-[#22c55e] text-[#0a0f1a] font-semibold
                           text-sm hover:bg-[#16a34a] transition-colors
                           disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {status === 'loading'
                  ? 'Sending…'
                  : mode === 'magic'
                  ? 'Send Magic Link'
                  : 'Sign In'}
              </button>
            </form>
          )}

          <p className="text-center text-xs text-[#334155] mt-6">
            No account?{' '}
            <a href="/onboarding" className="text-[#22c55e] hover:underline">
              Analyze your blog for free →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
