'use client';

import { Skeleton } from './Skeleton';

// Skeleton color: bg-[#1A1D26] with shimmer gradient #1A1D26 → #23262F → #1A1D26
// All skeletons use the global .skeleton class for shimmer animation

/* ─── Shared Helpers ──────────────────────────────── */

function SkeletonCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`border border-[#23262F] rounded-xl p-5 bg-[#13151B] ${className}`}>
      {children}
    </div>
  );
}

function SkeletonTableHeader({ columns = 4 }: { columns?: number }) {
  return (
    <div className="flex items-center gap-4 py-3 border-b border-[#23262F]">
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === 0 ? '40%' : `${60 / (columns - 1)}%`}
          height={12}
        />
      ))}
    </div>
  );
}

function SkeletonTableRows({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 py-3 border-b border-[#23262F]">
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton
              key={c}
              width={c === 0 ? '40%' : `${60 / (columns - 1)}%`}
              height={14}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function TitleSkeleton() {
  return <Skeleton width={192} height={24} className="mb-2" />;
}

function BodyTextSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton width="100%" height={14} />
      <Skeleton width="80%" height={14} />
      <Skeleton width="60%" height={14} />
    </div>
  );
}

/* ─── 1. TodaySkeleton ───────────────────────────── */

export function TodaySkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Health score card */}
      <SkeletonCard>
        <div className="flex items-center gap-6">
          <Skeleton variant="circular" width={120} height={120} />
          <div className="flex-1 space-y-3">
            <Skeleton width={96} height={12} />
            <Skeleton width="60%" height={28} />
            <Skeleton width="40%" height={14} />
          </div>
        </div>
      </SkeletonCard>

      {/* Trend card + Priority card row */}
      <div className="grid grid-cols-2 gap-4">
        <SkeletonCard>
          <Skeleton width={120} height={16} className="mb-4" />
          <Skeleton width="100%" height={80} />
        </SkeletonCard>
        <SkeletonCard>
          <Skeleton width={160} height={16} className="mb-4" />
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton variant="circular" width={8} height={8} />
                <Skeleton width="70%" height={14} />
              </div>
            ))}
          </div>
        </SkeletonCard>
      </div>

      {/* Secondary cards row */}
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <SkeletonCard key={i}>
            <Skeleton width={80} height={12} className="mb-3" />
            <Skeleton width={48} height={28} className="mb-2" />
            <Skeleton width="60%" height={12} />
          </SkeletonCard>
        ))}
      </div>

      {/* Stats card */}
      <SkeletonCard>
        <div className="grid grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton width={64} height={12} />
              <Skeleton width={48} height={24} />
            </div>
          ))}
        </div>
      </SkeletonCard>
    </div>
  );
}

/* ─── 2. LandscapeSkeleton ───────────────────────── */

