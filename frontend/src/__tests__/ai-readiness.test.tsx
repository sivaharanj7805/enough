import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AIReadinessCard } from '@/components/dashboard/AIReadinessCard';

const mockScores = {
  avg_citability: 65,
  avg_eeat: 55,
  avg_schema: 30,
  avg_extraction: 70,
  pct_has_schema: 25,
  pct_ai_ready: 45,
  total_scored: 120,
};

describe('AIReadinessCard', () => {
  it('shows loading state', () => {
    const { container } = render(<AIReadinessCard scores={null} loading />);
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('shows empty state when no scores', () => {
    render(<AIReadinessCard scores={null} />);
    expect(screen.getByText('AI Readiness')).toBeInTheDocument();
    expect(screen.getByText(/Score your content/)).toBeInTheDocument();
  });

  it('shows empty state when total_scored is 0', () => {
    render(<AIReadinessCard scores={{ ...mockScores, total_scored: 0 }} />);
    expect(screen.getByText(/Score your content/)).toBeInTheDocument();
  });

  it('shows run scan button when callback provided', () => {
    const onRunScan = vi.fn();
    render(<AIReadinessCard scores={null} onRunScan={onRunScan} />);
    const btn = screen.getByText('Run AI Readiness Scan');
    fireEvent.click(btn);
    expect(onRunScan).toHaveBeenCalledOnce();
  });

  it('displays all four score bars', () => {
    render(<AIReadinessCard scores={mockScores} />);
    expect(screen.getByText('AI Citability')).toBeInTheDocument();
    expect(screen.getByText('E-E-A-T Signals')).toBeInTheDocument();
    expect(screen.getByText('Schema Markup')).toBeInTheDocument();
    expect(screen.getByText('AI Extraction')).toBeInTheDocument();
  });

  it('displays overall score', () => {
    render(<AIReadinessCard scores={mockScores} />);
    // Overall = (65+55+30+70)/4 = 55
    expect(screen.getByText('55')).toBeInTheDocument();
  });

  it('displays AI-Ready Posts percentage', () => {
    render(<AIReadinessCard scores={mockScores} />);
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByText('AI-Ready Posts')).toBeInTheDocument();
  });

  it('displays Have Schema percentage', () => {
    render(<AIReadinessCard scores={mockScores} />);
    expect(screen.getByText('25%')).toBeInTheDocument();
    expect(screen.getByText('Have Schema')).toBeInTheDocument();
  });

  it('displays total scored count', () => {
    render(<AIReadinessCard scores={mockScores} />);
    expect(screen.getByText(/120 posts scored/)).toBeInTheDocument();
  });
});
