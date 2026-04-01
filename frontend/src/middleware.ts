import { createServerClient } from '@supabase/ssr';
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
  '/patcher',
  '/pioneer',
];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Demo mode bypasses auth — the AuthProvider handles fake sessions client-side
  if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
    return NextResponse.next();
  }

  // Only protect dashboard routes
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  if (!isProtected) {
    return NextResponse.next();
  }

  // Create a Supabase server client that reads/writes cookies on the request/response
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          // Forward refreshed cookies to downstream server components
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          // Set cookies on the outgoing response so the browser stores them
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
          // Apply cache-control headers to prevent CDN caching of authenticated responses
          if (headers) {
            Object.entries(headers).forEach(([key, value]) =>
              supabaseResponse.headers.set(key, String(value))
            );
          }
        },
      },
    }
  );

  // Validate the session — this also refreshes expired tokens
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirectTo', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return supabaseResponse;
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
    '/patcher/:path*',
    '/pioneer/:path*',
  ],
};
