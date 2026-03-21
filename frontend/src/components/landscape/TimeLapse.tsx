'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

interface HealthSnapshot {
  date: string;
  score: number;
}

interface TimeLapseProps {
  onDateChange?: (date: string, score: number) => void;
}

export function TimeLapse({ onDateChange }: TimeLapseProps) {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const [history, setHistory] = useState<HealthSnapshot[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const siteId = currentSite?.id;

  useEffect(() => {
    if (!siteId || !token) return;
    setLoading(true);
    apiFetch<{ history: HealthSnapshot[] }>(
      `/sites/${siteId}/analytics/health-history`,
      { token: token ?? undefined },
    )
      .then((res) => {
        const sorted = (res.history || []).sort(
          (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
        );
        setHistory(sorted);
        setCurrentIndex(sorted.length - 1);
      })
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, [siteId, token]);

  const goTo = useCallback(
    (idx: number) => {
      const clamped = Math.max(0, Math.min(idx, history.length - 1));
      setCurrentIndex(clamped);
      if (history[clamped]) {
        onDateChange?.(history[clamped].date, history[clamped].score);
      }
    },
    [history, onDateChange],
  );

  // Auto-play
  useEffect(() => {
    if (playing && history.length > 0) {
      intervalRef.current = setInterval(() => {
        setCurrentIndex((prev) => {
          const next = prev + 1;
          if (next >= history.length) {
            setPlaying(false);
            return prev;
          }
          if (history[next]) {
            onDateChange?.(history[next].date, history[next].score);
          }
          return next;
        });
      }, 800);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, history, onDateChange]);

  if (loading || history.length < 2) {
    return null;
  }

  const current = history[currentIndex];
  const scoreColor =
    current.score >= 70 ? '#22c55e' : current.score >= 40 ? '#eab308' : '#ef4444';

  return (
    <Card className="!p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b]">
          Time-Lapse
        </p>
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-[#e2e8f0]">{current.date}</span>
          <span className="text-sm font-bold" style={{ color: scoreColor }}>
            {current.score.toFixed(0)}
          </span>
        </div>
      </div>

      {/* Score visualization bar */}
      <div className="relative h-12 mb-3 bg-[#0f172a] rounded-lg overflow-hidden">
        {history.map((snap, idx) => {
          const x = (idx / (history.length - 1)) * 100;
          const h = (snap.score / 100) * 100;
          const color =
            snap.score >= 70 ? '#22c55e' : snap.score >= 40 ? '#eab308' : '#ef4444';
          return (
            <div
              key={idx}
              className="absolute bottom-0 transition-all duration-150"
              style={{
                left: `${x}%`,
                width: `${Math.max(100 / history.length, 2)}%`,
                height: `${h}%`,
                backgroundColor: idx === currentIndex ? color : `${color}40`,
              }}
            />
          );
        })}
        {/* Playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white/80 transition-all duration-150"
          style={{ left: `${(currentIndex / (history.length - 1)) * 100}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => goTo(0)}
          className="p-1.5 rounded text-[#64748b] hover:text-[#e2e8f0] transition-colors"
          title="Go to start"
        >
          <SkipBack size={14} />
        </button>

        <button
          onClick={() => setPlaying((p) => !p)}
          className="p-2 rounded-lg bg-[#3b82f6]/10 text-[#3b82f6] hover:bg-[#3b82f6]/20 transition-colors"
          title={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </button>

        <button
          onClick={() => goTo(history.length - 1)}
          className="p-1.5 rounded text-[#64748b] hover:text-[#e2e8f0] transition-colors"
          title="Go to end"
        >
          <SkipForward size={14} />
        </button>

        {/* Slider */}
        <input
          type="range"
          min={0}
          max={history.length - 1}
          value={currentIndex}
          onChange={(e) => goTo(Number(e.target.value))}
          className="flex-1 h-1 bg-[#1e293b] rounded-full appearance-none cursor-pointer accent-[#3b82f6]"
        />
      </div>
    </Card>
  );
}
