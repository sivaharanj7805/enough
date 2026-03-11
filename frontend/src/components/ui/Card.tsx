import { type HTMLAttributes, forwardRef } from 'react';
import { twMerge } from 'tailwind-merge';
import { clsx } from 'clsx';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: boolean;
  glowColor?: string;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, glow, glowColor, style, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={twMerge(
          clsx(
            'rounded-xl border border-brand-border bg-brand-surface p-6',
            glow && 'ring-1',
            className
          )
        )}
        style={{
          ...(glow && glowColor ? { boxShadow: `0 0 20px ${glowColor}20`, borderColor: glowColor } : {}),
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';
