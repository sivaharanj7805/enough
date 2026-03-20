import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { EmptyState } from '@/components/ui/EmptyState';
import { Search } from 'lucide-react';

describe('ProgressBar', () => {
  it('renders with correct percentage width', () => {
    const { container } = render(<ProgressBar value={50} max={100} />);
    const bar = container.querySelector('[style*="width"]') as HTMLElement;
    expect(bar.style.width).toBe('50%');
  });

  it('clamps to 100% when value exceeds max', () => {
    const { container } = render(<ProgressBar value={150} max={100} />);
    const bar = container.querySelector('[style*="width"]') as HTMLElement;
    expect(bar.style.width).toBe('100%');
  });

  it('clamps to 0% when value is negative', () => {
    const { container } = render(<ProgressBar value={-10} max={100} />);
    const bar = container.querySelector('[style*="width"]') as HTMLElement;
    expect(bar.style.width).toBe('0%');
  });

  it('applies custom color', () => {
    const { container } = render(<ProgressBar value={50} color="#ef4444" />);
    const bar = container.querySelector('[style*="background"]') as HTMLElement;
    expect(bar.style.backgroundColor).toBe('rgb(239, 68, 68)');
  });

  it('shows label when showLabel is true', () => {
    render(<ProgressBar value={75} max={100} showLabel />);
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('hides label by default', () => {
    const { container } = render(<ProgressBar value={75} />);
    expect(container.querySelector('p')).toBeNull();
  });
});

describe('Input', () => {
  it('renders with label', () => {
    render(<Input label="Email" id="email" />);
    expect(screen.getByText('Email')).toBeInTheDocument();
  });

  it('renders without label', () => {
    const { container } = render(<Input placeholder="Type here" />);
    expect(container.querySelector('label')).toBeNull();
  });

  it('shows error message', () => {
    render(<Input error="This field is required" />);
    expect(screen.getByText('This field is required')).toBeInTheDocument();
  });

  it('applies error styling', () => {
    const { container } = render(<Input error="Invalid" />);
    const input = container.querySelector('input')!;
    expect(input.className).toContain('border-red');
  });

  it('passes through HTML input props', () => {
    render(<Input placeholder="Enter email" type="email" data-testid="input" />);
    const input = screen.getByTestId('input');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toHaveAttribute('placeholder', 'Enter email');
  });
});

describe('Modal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Modal open={false} onClose={() => {}}>
        <p>Modal Content</p>
      </Modal>
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders content when open', () => {
    render(
      <Modal open={true} onClose={() => {}}>
        <p>Modal Content</p>
      </Modal>
    );
    expect(screen.getByText('Modal Content')).toBeInTheDocument();
  });

  it('renders title when provided', () => {
    render(
      <Modal open={true} onClose={() => {}} title="Confirm Action">
        <p>Are you sure?</p>
      </Modal>
    );
    expect(screen.getByText('Confirm Action')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(
      <Modal open={true} onClose={() => {}} description="This cannot be undone">
        <p>Content</p>
      </Modal>
    );
    expect(screen.getByText('This cannot be undone')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose}>
        <p>Content</p>
      </Modal>
    );
    fireEvent.click(screen.getByLabelText('Close dialog'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose}>
        <p>Content</p>
      </Modal>
    );
    // Click the backdrop (first fixed div with bg-black)
    const backdrop = document.querySelector('[aria-hidden="true"]')!;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('has correct ARIA attributes', () => {
    render(
      <Modal open={true} onClose={() => {}} title="Test" description="Desc">
        <p>Content</p>
      </Modal>
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'modal-description');
  });
});

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(
      <EmptyState
        title="No posts yet"
        description="Posts will appear after crawling."
      />
    );
    expect(screen.getByText('No posts yet')).toBeInTheDocument();
    expect(screen.getByText('Posts will appear after crawling.')).toBeInTheDocument();
  });

  it('renders action link', () => {
    render(
      <EmptyState
        title="Empty"
        description="Nothing here"
        actionLabel="Get Started"
        actionHref="/onboarding"
      />
    );
    const link = screen.getByText('Get Started');
    expect(link.closest('a')).toHaveAttribute('href', '/onboarding');
  });

  it('renders action button', () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        title="Empty"
        description="Nothing here"
        actionLabel="Start Analysis"
        onAction={onAction}
      />
    );
    fireEvent.click(screen.getByText('Start Analysis'));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it('renders secondary action', () => {
    const onSecondary = vi.fn();
    render(
      <EmptyState
        title="Empty"
        description="Nothing"
        secondaryLabel="Learn more"
        onSecondaryAction={onSecondary}
      />
    );
    fireEvent.click(screen.getByText('Learn more'));
    expect(onSecondary).toHaveBeenCalledOnce();
  });

  it('renders icon when provided', () => {
    const { container } = render(
      <EmptyState
        icon={Search}
        title="No results"
        description="Try a different search."
      />
    );
    // Search icon renders as SVG
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('shows demo banner when enabled', () => {
    render(
      <EmptyState
        title="Empty"
        description="Nothing"
        showDemoBanner
      />
    );
    expect(screen.getByText('See a live example with Close.com data')).toBeInTheDocument();
    expect(screen.getByText('Try demo')).toBeInTheDocument();
  });
});
