'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { Spinner } from '@/components/ui/Spinner';
import Link from 'next/link';
import {
  Map,
  Network,
  Sparkles,
  Wrench,
  ArrowRight,
  Check,
  BarChart3,
  TrendingUp,
  Layers,
} from 'lucide-react';

function LandingPage() {
  return (
    <div className="min-h-screen bg-brand-bg text-brand-text">
      {/* Nav */}
      <nav className="border-b border-brand-border">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <span className="text-xl font-bold text-brand-accent">Enough</span>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm text-brand-text-muted hover:text-brand-text transition-colors"
            >
              Log in
            </Link>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-accent px-4 py-2 text-sm font-medium text-white hover:bg-brand-accent-hover transition-colors"
            >
              Get Started Free
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-24 text-center">
        <h1 className="text-5xl font-bold leading-tight tracking-tight sm:text-6xl">
          Publish Less.{' '}
          <span className="text-brand-accent">Grow More.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-brand-text-muted">
          Every content tool tells you to create more. Enough is the only one that tells
          you when more is less. See your content library as a living ecosystem —
          and make it thrive.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-accent px-6 py-3 text-base font-semibold text-white hover:bg-brand-accent-hover transition-colors"
          >
            See Your Ecosystem Free
            <ArrowRight size={18} />
          </Link>
          <Link
            href="#features"
            className="inline-flex items-center gap-2 rounded-lg border border-brand-border px-6 py-3 text-base font-medium text-brand-text hover:bg-brand-surface transition-colors"
          >
            Learn More
          </Link>
        </div>

        {/* Mock landscape */}
        <div className="mt-16 rounded-xl border border-brand-border bg-brand-surface p-1 shadow-2xl">
          <div className="rounded-lg bg-brand-bg p-8">
            <div className="grid grid-cols-5 gap-3">
              {[
                { state: 'forest', h: 'h-32' },
                { state: 'meadow', h: 'h-24' },
                { state: 'swamp', h: 'h-28' },
                { state: 'seedbed', h: 'h-20' },
                { state: 'desert', h: 'h-16' },
              ].map(({ state, h }, i) => (
                <div
                  key={i}
                  className={`${h} rounded-lg opacity-60`}
                  style={{
                    backgroundColor:
                      state === 'forest' ? '#1a4731'
                      : state === 'meadow' ? '#3d6b3d'
                      : state === 'swamp' ? '#2d3a1f'
                      : state === 'seedbed' ? '#2d5a27'
                      : '#8b7355',
                  }}
                />
              ))}
            </div>
            <p className="mt-4 text-xs text-brand-text-muted text-center">
              Your content ecosystem — forests thrive, swamps need clearing, deserts need revival.
            </p>
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section className="border-t border-brand-border bg-brand-surface/50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold mb-12">How It Works</h2>
          <div className="grid grid-cols-3 gap-8">
            {[
              {
                step: '1',
                title: 'Connect',
                desc: 'Link your CMS, Google Analytics, and Search Console. We ingest your entire content library.',
                icon: Layers,
              },
              {
                step: '2',
                title: 'See',
                desc: 'Your content becomes a living landscape. Forests, swamps, deserts — each cluster tells a story.',
                icon: Map,
              },
              {
                step: '3',
                title: 'Act',
                desc: 'Consolidate swamps, revive deserts, protect forests. Fewer posts, more impact.',
                icon: TrendingUp,
              },
            ].map(({ step, title, desc, icon: Icon }) => (
              <div key={step} className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand-accent/20">
                  <Icon size={24} className="text-brand-accent" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{title}</h3>
                <p className="text-sm text-brand-text-muted">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold mb-12">Built for Content Strategists</h2>
          <div className="grid grid-cols-2 gap-8">
            {[
              {
                icon: Map,
                title: 'The Landscape',
                desc: 'See your entire content library as a living ecosystem. Each cluster is a biome — forests thriving, swamps choking, deserts wasting.',
              },
              {
                icon: Network,
                title: 'Cannibalization Detection',
                desc: 'Find posts competing against each other for the same keywords. Stop fighting yourself in search results.',
              },
              {
                icon: Sparkles,
                title: 'Pre-Publish Oracle',
                desc: 'Before you publish, ask the Oracle. It checks your draft against your entire library and warns you of potential conflicts.',
              },
              {
                icon: Wrench,
                title: 'Consolidation Engine',
                desc: 'AI-powered consolidation plans with redirect maps, merged drafts, and one-click push to WordPress.',
              },
            ].map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-xl border border-brand-border bg-brand-surface p-6"
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-accent/20">
                  <Icon size={20} className="text-brand-accent" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{title}</h3>
                <p className="text-sm text-brand-text-muted">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Social Proof */}
      <section className="border-t border-brand-border bg-brand-surface/50 py-20">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <div className="rounded-xl border border-brand-border bg-brand-surface p-8">
            <BarChart3 size={32} className="mx-auto mb-4 text-brand-accent" />
            <p className="text-2xl font-semibold text-brand-text mb-2">
              Increase traffic 35% by publishing 40% less
            </p>
            <p className="text-sm text-brand-text-muted">
              Content teams using Enough focus on quality over quantity — and the numbers prove it.
            </p>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold mb-12">Simple Pricing</h2>
          <div className="grid grid-cols-3 gap-6">
            {[
              {
                name: 'Free',
                price: '$0',
                features: ['1 site', 'Up to 50 posts', 'Basic landscape', 'Dashboard'],
                cta: 'Get Started Free',
                highlighted: false,
              },
              {
                name: 'Growth',
                price: '$99',
                features: [
                  '1 site',
                  'Up to 500 posts',
                  'Full features',
                  'Pre-Publish Oracle',
                  '5 consolidations/mo',
                  'Weekly reports',
                ],
                cta: 'Start Growth Plan',
                highlighted: true,
              },
              {
                name: 'Scale',
                price: '$299',
                features: [
                  'Up to 10 sites',
                  'Up to 5,000 posts',
                  'Unlimited consolidations',
                  'Impact tracking',
                  'Priority support',
                ],
                cta: 'Start Scale Plan',
                highlighted: false,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={`rounded-xl border p-6 flex flex-col ${
                  plan.highlighted
                    ? 'border-brand-accent bg-brand-accent/5 ring-2 ring-brand-accent'
                    : 'border-brand-border bg-brand-surface'
                }`}
              >
                <h3 className="text-lg font-bold mb-1">{plan.name}</h3>
                <div className="mb-4">
                  <span className="text-3xl font-bold">{plan.price}</span>
                  <span className="text-brand-text-muted">/mo</span>
                </div>
                <ul className="space-y-2 flex-1 mb-6">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm">
                      <Check size={14} className="text-brand-accent shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/register"
                  className={`block w-full rounded-lg py-2.5 text-center text-sm font-medium transition-colors ${
                    plan.highlighted
                      ? 'bg-brand-accent text-white hover:bg-brand-accent-hover'
                      : 'border border-brand-border text-brand-text hover:bg-brand-surface-hover'
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-brand-border py-20">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-3xl font-bold mb-4">
            Your content library is a living ecosystem.
          </h2>
          <p className="text-lg text-brand-text-muted mb-8">
            Time to see it.
          </p>
          <Link
            href="/register"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-accent px-8 py-3 text-base font-semibold text-white hover:bg-brand-accent-hover transition-colors"
          >
            Get Started Free
            <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-brand-border py-8">
        <div className="mx-auto max-w-6xl px-6 flex items-center justify-between">
          <span className="text-sm text-brand-text-muted">
            © {new Date().getFullYear()} Enough. Publish less. Grow more.
          </span>
          <div className="flex items-center gap-6 text-sm text-brand-text-muted">
            <Link href="/login" className="hover:text-brand-text transition-colors">
              Log in
            </Link>
            <Link href="/register" className="hover:text-brand-text transition-colors">
              Sign up
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace('/landscape');
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return <LandingPage />;
}
