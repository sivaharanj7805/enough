'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { ChevronDown, ChevronUp, Trophy, Target, CheckCircle2, Sparkles } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSiteHealth, useClusters, useCannibalizationPairs, useRecommendations } from '@/lib/hooks/useApi';
import { useSite } from '@/lib/hooks/useSite';
import type { SiteHealth, Cluster } from '@/lib/types';

// ─── Types ──────────────────────────────────────────

interface Quest {
  id: string;
  title: string;
  description: string;
  target: number;
  rewardText: string;
  type: 'orphan' | 'decay' | 'swamp' | 'cann' | 'health';
  period: 'daily' | 'weekly';
}

interface QuestProgress {
  questId: string;
  current: number;
  completed: boolean;
  completedAt?: number;
}

interface QuestState {
  weekKey: string;
  progress: Record<string, QuestProgress>;
  discoveredRewards: string[];
}

// ─── ISO week number ────────────────────────────────

function getISOWeekKey(): string {
  const now = new Date();
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

// ─── Deterministic quest generation ─────────────────

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + ch;
    hash = hash & hash; // Convert to 32-bit int
  }
  return Math.abs(hash);
}

const QUEST_TEMPLATES: Omit<Quest, 'id' | 'period'>[] = [
  { title: 'Fix orphan posts', description: 'Add internal links to posts with zero incoming links', target: 3, rewardText: 'Improved crawlability across 3 posts', type: 'orphan' },
  { title: 'Update decaying posts', description: 'Refresh content on posts with declining health trends', target: 2, rewardText: 'Prevented content decay on 2 posts', type: 'decay' },
  { title: 'Consolidate a swamp cluster', description: 'Merge or redirect posts in a swamp-state cluster', target: 1, rewardText: 'Cleaned up keyword cannibalization', type: 'swamp' },
  { title: 'Review cannibalization pairs', description: 'Analyze and resolve cannibalizing post pairs', target: 5, rewardText: 'Resolved overlap between competing posts', type: 'cann' },
  { title: 'Reach health score 60', description: 'Improve your overall site health score to at least 60', target: 60, rewardText: 'Site health is now in the green zone!', type: 'health' },
  { title: 'Fix 5 orphan posts', description: 'Interlink 5 orphan posts to improve site structure', target: 5, rewardText: 'Major interlinking improvement', type: 'orphan' },
  { title: 'Update 3 decaying posts', description: 'Refresh 3 posts showing declining metrics', target: 3, rewardText: 'Reversed decay on 3 key pages', type: 'decay' },
  { title: 'Review 3 cannibalization pairs', description: 'Check and resolve 3 keyword overlapping pairs', target: 3, rewardText: 'Reduced keyword competition', type: 'cann' },
];

function generateWeeklyQuests(weekKey: string): Quest[] {
  const seed = hashString(weekKey);
  const rng = seededRandom(seed);

  // Pick 3-4 quests from templates
  const shuffled = [...QUEST_TEMPLATES].sort(() => rng() - 0.5);
  const picked = shuffled.slice(0, 3 + (rng() > 0.5 ? 1 : 0));

  return picked.map((t, i) => ({
    ...t,
    id: `${weekKey}-${i}`,
    period: 'weekly' as const,
  }));
}

// ─── Compute quest progress from actual data ────────

function computeProgress(
  quest: Quest,
  health: SiteHealth | undefined,
  clusters: Cluster[] | undefined,
  cannCount: number,
): number {
  switch (quest.type) {
    case 'health':
      return Math.round(health?.content_health_score ?? 0);
    case 'orphan': {
      // Count posts that have been fixed (approximate via active_posts ratio)
      const total = health?.total_posts ?? 0;
      const active = health?.active_posts ?? 0;
      return Math.min(quest.target, Math.round((active / Math.max(total, 1)) * quest.target));
    }
    case 'decay': {
      const passive = health?.passive_posts ?? 0;
      const total = health?.total_posts ?? 0;
      // Progress = how many are NOT decaying (inverse)
      const decaying = total - (health?.active_posts ?? 0) - passive;
      return Math.max(0, quest.target - Math.min(quest.target, decaying));
    }
    case 'swamp': {
      const swampCount = clusters?.filter(c => c.ecosystem_state === 'swamp').length ?? 0;
      // If there are no swamps, quest is complete
      return swampCount === 0 ? quest.target : 0;
    }
    case 'cann':
      // Use the count of resolved pairs (approximate)
      return Math.min(quest.target, Math.round(cannCount * 0.3));
    default:
      return 0;
  }
}

// ─── localStorage persistence ───────────────────────

const STORAGE_KEY = 'tended_quests_state';

function loadQuestState(): QuestState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveQuestState(state: QuestState): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // storage full
  }
}

// ─── Component ──────────────────────────────────────

