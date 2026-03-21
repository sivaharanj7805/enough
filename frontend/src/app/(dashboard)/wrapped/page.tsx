'use client';

import { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Share2, Sparkles } from 'lucide-react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';

interface Slide {
  title: string;
  subtitle: string;
  stat: string | null;
  stat_label?: string;
  color: string;
}

interface WrappedData {
  period: string;
  data: {
    total_posts: number;
    posts_created: number;
    health_score_start: number | null;
    health_score_end: number | null;
    health_improvement: number | null;
    biggest_improvement: { title: string; url: string; score: number } | null;
    worst_offender: { title: string; url: string; score: number } | null;
    top_cluster: { label: string; health_score: number; post_count: number } | null;
    cluster_count: number;
    swamps_found: number;
    deserts_found: number;
    cannibalization_pairs: number;
    total_words: number;
    ecosystem_narrative: string;
    slides: Slide[];
  };
  generated_at: string | null;
}

const GRADIENT_CLASSES: Record<string, string> = {
  'from-indigo-600 to-purple-700': 'bg-gradient-to-br from-indigo-600 to-purple-700',
  'from-blue-600 to-cyan-600': 'bg-gradient-to-br from-blue-600 to-cyan-600',
  'from-emerald-600 to-teal-600': 'bg-gradient-to-br from-emerald-600 to-teal-600',
  'from-green-600 to-emerald-600': 'bg-gradient-to-br from-green-600 to-emerald-600',
  'from-orange-600 to-red-600': 'bg-gradient-to-br from-orange-600 to-red-600',
  'from-violet-600 to-purple-600': 'bg-gradient-to-br from-violet-600 to-purple-600',
  'from-yellow-500 to-orange-500': 'bg-gradient-to-br from-yellow-500 to-orange-500',
  'from-red-600 to-pink-600': 'bg-gradient-to-br from-red-600 to-pink-600',
  'from-red-700 to-orange-600': 'bg-gradient-to-br from-red-700 to-orange-600',
  'from-cyan-600 to-blue-600': 'bg-gradient-to-br from-cyan-600 to-blue-600',
  'from-indigo-600 to-violet-700': 'bg-gradient-to-br from-indigo-600 to-violet-700',
};

function getGradientClass(color: string): string {
  return GRADIENT_CLASSES[color] || 'bg-gradient-to-br from-indigo-600 to-purple-700';
}

