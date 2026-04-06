'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/hooks/useAuth';
import { Spinner } from '@/components/ui/Spinner';
import { apiUrl } from '@/lib/api';
import { freeAudit } from '@/lib/copy';
import Link from 'next/link';
import {
  Shield,
  Clock,
  Zap,
  Link as LinkIcon,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Loader2,
  ArrowRight,
  Check,
  AlertTriangle,
  TrendingDown,
  Trash2,
  GitCompare,
} from 'lucide-react';

/* ─── Validation ─── */
const URL_RE = /^https?:\/\/.+\..+/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/* ─── FAQ Data ─── */
const FAQ_ITEMS = [
  {
    q: 'Is it read-only?',
    a: 'Yes. We crawl and read your blog content, but we never modify, publish, or delete anything on your site.',
  },
  {
    q: 'How long does analysis take?',
    a: '20-25 minutes for most blogs. You can browse partial results while the pipeline runs.',
  },
  {
    q: 'Do I need to cancel my existing SEO tool?',
    a: "No. Tended complements tools like Ahrefs, SEMrush, and Surfer. We focus specifically on content ecosystem health \u2014 the cannibalization, decay, and structural problems they don\u2019t catch.",
  },
  {
    q: "What if it\u2019s not worth it?",
    a: "We offer a 30-day money-back guarantee, no questions asked. If you don\u2019t find value, we\u2019ll refund you.",
  },
  {
    q: 'Can I try it first?',
    a: "Yes. Enter your blog URL above and we\u2019ll send you a free audit report with your health score, AI Readiness grade, and issue count. No credit card required.",
  },
  {
    q: 'What is AI Readiness and why does it matter?',
    a: "Google AI Overviews now appear on ~50% of searches and cut organic CTR by 34%. Tended scores every post on 4 AI dimensions: citability, E-E-A-T, schema markup, and extraction structure. We tell you exactly which posts AI systems skip and what to change so ChatGPT, Perplexity, and Google AI Overviews cite your content.",
  },
];

/* ─── Pricing Data ─── */
const PLANS = {
  growth: {
    name: 'Growth',
    monthlyPrice: 149,
    annualPrice: 1490,
    monthlyEquiv: '$124.17',
    features: [
      '500 posts',
      '1 site',
      'Full analysis pipeline',
      'Weekly digest email',
      'Pre-Publish Oracle',
      'GSC & GA4 integration',
      'Unlimited recommendations',
      'Impact tracking',
      'PDF reports',
      'Weekly re-analysis',
    ],
  },
  scale: {
    name: 'Scale',
    monthlyPrice: 349,
    annualPrice: 3490,
    monthlyEquiv: '$290.83',
    features: [
      '2,000 posts',
      '3 sites',
      'White-label reports',
      'Priority pipeline',
      'Consolidation drafts',
      'API access',
      'Daily re-analysis',
      'Everything in Growth',
    ],
  },
};

/* ─── Audit Progress Component ─── */
const AUDIT_STAGES = [
  { label: 'Crawling posts', duration: 5 },
  { label: 'Understanding content', duration: 7 },
  { label: 'Running analysis', duration: 5 },
  { label: 'Scoring health', duration: 3 },
  { label: 'Building your report', duration: 3 },
];