export function QuestsPanel() {
  const [collapsed, setCollapsed] = useState(false);
  const { currentSite } = useSite();
  const { data: health } = useSiteHealth(currentSite?.id ?? null);
  const { data: clusters } = useClusters(currentSite?.id ?? null);
  const { data: cannPairs } = useCannibalizationPairs(currentSite?.id ?? null);
  const { data: recs } = useRecommendations(currentSite?.id ?? null, { status: 'completed' });

  const weekKey = useMemo(() => getISOWeekKey(), []);
  const quests = useMemo(() => generateWeeklyQuests(weekKey), [weekKey]);

  const [questState, setQuestState] = useState<QuestState>(() => {
    const loaded = loadQuestState();
    if (loaded && loaded.weekKey === weekKey) return loaded;
    return { weekKey, progress: {}, discoveredRewards: [] };
  });

  const cannCount = cannPairs?.length ?? 0;

  // Recompute live progress
  const questsWithProgress = useMemo(() => {
    return quests.map((quest) => {
      const saved = questState.progress[quest.id];
      const liveProgress = computeProgress(quest, health, clusters ?? undefined, cannCount);
      const current = Math.max(saved?.current ?? 0, liveProgress);
      const completed = saved?.completed || current >= quest.target;

      return {
        quest,
        current: Math.min(current, quest.target),
        completed,
      };
    });
  }, [quests, health, clusters, cannCount, questState]);

  const completedCount = questsWithProgress.filter(q => q.completed).length;
  const totalCount = questsWithProgress.length;

  // Persist changes
  const markComplete = useCallback((questId: string) => {
    setQuestState(prev => {
      const next: QuestState = {
        ...prev,
        progress: {
          ...prev.progress,
          [questId]: {
            questId,
            current: quests.find(q => q.id === questId)?.target ?? 0,
            completed: true,
            completedAt: Date.now(),
          },
        },
      };
      saveQuestState(next);
      return next;
    });
  }, [quests]);

  // Auto-mark completed quests
  useEffect(() => {
    questsWithProgress.forEach(({ quest, completed }) => {
      if (completed && !questState.progress[quest.id]?.completed) {
        markComplete(quest.id);
      }
    });
  }, [questsWithProgress, questState, markComplete]);

  if (!health) return null;

  return (
    <Card className="!p-0 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-brand-surface-hover transition-colors"
      >
        <div className="flex items-center gap-2">
          <Target size={16} className="text-purple-400" />
          <span className="text-sm font-semibold text-brand-text">Weekly Quests</span>
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
            {completedCount}/{totalCount}
          </span>
        </div>
        {collapsed ? <ChevronDown size={14} className="text-brand-text-muted" /> : <ChevronUp size={14} className="text-brand-text-muted" />}
      </button>

      {!collapsed && (
        <div className="px-5 pb-4 space-y-3">
          {/* Week label */}
          <p className="text-[10px] uppercase tracking-wider text-[#64748b]">
            Week of {weekKey} — Resets Monday
          </p>

          {questsWithProgress.map(({ quest, current, completed }) => {
            const pct = Math.min(100, (current / quest.target) * 100);

            return (
              <div
                key={quest.id}
                className={`rounded-lg border px-3 py-2.5 transition-all ${
                  completed
                    ? 'border-green-500/20 bg-green-500/5'
                    : 'border-brand-border bg-brand-surface-hover'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-1.5">
                      {completed ? (
                        <CheckCircle2 size={12} className="text-green-400 flex-shrink-0" />
                      ) : (
                        <Sparkles size={12} className="text-purple-400 flex-shrink-0" />
                      )}
                      <span className={`text-xs font-semibold ${completed ? 'text-green-400 line-through' : 'text-brand-text'}`}>
                        {quest.title}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#64748b] mt-0.5 ml-[18px]">{quest.description}</p>
                  </div>
                  <span className="text-[10px] font-mono text-[#64748b] flex-shrink-0">
                    {current}/{quest.target}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="mt-2 ml-[18px]">
                  <div className="h-1 rounded-full bg-[#1e293b] overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: completed ? '#22c55e' : '#a855f7',
                      }}
                    />
                  </div>
                </div>

                {/* Reward text on completion */}
                {completed && (
                  <div className="mt-1.5 ml-[18px] flex items-center gap-1">
                    <Trophy size={10} className="text-yellow-400" />
                    <span className="text-[10px] text-yellow-400">{quest.rewardText}</span>
                  </div>
                )}
              </div>
            );
          })}

          {/* All quests completed */}
          {completedCount === totalCount && (
            <div className="text-center py-2">
              <p className="text-xs font-medium text-green-400">All quests completed this week!</p>
              <p className="text-[10px] text-[#64748b] mt-0.5">New quests arrive Monday</p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
