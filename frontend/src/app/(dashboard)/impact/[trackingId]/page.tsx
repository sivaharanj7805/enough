'use client';

import { useParams } from 'next/navigation';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ImpactCard } from '@/components/impact/ImpactCard';
import { ImpactTimeline } from '@/components/impact/ImpactTimeline';
import { TrafficChangeChart } from '@/components/impact/TrafficChangeChart';
import { ArrowLeft, RefreshCw, ExternalLink, Clock, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import type { ImpactDetailResponse, ImpactCardResponse } from '@/lib/types/phase5';

export default function ImpactDetailPage() {
  const { trackingId } = useParams<{ trackingId: string }>();
  const { currentSite } = useSite();
  const { session } = useAuth();
  const [checking, setChecking] = useState(false);

  const { data: detail, isLoading, mutate } = useSWRFetch<ImpactDetailResponse>(
    currentSite && trackingId
      ? `/sites/${currentSite.id}/impact/${trackingId}`
      : null
  );

  const { data: card } = useSWRFetch<ImpactCardResponse>(
    currentSite && trackingId
      ? `/sites/${currentSite.id}/impact/${trackingId}/card`
      : null
  );

  const handleCheck = async () => {
    if (!currentSite || !session?.access_token || !trackingId) return;
    setChecking(true);
    try {
      await apiFetch(`/sites/${currentSite.id}/impact/${trackingId}/check`, {
        method: 'POST',
        token: session.access_token,
      });
      await mutate();
    } catch (err) {
      console.error('Failed to check impact:', err);
    } finally {
      setChecking(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-center py-20 text-brand-text-muted">
        Tracking not found.
      </div>
    );
  }

  const t = detail.tracking;
  const isPositive = (t.traffic_change_pct ?? 0) >= 0;
  const hasGSCData = t.baseline_avg_position !== null;
  const isPending = t.days_since < 14 && t.latest_traffic === null;

  // Build narrative summary
  const buildNarrativeSummary = () => {
    if (isPending) return null;

    const positionPart =
      t.baseline_avg_position !== null && t.latest_avg_position !== null
        ? ` Rankings improved from position ${t.baseline_avg_position.toFixed(1)} to ${t.latest_avg_position.toFixed(1)}.`
        : '';

    return `It\u2019s been ${t.days_since} day${t.days_since === 1 ? '' : 's'} since you consolidated ${t.consolidated_urls.length} post${t.consolidated_urls.length === 1 ? '' : 's'} into this pillar.${positionPart}`;
  };

  const narrativeSummary = buildNarrativeSummary();

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/impact"
            className="rounded-lg p-2 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text transition-colors"
            aria-label="Back to impact overview"
          >
            <ArrowLeft size={20} />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-brand-text">Impact Detail</h1>
            <p className="text-sm text-brand-text-muted truncate max-w-lg">
              {t.pillar_url}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge color={t.status === 'tracking' ? '#3b82f6' : '#22c55e'}>
            {t.status}
          </Badge>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCheck}
            loading={checking}
          >
            <RefreshCw size={14} />
            Check Now
          </Button>
        </div>
      </div>

      {/* Narrative Summary */}
      {narrativeSummary && (
        <Card className="bg-brand-accent/5 border-brand-accent/20">
          <p className="text-sm text-brand-text leading-relaxed">
            {narrativeSummary}
          </p>
          {t.cluster_id && (
            <Link
              href={`/clusters/${t.cluster_id}`}
              className="inline-flex items-center gap-1 mt-2 text-xs text-brand-accent hover:underline"
            >
              <ExternalLink size={12} />
              View original recommendation
            </Link>
          )}
        </Card>
      )}

      {/* Pending state */}
      {isPending && (
        <Card className="bg-amber-500/5 border-amber-500/20">
          <div className="flex items-start gap-3">
            <Clock size={20} className="text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-brand-text">
                Impact data will be available in 7&ndash;14 days
              </p>
              <p className="text-xs text-brand-text-muted mt-1">
                It takes time for search engines to re-index consolidated content and for traffic patterns to stabilize. We&rsquo;ll check automatically and notify you when results are ready.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* No GSC fallback */}
      {!hasGSCData && (
        <Card className="bg-blue-500/5 border-blue-500/20">
          <div className="flex items-start gap-3">
            <AlertTriangle size={20} className="text-blue-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-brand-text">
                Connect Google Search Console to track the impact of your changes
              </p>
              <p className="text-xs text-brand-text-muted mt-1">
                Ranking position data, CTR analysis, and keyword-level impact tracking require a Google Search Console connection.
              </p>
              <Link
                href="/settings"
                className="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors"
              >
                Connect Google Search Console
              </Link>
            </div>
          </div>
        </Card>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <div className="text-xs text-brand-text-muted uppercase">Baseline</div>
          <div className="text-xl font-bold text-brand-text mt-1">
            {t.baseline_traffic.toLocaleString()}
          </div>
          <div className="text-xs text-brand-text-muted">sessions / 30d</div>
        </Card>
        <Card>
          <div className="text-xs text-brand-text-muted uppercase">Current</div>
          <div className="text-xl font-bold text-brand-text mt-1">
            {t.latest_traffic !== null ? t.latest_traffic.toLocaleString() : '\u2014'}
          </div>
          <div className="text-xs text-brand-text-muted">sessions / 30d</div>
        </Card>
        <Card>
          <div className="text-xs text-brand-text-muted uppercase">Change</div>
          <div
            className={`text-xl font-bold mt-1 ${
              isPositive ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {t.traffic_change_pct !== null
              ? `${isPositive ? '+' : ''}${t.traffic_change_pct.toFixed(1)}%`
              : '\u2014'}
          </div>
          <div className="text-xs text-brand-text-muted">traffic</div>
        </Card>
        <Card>
          <div className="text-xs text-brand-text-muted uppercase">Days</div>
          <div className="text-xl font-bold text-brand-text mt-1">{t.days_since}</div>
          <div className="text-xs text-brand-text-muted">since consolidation</div>
        </Card>
      </div>

      {/* Chart */}
      <Card>
        <h2 className="text-sm font-medium text-brand-text-muted uppercase mb-4">
          Traffic Over Time
        </h2>
        <TrafficChangeChart
          baselineTraffic={t.baseline_traffic}
          latestTraffic={t.latest_traffic}
          snapshots={detail.snapshots}
        />
      </Card>

      {/* Two-column: Timeline + Impact Card */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <h2 className="text-sm font-medium text-brand-text-muted uppercase mb-4">
            Milestone Timeline
          </h2>
          <ImpactTimeline snapshots={detail.snapshots} daysSince={t.days_since} />
        </Card>

        {card && (
          <div>
            <h2 className="text-sm font-medium text-brand-text-muted uppercase mb-4">
              Shareable Impact Card
            </h2>
            <ImpactCard card={card} />
          </div>
        )}
      </div>

      {/* Consolidated URLs */}
      <Card>
        <h2 className="text-sm font-medium text-brand-text-muted uppercase mb-3">
          Consolidated URLs ({t.consolidated_urls.length})
        </h2>
        <div className="space-y-1">
          {t.consolidated_urls.map((url) => (
            <div
              key={url}
              className="text-sm text-brand-text-muted truncate py-1 px-2 rounded hover:bg-brand-surface-hover"
            >
              {url}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
