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

        {/* Landscape SVG Illustration */}
        <div className="mt-16 rounded-xl border border-brand-border bg-brand-surface p-1 shadow-2xl">
          <div className="rounded-lg bg-brand-bg overflow-hidden">
            <svg viewBox="0 0 900 320" className="w-full" xmlns="http://www.w3.org/2000/svg">
              {/* Sky gradient */}
              <defs>
                <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0f172a" />
                  <stop offset="100%" stopColor="#1e293b" />
                </linearGradient>
                <linearGradient id="forestGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#166534" />
                  <stop offset="100%" stopColor="#14532d" />
                </linearGradient>
                <linearGradient id="swampGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#365314" />
                  <stop offset="100%" stopColor="#1a2e05" />
                </linearGradient>
                <linearGradient id="desertGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#92400e" />
                  <stop offset="100%" stopColor="#78350f" />
                </linearGradient>
                <linearGradient id="seedbedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#15803d" />
                  <stop offset="100%" stopColor="#166534" />
                </linearGradient>
              </defs>
              <rect width="900" height="320" fill="url(#sky)" />

              {/* Stars */}
              {[
                [120, 25], [280, 15], [400, 35], [550, 20], [700, 30], [820, 18],
                [60, 50], [350, 55], [650, 45], [780, 55],
              ].map(([cx, cy], i) => (
                <circle key={`star-${i}`} cx={cx} cy={cy} r={1} fill="#94a3b8" opacity={0.6} />
              ))}

              {/* ── FOREST region (left) ── */}
              {/* Hills */}
              <path d="M0 200 Q50 140 100 180 Q150 130 200 170 Q230 160 260 190 L260 320 L0 320Z"
                    fill="url(#forestGrad)" opacity={0.9} />
              {/* Trees — tall triangles */}
              {[[30, 195], [55, 185], [80, 190], [110, 175], [135, 180], [160, 168], [185, 172], [210, 165], [240, 185]].map(
                ([x, y], i) => (
                  <g key={`tree-${i}`}>
                    <polygon points={`${x},${y - 45} ${x - 10},${y} ${x + 10},${y}`} fill="#22c55e" opacity={0.7 + (i % 3) * 0.1} />
                    <polygon points={`${x},${y - 60} ${x - 8},${y - 25} ${x + 8},${y - 25}`} fill="#4ade80" opacity={0.6} />
                    <rect x={x - 2} y={y} width={4} height={8} fill="#854d0e" opacity={0.6} />
                  </g>
                )
              )}
              {/* Forest label */}
              <text x="130" y="290" textAnchor="middle" fill="#4ade80" fontSize="11" fontFamily="sans-serif" fontWeight="600" opacity={0.8}>FOREST</text>
              <text x="130" y="305" textAnchor="middle" fill="#86efac" fontSize="8" fontFamily="sans-serif" opacity={0.5}>Thriving</text>

              {/* ── SWAMP region ── */}
              <path d="M260 190 Q290 210 330 200 Q370 215 410 195 Q430 200 440 210 L440 320 L260 320Z"
                    fill="url(#swampGrad)" opacity={0.85} />
              {/* Swamp vegetation — messy, tangled */}
              {[[275, 200], [305, 195], [330, 200], [360, 198], [390, 195], [415, 200]].map(
                ([x, y], i) => (
                  <g key={`swamp-${i}`}>
                    {/* Tangled roots/vines */}
                    <path d={`M${x} ${y} Q${x - 5} ${y - 15} ${x + 3} ${y - 25} Q${x + 8} ${y - 30} ${x - 2} ${y - 35}`}
                          fill="none" stroke="#65a30d" strokeWidth={1.5} opacity={0.5} />
                    <path d={`M${x + 5} ${y} Q${x + 12} ${y - 20} ${x + 2} ${y - 28}`}
                          fill="none" stroke="#4d7c0f" strokeWidth={1} opacity={0.4} />
                    <circle cx={x} cy={y + 5} r={5} fill="#1a2e05" opacity={0.3} />
                  </g>
                )
              )}
              {/* Murky water highlights */}
              <ellipse cx="350" cy="245" rx="60" ry="4" fill="#365314" opacity={0.3} />
              <text x="350" y="290" textAnchor="middle" fill="#a3e635" fontSize="11" fontFamily="sans-serif" fontWeight="600" opacity={0.8}>SWAMP</text>
              <text x="350" y="305" textAnchor="middle" fill="#bef264" fontSize="8" fontFamily="sans-serif" opacity={0.5}>Cannibalized</text>

              {/* ── DESERT region ── */}
              <path d="M440 210 Q480 185 530 195 Q580 175 630 195 Q650 190 660 200 L660 320 L440 320Z"
                    fill="url(#desertGrad)" opacity={0.85} />
              {/* Sand dunes */}
              <path d="M450 230 Q490 215 530 225 Q570 210 610 220 Q640 215 660 225 L660 250 L440 250Z"
                    fill="#b45309" opacity={0.3} />
              {/* Dead stumps */}
              {[[475, 215], [520, 205], [565, 200], [610, 210]].map(
                ([x, y], i) => (
                  <g key={`stump-${i}`}>
                    <rect x={x - 2} y={y - 10} width={4} height={14} fill="#78350f" opacity={0.5} />
                    <line x1={x - 5} y1={y - 7} x2={x} y2={y - 12} stroke="#78350f" strokeWidth={1.5} opacity={0.4} />
                    <line x1={x + 5} y1={y - 5} x2={x} y2={y - 10} stroke="#78350f" strokeWidth={1.5} opacity={0.4} />
                  </g>
                )
              )}
              {/* Tumbleweed */}
              <circle cx="555" cy="225" r={6} fill="none" stroke="#a16207" strokeWidth={1} opacity={0.4} strokeDasharray="2 2" />
              <text x="550" y="290" textAnchor="middle" fill="#fbbf24" fontSize="11" fontFamily="sans-serif" fontWeight="600" opacity={0.8}>DESERT</text>
              <text x="550" y="305" textAnchor="middle" fill="#fde68a" fontSize="8" fontFamily="sans-serif" opacity={0.5}>Declining</text>

              {/* ── SEEDBED region (right) ── */}
              <path d="M660 200 Q700 185 750 195 Q800 180 850 190 Q875 195 900 200 L900 320 L660 320Z"
                    fill="url(#seedbedGrad)" opacity={0.85} />
              {/* Small sprouts */}
              {[[690, 200], [720, 192], [755, 188], [790, 185], [825, 190], [860, 195]].map(
                ([x, y], i) => (
                  <g key={`sprout-${i}`}>
                    <line x1={x} y1={y} x2={x} y2={y - 12 - (i % 3) * 4} stroke="#22c55e" strokeWidth={1.5} opacity={0.6} />
                    <ellipse cx={x - 4} cy={y - 12 - (i % 3) * 4} rx={4} ry={2.5} fill="#4ade80" opacity={0.5} />
                    <ellipse cx={x + 4} cy={y - 14 - (i % 3) * 4} rx={4} ry={2.5} fill="#86efac" opacity={0.4} />
                  </g>
                )
              )}
              {/* Soil texture */}
              <path d="M660 240 Q720 235 780 240 Q840 235 900 240 L900 260 L660 260Z"
                    fill="#15803d" opacity={0.15} />
              <text x="780" y="290" textAnchor="middle" fill="#4ade80" fontSize="11" fontFamily="sans-serif" fontWeight="600" opacity={0.8}>SEEDBED</text>
              <text x="780" y="305" textAnchor="middle" fill="#86efac" fontSize="8" fontFamily="sans-serif" opacity={0.5}>New Growth</text>

              {/* Terrain divider lines */}
              <line x1="260" y1="180" x2="260" y2="320" stroke="#334155" strokeWidth={0.5} opacity={0.3} />
              <line x1="440" y1="195" x2="440" y2="320" stroke="#334155" strokeWidth={0.5} opacity={0.3} />
              <line x1="660" y1="195" x2="660" y2="320" stroke="#334155" strokeWidth={0.5} opacity={0.3} />
            </svg>
            <p className="py-3 text-xs text-brand-text-muted text-center">
              Your content ecosystem — forests thrive, swamps need clearing, deserts need revival, seedbeds hold new growth.
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
      router.replace('/today');
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
