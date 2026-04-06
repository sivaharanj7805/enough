'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { Spinner } from '@/components/ui/Spinner';
import { useToast } from '@/components/ui/Toast';
import { apiFetch, apiUrl } from '@/lib/api';
import { CheckCircle, XCircle, RefreshCw, Settings, Globe, Bell, User, Search, TrendingUp, Link2 } from 'lucide-react';

interface GoogleStatus { connected: boolean; gsc_site_url: string | null; ga4_property_id: string | null; last_gsc_sync: string | null; last_ga4_sync: string | null }
interface GA4Property { property_id: string; display_name: string; account: string }
type Tab = 'integrations' | 'site' | 'notifications' | 'account';

const CMS_OPTIONS = ['WordPress', 'Sitemap', 'HubSpot', 'Webflow', 'Ghost'] as const;
const RECRAWL_OPTIONS = ['Manual', 'Weekly', 'Monthly'] as const;
const DIGEST_OPTIONS = ['Weekly', 'Biweekly', 'Monthly', 'Off'] as const;
const TABS: { id: Tab; label: string; icon: typeof Settings }[] = [
  { id: 'integrations', label: 'Integrations', icon: Link2 },
  { id: 'site', label: 'Site', icon: Globe },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'account', label: 'Account', icon: User },
];

