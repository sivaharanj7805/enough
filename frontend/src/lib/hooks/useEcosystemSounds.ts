'use client';

import { useCallback, useRef, useState, useEffect } from 'react';

const STORAGE_KEY = 'enough_sounds_enabled';

type OscillatorType = 'sine' | 'triangle' | 'sawtooth' | 'square';

interface ToneConfig {
  frequency: number;
  duration: number;
  type: OscillatorType;
  gain: number;
  rampDown?: boolean;
  detune?: number;
}

/**
 * Play a short oscillator tone using Web Audio API.
 * No mp3 files needed — pure synthesis.
 */
function playTone(ctx: AudioContext, config: ToneConfig): void {
  const osc = ctx.createOscillator();
  const gainNode = ctx.createGain();

  osc.type = config.type;
  osc.frequency.setValueAtTime(config.frequency, ctx.currentTime);
  if (config.detune) {
    osc.detune.setValueAtTime(config.detune, ctx.currentTime);
  }

  gainNode.gain.setValueAtTime(config.gain, ctx.currentTime);
  if (config.rampDown !== false) {
    gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + config.duration);
  }

  osc.connect(gainNode);
  gainNode.connect(ctx.destination);

  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + config.duration);
}

/**
 * Play a chord (multiple tones at once).
 */
function playChord(ctx: AudioContext, tones: ToneConfig[]): void {
  tones.forEach(t => playTone(ctx, t));
}

export interface EcosystemSounds {
  /** Whether sounds are enabled */
  enabled: boolean;
  /** Toggle sound on/off */
  toggle: () => void;
  /** Subtle chime when hovering a cluster */
  playHoverCluster: () => void;
  /** Soft click when selecting a post */
  playClickPost: () => void;
  /** Nature sound when opening a creature panel */
  playCreatureOpen: () => void;
  /** Ambient shift for season transitions */
  playSeasonTransition: () => void;
  /** Quest completion fanfare */
  playQuestComplete: () => void;
}

export function useEcosystemSounds(): EcosystemSounds {
  const ctxRef = useRef<AudioContext | null>(null);
  const [enabled, setEnabled] = useState(false);

  // Load preference from localStorage on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(STORAGE_KEY);
    setEnabled(stored === 'true');
  }, []);

  const getCtx = useCallback((): AudioContext | null => {
    if (!enabled) return null;
    if (!ctxRef.current) {
      try {
        ctxRef.current = new AudioContext();
      } catch {
        return null;
      }
    }
    if (ctxRef.current.state === 'suspended') {
      void ctxRef.current.resume();
    }
    return ctxRef.current;
  }, [enabled]);

  const toggle = useCallback(() => {
    setEnabled(prev => {
      const next = !prev;
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, String(next));
      }
      return next;
    });
  }, []);

  const playHoverCluster = useCallback(() => {
    const ctx = getCtx();
    if (!ctx) return;
    playTone(ctx, { frequency: 880, duration: 0.08, type: 'sine', gain: 0.05 });
  }, [getCtx]);

  const playClickPost = useCallback(() => {
    const ctx = getCtx();
    if (!ctx) return;
    playChord(ctx, [
      { frequency: 600, duration: 0.06, type: 'triangle', gain: 0.08 },
      { frequency: 900, duration: 0.04, type: 'sine', gain: 0.04 },
    ]);
  }, [getCtx]);

  const playCreatureOpen = useCallback(() => {
    const ctx = getCtx();
    if (!ctx) return;
    // Bird-like ascending tones
    playTone(ctx, { frequency: 523, duration: 0.15, type: 'sine', gain: 0.06 });
    setTimeout(() => {
      const c = getCtx();
      if (c) playTone(c, { frequency: 659, duration: 0.15, type: 'sine', gain: 0.05 });
    }, 100);
    setTimeout(() => {
      const c = getCtx();
      if (c) playTone(c, { frequency: 784, duration: 0.2, type: 'sine', gain: 0.04 });
    }, 200);
  }, [getCtx]);

  const playSeasonTransition = useCallback(() => {
    const ctx = getCtx();
    if (!ctx) return;
    // Ambient pad — slow chord
    playChord(ctx, [
      { frequency: 261, duration: 1.0, type: 'sine', gain: 0.04, rampDown: true },
      { frequency: 329, duration: 1.2, type: 'sine', gain: 0.03, rampDown: true },
      { frequency: 392, duration: 1.4, type: 'sine', gain: 0.02, rampDown: true },
    ]);
  }, [getCtx]);

  const playQuestComplete = useCallback(() => {
    const ctx = getCtx();
    if (!ctx) return;
    // Triumphant ascending arpeggio
    const notes = [523, 659, 784, 1047];
    notes.forEach((freq, i) => {
      setTimeout(() => {
        const c = getCtx();
        if (c) playTone(c, { frequency: freq, duration: 0.2, type: 'triangle', gain: 0.06 - i * 0.01 });
      }, i * 80);
    });
  }, [getCtx]);

  return {
    enabled,
    toggle,
    playHoverCluster,
    playClickPost,
    playCreatureOpen,
    playSeasonTransition,
    playQuestComplete,
  };
}
