'use client';

import { type ButtonHTMLAttributes, forwardRef, type ReactNode, Children } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Spinner } from './Spinner';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-brand-accent text-white hover:bg-brand-accent-hover',
  secondary: 'bg-brand-surface text-brand-text border border-brand-border hover:bg-brand-surface-hover',
  ghost: 'text-brand-text-muted hover:text-brand-text hover:bg-brand-surface',
  danger: 'bg-red-600 text-white hover:bg-red-700',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

/**
 * Check if children consist only of icon elements (no text).
 * Icon-only buttons need an aria-label for accessibility.
 */
function isIconOnly(children: ReactNode): boolean {
  const childArray = Children.toArray(children);
  if (childArray.length === 0) return false;
  return childArray.every(
    (child) => typeof child !== 'string' || child.trim() === ''
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, disabled, children, ...props }, ref) => {
    // Warn in development if icon-only button lacks aria-label
    if (process.env.NODE_ENV === 'development' && isIconOnly(children) && !props['aria-label']) {
      console.warn('Button: Icon-only buttons should have an aria-label for accessibility.');
    }

    return (
      <button
        ref={ref}
        className={twMerge(
          clsx(
            'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed',
            variantStyles[variant],
            sizeStyles[size],
            className
          )
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Spinner size="sm" />}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
