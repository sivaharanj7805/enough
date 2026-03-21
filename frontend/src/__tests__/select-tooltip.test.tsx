import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Select } from '@/components/ui/Select';
import { Tooltip } from '@/components/ui/Tooltip';
import { Spinner } from '@/components/ui/Spinner';

describe('Select', () => {
  const options = [
    { value: 'a', label: 'Option A' },
    { value: 'b', label: 'Option B' },
    { value: 'c', label: 'Option C' },
  ];

  it('renders all options', () => {
    render(<Select options={options} />);
    expect(screen.getByText('Option A')).toBeInTheDocument();
    expect(screen.getByText('Option B')).toBeInTheDocument();
    expect(screen.getByText('Option C')).toBeInTheDocument();
  });

  it('renders label when provided', () => {
    render(<Select label="Choose one" id="sel" options={options} />);
    expect(screen.getByText('Choose one')).toBeInTheDocument();
  });

  it('renders placeholder option', () => {
    render(<Select options={options} placeholder="Select..." />);
    expect(screen.getByText('Select...')).toBeInTheDocument();
  });

  it('fires onChange', () => {
    const onChange = vi.fn();
    render(<Select options={options} onChange={onChange} data-testid="sel" />);
    fireEvent.change(screen.getByTestId('sel'), { target: { value: 'b' } });
    expect(onChange).toHaveBeenCalled();
  });

  it('renders without label', () => {
    const { container } = render(<Select options={options} />);
    expect(container.querySelector('label')).toBeNull();
  });
});

describe('Tooltip', () => {
  it('shows content on hover', () => {
    render(
      <Tooltip content="Help text">
        <button>Hover me</button>
      </Tooltip>
    );
    expect(screen.queryByText('Help text')).toBeNull();
    fireEvent.mouseEnter(screen.getByText('Hover me'));
    expect(screen.getByText('Help text')).toBeInTheDocument();
  });

  it('hides content on mouse leave', () => {
    render(
      <Tooltip content="Help text">
        <button>Hover me</button>
      </Tooltip>
    );
    fireEvent.mouseEnter(screen.getByText('Hover me'));
    expect(screen.getByText('Help text')).toBeInTheDocument();
    fireEvent.mouseLeave(screen.getByText('Hover me'));
    expect(screen.queryByText('Help text')).toBeNull();
  });
});

describe('Spinner', () => {
  it('renders without error', () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector('svg')).not.toBeNull();
  });
});
