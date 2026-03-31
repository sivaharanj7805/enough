'use client';

import { Sparkles, Shield, Code2, Brain } from 'lucide-react';
import { Card } from '@/components/ui/Card';

interface AIScores {
  avg_citability: number;
  avg_eeat: number;
  avg_schema: number;
  avg_extraction: number;
  pct_has_schema: number;
  pct_ai_ready: number;
  total_scored: number;
}

interface Props {
  scores: AIScores | null;
  loading?: boolean;
  onRunScan?: () => void;
}

function ScoreBar({ label, score, icon, color }: {
  label: string;
  score: number;
  icon: React.ReactNode;
  color: string;
}) {
  const pct = Math.round(Math.min(score, 100));
  const colorMap: Record<string, string> = {
    amber: 'bg-amber-400',
    blue: 'bg-blue-400',
    purple: 'bg-purple-400',
    green: 'bg-[#22c55e]',
  };
  const textMap: Record<string, string> = {
    amber: 'text-amber-400',
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    green: 'text-[#22c55e]',
  };

  return (
    <div className="flex items-center gap-3">
      <div className={`shrink-0 ${textMap[color] ?? 'text-gray-400'}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-[#94a3b8]">{label}</span>
          <span className={`text-xs font-semibold ${textMap[color] ?? 'text-gray-400'}`}>{pct}/100</span>
        </div>
        <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${colorMap[color] ?? 'bg-gray-400'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function AIReadinessCard({ scores, loading, onRunScan }: Props) {
  if (loading) {
    return (
      <Card className="animate-pulse">
        <div className="h-4 w-32 bg-[#1e293b] rounded mb-4" />
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-8 bg-[#1e293b] rounded" />
          ))}
        </div>
      </Card>
    );
  }

  if (!scores || scores.total_scored === 0) {
    return (
      <Card>
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-1.5">
              <Sparkles size={14} className="text-amber-400" />
              AI Readiness
            </h3>
            <p className="text-xs text-[#64748b] mt-0.5">2026 SEO scoring</p>
          </div>
        </div>
        <div className="text-center py-4">
          <p className="text-xs text-[#64748b] mb-3">
            Score your content for AI citability, E-E-A-T signals, schema markup, and extraction structure.
          </p>
          {onRunScan && (
            <button
              onClick={onRunScan}
              className="px-4 py-2 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-medium hover:bg-amber-500/20 transition-colors"
            >
              Run AI Readiness Scan
            </button>
          )}
        </div>
      </Card>
    );
  }

  const overallScore = Math.round(
    (scores.avg_citability + scores.avg_eeat + scores.avg_schema + scores.avg_extraction) / 4
  );

  const overallColor =
    overallScore >= 60 ? 'text-[#22c55e]' :
    overallScore >= 35 ? 'text-amber-400' :
    'text-red-400';

  // Identify which dimension is dragging the composite down the most
  const dimensions = [
    { name: 'Schema Markup', score: scores.avg_schema },
    { name: 'AI Citability', score: scores.avg_citability },
    { name: 'E-E-A-T', score: scores.avg_eeat },
    { name: 'AI Extraction', score: scores.avg_extraction },
  ];
  const otherDimsAvg = (dim: typeof dimensions[0]) => {
    const others = dimensions.filter(d => d !== dim);
    return others.reduce((sum, d) => sum + d.score, 0) / others.length;
  };
  const biggestGap = dimensions.reduce<{ name: string; gap: number; score: number }>((worst, dim) => {
    const gap = otherDimsAvg(dim) - dim.score;
    return gap > worst.gap ? { name: dim.name, gap, score: dim.score } : worst;
  }, { name: '', gap: 0, score: 0 });
  const showGapHint = biggestGap.gap >= 20;

  return (
    <Card>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-1.5">
            <Sparkles size={14} className="text-amber-400" />
            AI Readiness
          </h3>
          <p className="text-xs text-[#64748b] mt-0.5">2026 SEO · {scores.total_scored} posts scored</p>
        </div>
        <div className="text-right">
          <span className={`text-2xl font-bold ${overallColor}`}>{overallScore}</span>
          <span className="text-xs text-[#475569]">/100</span>
          {showGapHint && (
            <p className="text-[10px] text-[#64748b] mt-0.5">
              {biggestGap.name} ({Math.round(biggestGap.score)}/100) is your biggest gap
            </p>
          )}
        </div>
      </div>

      <div className="space-y-3 mb-4">
        <ScoreBar
          label="AI Citability"
          score={scores.avg_citability}
          icon={<Sparkles size={13} />}
          color="amber"
        />
        <ScoreBar
          label="E-E-A-T Signals"
          score={scores.avg_eeat}
          icon={<Shield size={13} />}
          color="blue"
        />
        <ScoreBar
          label="Schema Markup"
          score={scores.avg_schema}
          icon={<Code2 size={13} />}
          color="purple"
        />
        <ScoreBar
          label="AI Extraction"
          score={scores.avg_extraction}
          icon={<Brain size={13} />}
          color="green"
        />
      </div>

      <div className="flex gap-3 pt-3 border-t border-[#1e293b]">
        <div className="flex-1 text-center">
          <p className="text-lg font-bold text-[#22c55e]">{scores.pct_ai_ready}%</p>
          <p className="text-[10px] text-[#64748b]">AI-Ready Posts</p>
        </div>
        <div className="flex-1 text-center">
          <p className="text-lg font-bold text-amber-400">{scores.pct_has_schema}%</p>
          <p className="text-[10px] text-[#64748b]">Have Schema</p>
        </div>
      </div>
    </Card>
  );
}
