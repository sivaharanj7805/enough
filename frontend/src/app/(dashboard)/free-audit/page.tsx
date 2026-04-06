'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiUrl } from '@/lib/api';
import { freeAudit } from '@/lib/copy';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { FileText, ArrowRight, CheckCircle, Loader2, Check } from 'lucide-react';
import Link from 'next/link';

const URL_RE = /^https?:\/\/.+\..+/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const AUDIT_STAGES = [
  { label: 'Crawling posts', duration: 5 },
  { label: 'Understanding content', duration: 7 },
  { label: 'Running analysis', duration: 5 },
  { label: 'Scoring health', duration: 3 },
  { label: 'Building your report', duration: 3 },
];

function AuditProgressStages({ domain }: { domain: string }) {
  const [activeStage, setActiveStage] = useState(0);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const totalDuration = AUDIT_STAGES.reduce((s, st) => s + st.duration, 0);
    const tickMs = 2000;
    let elapsed = 0;
    const timer = setInterval(() => {
      elapsed += tickMs / 1000 / 60;
      let stage = 0;
      let cumulative = 0;
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
    <div>
      <div className="flex items-center gap-3 mb-4">
        {done ? (
          <CheckCircle size={20} className="text-green-500" />
        ) : (
          <Loader2 size={20} className="animate-spin text-brand-accent" />
        )}
        <h1 className="text-lg font-bold text-brand-text">
          {done ? `Report sent for ${domain}` : `Analyzing ${domain}`}
        </h1>
      </div>
      <div className="w-full h-2 rounded-full bg-brand-border overflow-hidden mb-5">
        <div className="h-full rounded-full bg-brand-accent transition-all duration-1000 ease-out" style={{ width: `${progress}%` }} />
      </div>
      <div className="space-y-3">
        {AUDIT_STAGES.map((stage, i) => (
          <div key={stage.label} className="flex items-center gap-3">
            {i < activeStage || done ? (
              <Check size={16} className="text-green-500 flex-shrink-0" />
            ) : i === activeStage ? (
              <Loader2 size={16} className="animate-spin text-brand-accent flex-shrink-0" />
            ) : (
              <div className="w-4 h-4 rounded-full border border-brand-border flex-shrink-0" />
            )}
            <span className={`text-sm ${i <= activeStage || done ? 'text-brand-text' : 'text-brand-text-muted'}`}>
              {stage.label}
            </span>
          </div>
        ))}
      </div>
      {done ? (
        <p className="mt-4 text-xs text-green-500">
          Your report should be in your inbox. Check spam if you don&apos;t see it.
        </p>
      ) : (
        <p className="mt-4 text-xs text-brand-text-muted">
          Your PDF report will arrive at your inbox in ~20 minutes.
        </p>
      )}
    </div>
  );
}

export default function FreeAuditPage() {
  const { user } = useAuth();

  const [url, setUrl] = useState('');
  const [email, setEmail] = useState(user?.email ?? '');
  const [errors, setErrors] = useState<{ url?: string; email?: string; form?: string }>({});

  // Pre-fill email when auth loads asynchronously
  useEffect(() => {
    if (user?.email && !email) setEmail(user.email);
  }, [user?.email]);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedDomain, setSubmittedDomain] = useState('');

  const normalizeUrl = (raw: string): string => {
    const trimmed = raw.trim();
    if (!trimmed) return trimmed;
    return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  };

  const validate = () => {
    const errs: { url?: string; email?: string } = {};
    if (!URL_RE.test(normalizeUrl(url))) errs.url = freeAudit.urlError;
    if (!EMAIL_RE.test(email)) errs.email = freeAudit.emailError;
    return errs;
  };

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
        throw new Error(data?.message || freeAudit.genericError);
      }
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
      setSubmitted(true);
    } catch (err: unknown) {
      setErrors({ form: err instanceof Error ? err.message : freeAudit.genericError });
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="max-w-lg mx-auto py-16">
        <Card className="p-8">
          <AuditProgressStages domain={submittedDomain} />
          <div className="mt-5 pt-4 border-t border-brand-border">
            <p className="text-xs text-brand-text-muted mb-3">{freeAudit.upgradeCta}</p>
            <Link href="/billing">
              <Button variant="primary" size="sm">
                {freeAudit.upgradeButton}
                <ArrowRight size={14} />
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto py-16">
      <Card className="p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-accent/20">
            <FileText size={20} className="text-brand-accent" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-brand-text">{freeAudit.heading}</h1>
            <p className="text-sm text-brand-text-muted">{freeAudit.subheading}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="audit-url" className="block text-sm font-medium text-brand-text mb-1">
              {freeAudit.urlLabel}
            </label>
            <input
              id="audit-url"
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={freeAudit.urlPlaceholder}
              className="w-full rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted focus:outline-none focus:ring-2 focus:ring-brand-accent"
            />
            {errors.url && <p className="text-xs text-red-400 mt-1">{errors.url}</p>}
          </div>

          <div>
            <label htmlFor="audit-email" className="block text-sm font-medium text-brand-text mb-1">
              {freeAudit.emailLabel}
            </label>
            <input
              id="audit-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={freeAudit.emailPlaceholder}
              className="w-full rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted focus:outline-none focus:ring-2 focus:ring-brand-accent"
            />
            {errors.email && <p className="text-xs text-red-400 mt-1">{errors.email}</p>}
          </div>

          {errors.form && (
            <p className="text-sm text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{errors.form}</p>
          )}

          <Button
            type="submit"
            variant="primary"
            className="w-full"
            disabled={loading}
          >
            {loading ? freeAudit.submitting : freeAudit.submit}
          </Button>
        </form>

        <div className="mt-6 pt-4 border-t border-brand-border text-center">
          <p className="text-xs text-brand-text-muted mb-2">{freeAudit.upgradeCta}</p>
          <Link href="/billing" className="text-xs text-brand-accent hover:underline">
            {freeAudit.upgradeButton} <ArrowRight size={12} className="inline" />
          </Link>
        </div>
      </Card>
    </div>
  );
}