export function LandscapeSkeleton() {
  return (
    <div className="p-6">
      <TitleSkeleton />
      <div className="border border-[#23262F] rounded-xl bg-[#13151B] p-6 mt-4" style={{ height: 520 }}>
        {/* Terrain outlines — abstract cluster blobs */}
        <div className="relative w-full h-full">
          {[
            { top: '10%', left: '5%', w: 180, h: 120 },
            { top: '15%', left: '45%', w: 220, h: 140 },
            { top: '55%', left: '10%', w: 160, h: 100 },
            { top: '50%', left: '55%', w: 200, h: 130 },
            { top: '30%', left: '75%', w: 140, h: 90 },
          ].map((blob, i) => (
            <div
              key={i}
              className="skeleton absolute rounded-full opacity-40"
              style={{
                top: blob.top,
                left: blob.left,
                width: blob.w,
                height: blob.h,
              }}
            />
          ))}
          {/* Scattered dot placeholders */}
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={`dot-${i}`}
              className="skeleton absolute rounded-full"
              style={{
                top: `${15 + Math.floor(i / 4) * 30 + (i % 3) * 5}%`,
                left: `${10 + (i % 4) * 22 + (i % 3) * 3}%`,
                width: 10,
                height: 10,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── 3. ClusterDetailSkeleton ───────────────────── */

export function ClusterDetailSkeleton() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <Skeleton width={240} height={28} />
        <div className="flex items-center gap-4">
          <Skeleton width={80} height={24} className="rounded-full" />
          <Skeleton width={120} height={14} />
          <Skeleton width={100} height={14} />
        </div>
      </div>

      {/* Post table */}
      <SkeletonCard>
        <SkeletonTableHeader columns={5} />
        <SkeletonTableRows rows={8} columns={5} />
      </SkeletonCard>
    </div>
  );
}

/* ─── 4. PostListSkeleton ────────────────────────── */

export function PostListSkeleton() {
  return (
    <div className="p-6 space-y-4">
      {/* Search bar */}
      <div className="flex items-center gap-3">
        <Skeleton width="100%" height={40} className="rounded-lg" />
        <Skeleton width={120} height={40} className="rounded-lg" />
      </div>

      {/* Table */}
      <SkeletonCard>
        <SkeletonTableHeader columns={6} />
        <SkeletonTableRows rows={8} columns={6} />
      </SkeletonCard>
    </div>
  );
}

/* ─── 5. PostDetailSkeleton ──────────────────────── */

export function PostDetailSkeleton() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <Skeleton width={64} height={14} />
        <Skeleton width="70%" height={28} />
        <div className="flex items-center gap-4">
          <Skeleton width={100} height={24} className="rounded-full" />
          <Skeleton width={80} height={14} />
          <Skeleton width={120} height={14} />
        </div>
      </div>

      {/* Health breakdown grid */}
      <div className="grid grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonCard key={i}>
            <Skeleton width={80} height={12} className="mb-3" />
            <Skeleton width={48} height={28} className="mb-1" />
            <Skeleton width="50%" height={10} />
          </SkeletonCard>
        ))}
      </div>

      {/* Content analysis */}
      <SkeletonCard>
        <Skeleton width={160} height={18} className="mb-4" />
        <BodyTextSkeleton />
      </SkeletonCard>

      {/* Links */}
      <SkeletonCard>
        <Skeleton width={120} height={18} className="mb-4" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <Skeleton width={16} height={16} />
              <Skeleton width="60%" height={14} />
            </div>
          ))}
        </div>
      </SkeletonCard>

      {/* Problems */}
      <SkeletonCard>
        <Skeleton width={140} height={18} className="mb-4" />
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton width={60} height={22} className="rounded-full" />
              <Skeleton width="50%" height={14} />
            </div>
          ))}
        </div>
      </SkeletonCard>
    </div>
  );
}

/* ─── 6. RecommendationsSkeleton ─────────────────── */

export function RecommendationsSkeleton() {
  return (
    <div className="p-6 space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} width={90} height={36} className="rounded-lg" />
        ))}
      </div>

      {/* 4 card placeholders */}
      <div className="space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonCard key={i}>
            <div className="flex items-center gap-3 mb-3">
              <Skeleton variant="circular" width={8} height={8} />
              <Skeleton width={64} height={16} />
              <Skeleton width={100} height={12} />
            </div>
            <Skeleton width="85%" height={16} className="mb-2" />
            <Skeleton variant="text" lines={2} />
          </SkeletonCard>
        ))}
      </div>
    </div>
  );
}

/* ─── 7. IssuesSkeleton ──────────────────────────── */

export function IssuesSkeleton() {
  return (
    <div className="p-6 space-y-4">
      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-[#23262F] pb-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} width={80} height={32} className="rounded-lg" />
        ))}
      </div>

      {/* Severity bar */}
      <div className="flex items-center gap-2 h-6">
        <Skeleton width="30%" height={24} className="rounded-l-md" />
        <Skeleton width="25%" height={24} />
        <Skeleton width="25%" height={24} />
        <Skeleton width="20%" height={24} className="rounded-r-md" />
      </div>

      {/* Table rows */}
      <SkeletonCard>
        <SkeletonTableHeader columns={5} />
        <SkeletonTableRows rows={6} columns={5} />
      </SkeletonCard>
    </div>
  );
}

/* ─── 8. CannibalizationSkeleton ─────────────────── */

