'use client';

import { Calendar } from 'lucide-react';

interface TimelineSliderProps {
  months: string[];
  currentMonth: string;
  onChange: (month: string) => void;
}

export function TimelineSlider({ months, currentMonth, onChange }: TimelineSliderProps) {
  const currentIndex = months.indexOf(currentMonth);

  return (
    <div className="absolute bottom-4 left-4 z-10 flex items-center gap-3 rounded-xl border border-brand-border bg-brand-surface/95 backdrop-blur-sm px-4 py-3 shadow-xl">
      <Calendar size={14} className="text-brand-text-muted shrink-0" />
      <input
        type="range"
        min={0}
        max={months.length - 1}
        value={currentIndex >= 0 ? currentIndex : months.length - 1}
        onChange={(e) => {
          const idx = parseInt(e.target.value, 10);
          if (months[idx]) onChange(months[idx]);
        }}
        className="w-40 accent-brand-accent"
      />
      <span className="text-xs font-mono text-brand-text min-w-[70px] text-right">
        {currentMonth}
      </span>
    </div>
  );
}
