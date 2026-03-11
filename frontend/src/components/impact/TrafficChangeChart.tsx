'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { ImpactSnapshotResponse } from '@/lib/types/phase5';

interface TrafficChangeChartProps {
  baselineTraffic: number;
  latestTraffic: number | null;
  snapshots: ImpactSnapshotResponse[];
}

export function TrafficChangeChart({
  baselineTraffic,
  latestTraffic,
  snapshots,
}: TrafficChangeChartProps) {
  const data = [
    { name: 'Baseline', traffic: baselineTraffic },
    ...snapshots
      .filter((s) => s.milestone !== null)
      .map((s) => ({
        name: s.milestone ?? '',
        traffic: s.traffic,
      })),
  ];

  // Add current if different from last snapshot
  if (latestTraffic !== null) {
    const lastSnapshot = snapshots[snapshots.length - 1];
    if (!lastSnapshot || lastSnapshot.traffic !== latestTraffic) {
      data.push({ name: 'Current', traffic: latestTraffic });
    }
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="name"
            tick={{ fill: '#94a3b8', fontSize: 12 }}
            axisLine={{ stroke: '#1f2937' }}
          />
          <YAxis
            tick={{ fill: '#94a3b8', fontSize: 12 }}
            axisLine={{ stroke: '#1f2937' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#111827',
              border: '1px solid #1f2937',
              borderRadius: '8px',
              color: '#e2e8f0',
            }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <Bar dataKey="traffic" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={
                  index === 0
                    ? '#6b7280'
                    : entry.traffic >= baselineTraffic
                    ? '#22c55e'
                    : '#ef4444'
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
