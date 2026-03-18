'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { apiFetch } from '@/lib/api';
import {
  CheckCircle,
  XCircle,
  RefreshCw,
  ExternalLink,
  Settings,
  Database,
  TrendingUp,
  Search,
} from 'lucide-react';

interface GoogleStatus {
  connected: boolean;
  gsc_site_url: string | null;
  ga4_property_id: string | null;
  last_gsc_sync: string | null;
  last_ga4_sync: string | null;
}

interface GSCSite {
  siteUrl: string;
}

interface GA4Property {
  property_id: string;
  display_name: string;
  account: string;
}

export default function SettingsPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const siteId = currentSite?.id;
  const token = session?.access_token;
  const searchParams = useSearchParams();

  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<'gsc' | 'ga4' | 'all' | null>(null);
  const [gscSites, setGscSites] = useState<string[]>([]);
  const [ga4Properties, setGa4Properties] = useState<GA4Property[]>([]);
  const [gscUrl, setGscUrl] = useState('');
  const [ga4Id, setGa4Id] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const fetchStatus = async () => {
    if (!siteId) return;
    try {
      const status = await apiFetch<GoogleStatus>(
        `/sites/${siteId}/google/status`,
        { token },
      );
      setGoogleStatus(status);
      if (status.gsc_site_url) setGscUrl(status.gsc_site_url);
      if (status.ga4_property_id) setGa4Id(status.ga4_property_id);
    } catch {
      // Not connected yet
      setGoogleStatus({ connected: false, gsc_site_url: null, ga4_property_id: null, last_gsc_sync: null, last_ga4_sync: null });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchStatus();
    // Handle OAuth callback
    const connected = searchParams.get('google_connected');
    const error = searchParams.get('google_error');
    if (connected) showMessage('success', '✅ Google account connected successfully!');
    if (error) showMessage('error', `Google connection failed: ${error}`);
  }, [siteId]);

  const handleConnect = () => {
    if (!siteId) return;
    // Use the existing auth/google endpoint which handles state + redirect
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'https://pst-leaving-otherwise-roles.trycloudflare.com';
    window.location.href = `${apiBase}/v1/auth/google?site_id=${siteId}`;
  };

  const handleDisconnect = async () => {
    if (!siteId || !confirm('Disconnect Google account? This will stop data syncing.')) return;
    await apiFetch(`/sites/${siteId}/google/disconnect`, { method: 'DELETE', token });
    await fetchStatus();
    showMessage('success', 'Google account disconnected');
  };

  const fetchGSCSites = async () => {
    if (!siteId) return;
    try {
      const data = await apiFetch<{ sites: string[] }>(`/sites/${siteId}/gsc/sites`, { token });
      setGscSites(data.sites);
    } catch {
      showMessage('error', 'Could not fetch GSC sites');
    }
  };

  const fetchGA4Properties = async () => {
    if (!siteId) return;
    try {
      const data = await apiFetch<{ properties: GA4Property[] }>(`/sites/${siteId}/ga4/properties`, { token });
      setGa4Properties(data.properties);
    } catch {
      showMessage('error', 'Could not fetch GA4 properties');
    }
  };

  const saveGSCUrl = async () => {
    if (!siteId || !gscUrl) return;
    await apiFetch(`/sites/${siteId}/gsc/site-url`, {
      method: 'PATCH', token,
      body: JSON.stringify({ gsc_site_url: gscUrl }),
    });
    showMessage('success', 'GSC site URL saved');
    await fetchStatus();
  };

  const saveGA4Id = async () => {
    if (!siteId || !ga4Id) return;
    await apiFetch(`/sites/${siteId}/ga4/property-id`, {
      method: 'PATCH', token,
      body: JSON.stringify({ property_id: ga4Id }),
    });
    showMessage('success', 'GA4 property ID saved');
    await fetchStatus();
  };

  const syncData = async (type: 'gsc' | 'ga4' | 'all') => {
    if (!siteId) return;
    setSyncing(type);
    try {
      const endpoint = type === 'all' ? 'google/sync-all' : `${type}/sync`;
      const result = await apiFetch(`/sites/${siteId}/${endpoint}`, {
        method: 'POST', token,
      });
      const r = result as Record<string, unknown>;
      if (type === 'all') {
        const gsc = r.gsc as Record<string, unknown>;
        const ga4 = r.ga4 as Record<string, unknown>;
        showMessage('success', `Synced! GSC: ${gsc?.synced ?? 0} rows, GA4: ${ga4?.synced ?? 0} rows`);
      } else {
        showMessage('success', `Synced ${r.synced ?? 0} rows`);
      }
      await fetchStatus();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sync failed';
      showMessage('error', msg);
    } finally {
      setSyncing(null);
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleString();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-6 px-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-text flex items-center gap-2">
          <Settings size={24} className="text-brand-accent" /> Settings
        </h1>
        <p className="text-brand-text-muted text-sm mt-1">
          Connect data sources to unlock full intelligence scoring
        </p>
      </div>

      {message && (
        <div className={`px-4 py-3 rounded-lg text-sm font-medium ${
          message.type === 'success'
            ? 'bg-green-500/10 text-green-400 border border-green-500/20'
            : 'bg-red-500/10 text-red-400 border border-red-500/20'
        }`}>
          {message.text}
        </div>
      )}

      {/* Google Account */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-brand-text flex items-center gap-2">
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Google Account
            </h2>
            <p className="text-xs text-brand-text-muted mt-1">
              Required for Google Search Console and Google Analytics 4
            </p>
          </div>
          <div className="flex items-center gap-2">
            {googleStatus?.connected ? (
              <span className="flex items-center gap-1 text-xs text-green-400">
                <CheckCircle size={14} /> Connected
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-red-400">
                <XCircle size={14} /> Not connected
              </span>
            )}
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          {googleStatus?.connected ? (
            <>
              <button
                onClick={() => void syncData('all')}
                disabled={syncing === 'all'}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-accent/10 text-brand-accent text-sm font-medium hover:bg-brand-accent/20 transition-colors disabled:opacity-50"
              >
                {syncing === 'all' ? <Spinner size="sm" /> : <RefreshCw size={14} />}
                Sync All Data
              </button>
              <button
                onClick={handleDisconnect}
                className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm text-brand-text-muted hover:text-red-400 transition-colors"
              >
                Disconnect
              </button>
            </>
          ) : (
            <button
              onClick={handleConnect}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-accent text-black text-sm font-semibold hover:bg-brand-accent/90 transition-colors"
            >
              Connect Google Account
            </button>
          )}
        </div>
      </Card>

      {/* GSC Section */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Search size={18} className="text-blue-400" />
          <div>
            <h2 className="text-base font-semibold text-brand-text">Google Search Console</h2>
            <p className="text-xs text-brand-text-muted">
              Unlocks: ranking positions, decay detection, CTR analysis, keyword data
            </p>
          </div>
          <div className="ml-auto">
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${
              googleStatus?.gsc_site_url
                ? 'bg-green-500/10 text-green-400'
                : 'bg-amber-500/10 text-amber-400'
            }`}>
              {googleStatus?.last_gsc_sync ? `Last synced: ${formatDate(googleStatus.last_gsc_sync)}` : googleStatus?.gsc_site_url ? 'Configured' : 'Not configured'}
            </span>
          </div>
        </div>

        {googleStatus?.connected && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={gscUrl}
                onChange={e => setGscUrl(e.target.value)}
                placeholder="e.g. https://www.close.com/ or sc-domain:close.com"
                className="flex-1 px-3 py-2 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text placeholder-brand-text-muted focus:outline-none focus:border-brand-accent"
              />
              <button
                onClick={() => void fetchGSCSites()}
                className="px-3 py-2 rounded-lg border border-brand-border text-xs text-brand-text-muted hover:text-brand-text transition-colors whitespace-nowrap"
              >
                Browse sites
              </button>
              <button
                onClick={() => void saveGSCUrl()}
                disabled={!gscUrl}
                className="px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm font-medium hover:bg-blue-500/20 transition-colors disabled:opacity-50"
              >
                Save
              </button>
            </div>

            {gscSites.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="text-xs text-brand-text-muted">Your verified sites:</p>
                {gscSites.map(s => (
                  <button
                    key={s}
                    onClick={() => setGscUrl(s)}
                    className="block text-xs text-brand-accent hover:underline"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {googleStatus.gsc_site_url && (
              <button
                onClick={() => void syncData('gsc')}
                disabled={syncing === 'gsc'}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-sm hover:bg-blue-500/20 transition-colors disabled:opacity-50"
              >
                {syncing === 'gsc' ? <Spinner size="sm" /> : <RefreshCw size={14} />}
                Sync GSC (90 days)
              </button>
            )}
          </div>
        )}

        {!googleStatus?.connected && (
          <p className="text-sm text-brand-text-muted">Connect your Google account above to configure GSC.</p>
        )}
      </Card>

      {/* GA4 Section */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={18} className="text-purple-400" />
          <div>
            <h2 className="text-base font-semibold text-brand-text">Google Analytics 4</h2>
            <p className="text-xs text-brand-text-muted">
              Unlocks: pageviews, engagement rate, traffic trends, impact scoring
            </p>
          </div>
          <div className="ml-auto">
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${
              googleStatus?.ga4_property_id
                ? 'bg-green-500/10 text-green-400'
                : 'bg-amber-500/10 text-amber-400'
            }`}>
              {googleStatus?.last_ga4_sync ? `Last synced: ${formatDate(googleStatus.last_ga4_sync)}` : googleStatus?.ga4_property_id ? 'Configured' : 'Not configured'}
            </span>
          </div>
        </div>

        {googleStatus?.connected && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={ga4Id}
                onChange={e => setGa4Id(e.target.value)}
                placeholder="e.g. 123456789"
                className="flex-1 px-3 py-2 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text placeholder-brand-text-muted focus:outline-none focus:border-brand-accent"
              />
              <button
                onClick={() => void fetchGA4Properties()}
                className="px-3 py-2 rounded-lg border border-brand-border text-xs text-brand-text-muted hover:text-brand-text transition-colors whitespace-nowrap"
              >
                Browse properties
              </button>
              <button
                onClick={() => void saveGA4Id()}
                disabled={!ga4Id}
                className="px-4 py-2 rounded-lg bg-purple-500/10 text-purple-400 text-sm font-medium hover:bg-purple-500/20 transition-colors disabled:opacity-50"
              >
                Save
              </button>
            </div>

            {ga4Properties.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="text-xs text-brand-text-muted">Your GA4 properties:</p>
                {ga4Properties.map(p => (
                  <button
                    key={p.property_id}
                    onClick={() => setGa4Id(p.property_id)}
                    className="block text-xs text-brand-accent hover:underline"
                  >
                    {p.display_name} ({p.property_id}) — {p.account}
                  </button>
                ))}
              </div>
            )}

            {googleStatus.ga4_property_id && (
              <button
                onClick={() => void syncData('ga4')}
                disabled={syncing === 'ga4'}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-500/10 text-purple-400 text-sm hover:bg-purple-500/20 transition-colors disabled:opacity-50"
              >
                {syncing === 'ga4' ? <Spinner size="sm" /> : <RefreshCw size={14} />}
                Sync GA4 (90 days)
              </button>
            )}
          </div>
        )}

        {!googleStatus?.connected && (
          <p className="text-sm text-brand-text-muted">Connect your Google account above to configure GA4.</p>
        )}
      </Card>

      {/* What this unlocks */}
      <Card className="bg-brand-bg border-brand-accent/20">
        <h3 className="text-sm font-semibold text-brand-text mb-3 flex items-center gap-2">
          <Database size={16} className="text-brand-accent" />
          What these integrations unlock
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Health Score', before: '5/10', after: '9/10', color: '#22c55e' },
            { label: 'Problem Detection', before: '7/10', after: '10/10', color: '#22c55e' },
            { label: 'Recommendations', before: '6/10', after: '9/10', color: '#3b82f6' },
            { label: 'Freshness', before: '5/10', after: '9/10', color: '#8b5cf6' },
            { label: 'Cannibalization', before: '8.5/10', after: '10/10', color: '#f97316' },
            { label: 'Overall', before: '7/10', after: '9.5/10', color: '#22c55e' },
          ].map(item => (
            <div key={item.label} className="flex items-center justify-between text-sm">
              <span className="text-brand-text-muted">{item.label}</span>
              <span className="flex items-center gap-1">
                <span className="text-brand-text-muted text-xs">{item.before}</span>
                <span className="text-brand-text-muted text-xs">→</span>
                <span className="font-semibold text-xs" style={{ color: item.color }}>{item.after}</span>
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
