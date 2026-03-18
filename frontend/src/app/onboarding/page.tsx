'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Globe, CheckCircle, Loader2, AlertCircle } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';

type Step = 'url' | 'creating' | 'crawling' | 'analyzing' | 'done' | 'error';

interface EarlyFindings {
  posts_sampled: number;
  clusters_found: number;
  cann_pairs_found: number;
  thin_content_count: number;
  preview_ready: boolean;
}

interface CrawlStatus {
  status: string;
  posts_found: number;
  posts_processed: number;
  early_findings?: EarlyFindings | null;
}

const PIPELINE_STAGES = [
  { key: 'crawling', label: 'Crawling posts', emoji: '🕷️' },
  { key: 'embedding', label: 'Generating embeddings', emoji: '🧠' },
  { key: 'analyzing', label: 'Running analysis', emoji: '🔬' },
  { key: 'clustering', label: 'Clustering topics', emoji: '🗂️' },
  { key: 'completed', label: 'Building recommendations', emoji: '✦' },
];

export default function OnboardingPage() {
  const router = useRouter();
  const auth = useAuth();
  const token = auth.session?.access_token;

  const [step, setStep] = useState<Step>('url');
  const [url, setUrl] = useState('');
  const [siteName, setSiteName] = useState('');
  const [urlPatterns, setUrlPatterns] = useState('');
  const [siteId, setSiteId] = useState<string | null>(null);
  const [crawlStatus, setCrawlStatus] = useState<CrawlStatus | null>(null);
  const [pipelineStage, setPipelineStage] = useState<string>('crawling');
  const [error, setError] = useState<string | null>(null);

  const extractDomain = (input: string): string => {
    try {
      const u = new URL(input.startsWith('http') ? input : `https://${input}`);
      return u.hostname.replace(/^www\./, '');
    } catch {
      return input.replace(/^www\./, '').split('/')[0];
    }
  };

  const pollStatus = async (id: string) => {
    let attempts = 0;
    const maxAttempts = 300; // 25 min max

    while (attempts < maxAttempts) {
      await new Promise((r) => setTimeout(r, 5000));
      attempts++;

      try {
        const status = await apiFetch<CrawlStatus>(
          `/sites/${id}/crawl/status`,
          { token },
        );
        setCrawlStatus(status);
        setPipelineStage(status.status);

        if (status.status === 'completed') {
          setStep('done');
          return;
        }
        if (status.status === 'failed') {
          setError('Pipeline failed. Check that your blog has a sitemap.xml.');
          setStep('error');
          return;
        }
      } catch {
        // poll failure is ok, keep trying
      }
    }
    setError('Analysis is taking longer than expected. Check back in a few minutes.');
    setStep('error');
  };

  const handleSubmit = async () => {
    if (!url.trim()) return;
    setError(null);
    setStep('creating');

    const domain = extractDomain(url);
    const name = siteName.trim() || domain;
    const sitemapUrl = url.startsWith('http') ? url : `https://${url}`;

    try {
      // Create site
      const site = await apiFetch<{ id: string; name: string }>('/sites', {
        method: 'POST',
        token,
        body: JSON.stringify({
          name,
          domain,
          cms_type: 'sitemap',
          sitemap_url: sitemapUrl.includes('sitemap') ? sitemapUrl : null,
        }),
      });

      setSiteId(site.id);
      setStep('crawling');

      // Trigger full pipeline (with optional URL path filter)
      const patterns = urlPatterns.trim()
        ? urlPatterns.split(',').map(p => p.trim()).filter(Boolean)
        : [];
      await apiFetch(`/sites/${site.id}/pipeline`, {
        method: 'POST',
        token,
        body: patterns.length ? JSON.stringify({ url_patterns: patterns }) : undefined,
      });

      // Poll for progress
      void pollStatus(site.id);

    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.');
      setStep('error');
    }
  };

  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.key === pipelineStage);

  return (
    <div className="min-h-screen bg-[#0a0f1a] flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold text-[#e2e8f0]">enough</h1>
          <p className="text-sm text-[#64748b] mt-1">Content Ecosystem Intelligence</p>
        </div>

        {/* Step: URL entry */}
        {(step === 'url' || step === 'creating') && (
          <div className="rounded-2xl bg-[#111827] border border-[#1e293b] p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-[#22c55e]/10 flex items-center justify-center">
                <Globe size={20} className="text-[#22c55e]" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-[#e2e8f0]">Connect your blog</h2>
                <p className="text-sm text-[#64748b]">We'll analyze every post and find what to fix</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">
                  Blog URL or sitemap URL
                </label>
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit(); }}
                  placeholder="https://yourblog.com/sitemap.xml"
                  disabled={step === 'creating'}
                  className="w-full rounded-xl bg-[#0a0f1a] border border-[#1e293b] px-4 py-3 text-sm text-[#e2e8f0] placeholder-[#475569] focus:outline-none focus:border-[#22c55e] disabled:opacity-50 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">
                  Site name <span className="text-[#475569]">(optional)</span>
                </label>
                <input
                  type="text"
                  value={siteName}
                  onChange={(e) => setSiteName(e.target.value)}
                  placeholder="My Blog"
                  disabled={step === 'creating'}
                  className="w-full rounded-xl bg-[#0a0f1a] border border-[#1e293b] px-4 py-3 text-sm text-[#e2e8f0] placeholder-[#475569] focus:outline-none focus:border-[#22c55e] disabled:opacity-50 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94a3b8] mb-1.5">
                  URL path filter <span className="text-[#475569]">(optional — recommended for large sites)</span>
                </label>
                <input
                  type="text"
                  value={urlPatterns}
                  onChange={(e) => setUrlPatterns(e.target.value)}
                  placeholder="/blog/, /resources/ (comma-separated)"
                  disabled={step === 'creating'}
                  className="w-full rounded-xl bg-[#0a0f1a] border border-[#1e293b] px-4 py-3 text-sm text-[#e2e8f0] placeholder-[#475569] focus:outline-none focus:border-[#22c55e] disabled:opacity-50 transition-colors"
                />
                <p className="text-[#475569] text-xs mt-1">
                  Only analyze URLs containing these paths. Leave blank to analyze everything.
                </p>
              </div>

              <button
                onClick={() => void handleSubmit()}
                disabled={!url.trim() || step === 'creating'}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#22c55e] text-black font-semibold py-3 text-sm hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {step === 'creating' ? (
                  <><Loader2 size={16} className="animate-spin" /> Creating site...</>
                ) : (
                  <>Analyze my blog <ArrowRight size={16} /></>
                )}
              </button>
            </div>

            <p className="mt-4 text-xs text-center text-[#475569]">
              Takes 10–40 min depending on blog size. We'll analyze every post.
            </p>
          </div>
        )}

        {/* Step: Pipeline running */}
        {(step === 'crawling' || step === 'analyzing') && (
          <div className="rounded-2xl bg-[#111827] border border-[#1e293b] p-8">
            <div className="text-center mb-8">
              <div className="text-4xl mb-3">🔬</div>
              <h2 className="text-lg font-semibold text-[#e2e8f0]">Analyzing your blog</h2>
              <p className="text-sm text-[#64748b] mt-1">
                {crawlStatus?.posts_found
                  ? `Found ${crawlStatus.posts_found} posts — processing ${crawlStatus.posts_processed || 0} so far`
                  : 'Discovering posts...'}
              </p>
            </div>

            {/* Early findings preview — show once 50+ posts analyzed */}
            {crawlStatus?.early_findings?.preview_ready && (
              <div className="mb-6 rounded-xl bg-[#22c55e]/5 border border-[#22c55e]/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-widest text-[#22c55e] mb-3">
                  Early look — full analysis still running
                </p>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-xl font-bold text-[#e2e8f0]">
                      {crawlStatus.early_findings.clusters_found}
                    </div>
                    <div className="text-xs text-[#64748b]">Topic clusters</div>
                  </div>
                  <div>
                    <div className="text-xl font-bold text-[#f97316]">
                      {crawlStatus.early_findings.cann_pairs_found}
                    </div>
                    <div className="text-xs text-[#64748b]">Overlap pairs</div>
                  </div>
                  <div>
                    <div className="text-xl font-bold text-[#eab308]">
                      {crawlStatus.early_findings.thin_content_count}
                    </div>
                    <div className="text-xs text-[#64748b]">Thin content</div>
                  </div>
                </div>
                <p className="text-xs text-[#64748b] mt-3 text-center">
                  From first {crawlStatus.early_findings.posts_sampled} posts analyzed
                </p>
              </div>
            )}

            <div className="space-y-3">
              {PIPELINE_STAGES.map((stage, i) => {
                const isDone = i < currentStageIndex;
                const isActive = stage.key === pipelineStage || (pipelineStage === 'completed' && i === PIPELINE_STAGES.length - 1);
                const isPending = i > currentStageIndex;

                return (
                  <div
                    key={stage.key}
                    className={`flex items-center gap-3 rounded-xl px-4 py-3 transition-all ${
                      isActive ? 'bg-[#22c55e]/10 border border-[#22c55e]/30' :
                      isDone ? 'bg-[#0a0f1a]/50' : 'opacity-40'
                    }`}
                  >
                    <span className="text-lg w-6 text-center">
                      {isDone ? '✓' : isActive ? stage.emoji : '○'}
                    </span>
                    <span className={`text-sm font-medium ${
                      isDone ? 'text-[#22c55e]' :
                      isActive ? 'text-[#e2e8f0]' : 'text-[#475569]'
                    }`}>
                      {stage.label}
                    </span>
                    {isActive && !isPending && (
                      <Loader2 size={14} className="ml-auto animate-spin text-[#22c55e]" />
                    )}
                    {isDone && (
                      <CheckCircle size={14} className="ml-auto text-[#22c55e]" />
                    )}
                  </div>
                );
              })}
            </div>

            <p className="mt-6 text-xs text-center text-[#475569]">
              You can close this tab — we'll finish in the background. Come back in ~20 min.
            </p>
          </div>
        )}

        {/* Step: Done */}
        {step === 'done' && siteId && (
          <div className="rounded-2xl bg-[#111827] border border-[#22c55e]/30 p-8 text-center">
            <div className="text-5xl mb-4">🎉</div>
            <h2 className="text-xl font-bold text-[#e2e8f0] mb-2">Analysis complete</h2>
            <p className="text-sm text-[#64748b] mb-6">
              {crawlStatus?.posts_processed
                ? `Analyzed ${crawlStatus.posts_processed} posts. Here's what we found.`
                : 'Your content ecosystem is ready.'}
            </p>

            <div className="flex flex-col gap-3">
              <button
                onClick={() => router.push(`/overview?site=${siteId}`)}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#22c55e] text-black font-semibold py-3 text-sm hover:bg-[#16a34a] transition-colors"
              >
                View Dashboard <ArrowRight size={16} />
              </button>
              <button
                onClick={() => router.push(`/report/${siteId}`)}
                className="w-full flex items-center justify-center gap-2 rounded-xl border border-[#1e293b] text-[#94a3b8] py-3 text-sm hover:bg-[#1e293b] transition-colors"
              >
                View Shareable Report
              </button>
            </div>
          </div>
        )}

        {/* Step: Error */}
        {step === 'error' && (
          <div className="rounded-2xl bg-[#111827] border border-red-500/30 p-8 text-center">
            <AlertCircle size={40} className="mx-auto mb-4 text-red-400" />
            <h2 className="text-lg font-semibold text-[#e2e8f0] mb-2">Something went wrong</h2>
            <p className="text-sm text-[#64748b] mb-6">{error}</p>
            <button
              onClick={() => { setStep('url'); setError(null); }}
              className="px-6 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-sm text-[#94a3b8] hover:bg-[#1e293b] transition-colors"
            >
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
