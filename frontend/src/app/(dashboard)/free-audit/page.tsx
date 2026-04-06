'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiUrl } from '@/lib/api';
import { freeAudit } from '@/lib/copy';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { FileText, ArrowRight, CheckCircle } from 'lucide-react';
import Link from 'next/link';

const URL_RE = /^https?:\/\/.+\..+/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function FreeAuditPage() {
  const { user } = useAuth();

  const [url, setUrl] = useState('');
  const [email, setEmail] = useState(user?.email ?? '');
  const [errors, setErrors] = useState<{ url?: string; email?: string; form?: string }>({});
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
      try {
        setSubmittedDomain(new URL(finalUrl).hostname);
      } catch {
        setSubmittedDomain(finalUrl);
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
        <Card className="text-center space-y-4 p-8">
          <CheckCircle size={48} className="mx-auto text-[#22c55e]" />
          <h1 className="text-xl font-bold text-brand-text">{freeAudit.successHeading}</h1>
          <p className="text-sm text-brand-text-muted">
            {freeAudit.successMessage(submittedDomain)}
          </p>
          <div className="pt-4 border-t border-brand-border">
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
              type="url"
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
