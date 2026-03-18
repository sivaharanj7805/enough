'use client';

import { useState, useEffect } from 'react';
import { X, ChevronRight, ChevronLeft } from 'lucide-react';

const TOUR_KEY = 'enough_landscape_tour_seen';

const STEPS = [
  {
    emoji: '🌍',
    title: 'Your Content Ecosystem',
    body: 'This is your entire blog visualized as a living world. Each colored zone is a topic cluster. Zoom in, pan around — explore.',
  },
  {
    emoji: '🌳',
    title: 'Trees Are Your Posts',
    body: 'Tall green oaks = high-value pillar posts. Blue bushes = supporting content. Orange vines = cannibalizing posts fighting each other. Grey stumps = dead weight with no traffic.',
  },
  {
    emoji: '🐾',
    title: 'Creatures Signal Problems',
    body: 'Green bloomlings = healthy posts with traffic. Orange rustmites = content that\'s decaying in rankings. Pale foglings = orphaned posts Google can\'t find. Click any creature to see what\'s wrong.',
  },
  {
    emoji: '🔗',
    title: 'Orange Lines = Cannibalization',
    body: 'Dashed lines connecting posts are Tanglevines — they show pairs of posts competing for the same keywords. Thicker and redder = more dangerous overlap.',
  },
  {
    emoji: '✦',
    title: 'Click Anything',
    body: 'Click a tree or creature to open the post detail panel with health score and specific AI recommendations. Click a zone label to zoom in. Everything is interactive.',
  },
];

export function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const seen = localStorage.getItem(TOUR_KEY);
      if (!seen) setVisible(true);
    }
  }, []);

  const close = () => {
    setVisible(false);
    if (typeof window !== 'undefined') localStorage.setItem(TOUR_KEY, '1');
  };

  const next = () => {
    if (step < STEPS.length - 1) setStep(step + 1);
    else close();
  };

  const prev = () => {
    if (step > 0) setStep(step - 1);
  };

  if (!visible) return null;

  const current = STEPS[step];

  return (
    <div className="absolute inset-0 z-50 flex items-end justify-center pb-12 pointer-events-none">
      {/* Dim overlay */}
      <div className="absolute inset-0 bg-black/40 pointer-events-auto" onClick={close} />

      {/* Tour card */}
      <div className="relative pointer-events-auto w-full max-w-sm mx-4 rounded-2xl bg-brand-surface border border-brand-border shadow-2xl overflow-hidden">
        {/* Progress bar */}
        <div className="h-0.5 bg-brand-surface-hover">
          <div
            className="h-full bg-brand-accent transition-all duration-300"
            style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
          />
        </div>

        <div className="p-5">
          {/* Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">{current.emoji}</span>
              <h3 className="text-sm font-semibold text-brand-text">{current.title}</h3>
            </div>
            <button
              onClick={close}
              className="rounded-lg p-1 text-brand-text-muted hover:text-brand-text hover:bg-brand-surface-hover transition-colors"
            >
              <X size={14} />
            </button>
          </div>

          <p className="text-sm text-brand-text-muted leading-relaxed mb-4">{current.body}</p>

          {/* Controls */}
          <div className="flex items-center justify-between">
            <div className="flex gap-1">
              {STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`w-1.5 h-1.5 rounded-full transition-all ${i === step ? 'bg-brand-accent w-3' : 'bg-brand-border'}`}
                />
              ))}
            </div>

            <div className="flex gap-2">
              {step > 0 && (
                <button
                  onClick={prev}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-brand-text-muted hover:bg-brand-surface-hover transition-colors"
                >
                  <ChevronLeft size={12} /> Back
                </button>
              )}
              <button
                onClick={next}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-brand-accent text-black text-xs font-medium hover:bg-brand-accent/90 transition-colors"
              >
                {step < STEPS.length - 1 ? <>Next <ChevronRight size={12} /></> : 'Got it ✓'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
