'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Globe, BarChart3, Search, Sparkles, Check, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import type { Site } from '@/lib/types';

/** Local build status for the onboarding animation (not the backend PipelineStatus). */
interface BuildStatus {
  stage: string;
  progress: number;
  message: string;
  completed: boolean;
  error: string | null;
}

type CmsType = 'wordpress' | 'other';

interface StepProps {
  onNext: () => void;
  onSkip?: () => void;
}

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`h-2 rounded-full transition-all ${
            i < current
              ? 'w-8 bg-brand-accent'
              : i === current
              ? 'w-8 bg-brand-accent/50'
              : 'w-2 bg-brand-border'
          }`}
        />
      ))}
    </div>
  );
}

function AddSiteStep({ onComplete }: { onComplete: (site: Site) => void }) {
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [cmsType, setCmsType] = useState<CmsType>('wordpress');
  const [sitemapUrl, setSitemapUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { session } = useAuth();

  async function handleSubmit() {
    setError('');
    setLoading(true);
    try {
      const site = await apiFetch<Site>('/sites', {
        method: 'POST',
        token: session?.access_token,
        body: JSON.stringify({
          name,
          domain,
          cms_type: cmsType,
          sitemap_url: sitemapUrl || null,
        }),
      });
      onComplete(site);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add site');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="rounded-lg bg-brand-accent/10 p-2">
            <Globe size={24} className="text-brand-accent" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-brand-text">Add Your Site</h2>
            <p className="text-sm text-brand-text-muted">Tell us about your content</p>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <Input
          id="site-name"
          label="Site Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My Blog"
        />

        <Input
          id="domain"
          label="Domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="example.com"
        />

        <div>
          <label className="mb-1.5 block text-sm font-medium text-brand-text">CMS</label>
          <div className="flex gap-3">
            {(['wordpress', 'other'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setCmsType(type)}
                className={`flex-1 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                  cmsType === type
                    ? 'border-brand-accent bg-brand-accent/10 text-brand-accent'
                    : 'border-brand-border text-brand-text-muted hover:border-brand-border-hover'
                }`}
              >
                {type === 'wordpress' ? 'WordPress' : 'Other'}
              </button>
            ))}
          </div>
        </div>

        <Input
          id="sitemap"
          label={cmsType === 'wordpress' ? 'Site URL' : 'Sitemap URL'}
          value={sitemapUrl}
          onChange={(e) => setSitemapUrl(e.target.value)}
          placeholder={cmsType === 'wordpress' ? 'https://example.com' : 'https://example.com/sitemap.xml'}
        />

        <Button
          className="w-full"
          loading={loading}
          disabled={!name || !domain}
          onClick={() => void handleSubmit()}
        >
          Add Site
          <ArrowRight size={16} />
        </Button>
      </div>
    </Card>
  );
}

function ConnectStep({ icon: Icon, title, description, onNext, onSkip }: StepProps & {
  icon: typeof BarChart3;
  title: string;
  description: string;
}) {
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);

  function handleConnect() {
    setLoading(true);
    // In production, this would trigger Google OAuth
    setTimeout(() => {
      setLoading(false);
      setConnected(true);
    }, 1500);
  }

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="rounded-lg bg-brand-accent/10 p-2">
            <Icon size={24} className="text-brand-accent" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-brand-text">{title}</h2>
            <p className="text-sm text-brand-text-muted">{description}</p>
          </div>
        </div>

        {connected ? (
          <div className="flex items-center gap-2 rounded-lg bg-green-500/10 border border-green-500/20 p-3 text-sm text-green-400">
            <Check size={18} />
            Connected successfully
          </div>
        ) : (
          <Button
            className="w-full"
            loading={loading}
            onClick={handleConnect}
          >
            Connect with Google
          </Button>
        )}

        <div className="flex gap-3">
          {onSkip && !connected && (
            <Button variant="ghost" className="flex-1" onClick={onSkip}>
              Skip for now
            </Button>
          )}
          {connected && (
            <Button className="flex-1" onClick={onNext}>
              Continue
              <ArrowRight size={16} />
            </Button>
          )}
          {onSkip && !connected && (
            <Button variant="secondary" className="flex-1" onClick={onNext}>
              Continue
              <ArrowRight size={16} />
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

function BuildingStep({ siteId }: { siteId: string }) {
  const router = useRouter();
  const { session } = useAuth();
  const [status, setStatus] = useState<BuildStatus>({
    stage: 'crawling',
    progress: 0,
    message: 'Starting ecosystem analysis...',
    completed: false,
    error: null,
  });
  const [started, setStarted] = useState(false);

  const startBuild = useCallback(async () => {
    if (started) return;
    setStarted(true);

    try {
      await apiFetch(`/sites/${siteId}/pipeline/start`, {
        method: 'POST',
        token: session?.access_token,
      });
    } catch {
      // Pipeline may already be running
    }

    const stages = [
      { stage: 'crawling', message: 'Crawling content...', progress: 20 },
      { stage: 'analytics', message: 'Syncing analytics data...', progress: 40 },
      { stage: 'embeddings', message: 'Generating embeddings...', progress: 60 },
      { stage: 'analyzing', message: 'Analyzing your ecosystem...', progress: 80 },
      { stage: 'complete', message: 'Your ecosystem is ready!', progress: 100 },
    ];

    for (const s of stages) {
      await new Promise((r) => setTimeout(r, 2000));
      setStatus({
        stage: s.stage,
        progress: s.progress,
        message: s.message,
        completed: s.stage === 'complete',
        error: null,
      });
    }
  }, [siteId, session?.access_token, started]);

  // Auto-start on mount
  useState(() => {
    void startBuild();
  });

  return (
    <Card>
      <div className="space-y-6 text-center">
        <div className="rounded-lg bg-brand-accent/10 p-3 inline-block">
          <Sparkles size={32} className="text-brand-accent" />
        </div>

        <div>
          <h2 className="text-lg font-semibold text-brand-text">
            {status.completed ? '🎉 Your Ecosystem is Ready!' : 'Building Your Ecosystem...'}
          </h2>
          <p className="mt-2 text-sm text-brand-text-muted">{status.message}</p>
        </div>

        <div className="w-full">
          <div className="h-2 rounded-full bg-brand-surface-hover overflow-hidden">
            <div
              className="h-full rounded-full bg-brand-accent transition-all duration-1000"
              style={{ width: `${status.progress}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-brand-text-muted">{status.progress}%</p>
        </div>

        {!status.completed && <Spinner className="mx-auto" />}

        {status.completed && (
          <Button
            className="w-full"
            onClick={() => router.push('/landscape')}
          >
            Explore Your Landscape
            <ArrowRight size={16} />
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [siteId, setSiteId] = useState<string | null>(null);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md">
        <StepIndicator current={step} total={4} />

        {step === 0 && (
          <AddSiteStep
            onComplete={(site) => {
              setSiteId(site.id);
              setStep(1);
            }}
          />
        )}

        {step === 1 && (
          <ConnectStep
            icon={BarChart3}
            title="Connect Google Analytics"
            description="Import traffic data to understand content performance"
            onNext={() => setStep(2)}
            onSkip={() => setStep(2)}
          />
        )}

        {step === 2 && (
          <ConnectStep
            icon={Search}
            title="Connect Search Console"
            description="Import search queries and rankings"
            onNext={() => setStep(3)}
            onSkip={() => setStep(3)}
          />
        )}

        {step === 3 && siteId && <BuildingStep siteId={siteId} />}
      </div>
    </div>
  );
}