export default function WrappedPage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const token =
    session?.access_token ??
    (typeof window !== 'undefined' ? localStorage.getItem('enough_access_token') : null);

  const [wrapped, setWrapped] = useState<WrappedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [animating, setAnimating] = useState(false);

  const siteId = currentSite?.id;

  // Try to load existing wrapped data
  useEffect(() => {
    if (!siteId || !token) return;
    setLoading(true);
    const year = new Date().getFullYear() - 1;
    apiFetch<WrappedData>(`/sites/${siteId}/gamification/wrapped/${year}`, {
      token: token ?? undefined,
    })
      .then(setWrapped)
      .catch(() => setWrapped(null))
      .finally(() => setLoading(false));
  }, [siteId, token]);

  const handleGenerate = async () => {
    if (!siteId || !token) return;
    setGenerating(true);
    try {
      const result = await apiFetch<WrappedData>(
        `/sites/${siteId}/gamification/wrapped/generate`,
        { method: 'POST', token: token ?? undefined },
      );
      setWrapped(result);
      setCurrentSlide(0);
    } catch {
      // silent
    }
    setGenerating(false);
  };

  const slides = wrapped?.data?.slides ?? [];

  const goToSlide = useCallback((idx: number) => {
    if (animating) return;
    setAnimating(true);
    setCurrentSlide(idx);
    setTimeout(() => setAnimating(false), 400);
  }, [animating]);

  const handleNext = () => {
    if (currentSlide < slides.length - 1) goToSlide(currentSlide + 1);
  };
  const handlePrev = () => {
    if (currentSlide > 0) goToSlide(currentSlide - 1);
  };

  const handleShare = async () => {
    const slide = slides[currentSlide];
    if (!slide) return;
    const text = slide.stat
      ? `${slide.title}: ${slide.stat} ${slide.stat_label ?? ''} - ${slide.subtitle}`
      : `${slide.title} - ${slide.subtitle}`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // fallback
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') handleNext();
      if (e.key === 'ArrowLeft') handlePrev();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-[#3b82f6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!wrapped || slides.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <Sparkles size={48} className="text-[#3b82f6]" />
        <h2 className="text-xl font-bold text-[#e2e8f0]">Content Wrapped</h2>
        <p className="text-sm text-[#64748b] text-center max-w-sm">
          Generate your Spotify Wrapped-style content review. See your year in content at a glance.
        </p>
        <button
          onClick={() => void handleGenerate()}
          disabled={generating}
          className="px-6 py-2.5 rounded-xl bg-[#3b82f6] text-white font-semibold text-sm hover:bg-[#2563eb] transition-colors disabled:opacity-50"
        >
          {generating ? 'Generating...' : 'Generate My Wrapped'}
        </button>
      </div>
    );
  }

  const slide = slides[currentSlide];

  return (
    <div className="max-w-2xl mx-auto py-4">
      {/* Slide container */}
      <div
        className={`relative rounded-2xl overflow-hidden shadow-2xl ${getGradientClass(slide.color)} transition-all duration-500`}
        style={{ minHeight: '420px' }}
      >
        {/* Slide content */}
        <div
          className={`flex flex-col items-center justify-center text-center p-8 min-h-[420px] transition-opacity duration-300 ${
            animating ? 'opacity-0' : 'opacity-100'
          }`}
        >
          <p className="text-white/60 text-xs font-semibold uppercase tracking-widest mb-6">
            {wrapped.data.ecosystem_narrative ? 'Content Wrapped' : 'Your Year in Review'}
          </p>

          {slide.stat && (
            <div className="text-[72px] md:text-[96px] font-bold text-white leading-none mb-2">
              {slide.stat}
            </div>
          )}
          {slide.stat_label && (
            <p className="text-white/70 text-sm font-medium mb-4">{slide.stat_label}</p>
          )}

          <h2 className="text-2xl md:text-3xl font-bold text-white mb-3">{slide.title}</h2>
          <p className="text-white/80 text-sm md:text-base max-w-md leading-relaxed">
            {slide.subtitle}
          </p>
        </div>

        {/* Navigation arrows */}
        <div className="absolute inset-y-0 left-0 flex items-center">
          {currentSlide > 0 && (
            <button
              onClick={handlePrev}
              className="ml-3 p-2 rounded-full bg-black/20 text-white/80 hover:bg-black/40 transition-colors"
            >
              <ChevronLeft size={24} />
            </button>
          )}
        </div>
        <div className="absolute inset-y-0 right-0 flex items-center">
          {currentSlide < slides.length - 1 && (
            <button
              onClick={handleNext}
              className="mr-3 p-2 rounded-full bg-black/20 text-white/80 hover:bg-black/40 transition-colors"
            >
              <ChevronRight size={24} />
            </button>
          )}
        </div>

        {/* Share button */}
        <button
          onClick={() => void handleShare()}
          className="absolute top-4 right-4 p-2 rounded-full bg-black/20 text-white/80 hover:bg-black/40 transition-colors"
          title="Copy slide text"
        >
          <Share2 size={16} />
        </button>

        {/* Slide dots */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5">
          {slides.map((_, idx) => (
            <button
              key={idx}
              onClick={() => goToSlide(idx)}
              className={`w-2 h-2 rounded-full transition-all duration-300 ${
                idx === currentSlide
                  ? 'bg-white w-6'
                  : 'bg-white/40 hover:bg-white/60'
              }`}
            />
          ))}
        </div>
      </div>

      {/* Slide counter */}
      <div className="flex items-center justify-between mt-4 px-1">
        <p className="text-xs text-[#64748b]">
          {currentSlide + 1} of {slides.length}
        </p>
        <p className="text-xs text-[#64748b]">
          Period: {wrapped.period}
        </p>
      </div>
    </div>
  );
}
