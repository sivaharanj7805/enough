'use client';

import { useState, useEffect } from 'react';
import { Ghost, Plus, Eye, EyeOff } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import Link from 'next/link';

interface ContentGap {
  topic: string;
  gap_type: string;
  priority: number;
  cluster_label?: string;
}

interface GhostMapProps {
  visible: boolean;
  onToggle: () => void;
}

export function GhostMapToggle({ visible, onToggle }: GhostMapProps) {
  return (
    <button
      onClick={onToggle}
      className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
        visible
          ? 'bg-purple-500/20 text-purple-400'
          : 'bg-[#1e293b] text-[#64748b] hover:text-[#94a3b8]'
      }`}
      title="Toggle Ghost Map — show content gaps"
    >
      <Ghost size={14} />
      Ghosts
    </button>
  );
}

export function GhostMapOverlay() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const [gaps, setGaps] = useState<ContentGap[]>([]);
  const [loading, setLoading] = useState(true);

  const siteId = currentSite?.id;

  useEffect(() => {
    if (!siteId || !token) return;
    setLoading(true);
    // Try content gaps endpoint if available, fall back to cluster analysis
    apiFetch<{ gaps: ContentGap[] }>(`/sites/${siteId}/intelligence/content-gaps`, {
      token: token ?? undefined,
    })
      .then((res) => setGaps(res.gaps || []))
      .catch(() => {
        // Fallback: get clusters with desert state as "gaps"
        apiFetch<Array<{ label: string; ecosystem_state: string; health_score: number }>>(
          `/sites/${siteId}/intelligence/clusters`,
          { token: token ?? undefined },
        )
          .then((clusters) => {
            const desertGaps: ContentGap[] = (clusters || [])
              .filter((c) => c.ecosystem_state === 'desert')
              .map((c) => ({
                topic: c.label || 'Unnamed topic',
                gap_type: 'thin_coverage',
                priority: 1,
                cluster_label: c.label,
              }));
            setGaps(desertGaps);
          })
          .catch(() => setGaps([]));
      })
      .finally(() => setLoading(false));
  }, [siteId, token]);

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-[#1e293b]/50 rounded-lg" />
        ))}
      </div>
    );
  }

  if (gaps.length === 0) {
    return (
      <Card className="!p-4 text-center">
        <Ghost size={24} className="text-[#64748b] mx-auto mb-2" />
        <p className="text-xs text-[#64748b]">No content ghosts found. Your coverage looks solid!</p>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-widest text-purple-400 mb-2 flex items-center gap-1.5">
        <Ghost size={12} />
        Ghost Map — Missing Content
      </p>
      {gaps.map((gap, idx) => (
        <GhostCluster key={idx} gap={gap} />
      ))}
    </div>
  );
}

function GhostCluster({ gap }: { gap: ContentGap }) {
  const [hovered, setHovered] = useState(false);

  const priorityColor =
    gap.priority >= 3 ? '#ef4444' : gap.priority >= 2 ? '#f59e0b' : '#64748b';

  return (
    <div
      className="relative rounded-lg border border-dashed border-purple-500/30 bg-purple-500/5 p-3 transition-all duration-300 hover:border-purple-500/50 hover:bg-purple-500/10"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        animation: 'pulse 3s ease-in-out infinite',
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Ghost size={16} className="text-purple-400/60" />
          <span className="text-sm font-medium text-[#e2e8f0]">{gap.topic}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded"
            style={{ backgroundColor: `${priorityColor}20`, color: priorityColor }}
          >
            {gap.gap_type.replace(/_/g, ' ')}
          </span>
          <Link
            href={`/briefs?topic=${encodeURIComponent(gap.topic)}`}
            className="flex items-center gap-1 text-[10px] font-medium text-[#3b82f6] hover:text-[#2563eb] transition-colors"
          >
            <Plus size={10} /> Brief
          </Link>
        </div>
      </div>
      {gap.cluster_label && (
        <p className="text-[10px] text-[#64748b] mt-1 pl-6">
          Near cluster: {gap.cluster_label}
        </p>
      )}
    </div>
  );
}