export function CannibalizationSkeleton() {
  return (
    <div className="p-6 space-y-6">
      {/* Summary stat */}
      <SkeletonCard className="flex items-center gap-6">
        <div className="space-y-2">
          <Skeleton width={140} height={14} />
          <Skeleton width={64} height={32} />
        </div>
        <Skeleton width={200} height={14} />
      </SkeletonCard>

      {/* 4 pair cards */}
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonCard key={i}>
            <Skeleton width={120} height={14} className="mb-4" />
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Skeleton width={20} height={20} className="rounded" />
                <Skeleton width="70%" height={14} />
              </div>
              <div className="flex items-center justify-center">
                <Skeleton width={40} height={20} className="rounded-full" />
              </div>
              <div className="flex items-center gap-2">
                <Skeleton width={20} height={20} className="rounded" />
                <Skeleton width="65%" height={14} />
              </div>
            </div>
          </SkeletonCard>
        ))}
      </div>
    </div>
  );
}

/* ─── 9. ConsolidationSkeleton ───────────────────── */

export function ConsolidationSkeleton() {
  return (
    <div className="p-6 space-y-4">
      <TitleSkeleton />
      {/* 3 plan cards */}
      {[1, 2, 3].map((i) => (
        <SkeletonCard key={i}>
          <div className="flex items-center justify-between mb-4">
            <Skeleton width={200} height={18} />
            <Skeleton width={80} height={28} className="rounded-full" />
          </div>
          <div className="space-y-2">
            {[1, 2, 3].map((j) => (
              <div key={j} className="flex items-center gap-2">
                <Skeleton width={16} height={16} className="rounded" />
                <Skeleton width="60%" height={14} />
              </div>
            ))}
          </div>
        </SkeletonCard>
      ))}
    </div>
  );
}

/* ─── 10. OracleSkeleton ─────────────────────────── */

export function OracleSkeleton() {
  return (
    <div className="p-6 flex flex-col items-center justify-center" style={{ minHeight: 480 }}>
      {/* Empty chat area */}
      <Skeleton variant="circular" width={56} height={56} className="mb-4 opacity-40" />
      <Skeleton width={200} height={20} className="mb-2" />
      <Skeleton width={280} height={14} className="mb-8 opacity-60" />

      {/* Suggested question chips */}
      <div className="flex flex-wrap gap-3 justify-center max-w-lg">
        {[160, 200, 140, 180].map((w, i) => (
          <Skeleton key={i} width={w} height={36} className="rounded-full" />
        ))}
      </div>
    </div>
  );
}

/* ─── 11. OverviewSkeleton ───────────────────────── */

export function OverviewSkeleton() {
  return (
    <div className="p-6 space-y-4">
      <TitleSkeleton />
      {/* 6 chart placeholders in 3x2 grid */}
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <SkeletonCard key={i}>
            <Skeleton width={120} height={14} className="mb-4" />
            <Skeleton width="100%" height={160} className="rounded-lg" />
          </SkeletonCard>
        ))}
      </div>
    </div>
  );
}

/* ─── 12. ImpactSkeleton ─────────────────────────── */

export function ImpactSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <TitleSkeleton />

      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonCard key={i}>
            <Skeleton width={80} height={12} className="mb-2" />
            <Skeleton width={56} height={28} className="mb-1" />
            <Skeleton width={48} height={12} />
          </SkeletonCard>
        ))}
      </div>

      {/* Timeline */}
      <SkeletonCard>
        <Skeleton width={140} height={16} className="mb-4" />
        <Skeleton width="100%" height={200} className="rounded-lg" />
      </SkeletonCard>
    </div>
  );
}

/* ─── 13. SettingsSkeleton ───────────────────────── */

export function SettingsSkeleton() {
  return (
    <div className="p-6 space-y-6">
      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-[#23262F] pb-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} width={90} height={32} className="rounded-lg" />
        ))}
      </div>

      {/* Form fields */}
      <div className="max-w-lg space-y-5">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-2">
            <Skeleton width={100} height={14} />
            <Skeleton width="100%" height={40} className="rounded-lg" />
          </div>
        ))}
        <Skeleton width={120} height={40} className="rounded-lg mt-4" />
      </div>
    </div>
  );
}
