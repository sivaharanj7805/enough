'use client';

import { useState, useEffect } from 'react';
import { Flame, Check } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

interface StreakData {
  current_streak: number;
  longest_streak: number;
  last_check_in: string | null;
  total_check_ins: number;
  milestone: string | null;
  message?: string;
}

const MILESTONE_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  bronze: { bg: 'bg-amber-700/20', text: 'text-amber-500', label: '7-day Bronze' },
  silver: { bg: 'bg-slate-400/20', text: 'text-slate-300', label: '30-day Silver' },
  gold: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: '100-day Gold' },
};

export function StreakCard() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('tended_access_token') : null);

  const [streak, setStreak] = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkingIn, setCheckingIn] = useState(false);
  const [justCheckedIn, setJustCheckedIn] = useState(false);

  const siteId = currentSite?.id;

  useEffect(() => {
    if (!siteId || !token) return;
    setLoading(true);
    apiFetch<StreakData>(`/sites/${siteId}/gamification/streaks`, { token: token ?? undefined })
      .then(setStreak)
      .catch(() => setStreak(null))
      .finally(() => setLoading(false));
  }, [siteId, token]);

  const handleCheckIn = async () => {
    if (!siteId || !token || checkingIn) return;
    setCheckingIn(true);
    try {
      const result = await apiFetch<StreakData>(
        `/sites/${siteId}/gamification/streaks/check-in`,
        { method: 'POST', token: token ?? undefined },
      );
      setStreak(result);
      setJustCheckedIn(true);
    } catch {
      // silent
    }
    setCheckingIn(false);
  };

  if (loading) {
    return (
      <Card className="!p-4 animate-pulse">
        <div className="h-16 bg-[#1e293b] rounded" />
      </Card>
    );
  }

  const current = streak?.current_streak ?? 0;
  const longest = streak?.longest_streak ?? 0;
  const milestone = streak?.milestone;
  const milestoneStyle = milestone ? MILESTONE_COLORS[milestone] : null;

  // Determine flame color based on streak
  let flameColor = '#64748b'; // gray
  if (current >= 100) flameColor = '#eab308'; // gold
  else if (current >= 30) flameColor = '#94a3b8'; // silver
  else if (current >= 7) flameColor = '#d97706'; // bronze/amber
  else if (current >= 1) flameColor = '#f97316'; // orange

  const isCheckedInToday = streak?.last_check_in === new Date().toISOString().split('T')[0];

  return (
    <Card className="!p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <Flame
              size={32}
              style={{ color: flameColor }}
              className={current > 0 ? 'animate-pulse' : ''}
            />
            {current > 0 && (
              <span
                className="absolute -bottom-1 -right-1 text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center"
                style={{ backgroundColor: flameColor, color: '#fff' }}
              >
                {current}
              </span>
            )}
          </div>
          <div>
            <p className="text-sm font-semibold text-[#e2e8f0]">
              {current > 0 ? `${current}-day streak` : 'No streak yet'}
            </p>
            <p className="text-xs text-[#64748b]">
              Longest: {longest} days &middot; {streak?.total_check_ins ?? 0} total
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {milestoneStyle && (
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${milestoneStyle.bg} ${milestoneStyle.text}`}>
              {milestoneStyle.label}
            </span>
          )}

          {isCheckedInToday || justCheckedIn ? (
            <span className="flex items-center gap-1 text-xs font-medium text-[#22c55e] px-3 py-1.5 rounded-lg bg-[#22c55e]/10">
              <Check size={14} /> Done
            </span>
          ) : (
            <button
              onClick={() => void handleCheckIn()}
              disabled={checkingIn}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[#3b82f6]/10 text-[#3b82f6] hover:bg-[#3b82f6]/20 transition-colors disabled:opacity-50"
            >
              {checkingIn ? 'Checking in...' : 'Check in'}
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}
