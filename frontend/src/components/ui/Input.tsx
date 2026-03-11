'use client';

import { type InputHTMLAttributes, forwardRef } from 'react';
import { twMerge } from 'tailwind-merge';
import { clsx } from 'clsx';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-brand-text">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={id}
          className={twMerge(
            clsx(
              'w-full rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted focus:border-brand-accent focus:outline-none focus:ring-1 focus:ring-brand-accent/50 transition-colors',
              error && 'border-red-500 focus:border-red-500 focus:ring-red-500/50',
              className
            )
          )}
          {...props}
        />
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
