import { clsx } from 'clsx';

interface SkeletonProps {
  className?: string;
  /** Preset shape */
  variant?: 'text' | 'circular' | 'rectangular' | 'card';
  /** Width — accepts any CSS value */
  width?: string | number;
  /** Height — accepts any CSS value */
  height?: string | number;
  /** Number of text lines to render (only for variant="text") */
  lines?: number;
}

/**
 * Reusable skeleton loading placeholder.
 * Uses the `.skeleton` shimmer animation from globals.css.
 *
 * Usage:
 *   <Skeleton variant="text" lines={3} />
 *   <Skeleton variant="circular" width={48} height={48} />
 *   <Skeleton variant="card" height={120} />
 *   <Skeleton width="100%" height={20} />
 */
export function Skeleton({
  className,
  variant = 'rectangular',
  width,
  height,
  lines = 1,
}: SkeletonProps) {
  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height) style.height = typeof height === 'number' ? `${height}px` : height;

  if (variant === 'text') {
    return (
      <div className={clsx('space-y-2', className)}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="skeleton h-4 rounded"
            style={{
              width: i === lines - 1 && lines > 1 ? '75%' : '100%',
              ...style,
            }}
          />
        ))}
      </div>
    );
  }

  if (variant === 'circular') {
    const size = width ?? height ?? 40;
    const px = typeof size === 'number' ? `${size}px` : size;
    return (
      <div
        className={clsx('skeleton rounded-full', className)}
        style={{ width: px, height: px, ...style }}
      />
    );
  }

  if (variant === 'card') {
    return (
      <div
        className={clsx(
          'skeleton rounded-xl border border-[#1e293b]',
          className
        )}
        style={{ height: height ?? 120, width: width ?? '100%', ...style }}
      />
    );
  }

  // Default: rectangular
  return (
    <div
      className={clsx('skeleton rounded', className)}
      style={{ width: width ?? '100%', height: height ?? 16, ...style }}
    />
  );
}

/** Pre-built skeleton for the Today page hero section */
export function TodayHeroSkeleton() {
  return (
    <div className="flex items-center gap-8 p-6 rounded-2xl bg-[#111827] border border-[#1e293b]">
      <Skeleton variant="circular" width={140} height={140} />
      <div className="flex-1 space-y-3">
        <Skeleton width={96} height={12} />
        <Skeleton width="75%" height={28} />
        <Skeleton width="50%" height={16} />
        <div className="flex gap-6 mt-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} width={56} height={40} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Pre-built skeleton for a recommendation card */
export function RecommendationCardSkeleton() {
  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton variant="circular" width={8} height={8} />
        <Skeleton width={60} height={16} />
        <Skeleton width={100} height={12} />
      </div>
      <Skeleton variant="text" lines={2} />
    </div>
  );
}

/** Pre-built skeleton for a data table row */
export function TableRowSkeleton({ columns = 4 }: { columns?: number }) {
  return (
    <div className="flex items-center gap-4 py-3 border-b border-[#1e293b]">
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === 0 ? '40%' : `${60 / (columns - 1)}%`}
          height={14}
        />
      ))}
    </div>
  );
}
