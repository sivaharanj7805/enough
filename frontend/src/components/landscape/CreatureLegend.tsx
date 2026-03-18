'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

const CREATURES = [
  { emoji: '🌸', name: 'Bloomling', color: 'text-green-400', desc: 'Healthy post with traffic — growing opportunity' },
  { emoji: '🦀', name: 'Rustmite', color: 'text-orange-400', desc: 'Declining post — content needs updating' },
  { emoji: '👻', name: 'Fogling', color: 'text-slate-400', desc: 'Orphan post — no inbound links, hidden from Google' },
  { emoji: '〰️', name: 'Tanglevine', color: 'text-red-400', desc: 'Cannibalization — two posts fighting for same keywords' },
];

const TREES = [
  { emoji: '🌳', name: 'Pillar Oak', color: 'text-green-500', desc: 'High-value cornerstone content' },
  { emoji: '🫐', name: 'Supporter Bush', color: 'text-blue-400', desc: 'Supporting content — healthy but secondary' },
  { emoji: '🌿', name: 'Competitor Vine', color: 'text-orange-500', desc: 'Cannibalizing post — entangled with another' },
  { emoji: '🪵', name: 'Dead Stump', color: 'text-gray-500', desc: 'Low health, no traffic — needs action or removal' },
];

export function CreatureLegend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="absolute bottom-4 right-4 z-10 w-64">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-brand-surface/95 backdrop-blur-sm border border-brand-border text-xs text-brand-text-muted hover:text-brand-text transition-colors"
      >
        <span className="font-medium">Legend</span>
        {open ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
      </button>

      {open && (
        <div className="mt-1 rounded-lg bg-brand-surface/95 backdrop-blur-sm border border-brand-border p-3 space-y-3">
          <div>
            <p className="text-xs font-semibold text-brand-text mb-1.5">Creatures (Problems)</p>
            <div className="space-y-1.5">
              {CREATURES.map((c) => (
                <div key={c.name} className="flex items-start gap-2">
                  <span className="text-sm shrink-0">{c.emoji}</span>
                  <div>
                    <span className={`text-xs font-medium ${c.color}`}>{c.name}</span>
                    <p className="text-xs text-brand-text-muted leading-tight">{c.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-brand-border pt-2">
            <p className="text-xs font-semibold text-brand-text mb-1.5">Trees (Post Types)</p>
            <div className="space-y-1.5">
              {TREES.map((t) => (
                <div key={t.name} className="flex items-start gap-2">
                  <span className="text-sm shrink-0">{t.emoji}</span>
                  <div>
                    <span className={`text-xs font-medium ${t.color}`}>{t.name}</span>
                    <p className="text-xs text-brand-text-muted leading-tight">{t.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
