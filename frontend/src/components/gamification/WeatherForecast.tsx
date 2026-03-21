'use client';

import { useState, useEffect } from 'react';
import { Sun, Cloud, CloudRain, CloudLightning } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

interface ForecastDay {
  date: string;
  day_label: string;
  weather: string;
  icon: string;
  label: string;
  description: string;
  reasoning: string;
}

interface ForecastResponse {
  site_id: string;
  forecast: ForecastDay[];
}

const WEATHER_ICONS: Record<string, { Icon: typeof Sun; color: string; bg: string }> = {
  sunny: { Icon: Sun, color: '#eab308', bg: 'bg-yellow-500/10' },
  cloudy: { Icon: Cloud, color: '#94a3b8', bg: 'bg-slate-400/10' },
  rainy: { Icon: CloudRain, color: '#3b82f6', bg: 'bg-blue-500/10' },
  stormy: { Icon: CloudLightning, color: '#ef4444', bg: 'bg-red-500/10' },
};

export function WeatherForecast() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const [forecast, setForecast] = useState<ForecastDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredDay, setHoveredDay] = useState<number | null>(null);

  const siteId = currentSite?.id;

  useEffect(() => {
    if (!siteId || !token) return;
    setLoading(true);
    apiFetch<ForecastResponse>(`/sites/${siteId}/gamification/forecast`, {
      token: token ?? undefined,
    })
      .then((res) => setForecast(res.forecast || []))
      .catch(() => setForecast([]))
      .finally(() => setLoading(false));
  }, [siteId, token]);

  if (loading) {
    return (
      <Card className="!p-4 animate-pulse">
        <div className="h-20 bg-[#1e293b] rounded" />
      </Card>
    );
  }

  if (forecast.length === 0) {
    return null;
  }

  return (
    <Card className="!p-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#64748b] mb-3">
        7-Day Content Forecast
      </p>

      <div className="flex items-end justify-between gap-1">
        {forecast.map((day, idx) => {
          const weatherStyle = WEATHER_ICONS[day.weather] ?? WEATHER_ICONS.cloudy;
          const { Icon, color, bg } = weatherStyle;
          const isToday = idx === 0;

          return (
            <div
              key={day.date}
              className="relative flex flex-col items-center flex-1 min-w-0"
              onMouseEnter={() => setHoveredDay(idx)}
              onMouseLeave={() => setHoveredDay(null)}
            >
              {/* Tooltip */}
              {hoveredDay === idx && (
                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 z-10 w-48 rounded-lg bg-[#1e293b] border border-[#334155] p-2.5 text-xs text-[#94a3b8] shadow-lg">
                  <p className="font-medium text-[#e2e8f0] mb-1">{day.label}</p>
                  <p>{day.reasoning}</p>
                </div>
              )}

              <div className={`rounded-lg p-2 ${bg} ${isToday ? 'ring-1 ring-[#3b82f6]/30' : ''}`}>
                <Icon size={20} style={{ color }} />
              </div>
              <span className={`text-[10px] mt-1 ${isToday ? 'font-bold text-[#e2e8f0]' : 'text-[#64748b]'}`}>
                {isToday ? 'Today' : day.day_label}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
