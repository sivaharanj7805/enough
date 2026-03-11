'use client';

import { Sun, CloudRain, Waves } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/ProgressBar';
import type { OracleVerdict, OracleConfidence } from '@/lib/types';

interface VerdictDisplayProps {
  verdict: OracleVerdict;
}

interface VerdictConfig {
  icon: typeof Sun;
  color: string;
  glowColor: string;
  title: string;
  subtitle: string;
}

const VERDICT_CONFIG: Record<OracleConfidence, VerdictConfig> = {
  publish: {
    icon: Sun,
    color: '#22c55e',
    glowColor: '#22c55e',
    title: 'Clear skies. This content has room to grow.',
    subtitle: 'Publish with confidence',
  },
  update: {
    icon: CloudRain,
    color: '#eab308',
    glowColor: '#eab308',
    title: 'Some overlap detected. Consider updating existing content instead.',
    subtitle: 'Update recommended',
  },
  skip: {
    icon: Waves,
    color: '#ef4444',
    glowColor: '#ef4444',
    title: 'This topic is saturated. Publishing will likely cannibalize existing content.',
    subtitle: 'Skip or consolidate',
  },
};

export function VerdictDisplay({ verdict }: VerdictDisplayProps) {
  const config = VERDICT_CONFIG[verdict.confidence];
  const Icon = config.icon;

  return (
    <Card glow glowColor={config.glowColor}>
      <div className="text-center mb-6">
        <div
          className="inline-flex rounded-full p-4 mb-4"
          style={{ backgroundColor: `${config.color}15` }}
        >
          <Icon size={40} style={{ color: config.color }} />
        </div>
        <h3 className="text-lg font-semibold text-brand-text">{config.title}</h3>
        <p className="text-sm text-brand-text-muted mt-1">{config.subtitle}</p>
      </div>

      {/* Confidence bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-brand-text-muted">Confidence</span>
          <span className="text-xs font-mono" style={{ color: config.color }}>
            {(verdict.confidence_score * 100).toFixed(0)}%
          </span>
        </div>
        <ProgressBar value={verdict.confidence_score * 100} color={config.color} />
      </div>

      {/* Reasoning */}
      <div className="rounded-lg bg-brand-bg/50 p-4 mb-4">
        <h4 className="text-xs font-semibold text-brand-text-muted mb-2">Analysis</h4>
        <p className="text-sm text-brand-text leading-relaxed">{verdict.reasoning}</p>
      </div>

      {/* Recommendation */}
      <div
        className="rounded-lg p-4 border"
        style={{ borderColor: `${config.color}30`, backgroundColor: `${config.color}08` }}
      >
        <h4 className="text-xs font-semibold mb-2" style={{ color: config.color }}>
          Recommendation
        </h4>
        <p className="text-sm text-brand-text">{verdict.recommendation}</p>
      </div>

      {/* Existing post to update */}
      {verdict.existing_post_to_update && (
        <div className="mt-4 rounded-lg bg-yellow-500/5 border border-yellow-500/20 p-3">
          <p className="text-xs text-brand-text-muted mb-1">Consider updating instead:</p>
          <a
            href={verdict.existing_post_to_update}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-brand-accent hover:underline"
          >
            {verdict.existing_post_to_update}
          </a>
        </div>
      )}
    </Card>
  );
}
