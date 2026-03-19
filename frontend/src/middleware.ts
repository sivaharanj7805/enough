import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Protect /dashboard/* routes from unauthenticated access.
 * Reads the Supabase session token from localStorage is not possible in middleware
 * (no DOM access), so we check for the access_token cookie set by Supabase Auth.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Only protect dashboard routes
  if (!pathname.startsWith('/dashboard') && !pathname.startsWith('/(dashboard)')) {
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
    /*
     * Match all request paths starting with /dashboard
     * Excludes: _next/static, _next/image, favicon.ico, api routes
     */
    '/dashboard/:path*',
  ],
};
