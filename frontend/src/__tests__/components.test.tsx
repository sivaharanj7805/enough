import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { HealthScoreCard } from '@/components/dashboard/HealthScoreCard';
import { SeverityBadge } from '@/components/cannibalization/SeverityBadge';

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Test Badge</Badge>);
    expect(screen.getByText('Test Badge')).toBeInTheDocument();
  });

  it('applies custom color', () => {
    const { container } = render(<Badge color="#ef4444">Error</Badge>);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.style.color).toBe('rgb(239, 68, 68)');
  });
});

describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Click Me</Button>);
    expect(screen.getByText('Click Me')).toBeInTheDocument();
  });

  it('fires onClick', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Submit</Button>);
    fireEvent.click(screen.getByText('Submit'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('is disabled when disabled prop is set', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByText('Disabled').closest('button')).toBeDisabled();
  });

  it('is disabled when loading', () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByText('Loading').closest('button')).toBeDisabled();
  });

  it('renders danger variant', () => {
    const { container } = render(<Button variant="danger">Delete</Button>);
    const btn = container.querySelector('button')!;
    expect(btn.className).toContain('bg-red');
  });
});

describe('Card', () => {
  it('renders children', () => {
    render(<Card>Card Content</Card>);
    expect(screen.getByText('Card Content')).toBeInTheDocument();
  });

  it('applies glow styling', () => {
    const { container } = render(<Card glow glowColor="#22c55e">Glow</Card>);
    const card = container.firstElementChild as HTMLElement;
    expect(card.style.borderColor).toBe('rgb(34, 197, 94)');
  });
});

describe('HealthScoreCard', () => {
  it('displays value and title', () => {
    render(<HealthScoreCard title="Health Score" value={75} trend="growing" />);
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
  });

  it('displays suffix', () => {
    render(<HealthScoreCard title="Efficiency" value={85} suffix="%" trend="stable" />);
    expect(screen.getByText('%')).toBeInTheDocument();
  });

  it('shows description', () => {
    render(
      <HealthScoreCard
        title="Score"
        value={45}
        trend="declining"
        description="Needs improvement"
      />
    );
    expect(screen.getByText('Needs improvement')).toBeInTheDocument();
  });

  it('shows green color for high score', () => {
    const { container } = render(
      <HealthScoreCard title="Score" value={80} trend="growing" />
    );
    const valueEl = container.querySelector('[style*="color"]') as HTMLElement;
    expect(valueEl.style.color).toBe('rgb(34, 197, 94)');
  });

  it('shows yellow color for medium score', () => {
    const { container } = render(
      <HealthScoreCard title="Score" value={50} trend="stable" />
    );
    const valueEl = container.querySelector('[style*="color"]') as HTMLElement;
    expect(valueEl.style.color).toBe('rgb(234, 179, 8)');
  });

  it('shows red color for low score', () => {
    const { container } = render(
      <HealthScoreCard title="Score" value={20} trend="declining" />
    );
    const valueEl = container.querySelector('[style*="color"]') as HTMLElement;
    expect(valueEl.style.color).toBe('rgb(239, 68, 68)');
  });
});

describe('SeverityBadge', () => {
  it('renders critical severity', () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('renders high severity', () => {
    render(<SeverityBadge severity="high" />);
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('renders medium severity', () => {
    render(<SeverityBadge severity="medium" />);
    expect(screen.getByText('Medium')).toBeInTheDocument();
  });

  it('renders low severity', () => {
    render(<SeverityBadge severity="low" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });
});
