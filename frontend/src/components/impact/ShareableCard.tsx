'use client';

import { useRef, useState, useCallback } from 'react';
import { Copy, Share2, Download, Check } from 'lucide-react';
import { useSiteHealth } from '@/lib/hooks/useApi';
import { useSite } from '@/lib/hooks/useSite';

interface ImpactData {
  trafficChange: number;
  postsConsolidated: number;
  daysTracked: number;
  healthScore: number;
  healthImprovement: number;
  siteName: string;
}

function useImpactData(): ImpactData | null {
  const { currentSite } = useSite();
  const { data: health } = useSiteHealth(currentSite?.id ?? null);

  if (!health) return null;

  const trends = health.trends ?? {};
  const delta30d = trends['30d'] ?? 0;
  const daysTracked = trends['90d'] != null ? 90 : trends['60d'] != null ? 60 : trends['30d'] != null ? 30 : 0;

  return {
    trafficChange: delta30d,
    postsConsolidated: health.dead_posts + health.cannibalistic_posts,
    daysTracked,
    healthScore: Math.round(health.content_health_score),
    healthImprovement: delta30d,
    siteName: currentSite?.name ?? currentSite?.domain ?? 'My Site',
  };
}

function StatBlock({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col items-center">
      <span
        className="text-2xl font-bold"
        style={{ color: accent ? '#4ade80' : '#e2e8f0' }}
      >
        {value}
      </span>
      <span className="text-[10px] uppercase tracking-wider text-[#64748b] mt-1">{label}</span>
    </div>
  );
}

/** Props for standalone usage (backwards-compatible) */
interface ShareableCardProps {
  trafficChangePct?: number;
  postsConsolidated?: number;
  daysTracked?: number;
  healthBefore?: number;
  healthAfter?: number;
  siteName?: string;
}

