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
import { ArrowLeft, RefreshCw } from 'lucide-react';
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

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/impact"
            className="rounded-lg p-2 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text transition-colors"
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
            {t.latest_traffic !== null ? t.latest_traffic.toLocaleString() : '—'}
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
              : '—'}
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
