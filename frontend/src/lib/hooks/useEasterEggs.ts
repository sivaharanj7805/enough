'use client';

import { useEffect, useCallback, useRef, useState } from 'react';

const STORAGE_KEY = 'enough_easter_eggs';

interface EasterEggState {
  konami: boolean;
  logoClicks: boolean;
  bloom: boolean;
}

type EasterEgg = keyof EasterEggState;

function loadEggs(): EasterEggState {
  if (typeof window === 'undefined') return { konami: false, logoClicks: false, bloom: false };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : { konami: false, logoClicks: false, bloom: false };
  } catch {
    return { konami: false, logoClicks: false, bloom: false };
  }
}

function saveEggs(state: EasterEggState): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // storage full
  }
}

/**
 * Show a confetti animation on the page.
 * Uses DOM elements — no dependencies.
 */
function showConfetti(): void {
  const container = document.createElement('div');
  container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;overflow:hidden';
  document.body.appendChild(container);

  const colors = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#a855f7', '#ec4899'];

  for (let i = 0; i < 80; i++) {
    const particle = document.createElement('div');
    const color = colors[Math.floor(Math.random() * colors.length)];
    const size = 4 + Math.random() * 6;
    const x = Math.random() * 100;
    const delay = Math.random() * 0.5;
    const duration = 1.5 + Math.random() * 1.5;
    const rotation = Math.random() * 720;

    particle.style.cssText = `
      position: absolute;
      left: ${x}%;
      top: -10px;
      width: ${size}px;
      height: ${size}px;
      background: ${color};
      border-radius: ${Math.random() > 0.5 ? '50%' : '2px'};
      opacity: 0.9;
      animation: confetti-fall ${duration}s ${delay}s ease-in forwards;
      transform: rotate(${rotation}deg);
    `;
    container.appendChild(particle);
  }

  // Inject keyframe animation if not already present
  if (!document.getElementById('confetti-style')) {
    const style = document.createElement('style');
    style.id = 'confetti-style';
    style.textContent = `
      @keyframes confetti-fall {
        0% { transform: translateY(0) rotate(0deg); opacity: 1; }
        100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }

  // Clean up after animation
  setTimeout(() => container.remove(), 4000);
}

/**
 * Show a toast notification.
 */
function showToast(message: string, icon: string): void {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    z-index: 10000;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    border-radius: 12px;
    background: #1e293b;
    border: 1px solid #334155;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    font-size: 14px;
    color: #e2e8f0;
    font-family: system-ui, -apple-system, sans-serif;
    transition: transform 0.3s ease, opacity 0.3s ease;
    opacity: 0;
  `;
  toast.innerHTML = `<span style="font-size:20px">${icon}</span> ${message}`;
  document.body.appendChild(toast);

  // Animate in
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(-50%) translateY(0)';
  });

  // Animate out
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/**
 * Apply zen mode — dims the UI and makes it peaceful.
 */
function toggleZenMode(on: boolean): void {
  const existing = document.getElementById('enough-zen-overlay');
  if (on && !existing) {
    const overlay = document.createElement('div');
    overlay.id = 'enough-zen-overlay';
    overlay.style.cssText = `
      position: fixed;
      inset: 0;
      z-index: 9998;
      background: rgba(10, 15, 26, 0.7);
      backdrop-filter: blur(2px);
      pointer-events: none;
      transition: opacity 0.5s ease;
    `;
    document.body.appendChild(overlay);
    showToast('Zen Mode activated. Click anywhere to exit.', '🧘');

    // Click to exit
    const exitHandler = () => {
      toggleZenMode(false);
      document.removeEventListener('click', exitHandler);
    };
    setTimeout(() => {
      overlay.style.pointerEvents = 'auto';
      document.addEventListener('click', exitHandler);
    }, 500);
  } else if (!on && existing) {
    existing.style.opacity = '0';
    setTimeout(() => existing.remove(), 500);
  }
}

export interface EasterEggsAPI {
  /** Which eggs have been discovered */
  discovered: EasterEggState;
  /** Total eggs found */
  totalFound: number;
  /** Whether any eggs have been found (show trophy) */
  hasAnyEggs: boolean;
  /** Trigger the bloom easter egg (all creatures max level) */
  triggerBloom: () => void;
  /** Register a logo click (call from logo component) */
  registerLogoClick: () => void;
}

export function useEasterEggs(): EasterEggsAPI {
  const [discovered, setDiscovered] = useState<EasterEggState>(() => loadEggs());
  const konamiBuffer = useRef<string[]>([]);
  const logoClickCount = useRef(0);
  const logoClickTimer = useRef<NodeJS.Timeout | null>(null);
  const bloomBuffer = useRef('');

  const discover = useCallback((egg: EasterEgg) => {
    setDiscovered(prev => {
      if (prev[egg]) return prev;
      const next = { ...prev, [egg]: true };
      saveEggs(next);
      return next;
    });
  }, []);

  // Konami code listener: Up Up Down Down Left Right Left Right B A
  useEffect(() => {
    const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'KeyB', 'KeyA'];

    const handleKeyDown = (e: KeyboardEvent) => {
      // Konami code detection
      konamiBuffer.current.push(e.code);
      if (konamiBuffer.current.length > KONAMI.length) {
        konamiBuffer.current.shift();
      }
      if (konamiBuffer.current.length === KONAMI.length &&
          konamiBuffer.current.every((k, i) => k === KONAMI[i])) {
        konamiBuffer.current = [];
        showConfetti();
        showToast('You found the secret garden!', '🌿');
        discover('konami');
      }

      // "bloom" typing detection on landscape page
      if (window.location.pathname.includes('/landscape')) {
        if (e.key.length === 1) {
          bloomBuffer.current += e.key.toLowerCase();
          if (bloomBuffer.current.length > 10) {
            bloomBuffer.current = bloomBuffer.current.slice(-10);
          }
          if (bloomBuffer.current.includes('bloom')) {
            bloomBuffer.current = '';
            showConfetti();
            showToast('All creatures evolved to max level!', '🌸');
            discover('bloom');
            // Dispatch custom event that landscape can listen for
            window.dispatchEvent(new CustomEvent('enough:bloom'));
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [discover]);

  const triggerBloom = useCallback(() => {
    showConfetti();
    showToast('All creatures evolved to max level!', '🌸');
    discover('bloom');
    window.dispatchEvent(new CustomEvent('enough:bloom'));
  }, [discover]);

  const registerLogoClick = useCallback(() => {
    logoClickCount.current += 1;
    if (logoClickTimer.current) clearTimeout(logoClickTimer.current);

    if (logoClickCount.current >= 5) {
      logoClickCount.current = 0;
      toggleZenMode(true);
      discover('logoClicks');
    }

    logoClickTimer.current = setTimeout(() => {
      logoClickCount.current = 0;
    }, 2000);
  }, [discover]);

  const totalFound = Object.values(discovered).filter(Boolean).length;

  return {
    discovered,
    totalFound,
    hasAnyEggs: totalFound > 0,
    triggerBloom,
    registerLogoClick,
  };
}
