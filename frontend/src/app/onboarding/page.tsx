'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Globe, CheckCircle, Loader2, AlertCircle, Circle } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { useAuth } from '@/lib/hooks/useAuth';
import { onboarding, pipeline, errors } from '@/lib/copy';

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

const STAGES = Object.entries(pipeline.stages).map(([key, v]) => ({
  key, label: v.label, education: v.description,
}));

const CMS_OPTIONS = [
  { value: 'wordpress', label: 'WordPress' },
  { value: 'sitemap', label: 'Sitemap' },
  { value: 'hubspot', label: 'HubSpot' },
  { value: 'webflow', label: 'Webflow' },
  { value: 'ghost', label: 'Ghost' },
];

const inputCls =
  'w-full rounded-lg bg-brand-bg border border-brand-border px-4 py-3 text-sm text-brand-text placeholder:text-brand-text-tertiary focus:outline-none focus:ring-2 focus:ring-brand-accent/40 focus:border-brand-accent disabled:opacity-50 transition-colors';

export default function OnboardingPage() {
  const router = useRouter();
  const token = useAuth().session?.access_token;

  const [step, setStep] = useState<Step>('url');
  const [url, setUrl] = useState('');
  const [cmsType, setCmsType] = useState('sitemap');
  const [siteName, setSiteName] = useState('');
  const [urlPatterns, setUrlPatterns] = useState('');
  const [siteId, setSiteId] = useState<string | null>(null);
  const [crawlStatus, setCrawlStatus] = useState<CrawlStatus | null>(null);
  const [pipelineStage, setPipelineStage] = useState('crawling');
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  useEffect(() => () => { abortRef.current = true; }, []);

  const extractDomain = (input: string): string => {
    try {
      const u = new URL(input.startsWith('http') ? input : `https://${input}`);
      return u.hostname.replace(/^www\./, '');
    } catch { return input.replace(/^www\./, '').split('/')[0]; }
  };

  const pollStatus = async (id: string) => {
    let attempts = 0;
    while (attempts < 120 && !abortRef.current) {
      await new Promise((r) => setTimeout(r, Math.min(5000 * Math.pow(1.5, attempts), 30000)));
      attempts++;
      try {
        const s = await apiFetch<CrawlStatus>(`/sites/${id}/crawl/status`, { token });
        setCrawlStatus(s);
        setPipelineStage(s.status);
        if (s.status === 'completed') { setStep('done'); return; }
        if (s.status === 'failed') { setError(errors.pipelineFailed); setStep('error'); return; }
      } catch { /* keep trying */ }
    }
    setError(errors.pipelineTimeout);
    setStep('error');
  };

  // Resume an active pipeline if one exists
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const sites = await apiFetch<{ id: string; name: string; domain: string }[]>('/sites', { token });
        if (cancelled || !sites?.length) return;
        for (const site of sites) {
          try {
            const s = await apiFetch<CrawlStatus>(`/sites/${site.id}/crawl/status`, { token });
            if (cancelled) return;
            if (s.status === 'completed') { router.replace('/today'); return; }
            if (['crawling', 'embedding', 'analyzing', 'clustering'].includes(s.status)) {
              setSiteId(site.id); setUrl(site.domain); setCrawlStatus(s);
              setPipelineStage(s.status); setStep('crawling');
              void pollStatus(site.id); return;
            }
          } catch { /* try next */ }
        }
      } catch { /* show form */ }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleSubmit = async () => {
    if (!url.trim()) return;
    setError(null); setStep('creating');
    const domain = extractDomain(url);
    const sitemapUrl = url.startsWith('http') ? url : `https://${url}`;
    try {
      const site = await apiFetch<{ id: string; name: string }>('/sites', {
        method: 'POST', token,
        body: JSON.stringify({ name: siteName.trim() || domain, domain, cms_type: cmsType, sitemap_url: sitemapUrl.includes('sitemap') ? sitemapUrl : null }),
      });
      setSiteId(site.id); setStep('crawling');
      const patterns = urlPatterns.trim() ? urlPatterns.split(',').map((p) => p.trim()).filter(Boolean) : [];
      await apiFetch(`/sites/${site.id}/pipeline`, {
        method: 'POST', token,
        body: patterns.length ? JSON.stringify({ url_patterns: patterns }) : undefined,
      });
      void pollStatus(site.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : errors.generic); setStep('error');
    }
  };

  const stageIdx = STAGES.findIndex((s) => s.key === pipelineStage);
  const findings = crawlStatus?.early_findings;

  return (
    <div className="min-h-screen bg-brand-bg flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold text-brand-text tracking-tight">tended.</h1>
          <p className="text-sm text-brand-text-tertiary mt-1">Content Ecosystem Intelligence</p>
        </div>

        {/* Step 1: URL Entry */}
        {(step === 'url' || step === 'creating') && (
          <div className="rounded-xl bg-brand-surface border border-brand-border p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-brand-success/10 flex items-center justify-center">
                <Globe size={20} className="text-brand-success" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-brand-text">{onboarding.title}</h2>
                <p className="text-sm text-brand-text-secondary">{onboarding.subtitle}</p>
              </div>
            </div>
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-medium text-brand-text-secondary mb-1.5">CMS type</label>
                <select value={cmsType} onChange={(e) => setCmsType(e.target.value)} disabled={step === 'creating'} aria-label="CMS type" className={`${inputCls} appearance-none`}>
                  {CMS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-brand-text-secondary mb-1.5">{onboarding.urlLabel}</label>
                <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit(); }} placeholder={onboarding.urlPlaceholder} disabled={step === 'creating'} aria-label={onboarding.urlLabel} className={inputCls} />
                <p className="text-brand-text-tertiary text-xs mt-1.5">{onboarding.readOnly}</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-brand-text-secondary mb-1.5">
                  {onboarding.nameLabel} <span className="text-brand-text-tertiary">(optional)</span>
                </label>
                <input type="text" value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder={onboarding.namePlaceholder} disabled={step === 'creating'} aria-label={onboarding.nameLabel} className={inputCls} />
              </div>
              <div>
                <label className="block text-xs font-medium text-brand-text-secondary mb-1.5">
                  {onboarding.filterLabel} <span className="text-brand-text-tertiary">(optional)</span>
                </label>
                <input type="text" value={urlPatterns} onChange={(e) => setUrlPatterns(e.target.value)} placeholder={onboarding.filterPlaceholder} disabled={step === 'creating'} aria-label={onboarding.filterLabel} className={inputCls} />
                <p className="text-brand-text-tertiary text-xs mt-1">{onboarding.filterHelp}</p>
              </div>
              <button onClick={() => void handleSubmit()} disabled={!url.trim() || step === 'creating'} aria-label={onboarding.submitButton} className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-accent text-white px-6 py-3 font-semibold text-sm hover:bg-brand-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {step === 'creating'
                  ? <><Loader2 size={16} className="animate-spin" /> Creating site...</>
                  : <>{onboarding.submitButton} <ArrowRight size={16} /></>}
              </button>
            </div>
            <p className="mt-5 text-xs text-center text-brand-text-tertiary">{pipeline.timeEstimate}</p>
          </div>
        )}

        {/* Step 2: Pipeline Running */}
        {(step === 'crawling' || step === 'analyzing') && (
          <div className="rounded-xl bg-brand-surface border border-brand-border p-8">
            <div className="text-center mb-8">
              <div className="w-12 h-12 rounded-full bg-brand-accent/10 flex items-center justify-center mx-auto mb-4">
                <Loader2 size={24} className="animate-spin text-brand-accent" />
              </div>
              <h2 className="text-lg font-semibold text-brand-text">{onboarding.analyzing}</h2>
              <p className="text-sm text-brand-text-secondary mt-1">
                {crawlStatus?.posts_found ? pipeline.found(crawlStatus.posts_found, crawlStatus.posts_processed || 0) : pipeline.discovering}
              </p>
            </div>
            {/* Vertical timeline */}
            <div className="relative ml-3">
              {STAGES.map((stage, i) => {
                const isDone = i < stageIdx;
                const isActive = stage.key === pipelineStage || (pipelineStage === 'completed' && i === STAGES.length - 1);
                return (
                  <div key={stage.key} className="relative flex gap-4 pb-6 last:pb-0">
                    {i < STAGES.length - 1 && (
                      <div className={`absolute left-[11px] top-[28px] w-px h-[calc(100%-16px)] ${isDone ? 'bg-brand-success/40' : 'bg-brand-border'}`} />
                    )}
                    <div className="relative z-10 flex-shrink-0 mt-0.5">
                      {isDone ? <CheckCircle size={22} className="text-brand-success" />
                        : isActive ? <Loader2 size={22} className="animate-spin text-brand-accent" />
                        : <Circle size={22} className="text-brand-text-tertiary" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${isDone ? 'text-brand-success' : isActive ? 'text-brand-text' : 'text-brand-text-tertiary'}`}>{stage.label}</p>
                      {isActive && <p className="text-xs text-brand-text-secondary mt-1 leading-relaxed">{stage.education}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Early findings */}
            {findings?.preview_ready && (
              <div className="mt-6 pt-6 border-t border-brand-border">
                <p className="text-xs font-semibold uppercase tracking-widest text-brand-success mb-3">Early findings</p>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { value: findings.clusters_found, label: 'Topic clusters', color: 'text-brand-text' },
                    { value: findings.cann_pairs_found, label: 'Overlap pairs', color: 'text-brand-warning' },
                    { value: findings.thin_content_count, label: 'Thin content', color: 'text-severity-medium' },
                  ].map((card) => (
                    <div key={card.label} className="rounded-xl border border-brand-border bg-brand-surface p-4 text-center">
                      <div className={`text-xl font-bold ${card.color}`}>{card.value}</div>
                      <div className="text-xs text-brand-text-secondary mt-0.5">{card.label}</div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-brand-text-tertiary mt-2 text-center">From first {findings.posts_sampled} posts analyzed</p>
              </div>
            )}
            <p className="mt-6 text-xs text-center text-brand-text-tertiary">{pipeline.canClose}</p>
          </div>
        )}

        {/* Step 3: Complete */}
        {step === 'done' && siteId && (
          <div className="rounded-xl bg-brand-surface border border-brand-success/30 p-8 text-center">
            <div className="w-14 h-14 rounded-full bg-brand-success/10 flex items-center justify-center mx-auto mb-5">
              <CheckCircle size={28} className="text-brand-success" />
            </div>
            <h2 className="text-xl font-bold text-brand-text mb-2">Your analysis is ready</h2>
            <p className="text-sm text-brand-text-secondary mb-8">
              {crawlStatus?.posts_processed ? `Analyzed ${crawlStatus.posts_processed} posts. Here\u2019s what we found.` : 'Your content ecosystem is ready to explore.'}
            </p>
            <div className="flex flex-col gap-3">
              <button onClick={() => router.push('/today')} aria-label="Go to dashboard" className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-accent text-white px-6 py-3 font-semibold text-sm hover:bg-brand-accent-hover transition-colors">
                Go to Dashboard <ArrowRight size={16} />
              </button>
              <button onClick={() => router.push(`/report/${siteId}`)} aria-label="View report" className="w-full flex items-center justify-center gap-2 rounded-lg border border-brand-border text-brand-text-secondary py-3 text-sm hover:bg-brand-surface-hover transition-colors">
                View Report
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Error */}
        {step === 'error' && (
          <div className="rounded-xl bg-brand-surface border border-brand-critical/30 p-8 text-center">
            <div className="w-14 h-14 rounded-full bg-brand-critical/10 flex items-center justify-center mx-auto mb-5">
              <AlertCircle size={28} className="text-brand-critical" />
            </div>
            <h2 className="text-lg font-semibold text-brand-text mb-2">Something went wrong</h2>
            <p className="text-sm text-brand-text-secondary mb-6">{error}</p>
            <button onClick={() => { setStep('url'); setError(null); }} aria-label="Try again" className="px-6 py-3 rounded-lg border border-brand-border text-sm text-brand-text-secondary hover:bg-brand-surface-hover transition-colors">
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
