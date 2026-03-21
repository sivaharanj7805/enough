import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PostBreakdown } from '@/components/dashboard/PostBreakdown';
import { Skeleton, TodayHeroSkeleton, RecommendationCardSkeleton, TableRowSkeleton } from '@/components/ui/Skeleton';

describe('PostBreakdown', () => {
  it('renders all four segments', () => {
    render(<PostBreakdown active={10} passive={5} cannibal={3} dead={2} />);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Passive')).toBeInTheDocument();
    expect(screen.getByText('Cannibalistic')).toBeInTheDocument();
    expect(screen.getByText('Dead')).toBeInTheDocument();
  });

  it('displays correct counts', () => {
    render(<PostBreakdown active={10} passive={5} cannibal={3} dead={2} />);
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('handles zero counts', () => {
    render(<PostBreakdown active={0} passive={0} cannibal={0} dead={0} />);
    expect(screen.getAllByText('0')).toHaveLength(4);
  });

  it('displays Post Breakdown title', () => {
    render(<PostBreakdown active={1} passive={1} cannibal={1} dead={1} />);
    expect(screen.getByText('Post Breakdown')).toBeInTheDocument();
  });
});

describe('Skeleton', () => {
  it('renders text variant with multiple lines', () => {
    const { container } = render(<Skeleton variant="text" lines={3} />);
    const skeletons = container.querySelectorAll('.skeleton');
    expect(skeletons.length).toBe(3);
  });

  it('renders circular variant', () => {
    const { container } = render(<Skeleton variant="circular" width={48} height={48} />);
    const el = container.querySelector('.rounded-full');
    expect(el).not.toBeNull();
  });

  it('renders card variant', () => {
    const { container } = render(<Skeleton variant="card" height={120} />);
    const el = container.querySelector('.rounded-xl');
    expect(el).not.toBeNull();
  });

  it('renders rectangular variant by default', () => {
    const { container } = render(<Skeleton width="100%" height={20} />);
    const el = container.querySelector('.skeleton');
    expect(el).not.toBeNull();
  });

  it('applies custom width and height', () => {
    const { container } = render(<Skeleton width={200} height={30} />);
    const el = container.querySelector('.skeleton') as HTMLElement;
    expect(el.style.width).toBe('200px');
    expect(el.style.height).toBe('30px');
  });
});

describe('TodayHeroSkeleton', () => {
  it('renders without error', () => {
    const { container } = render(<TodayHeroSkeleton />);
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  });
});

describe('RecommendationCardSkeleton', () => {
  it('renders without error', () => {
    const { container } = render(<RecommendationCardSkeleton />);
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  });
});

describe('TableRowSkeleton', () => {
  it('renders default 4 columns', () => {
    const { container } = render(<TableRowSkeleton />);
    expect(container.querySelectorAll('.skeleton').length).toBe(4);
  });

  it('renders custom column count', () => {
    const { container } = render(<TableRowSkeleton columns={6} />);
    expect(container.querySelectorAll('.skeleton').length).toBe(6);
  });
});
