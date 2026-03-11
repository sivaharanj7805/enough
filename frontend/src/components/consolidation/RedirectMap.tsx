'use client';

import { useState, useCallback } from 'react';
import { Download, Upload, CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/lib/hooks/useAuth';
import { useSite } from '@/lib/hooks/useSite';
import { apiFetch } from '@/lib/api';
import type { RedirectEntry, RedirectStatusResponse, RedirectStatusEntry } from '@/lib/types';

interface RedirectMapProps {
  entries: RedirectEntry[];
  isWordPress: boolean;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'pushed':
      return <CheckCircle size={14} className="text-green-400" />;
    case 'verified':
      return <CheckCircle size={14} className="text-emerald-400" />;
    case 'failed':
      return <XCircle size={14} className="text-red-400" />;
    case 'pending':
      return <Clock size={14} className="text-yellow-400" />;
    default:
      return null;
  }
}

export function RedirectMap({ entries, isWordPress }: RedirectMapProps) {
  const { session } = useAuth();
  const { currentSite } = useSite();
  const [pushing, setPushing] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [pushResult, setPushResult] = useState<RedirectStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const statusMap = new Map<string, RedirectStatusEntry>();
  if (pushResult) {
    for (const entry of pushResult.entries) {
      statusMap.set(entry.old_url, entry);
    }
  }

  const handlePush = useCallback(async () => {
    if (!currentSite || !session?.access_token || entries.length === 0) return;
    setPushing(true);
    setError(null);
    try {
      const result = await apiFetch<RedirectStatusResponse>(
        `/sites/${currentSite.id}/redirects/push`,
        {
          method: 'POST',
          token: session.access_token,
          body: JSON.stringify({
            redirect_map: entries.map((e) => ({
              old_url: e.old_url,
              new_url: e.new_url,
            })),
          }),
        }
      );
      setPushResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Push failed');
    } finally {
      setPushing(false);
    }
  }, [currentSite, session, entries]);

  const handleVerify = useCallback(async () => {
    if (!currentSite || !session?.access_token) return;
    setVerifying(true);
    setError(null);
    try {
      const result = await apiFetch<RedirectStatusResponse>(
        `/sites/${currentSite.id}/redirects/verify`,
        { method: 'POST', token: session.access_token }
      );
      setPushResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setVerifying(false);
    }
  }, [currentSite, session]);

  function exportCsv() {
    const header = 'old_url,new_url';
    const rows = entries.map(
      (e) => `"${e.old_url}","${e.new_url}"`
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'redirect-map.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-brand-text">Redirect Map</h3>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={exportCsv}>
            <Download size={14} />
            Export CSV
          </Button>
          {pushResult && pushResult.pushed > 0 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleVerify}
              disabled={verifying}
            >
              {verifying ? (
                <Spinner size="sm" />
              ) : (
                <RefreshCw size={14} />
              )}
              Verify Redirects
            </Button>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handlePush}
            disabled={!isWordPress || pushing || entries.length === 0}
            title={!isWordPress ? 'Only available for WordPress sites' : undefined}
          >
            {pushing ? (
              <Spinner size="sm" />
            ) : (
              <Upload size={14} />
            )}
            Push to WordPress
          </Button>
        </div>
      </div>

      {/* Push summary */}
      {pushResult && (
        <div className="flex gap-4 mb-4 text-xs">
          <span className="text-green-400">
            ✅ Pushed: {pushResult.pushed}
          </span>
          <span className="text-emerald-400">
            ✓ Verified: {pushResult.verified}
          </span>
          <span className="text-red-400">
            ✗ Failed: {pushResult.failed}
          </span>
          <span className="text-brand-text-muted">
            Total: {pushResult.total}
          </span>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {entries.length === 0 ? (
        <p className="text-sm text-brand-text-muted text-center py-4">No redirects needed</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brand-border">
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">Old URL</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">→</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">New URL (Pillar)</th>
                {pushResult && (
                  <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">Status</th>
                )}
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const statusEntry = statusMap.get(entry.old_url);
                return (
                  <tr key={entry.old_url} className="border-b border-brand-border/50 hover:bg-brand-surface-hover">
                    <td className="py-2 px-3 text-brand-text-muted font-mono text-xs truncate max-w-[280px]">
                      {entry.old_url}
                    </td>
                    <td className="py-2 px-3 text-brand-text-muted">→</td>
                    <td className="py-2 px-3 text-brand-accent font-mono text-xs truncate max-w-[280px]">
                      {entry.new_url}
                    </td>
                    {pushResult && (
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-1.5">
                          <StatusIcon status={statusEntry?.status ?? 'pending'} />
                          <span className="text-xs text-brand-text-muted">
                            {statusEntry?.status ?? 'pending'}
                          </span>
                          {statusEntry?.error && (
                            <span className="text-xs text-red-400 truncate max-w-[150px]" title={statusEntry.error}>
                              {statusEntry.error}
                            </span>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
