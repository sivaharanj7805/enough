import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Protect authenticated routes from unauthenticated access at the edge.
 *
 * The (dashboard) route group is a Next.js grouping mechanism — its routes
 * resolve to /today, /landscape, /clusters, etc., NOT /dashboard/*.
 * This matcher must cover all actual route paths.
 */

const PROTECTED_PREFIXES = [
  '/today',
  '/landscape',
  '/dashboard',
  '/clusters',
  '/posts',
  '/actions',
  '/issues',
  '/cannibalization',
  '/consolidation',
  '/oracle',
  '/overview',
  '/billing',
  '/impact',
  '/explore',
  '/briefs',
  '/calendar',
  '/competitors',
  '/settings',
  '/profile',
  '/wrapped',
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Only protect dashboard routes
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  if (!isProtected) {
    return NextResponse.next();
  }

  // Check for Supabase auth cookie (set automatically by @supabase/ssr)
  const supabaseSession =
    request.cookies.get('sb-access-token') ||
    request.cookies.get('supabase-auth-token') ||
    request.cookies.get(`sb-${process.env.NEXT_PUBLIC_SUPABASE_URL?.split('//')[1]?.split('.')[0]}-auth-token`);

  // Also allow if Authorization header present (API-style auth)
  const authHeader = request.headers.get('authorization');

  if (!supabaseSession && !authHeader) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirectTo', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/today/:path*',
    '/landscape/:path*',
    '/dashboard/:path*',
    '/clusters/:path*',
    '/posts/:path*',
    '/actions/:path*',
    '/issues/:path*',
    '/cannibalization/:path*',
    '/consolidation/:path*',
    '/oracle/:path*',
    '/overview/:path*',
    '/billing/:path*',
    '/impact/:path*',
    '/explore/:path*',
    '/briefs/:path*',
    '/calendar/:path*',
    '/competitors/:path*',
    '/settings/:path*',
    '/profile/:path*',
    '/wrapped/:path*',
  ],
};
