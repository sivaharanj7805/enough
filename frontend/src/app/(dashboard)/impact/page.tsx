'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { TrendingUp, TrendingDown, Plus, ArrowRight, Target } from 'lucide-react';
import type { ImpactTrackingResponse, StartTrackingRequest } from '@/lib/types/phase5';

export default function ImpactPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [pillarUrl, setPillarUrl] = useState('');
  const [consolidatedUrls, setConsolidatedUrls] = useState('');

  const { data: trackings, isLoading, mutate } = useSWRFetch<ImpactTrackingResponse[]>(
    currentSite ? `/sites/${currentSite.id}/impact` : null
  );

  const handleStartTracking = async () => {
    if (!currentSite || !session?.access_token || !pillarUrl.trim()) return;

    setSubmitting(true);
    try {
      const body: StartTrackingRequest = {
        cluster_id: null,
        pillar_url: pillarUrl.trim(),
        consolidated_urls: consolidatedUrls
          .split('\n')
          .map((u) => u.trim())
          .filter(Boolean),
      };
      await apiFetch(`/sites/${currentSite.id}/impact/track`, {
        method: 'POST',
        token: session.access_token,
        body: JSON.stringify(body),
      });
      await mutate();
      setShowModal(false);
      setPillarUrl('');
      setConsolidatedUrls('');
    } catch (err) {
      console.error('Failed to start tracking:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!currentSite) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-brand-text-muted">
        <Target size={48} className="mb-4 opacity-50" />
        <p>Select a site to view impact tracking.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-text">Impact Tracking</h1>
          <p className="text-sm text-brand-text-muted mt-1">
            Track the real impact of your consolidation work over 30, 60, and 90 days.
          </p>
        </div>
        <Button onClick={() => setShowModal(true)} size="md">
          <Plus size={16} />
          Start Tracking
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : !trackings || trackings.length === 0 ? (
        <Card className="py-16 text-center">
          <Target size={48} className="mx-auto mb-4 text-brand-text-muted opacity-50" />
          <h3 className="text-lg font-medium text-brand-text mb-2">No trackings yet</h3>
          <p className="text-sm text-brand-text-muted mb-4">
            Start tracking a consolidation to measure its impact over time.
          </p>
          <Button onClick={() => setShowModal(true)} size="sm">
            <Plus size={14} />
            Start Your First Tracking
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4">
          {trackings.map((tracking) => {
            const isPositive = (tracking.traffic_change_pct ?? 0) >= 0;
            return (
              <Link key={tracking.id} href={`/impact/${tracking.id}`}>
                <Card className="hover:border-brand-border-hover transition-colors cursor-pointer">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-brand-text truncate">
                          {tracking.pillar_url}
                        </h3>
                        <Badge
                          color={tracking.status === 'tracking' ? '#3b82f6' : '#22c55e'}
                        >
                          {tracking.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-brand-text-muted">
                        <span>{tracking.consolidated_urls.length} posts consolidated</span>
                        <span>{tracking.days_since} days ago</span>
                        <span>Baseline: {tracking.baseline_traffic.toLocaleString()} sessions</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 ml-4">
                      {tracking.traffic_change_pct !== null && (
                        <div className="flex items-center gap-1">
                          {isPositive ? (
                            <TrendingUp size={16} className="text-green-400" />
                          ) : (
                            <TrendingDown size={16} className="text-red-400" />
                          )}
                          <span
                            className={`text-sm font-bold ${
                              isPositive ? 'text-green-400' : 'text-red-400'
                            }`}
                          >
                            {isPositive ? '+' : ''}
                            {tracking.traffic_change_pct.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      <ArrowRight size={16} className="text-brand-text-muted" />
                    </div>
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      )}

      <Modal open={showModal} onClose={() => setShowModal(false)} title="Start Impact Tracking">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-brand-text mb-1">
              Pillar URL
            </label>
            <Input
              value={pillarUrl}
              onChange={(e) => setPillarUrl(e.target.value)}
              placeholder="https://example.com/pillar-post"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-brand-text mb-1">
              Consolidated URLs (one per line)
            </label>
            <textarea
              value={consolidatedUrls}
              onChange={(e) => setConsolidatedUrls(e.target.value)}
              placeholder={"https://example.com/old-post-1\nhttps://example.com/old-post-2"}
              rows={4}
              className="w-full rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted focus:outline-none focus:ring-2 focus:ring-brand-accent/50"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleStartTracking}
              loading={submitting}
              disabled={!pillarUrl.trim()}
            >
              Start Tracking
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