const input = 'w-full rounded-lg bg-brand-bg border border-brand-border px-4 py-2.5 text-sm text-brand-text placeholder-brand-text-muted focus:outline-none focus:border-brand-accent transition-colors';
const btn = 'inline-flex items-center gap-2 rounded-lg bg-brand-accent text-white px-4 py-2 text-sm font-medium hover:bg-brand-accent/90 transition-colors disabled:opacity-50';
const card = 'rounded-xl border border-brand-border bg-brand-surface p-5';
const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : 'Never');

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${ok ? 'bg-green-500/10 text-green-400' : 'bg-neutral-500/10 text-brand-text-muted'}`}>
      {ok ? <CheckCircle size={12} /> : <XCircle size={12} />} {label}
    </span>
  );
}

export default function SettingsPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const { toast } = useToast();
  const searchParams = useSearchParams();
  const siteId = currentSite?.id;
  const token = session?.access_token;

  const [tab, setTab] = useState<Tab>('integrations');
  const [gs, setGs] = useState<GoogleStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<'gsc' | 'ga4' | 'all' | null>(null);
  const [gscSites, setGscSites] = useState<string[]>([]);
  const [ga4Props, setGa4Props] = useState<GA4Property[]>([]);
  const [gscUrl, setGscUrl] = useState('');
  const [ga4Id, setGa4Id] = useState('');
  const [siteUrl, setSiteUrl] = useState(currentSite?.domain ?? '');
  const [cmsType, setCmsType] = useState('Sitemap');
  const [recrawl, setRecrawl] = useState('Manual');
  const [savingSite, setSavingSite] = useState(false);
  const [digest, setDigest] = useState('Weekly');
  const [savingNotif, setSavingNotif] = useState(false);

  useEffect(() => { if (currentSite?.domain) setSiteUrl(currentSite.domain); }, [currentSite?.domain]);

  const fetchStatus = async () => {
    if (!siteId) return;
    try {
      const s = await apiFetch<GoogleStatus>(`/sites/${siteId}/google/status`, { token });
      setGs(s);
      if (s.gsc_site_url) setGscUrl(s.gsc_site_url);
      if (s.ga4_property_id) setGa4Id(s.ga4_property_id);
    } catch { setGs({ connected: false, gsc_site_url: null, ga4_property_id: null, last_gsc_sync: null, last_ga4_sync: null }); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    void fetchStatus();
    const c = searchParams.get('google_connected'), e = searchParams.get('google_error');
    if (c) toast('Google account connected successfully!', { type: 'success' });
    if (e) toast(`Google connection failed: ${e}`, { type: 'error' });
  }, [siteId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleConnect = () => { if (siteId) window.location.href = apiUrl(`/sites/${siteId}/google/connect`); };

  const handleDisconnect = async () => {
    if (!siteId || !confirm('Disconnect Google account? This will stop data syncing.')) return;
    await apiFetch(`/sites/${siteId}/google/disconnect`, { method: 'DELETE', token });
    await fetchStatus();
    toast('Google account disconnected', { type: 'success' });
  };

  const fetchGSCSites = async () => {
    if (!siteId) return;
    try { setGscSites((await apiFetch<{ sites: string[] }>(`/sites/${siteId}/gsc/sites`, { token })).sites); }
    catch { toast('Could not fetch GSC sites', { type: 'error' }); }
  };

  const fetchGA4Props = async () => {
    if (!siteId) return;
    try { setGa4Props((await apiFetch<{ properties: GA4Property[] }>(`/sites/${siteId}/ga4/properties`, { token })).properties); }
    catch { toast('Could not fetch GA4 properties', { type: 'error' }); }
  };

  const saveGSCUrl = async () => {
    if (!siteId || !gscUrl) return;
    await apiFetch(`/sites/${siteId}/gsc/site-url`, { method: 'PATCH', token, body: JSON.stringify({ gsc_site_url: gscUrl }) });
    toast('GSC site URL saved', { type: 'success' }); await fetchStatus();
  };

  const saveGA4Id = async () => {
    if (!siteId || !ga4Id) return;
    await apiFetch(`/sites/${siteId}/ga4/property-id`, { method: 'PATCH', token, body: JSON.stringify({ property_id: ga4Id }) });
    toast('GA4 property ID saved', { type: 'success' }); await fetchStatus();
  };

  const syncData = async (type: 'gsc' | 'ga4' | 'all') => {
    if (!siteId) return;
    setSyncing(type);
    try {
      const ep = type === 'all' ? 'google/sync-all' : `${type}/sync`;
      const r = (await apiFetch(`/sites/${siteId}/${ep}`, { method: 'POST', token })) as Record<string, unknown>;
      if (type === 'all') {
        const g = r.gsc as Record<string, unknown>, a = r.ga4 as Record<string, unknown>;
        toast(`Synced! GSC: ${g?.synced ?? 0} rows, GA4: ${a?.synced ?? 0} rows`, { type: 'success' });
      } else toast(`Synced ${r.synced ?? 0} rows`, { type: 'success' });
      await fetchStatus();
    } catch (e: unknown) { toast(e instanceof Error ? e.message : 'Sync failed', { type: 'error' }); }
    finally { setSyncing(null); }
  };

  const saveSiteSettings = async () => {
    if (!siteId) return; setSavingSite(true);
    try {
      await apiFetch(`/sites/${siteId}/settings`, { method: 'PATCH', token, body: JSON.stringify({ url: siteUrl, cms_type: cmsType.toLowerCase(), recrawl_schedule: recrawl.toLowerCase() }) });
      toast('Site settings saved successfully.', { type: 'success' });
    } catch { toast('Failed to save site settings.', { type: 'error' }); }
    finally { setSavingSite(false); }
  };

  const saveNotifications = async () => {
    if (!siteId) return; setSavingNotif(true);
    try {
      await apiFetch(`/sites/${siteId}/notifications`, { method: 'PATCH', token, body: JSON.stringify({ digest_frequency: digest.toLowerCase() }) });
      toast('Notification preferences saved.', { type: 'success' });
    } catch { toast('Failed to save notification preferences.', { type: 'error' }); }
    finally { setSavingNotif(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>;

  const GoogleSvg = () => (
    <svg className="w-8 h-8 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-6 px-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text flex items-center gap-2">
          <Settings size={22} className="text-brand-accent" /> Settings
        </h1>
        <p className="text-sm text-brand-text-muted mt-1">Manage integrations, site configuration, and preferences</p>
      </div>

      {/* Tabs */}
      <nav className="flex border-b border-brand-border" role="tablist" aria-label="Settings tabs">
        {TABS.map((t) => { const I = t.icon; return (
          <button key={t.id} role="tab" aria-selected={tab === t.id} aria-controls={`p-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${tab === t.id ? 'border-brand-accent text-brand-accent' : 'border-transparent text-brand-text-muted hover:text-brand-text hover:border-brand-border'}`}>
            <I size={16} /> {t.label}
          </button>
        ); })}
      </nav>

      {/* ── Integrations ── */}
      <div role="tabpanel" id="p-integrations" hidden={tab !== 'integrations'} className="space-y-6">
        {/* Google connection */}
        <div className={card}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <GoogleSvg />
              <div>
                <h2 className="text-base font-semibold text-brand-text">Google Account</h2>
                <p className="text-xs text-brand-text-muted mt-0.5">Required for Search Console and Analytics data</p>
              </div>
            </div>
            <Badge ok={!!gs?.connected} label={gs?.connected ? 'Connected' : 'Not connected'} />
          </div>
          <div className="mt-4 flex gap-2">
            {gs?.connected ? (<>
              <button onClick={() => void syncData('all')} disabled={syncing === 'all'} aria-label="Sync all Google data"
                className="inline-flex items-center gap-2 rounded-lg bg-brand-accent/10 text-brand-accent px-4 py-2 text-sm font-medium hover:bg-brand-accent/20 transition-colors disabled:opacity-50">
                {syncing === 'all' ? <Spinner size="sm" /> : <RefreshCw size={14} />} Sync All Data
              </button>
              <button onClick={() => void handleDisconnect()} aria-label="Disconnect Google"
                className="rounded-lg px-3 py-2 text-sm text-brand-text-muted hover:text-red-400 transition-colors">Disconnect</button>
            </>) : (
              <button onClick={handleConnect} aria-label="Connect Google account" className={btn}>Connect Google Account</button>
            )}
          </div>
        </div>

        {/* GSC */}
        <div className={card}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Search size={18} className="text-blue-400" />
              <div>
                <h2 className="text-base font-semibold text-brand-text">Google Search Console</h2>
                <p className="text-xs text-brand-text-muted">Rankings, CTR, keyword data</p>
              </div>
            </div>
            <Badge ok={!!gs?.gsc_site_url} label={gs?.last_gsc_sync ? `Synced ${fmtDate(gs.last_gsc_sync)}` : gs?.gsc_site_url ? 'Configured' : 'Not configured'} />
          </div>
          {gs?.connected ? (<div className="space-y-3">
            <div className="flex gap-2">
              <label htmlFor="gsc-url" className="sr-only">GSC site URL</label>
              <input id="gsc-url" type="text" value={gscUrl} onChange={(e) => setGscUrl(e.target.value)} placeholder="e.g. https://example.com/ or sc-domain:example.com" className={input.replace('w-full', 'flex-1')} />
              <button onClick={() => void fetchGSCSites()} aria-label="Browse GSC sites" className="shrink-0 rounded-lg border border-brand-border px-3 py-2.5 text-xs text-brand-text-muted hover:text-brand-text transition-colors">Browse</button>
              <button onClick={() => void saveGSCUrl()} disabled={!gscUrl} aria-label="Save GSC URL" className={btn}>Save</button>
            </div>
            {gscSites.length > 0 && <div className="space-y-1"><p className="text-xs text-brand-text-muted">Your verified sites:</p>
              {gscSites.map((s) => <button key={s} onClick={() => setGscUrl(s)} className="block text-xs text-brand-accent hover:underline">{s}</button>)}
            </div>}
            {gs.gsc_site_url && <button onClick={() => void syncData('gsc')} disabled={syncing === 'gsc'} aria-label="Sync GSC data"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-500/10 text-blue-400 px-3 py-2 text-sm hover:bg-blue-500/20 transition-colors disabled:opacity-50">
              {syncing === 'gsc' ? <Spinner size="sm" /> : <RefreshCw size={14} />} Sync GSC (90 days)
            </button>}
          </div>) : <p className="text-sm text-brand-text-muted">Connect your Google account above to configure GSC.</p>}
        </div>

        {/* GA4 */}
        <div className={card}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp size={18} className="text-purple-400" />
              <div>
                <h2 className="text-base font-semibold text-brand-text">Google Analytics 4</h2>
                <p className="text-xs text-brand-text-muted">Pageviews, engagement, traffic trends</p>
              </div>
            </div>
            <Badge ok={!!gs?.ga4_property_id} label={gs?.last_ga4_sync ? `Synced ${fmtDate(gs.last_ga4_sync)}` : gs?.ga4_property_id ? 'Configured' : 'Not configured'} />
          </div>
          {gs?.connected ? (<div className="space-y-3">
            <div className="flex gap-2">
              <label htmlFor="ga4-id" className="sr-only">GA4 property ID</label>
              <input id="ga4-id" type="text" value={ga4Id} onChange={(e) => setGa4Id(e.target.value)} placeholder="e.g. 123456789" className={input.replace('w-full', 'flex-1')} />
              <button onClick={() => void fetchGA4Props()} aria-label="Browse GA4 properties" className="shrink-0 rounded-lg border border-brand-border px-3 py-2.5 text-xs text-brand-text-muted hover:text-brand-text transition-colors">Browse</button>
              <button onClick={() => void saveGA4Id()} disabled={!ga4Id} aria-label="Save GA4 ID" className={btn}>Save</button>
            </div>
            {ga4Props.length > 0 && <div className="space-y-1"><p className="text-xs text-brand-text-muted">Your GA4 properties:</p>
              {ga4Props.map((p) => <button key={p.property_id} onClick={() => setGa4Id(p.property_id)} className="block text-xs text-brand-accent hover:underline">{p.display_name} ({p.property_id}) — {p.account}</button>)}
            </div>}
            {gs.ga4_property_id && <button onClick={() => void syncData('ga4')} disabled={syncing === 'ga4'} aria-label="Sync GA4 data"
              className="inline-flex items-center gap-2 rounded-lg bg-purple-500/10 text-purple-400 px-3 py-2 text-sm hover:bg-purple-500/20 transition-colors disabled:opacity-50">
              {syncing === 'ga4' ? <Spinner size="sm" /> : <RefreshCw size={14} />} Sync GA4 (90 days)
            </button>}
          </div>) : <p className="text-sm text-brand-text-muted">Connect your Google account above to configure GA4.</p>}
        </div>
      </div>

      {/* ── Site ── */}
      <div role="tabpanel" id="p-site" hidden={tab !== 'site'} className="space-y-6">
        <div className={card}>
          <h2 className="text-base font-semibold text-brand-text mb-5">Site Configuration</h2>
          <div className="space-y-4">
            <div>
              <label htmlFor="site-url" className="block text-sm font-medium text-brand-text mb-1.5">Domain</label>
              <input id="site-url" type="text" value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} placeholder="https://yourblog.com" aria-required="true" className={input} />
            </div>
            <div>
              <label htmlFor="cms-type" className="block text-sm font-medium text-brand-text mb-1.5">CMS Type</label>
              <select id="cms-type" value={cmsType} onChange={(e) => setCmsType(e.target.value)} className={input}>
                {CMS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="recrawl" className="block text-sm font-medium text-brand-text mb-1.5">Re-crawl Schedule</label>
              <select id="recrawl" value={recrawl} onChange={(e) => setRecrawl(e.target.value)} className={input}>
                {RECRAWL_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div className="border-t border-brand-border pt-4">
              <button onClick={() => void saveSiteSettings()} disabled={savingSite} className={btn}>
                {savingSite && <Spinner size="sm" />} Save Site Settings
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Notifications ── */}
      <div role="tabpanel" id="p-notifications" hidden={tab !== 'notifications'} className="space-y-6">
        <div className={card}>
          <h2 className="text-base font-semibold text-brand-text mb-4">Email Digest</h2>
          <fieldset>
            <legend className="block text-sm text-brand-text-muted mb-3">How often would you like to receive email digests?</legend>
            <div className="space-y-1">
              {DIGEST_OPTIONS.map((o) => (
                <label key={o} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-brand-bg cursor-pointer transition-colors">
                  <input type="radio" name="digest" value={o} checked={digest === o} onChange={(e) => setDigest(e.target.value)}
                    className="w-4 h-4 text-brand-accent border-brand-border focus:ring-2 focus:ring-brand-accent" />
                  <span className="text-sm text-brand-text">{o}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="border-t border-brand-border mt-4 pt-4">
            <button onClick={() => void saveNotifications()} disabled={savingNotif} className={btn}>
              {savingNotif && <Spinner size="sm" />} Save Preferences
            </button>
          </div>
        </div>
      </div>

      {/* ── Account ── */}
      <div role="tabpanel" id="p-account" hidden={tab !== 'account'} className="space-y-6">
        <div className={card}>
          <h2 className="text-base font-semibold text-brand-text mb-4">Account Information</h2>
          <div className="space-y-4">
            <div>
              <p className="text-xs text-brand-text-muted mb-0.5">Email</p>
              <p className="text-sm font-medium text-brand-text">{session?.user?.email ?? '—'}</p>
            </div>
            <div className="border-t border-brand-border pt-4">
              <button onClick={() => {
                void apiFetch('/auth/password-reset', { token: token ?? '', method: 'POST', body: JSON.stringify({ email: session?.user?.email }) })
                  .then(() => toast('Password reset email sent.', { type: 'success' }))
                  .catch(() => toast('Failed to send reset email.', { type: 'error' }));
              }} aria-label="Change password" className="rounded-lg border border-brand-border px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-bg transition-colors">
                Change Password
              </button>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-red-500/20 bg-brand-surface p-5">
          <h2 className="text-base font-semibold text-red-400 mb-2">Danger Zone</h2>
          <p className="text-sm text-brand-text-muted mb-4">Permanently delete your account, all sites, and all data. This cannot be undone.</p>
          <button onClick={() => {
            if (confirm('Are you absolutely sure? This will permanently delete your account and ALL data.')) {
              void apiFetch('/auth/account', { token: token ?? '', method: 'DELETE' })
                .then(() => { window.location.href = '/'; })
                .catch(() => toast('Failed to delete account.', { type: 'error' }));
            }
          }} aria-label="Delete account" className="rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors">
            Delete My Account
          </button>
        </div>
      </div>
    </div>
  );
}