function AuditProgress({ domain }: { domain: string }) {
  const [activeStage, setActiveStage] = useState(0);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Simulate progress through stages over ~20 minutes
    const totalDuration = AUDIT_STAGES.reduce((s, st) => s + st.duration, 0); // minutes
    const tickMs = 2000; // update every 2s
    let elapsed = 0;

    const timer = setInterval(() => {
      elapsed += tickMs / 1000 / 60; // in minutes
      let cumulative = 0;
      let stage = 0;
      for (let i = 0; i < AUDIT_STAGES.length; i++) {
        cumulative += AUDIT_STAGES[i].duration;
        if (elapsed < cumulative) { stage = i; break; }
        if (i === AUDIT_STAGES.length - 1) stage = i;
      }
      setActiveStage(stage);
      const pct = Math.min(Math.round((elapsed / totalDuration) * 100), 100);
      setProgress(pct);
      if (pct >= 100) {
        setDone(true);
        clearInterval(timer);
      }
    }, tickMs);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="mt-10 rounded-xl border border-[#23262F] bg-[#13151B] p-6 text-left">
      <div className="flex items-center gap-3 mb-4">
        {done ? (
          <Check size={20} className="text-green-400" />
        ) : (
          <Loader2 size={20} className="animate-spin text-[#3B82F6]" />
        )}
        <p className="text-lg font-semibold text-[#E8EAED]">
          {done ? `Report sent for ${domain}` : `Analyzing ${domain}`}
        </p>
      </div>

      {/* Progress bar */}
      <div className="w-full h-2 rounded-full bg-[#23262F] overflow-hidden mb-5">
        <div
          className="h-full rounded-full bg-[#3B82F6] transition-all duration-1000 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Stages */}
      <div className="space-y-3">
        {AUDIT_STAGES.map((stage, i) => (
          <div key={stage.label} className="flex items-center gap-3">
            {i < activeStage || done ? (
              <Check size={16} className="text-green-400 flex-shrink-0" />
            ) : i === activeStage ? (
              <Loader2 size={16} className="animate-spin text-[#3B82F6] flex-shrink-0" />
            ) : (
              <div className="w-4 h-4 rounded-full border border-[#23262F] flex-shrink-0" />
            )}
            <span className={`text-sm ${i <= activeStage || done ? 'text-[#E8EAED]' : 'text-[#9BA1AD]/50'}`}>
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-5 pt-4 border-t border-[#23262F]">
        {done ? (
          <p className="text-[13px] text-green-400">
            Your report should be in your inbox. Check spam if you don&apos;t see it.
          </p>
        ) : (
          <>
            <p className="text-[13px] text-[#9BA1AD]">
              Your PDF report will arrive at your inbox in ~20 minutes.
            </p>
            <p className="mt-1 text-[13px] text-[#9BA1AD]">
              Add <span className="font-medium text-[#E8EAED]">hello@usetended.io</span> to your contacts so it doesn&apos;t go to spam.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Landing Page Component ─── */
function LandingPage({ onAuditSubmitted }: { onAuditSubmitted: () => void }) {
  const [url, setUrl] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ url?: string; email?: string; form?: string }>({});
  const [submitted, setSubmitted] = useState(false);
  const [submittedDomain, setSubmittedDomain] = useState('');
  const [annual, setAnnual] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const normalizeUrl = (raw: string): string => {
    const trimmed = raw.trim();
    if (!trimmed) return trimmed;
    return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  };

  const validate = useCallback(() => {
    const errs: { url?: string; email?: string } = {};
    if (!URL_RE.test(normalizeUrl(url))) errs.url = 'Enter a valid URL starting with http:// or https://';
    if (!EMAIL_RE.test(email)) errs.email = 'Enter a valid email address';
    return errs;
  }, [url, email]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setLoading(true);
    setErrors({});
    const finalUrl = normalizeUrl(url);
    try {
      const res = await fetch(apiUrl('/sites/audit-report/pdf'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: finalUrl, email }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        if (res.status === 429) {
          throw new Error(freeAudit.rateLimitError);
        }
        throw new Error(data?.detail || data?.message || 'Something went wrong. Please try again.');
      }
      // Extract domain for display
      let domain = finalUrl;
      try { domain = new URL(finalUrl).hostname; } catch { /* use finalUrl */ }
      setSubmittedDomain(domain);
      // 200 with PDF binary = existing site, trigger download
      if (res.status === 200 && res.headers.get('content-type')?.includes('application/pdf')) {
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `tended-audit-${domain}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(blobUrl);
      }
      // Show progress screen (202 = pipeline running, 200 = PDF downloaded)
      setSubmitted(true);
      onAuditSubmitted();
    } catch (err: unknown) {
      setErrors({ form: err instanceof Error ? err.message : 'Something went wrong. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  const toggleFaq = (i: number) => {
    setOpenFaq(openFaq === i ? null : i);
  };

  return (
    <div className="min-h-screen bg-[#0B0D11] text-[#E8EAED]">
      {/* ════════════════════════════════════════════════
          1. HERO
         ════════════════════════════════════════════════ */}
      <section className="py-24 px-6">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-[48px] font-semibold tracking-tight leading-[1.1]">
            See your content health score, every post cannibalizing another, and your top 3 fixes
            <span className="text-[#3B82F6]"> &mdash; in your inbox in 25 minutes. Free.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-[14px] leading-relaxed text-[#9BA1AD]">
            Google AI Overviews cut organic CTR by 34%. Tended finds the cannibalization, decay, and dead weight your SEO tool misses &mdash; plus your AI Readiness score showing why ChatGPT doesn&apos;t cite you.
          </p>
          <p className="mx-auto mt-3 max-w-2xl text-[13px] font-medium text-[#E8EAED]">
            Actual meta descriptions to copy. Specific posts to merge. Redirect maps ready to implement.
          </p>

          {/* What You'll Get */}
          <div className="mx-auto mt-10 grid max-w-3xl grid-cols-1 md:grid-cols-3 gap-4 text-left">
            <div className="rounded-xl border border-[#23262F] bg-[#13151B] p-5">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-[#3B82F6]/10">
                <BarChart3 size={20} className="text-[#3B82F6]" />
              </div>
              <p className="text-[24px] font-bold text-[#E8EAED]">0-100</p>
              <h3 className="text-[14px] font-semibold mt-1">Content Health Score</h3>
              <p className="text-[13px] leading-relaxed text-[#9BA1AD] mt-1">Your overall content ecosystem health at a glance</p>
            </div>
            <div className="rounded-xl border border-[#23262F] bg-[#13151B] p-5">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-[#3B82F6]/10">
                <GitCompare size={20} className="text-[#3B82F6]" />
              </div>
              <h3 className="text-[14px] font-semibold">Cannibalization Detection</h3>
              <p className="text-[13px] leading-relaxed text-[#9BA1AD] mt-1">Every pair of posts competing for the same keywords</p>
            </div>
            <div className="rounded-xl border border-[#23262F] bg-[#13151B] p-5">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-[#3B82F6]/10">
                <Zap size={20} className="text-[#3B82F6]" />
              </div>
              <h3 className="text-[14px] font-semibold">AI Citability Score</h3>
              <p className="text-[13px] leading-relaxed text-[#9BA1AD] mt-1">How likely AI systems are to cite your content vs. industry average</p>
            </div>
          </div>

          {/* Audit Form */}
          {submitted ? (
            <AuditProgress domain={submittedDomain} />
          ) : (
            <form onSubmit={(e) => void handleSubmit(e)} className="mt-10">
              <div className="flex flex-col sm:flex-row items-stretch gap-3">
                <div className="flex-1">
                  <input
                    type="text"
                    placeholder="https://yourblog.com"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="w-full rounded-lg border border-[#23262F] bg-[#13151B] px-4 py-3 text-[14px] text-[#E8EAED] placeholder-[#9BA1AD]/50 outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] transition-colors"
                  />
                  {errors.url && (
                    <p className="mt-1 text-left text-xs text-red-400">{errors.url}</p>
                  )}
                </div>
                <div className="flex-1">
                  <input
                    type="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-lg border border-[#23262F] bg-[#13151B] px-4 py-3 text-[14px] text-[#E8EAED] placeholder-[#9BA1AD]/50 outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] transition-colors"
                  />
                  {errors.email && (
                    <p className="mt-1 text-left text-xs text-red-400">{errors.email}</p>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#3B82F6] px-6 py-3 text-[14px] font-semibold text-white hover:bg-[#2563EB] disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                >
                  {loading ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Requesting...
                    </>
                  ) : (
                    'Get Free Audit + AI Score'
                  )}
                </button>
              </div>
              {errors.form && (
                <p className="mt-3 text-sm text-red-400">{errors.form}</p>
              )}
            </form>
          )}

          {/* Secondary CTA */}
          <div className="mt-4">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 rounded-lg border border-[#23262F] px-6 py-3 text-[14px] font-medium text-[#E8EAED] hover:bg-[#13151B] transition-colors"
            >
              Subscribe &amp; Start Fixing
              <ArrowRight size={14} />
            </Link>
          </div>

          {/* Trust badges */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-6 text-[12px] text-[#9BA1AD]">
            <span className="inline-flex items-center gap-1.5">
              <Shield size={14} className="text-[#3B82F6]" />
              Read-only
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Check size={14} className="text-[#3B82F6]" />
              30-day money-back
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Shield size={14} className="text-[#3B82F6]" />
              Your data stays private
            </span>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          2. SOCIAL PROOF BAR
         ════════════════════════════════════════════════ */}
      <section className="border-y border-[#23262F] bg-[#13151B]/60 py-8">
        <div className="mx-auto max-w-5xl px-6">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 sm:gap-12 text-center">
            <div>
              <p className="text-lg font-semibold text-[#E8EAED]">958 posts</p>
              <p className="text-[12px] text-[#9BA1AD]">Analyzed on Close.com&apos;s blog</p>
            </div>
            <div className="hidden sm:block h-8 w-px bg-[#23262F]" />
            <div>
              <p className="text-lg font-semibold text-[#E8EAED]">200 cannibalization pairs</p>
              <p className="text-[12px] text-[#9BA1AD]">and 24 exact duplicates found</p>
            </div>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          3. PROBLEM STATEMENT
         ════════════════════════════════════════════════ */}
      <section className="py-24 px-6">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-[28px] font-semibold mb-14">
            Three problems killing your organic traffic
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: AlertTriangle,
                title: 'Posts competing against each other',
                desc: 'Multiple articles target the same keywords. Google picks one; the rest cannibalize each other.',
              },
              {
                icon: TrendingDown,
                title: 'Content decaying over time',
                desc: 'Posts that once ranked are quietly losing traffic. Without monitoring, you won\u2019t notice until it\u2019s too late.',
              },
              {
                icon: Trash2,
                title: 'Dead weight dragging you down',
                desc: 'Thin, outdated, and duplicate pages dilute your domain authority and waste crawl budget.',
              },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="rounded-xl border border-[#23262F] bg-[#13151B] p-6">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                  <Icon size={20} className="text-red-400" />
                </div>
                <h3 className="text-[14px] font-semibold mb-2">{title}</h3>
                <p className="text-[14px] leading-relaxed text-[#9BA1AD]">{desc}</p>
              </div>
            ))}
          </div>
          <p className="mt-10 text-center text-[#3B82F6] font-semibold text-lg">
            We find all of it in 25 minutes.
          </p>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          4. HOW IT WORKS
         ════════════════════════════════════════════════ */}
      <section className="py-24 px-6 border-t border-[#23262F]">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-[28px] font-semibold mb-14">How it works</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              {
                step: '1',
                icon: LinkIcon,
                title: 'Connect your blog',
                desc: 'Paste your URL. We read your sitemap and crawl every post. Read-only \u2014 we never touch your content.',
              },
              {
                step: '2',
                icon: BarChart3,
                title: 'We analyze everything',
                desc: 'Embeddings, clustering, health scoring, cannibalization detection, AI readiness. 25 minutes, fully automated.',
              },
              {
                step: '3',
                icon: Shield,
                title: 'Get your AI Readiness score',
                desc: 'Find out why ChatGPT doesn\u2019t cite you. See which posts are invisible to AI and what to change.',
              },
              {
                step: '4',
                icon: Zap,
                title: 'Act on specific fixes',
                desc: 'Actual meta descriptions to copy. Specific posts to merge. FAQ sections to add. Redirect maps ready to implement.',
              },
            ].map(({ step, icon: Icon, title, desc }) => (
              <div key={step} className="text-center">
                <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-[#3B82F6]/15">
                  <Icon size={24} className="text-[#3B82F6]" />
                </div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
                  Step {step}
                </div>
                <h3 className="text-[16px] font-semibold mb-2">{title}</h3>
                <p className="text-[14px] leading-relaxed text-[#9BA1AD]">{desc}</p>
              </div>
            ))}
          </div>

          {/* Product screenshot placeholder */}
          <div
            className="mt-16 rounded-xl border border-[#23262F] overflow-hidden shadow-2xl shadow-[#3B82F6]/5 bg-[#0F1117] relative"
            style={{ aspectRatio: '16/9' }}
            role="img"
            aria-label="Tended ecosystem landscape — interactive visualization of your content clusters, health scores, and cannibalization patterns"
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <svg viewBox="0 0 800 450" className="w-full h-full opacity-60" xmlns="http://www.w3.org/2000/svg">
                {/* Cluster nodes */}
                <circle cx="200" cy="180" r="45" fill="#3B82F6" opacity="0.15" stroke="#3B82F6" strokeWidth="1" />
                <circle cx="200" cy="180" r="6" fill="#3B82F6" />
                <circle cx="360" cy="120" r="60" fill="#22C55E" opacity="0.12" stroke="#22C55E" strokeWidth="1" />
                <circle cx="360" cy="120" r="7" fill="#22C55E" />
                <circle cx="550" cy="200" r="50" fill="#F97316" opacity="0.12" stroke="#F97316" strokeWidth="1" />
                <circle cx="550" cy="200" r="6" fill="#F97316" />
                <circle cx="450" cy="300" r="40" fill="#8B5CF6" opacity="0.12" stroke="#8B5CF6" strokeWidth="1" />
                <circle cx="450" cy="300" r="5" fill="#8B5CF6" />
                <circle cx="650" cy="340" r="35" fill="#3B82F6" opacity="0.12" stroke="#3B82F6" strokeWidth="1" />
                <circle cx="650" cy="340" r="5" fill="#3B82F6" />
                <circle cx="150" cy="330" r="30" fill="#EAB308" opacity="0.12" stroke="#EAB308" strokeWidth="1" />
                <circle cx="150" cy="330" r="5" fill="#EAB308" />
                {/* Connections */}
                <line x1="200" y1="180" x2="360" y2="120" stroke="#3B82F6" strokeWidth="0.5" opacity="0.3" />
                <line x1="360" y1="120" x2="550" y2="200" stroke="#22C55E" strokeWidth="0.5" opacity="0.3" />
                <line x1="550" y1="200" x2="450" y2="300" stroke="#F97316" strokeWidth="0.5" opacity="0.3" />
                <line x1="450" y1="300" x2="650" y2="340" stroke="#8B5CF6" strokeWidth="0.5" opacity="0.3" />
                <line x1="200" y1="180" x2="150" y2="330" stroke="#EAB308" strokeWidth="0.5" opacity="0.3" />
                <line x1="150" y1="330" x2="450" y2="300" stroke="#EAB308" strokeWidth="0.5" opacity="0.3" />
                {/* Scatter dots */}
                <circle cx="180" cy="160" r="2" fill="#3B82F6" opacity="0.5" />
                <circle cx="220" cy="195" r="2" fill="#3B82F6" opacity="0.5" />
                <circle cx="340" cy="105" r="2" fill="#22C55E" opacity="0.5" />
                <circle cx="380" cy="140" r="2" fill="#22C55E" opacity="0.5" />
                <circle cx="530" cy="185" r="2" fill="#F97316" opacity="0.5" />
                <circle cx="570" cy="220" r="2" fill="#F97316" opacity="0.5" />
                <circle cx="435" cy="285" r="2" fill="#8B5CF6" opacity="0.5" />
                <circle cx="465" cy="315" r="2" fill="#8B5CF6" opacity="0.5" />
              </svg>
            </div>
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-[#0F1117]/80 backdrop-blur px-4 py-2 rounded-lg border border-[#23262F]">
              <span className="text-xs text-[#9BA1AD]">Live ecosystem visualization — available after analysis</span>
            </div>
          </div>
          <p className="text-center mt-4 text-[13px] text-[#9BA1AD]">
            Your content ecosystem, visualized. Every cluster, every connection, every problem.
          </p>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          5. PRICING
         ════════════════════════════════════════════════ */}
      <section className="py-24 px-6 border-t border-[#23262F]">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-center text-[28px] font-semibold mb-4">Simple, transparent pricing</h2>
          <p className="text-center text-[14px] text-[#9BA1AD] mb-4">
            30-day money-back guarantee on every plan.
          </p>
          <p className="text-center text-[14px] font-medium text-[#E8EAED] mb-8">
            Built for SEO agencies and content teams managing 50+ posts.
          </p>

          {/* Annual toggle */}
          <div className="flex items-center justify-center gap-3 mb-10">
            <span className={`text-[14px] ${!annual ? 'text-[#E8EAED]' : 'text-[#9BA1AD]'}`}>Monthly</span>
            <button
              onClick={() => setAnnual(!annual)}
              className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${annual ? 'bg-[#3B82F6]' : 'bg-[#23262F]'
                }`}
              aria-label="Toggle annual billing"
            >
              <span
                className={`inline-block h-5 w-5 rounded-full bg-white transition-transform ${annual ? 'translate-x-6' : 'translate-x-1'
                  }`}
              />
            </button>
            <span className={`text-[14px] ${annual ? 'text-[#E8EAED]' : 'text-[#9BA1AD]'}`}>
              Annual
            </span>
            {annual && (
              <span className="rounded-full bg-green-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-green-400">
                2 months free
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Growth */}
            <div className="rounded-xl border border-[#3B82F6] bg-[#13151B] p-6 ring-2 ring-[#3B82F6] flex flex-col relative">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                <span className="rounded-full bg-[#3B82F6] px-3 py-1 text-[11px] font-bold text-white uppercase tracking-wider">
                  Most Popular
                </span>
              </div>
              <h3 className="text-lg font-semibold">{PLANS.growth.name}</h3>
              <div className="mt-2 mb-1">
                <span className="text-4xl font-bold">
                  ${annual ? PLANS.growth.annualPrice.toLocaleString() : PLANS.growth.monthlyPrice}
                </span>
                <span className="text-[#9BA1AD] text-[14px]">
                  /{annual ? 'year' : 'mo'}
                </span>
              </div>
              {annual && (
                <p className="text-[12px] text-[#9BA1AD] mb-3">
                  Instead of ${(PLANS.growth.monthlyPrice * 12).toLocaleString()}/year
                </p>
              )}
              {!annual && <div className="mb-3" />}
              <ul className="space-y-2.5 flex-1 mb-6">
                {PLANS.growth.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-[14px]">
                    <Check size={14} className="text-[#3B82F6] shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2 mb-4 text-[12px] text-[#9BA1AD]">
                <Shield size={12} className="text-[#3B82F6]" />
                30-day money-back guarantee
              </div>
              <Link
                href="/signup"
                className="block w-full rounded-lg bg-[#3B82F6] py-3 text-center text-[14px] font-semibold text-white hover:bg-[#2563EB] transition-colors"
              >
                Start Growth Plan
              </Link>
            </div>

            {/* Scale */}
            <div className="rounded-xl border border-[#23262F] bg-[#13151B] p-6 flex flex-col">
              <h3 className="text-lg font-semibold">{PLANS.scale.name}</h3>
              <div className="mt-2 mb-1">
                <span className="text-4xl font-bold">
                  ${annual ? PLANS.scale.annualPrice.toLocaleString() : PLANS.scale.monthlyPrice}
                </span>
                <span className="text-[#9BA1AD] text-[14px]">
                  /{annual ? 'year' : 'mo'}
                </span>
              </div>
              {annual && (
                <p className="text-[12px] text-[#9BA1AD] mb-3">
                  Instead of ${(PLANS.scale.monthlyPrice * 12).toLocaleString()}/year
                </p>
              )}
              {!annual && <div className="mb-3" />}
              <ul className="space-y-2.5 flex-1 mb-6">
                {PLANS.scale.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-[14px]">
                    <Check size={14} className="text-[#3B82F6] shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2 mb-4 text-[12px] text-[#9BA1AD]">
                <Shield size={12} className="text-[#3B82F6]" />
                30-day money-back guarantee
              </div>
              <Link
                href="/signup"
                className="block w-full rounded-lg border border-[#23262F] py-3 text-center text-[14px] font-semibold text-[#E8EAED] hover:bg-[#23262F] transition-colors"
              >
                Start Scale Plan
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          6. FAQ
         ════════════════════════════════════════════════ */}
      <section className="py-24 px-6 border-t border-[#23262F]">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-center text-[28px] font-semibold mb-10">Frequently asked questions</h2>
          <div className="space-y-2">
            {FAQ_ITEMS.map((item, i) => (
              <div key={i} className="rounded-xl border border-[#23262F] bg-[#13151B]">
                <button
                  onClick={() => toggleFaq(i)}
                  className="flex w-full items-center justify-between px-6 py-4 text-left"
                >
                  <span className="text-[14px] font-semibold">{item.q}</span>
                  {openFaq === i ? (
                    <ChevronUp size={18} className="text-[#9BA1AD] shrink-0 ml-4" />
                  ) : (
                    <ChevronDown size={18} className="text-[#9BA1AD] shrink-0 ml-4" />
                  )}
                </button>
                {openFaq === i && (
                  <div className="px-6 pb-4">
                    <p className="text-[14px] leading-relaxed text-[#9BA1AD]">{item.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════
          7. FOOTER
         ════════════════════════════════════════════════ */}
      <footer className="border-t border-[#23262F] py-8 px-6">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-[12px] text-[#9BA1AD]">
            &copy; 2026 Tended. All rights reserved.
          </span>
          <div className="flex items-center gap-6 text-[12px] text-[#9BA1AD]">
            <Link href="/terms" className="hover:text-[#E8EAED] transition-colors">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-[#E8EAED] transition-colors">
              Privacy
            </Link>
            <a href="mailto:hello@usetended.io" className="hover:text-[#E8EAED] transition-colors">
              Contact
            </a>
          </div>
        </div>
      </footer>

      {/* ════════════════════════════════════════════════
          STICKY MOBILE CTA
         ════════════════════════════════════════════════ */}
      <div className="fixed bottom-0 left-0 right-0 sm:hidden border-t border-[#23262F] bg-[#0B0D11]/95 backdrop-blur-sm px-4 py-3 z-50">
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
          className="block w-full rounded-lg bg-[#3B82F6] py-3 text-center text-[14px] font-semibold text-white hover:bg-[#2563EB] transition-colors"
        >
          Get Your Free Audit
        </a>
      </div>
    </div>
  );
}

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [auditSubmitted, setAuditSubmitted] = useState(false);

  useEffect(() => {
    // Don't redirect if user just submitted the audit form — keep progress screen visible
    if (!loading && user && !auditSubmitted) {
      router.replace('/today');
    }
  }, [user, loading, router, auditSubmitted]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0B0D11]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (user && !auditSubmitted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0B0D11]">
        <Spinner size="lg" />
      </div>
    );
  }

  return <LandingPage onAuditSubmitted={() => setAuditSubmitted(true)} />;
}
