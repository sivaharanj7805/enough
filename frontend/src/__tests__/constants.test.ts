import { describe, it, expect } from 'vitest';
import {
  ECOSYSTEM_COLORS,
  ROLE_COLORS,
  ROLE_LABELS,
  SEVERITY_COLORS,
  TREND_ICONS,
  TREND_COLORS,
} from '@/lib/constants';

describe('Constants', () => {
  describe('ECOSYSTEM_COLORS', () => {
    it('has all ecosystem states', () => {
      expect(ECOSYSTEM_COLORS).toHaveProperty('forest');
      expect(ECOSYSTEM_COLORS).toHaveProperty('swamp');
      expect(ECOSYSTEM_COLORS).toHaveProperty('desert');
      expect(ECOSYSTEM_COLORS).toHaveProperty('seedbed');
      expect(ECOSYSTEM_COLORS).toHaveProperty('meadow');
    });

    it('each state has bg, border, and label', () => {
      Object.values(ECOSYSTEM_COLORS).forEach((val) => {
        expect(val).toHaveProperty('bg');
        expect(val).toHaveProperty('border');
        expect(val).toHaveProperty('label');
      });
    });
  });

  describe('ROLE_COLORS', () => {
    it('has all post roles', () => {
      expect(ROLE_COLORS).toHaveProperty('pillar');
      expect(ROLE_COLORS).toHaveProperty('supporter');
      expect(ROLE_COLORS).toHaveProperty('competitor');
      expect(ROLE_COLORS).toHaveProperty('dead_weight');
    });

    it('values are hex colors', () => {
      Object.values(ROLE_COLORS).forEach((val) => {
        expect(val).toMatch(/^#[0-9a-fA-F]{6}$/);
      });
    });
  });

  describe('ROLE_LABELS', () => {
    it('has all post roles with string labels', () => {
      expect(ROLE_LABELS.pillar).toBe('Pillar');
      expect(ROLE_LABELS.supporter).toBe('Supporter');
      expect(ROLE_LABELS.competitor).toBe('Competitor');
      expect(ROLE_LABELS.dead_weight).toBe('Dead Weight');
    });
  });

  describe('SEVERITY_COLORS', () => {
    it('has all severity levels', () => {
      expect(SEVERITY_COLORS).toHaveProperty('critical');
      expect(SEVERITY_COLORS).toHaveProperty('high');
      expect(SEVERITY_COLORS).toHaveProperty('medium');
      expect(SEVERITY_COLORS).toHaveProperty('low');
    });
  });

  describe('TREND_ICONS', () => {
    it('has icons for all trends', () => {
      expect(TREND_ICONS.growing).toBe('↑');
      expect(TREND_ICONS.stable).toBe('→');
      expect(TREND_ICONS.declining).toBe('↓');
    });
  });

  describe('TREND_COLORS', () => {
    it('growing is green', () => {
      expect(TREND_COLORS.growing).toBe('#22c55e');
    });
    it('declining is red', () => {
      expect(TREND_COLORS.declining).toBe('#ef4444');
    });
  });
});