export function ShareableCard(props: ShareableCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const hookData = useImpactData();

  // Use props if provided, otherwise fall back to hook data
  const data: ImpactData | null = props.trafficChangePct != null
    ? {
        trafficChange: props.trafficChangePct,
        postsConsolidated: props.postsConsolidated ?? 0,
        daysTracked: props.daysTracked ?? 0,
        healthScore: props.healthAfter ?? 0,
        healthImprovement: (props.healthAfter ?? 0) - (props.healthBefore ?? 0),
        siteName: props.siteName ?? 'My Site',
      }
    : hookData;

  const captureCard = useCallback(async (): Promise<Blob | null> => {
    const el = cardRef.current;
    if (!el || !data) return null;

    const canvas = document.createElement('canvas');
    const scale = 2;
    const w = 360;
    const h = 240;
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    ctx.scale(scale, scale);

    // Background gradient
    const grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#0a0f1a');
    grad.addColorStop(0.5, '#0f1729');
    grad.addColorStop(1, '#0a1628');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(0, 0, w, h, 16);
    ctx.fill();

    // Border
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(0.5, 0.5, w - 1, h - 1, 16);
    ctx.stroke();

    // Title
    ctx.font = 'bold 18px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#e2e8f0';
    ctx.textAlign = 'center';
    ctx.fillText('Content Health Report', w / 2, 36);

    // Site name
    ctx.font = '12px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.fillText(data.siteName, w / 2, 54);

    // Health score
    const scoreColor = data.healthScore >= 60 ? '#22c55e' : data.healthScore >= 40 ? '#eab308' : '#ef4444';
    ctx.font = 'bold 52px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = scoreColor;
    ctx.fillText(data.healthScore.toString(), w / 2, 118);

    ctx.font = '10px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.fillText('HEALTH SCORE', w / 2, 134);

    // Stats row
    const statsY = 172;
    const colW = w / 3;

    ctx.font = 'bold 20px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = data.trafficChange >= 0 ? '#4ade80' : '#ef4444';
    ctx.fillText(`${data.trafficChange >= 0 ? '+' : ''}${data.trafficChange}%`, colW * 0.5, statsY);
    ctx.font = '9px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.fillText('TRAFFIC CHANGE', colW * 0.5, statsY + 15);

    ctx.font = 'bold 20px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(data.postsConsolidated.toString(), colW * 1.5, statsY);
    ctx.font = '9px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.fillText('POSTS FLAGGED', colW * 1.5, statsY + 15);

    ctx.font = 'bold 20px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(data.daysTracked.toString(), colW * 2.5, statsY);
    ctx.font = '9px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.fillText('DAYS TRACKED', colW * 2.5, statsY + 15);

    // Footer
    ctx.font = '10px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#475569';
    ctx.fillText('Powered by Tended — Content Intelligence', w / 2, h - 14);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/png');
    });
  }, [data]);

  const handleCopy = useCallback(async () => {
    try {
      const blob = await captureCard();
      if (blob) {
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob }),
        ]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      if (data) {
        const text = `Content Health Report — ${data.siteName}\nHealth Score: ${data.healthScore}\nTraffic Change: ${data.trafficChange >= 0 ? '+' : ''}${data.trafficChange}%\nPosts Flagged: ${data.postsConsolidated}\nDays Tracked: ${data.daysTracked}`;
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    }
  }, [captureCard, data]);

  const handleShare = useCallback(async () => {
    if (!data) return;
    try {
      const blob = await captureCard();
      const files = blob ? [new File([blob], 'content-health.png', { type: 'image/png' })] : [];
      if (navigator.share) {
        await navigator.share({
          title: 'Content Health Report',
          text: `My content health score is ${data.healthScore}! Traffic changed ${data.trafficChange >= 0 ? '+' : ''}${data.trafficChange}% over ${data.daysTracked} days.`,
          ...(files.length > 0 ? { files } : {}),
        });
        setShared(true);
        setTimeout(() => setShared(false), 2000);
      }
    } catch {
      // User cancelled
    }
  }, [captureCard, data]);

  const handleDownload = useCallback(async () => {
    const blob = await captureCard();
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'content-health-report.png';
    a.click();
    URL.revokeObjectURL(url);
  }, [captureCard]);

  if (!data) return null;

  return (
    <div className="space-y-3">
      <div
        ref={cardRef}
        className="relative overflow-hidden rounded-xl border border-[#22c55e]/20 p-6"
        style={{
          background: 'linear-gradient(135deg, #0a0f1a 0%, #0f1729 50%, #0a1628 100%)',
          width: '360px',
          height: '240px',
        }}
      >
        <div
          className="absolute -top-20 -right-20 w-40 h-40 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #22c55e, transparent)' }}
        />
        <div
          className="absolute -bottom-16 -left-16 w-32 h-32 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #3b82f6, transparent)' }}
        />

        <div className="relative z-10 text-center">
          <h3 className="text-lg font-bold text-[#e2e8f0]">Content Health Report</h3>
          <p className="text-xs text-[#64748b] mt-0.5">{data.siteName}</p>

          <div
            className="text-[56px] font-bold leading-none mt-3"
            style={{
              color: data.healthScore >= 60 ? '#22c55e' : data.healthScore >= 40 ? '#eab308' : '#ef4444',
            }}
          >
            {data.healthScore}
          </div>
          <p className="text-[10px] uppercase tracking-widest text-[#64748b] mt-1">Health Score</p>

          <div className="flex justify-around mt-5">
            <StatBlock
              label="Traffic Change"
              value={`${data.trafficChange >= 0 ? '+' : ''}${data.trafficChange}%`}
              accent={data.trafficChange > 0}
            />
            <StatBlock label="Posts Flagged" value={data.postsConsolidated.toString()} />
            <StatBlock label="Days Tracked" value={data.daysTracked.toString()} />
          </div>
        </div>

        <p className="absolute bottom-2 left-0 right-0 text-center text-[9px] text-[#475569]">
          Powered by Tended — Content Intelligence
        </p>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => void handleCopy()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-surface border border-brand-border text-xs font-medium text-brand-text hover:bg-brand-surface-hover transition-colors"
        >
          {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
          {copied ? 'Copied!' : 'Copy Image'}
        </button>
        <button
          onClick={() => void handleShare()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-accent text-black hover:bg-brand-accent-hover transition-colors text-xs font-medium"
        >
          {shared ? <Check size={12} /> : <Share2 size={12} />}
          {shared ? 'Shared!' : 'Share'}
        </button>
        <button
          onClick={() => void handleDownload()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-surface border border-brand-border text-xs font-medium text-brand-text hover:bg-brand-surface-hover transition-colors"
        >
          <Download size={12} />
          Download
        </button>
      </div>
    </div>
  );
}
