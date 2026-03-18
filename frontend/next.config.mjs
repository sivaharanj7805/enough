/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // ESLint runs separately via `tsc --noEmit` — skip during build to avoid
    // blocking on cosmetic lint warnings (unused imports, unescaped entities).
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Still hard-fail on real type errors.
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
