import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Server-side handler for Supabase auth callbacks (OAuth, magic link, password reset).
 *
 * Supabase redirects here with a `code` query param (PKCE flow).
 * We exchange it for a session (which sets auth cookies), then redirect
 * to the `next` destination. This runs BEFORE middleware, so the user
 * arrives at protected routes with valid cookies already set.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');
  // Validate `next` to prevent open redirect — only allow relative paths
  const rawNext = searchParams.get('next') ?? '/today';
  const next = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/today';

  if (code) {
    const cookieStore = await cookies();

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          },
        },
      }
    );

    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      const redirectUrl = new URL(next, origin);
      return NextResponse.redirect(redirectUrl);
    }
  }

  // Code exchange failed or no code present — send to login with error hint
  return NextResponse.redirect(new URL('/login?error=auth', origin));
}
