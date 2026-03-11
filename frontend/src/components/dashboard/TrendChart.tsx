'use client';

import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Card } from '@/components/ui/Card';
interface TrendDataPoint {
  date: string;
  pageviews: number;
}

interface TrendChartProps {
  data: TrendDataPoint[];
}

type TimeRange = '30d' | '60d' | '90d';

const RANGE_DAYS: Record<TimeRange, number> = {
  '30d': 30,
  '60d': 60,
  '90d': 90,
};

export function TrendChart({ data }: TrendChartProps) {
  const [range, setRange] = useState<TimeRange>('30d');

  const filtered = data.slice(-RANGE_DAYS[range]);

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-medium text-brand-text-muted">Traffic Trend</p>
        <div className="flex gap-1">
          {(['30d', '60d', '90d'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                range === r
                  ? 'bg-brand-accent/10 text-brand-accent'
                  : 'text-brand-text-muted hover:text-brand-text'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={filtered}>
            <defs>
              <linearGradient id="trafficGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              tick={{ fontSize: 11 }}
              tickFormatter={(d: string) => {
                const date = new Date(d);
                return `${date.getMonth() + 1}/${date.getDate()}`;
              }}
            />
            <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#111827',
                border: '1px solid #1f2937',
                borderRadius: '8px',
                color: '#e2e8f0',
                fontSize: '12px',
              }}
            />
            <Area
              type="monotone"
              dataKey="pageviews"
              stroke="#22c55e"
              fill="url(#trafficGradient)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
