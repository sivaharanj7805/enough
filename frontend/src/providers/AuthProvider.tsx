'use client';

import {
  createContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';

interface AuthContextValue {
  user: User | null;
  session: Session | null;
  token: string | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signInWithMagicLink: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Manual token injection for backend JWT flow */
  login: (accessToken: string, userId: string) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [manualToken, setManualToken] = useState<string | null>(null);

  useEffect(() => {
    // Hydrate manual token from localStorage (only on client, inside useEffect)
    const storedToken = localStorage.getItem('tended_access_token');
    if (storedToken) setManualToken(storedToken);

    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setUser(s?.user ?? null);
      setLoading(false);
    }).catch(() => {
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setUser(s?.user ?? null);
      // On SIGNED_IN via Supabase, clear any old manual localStorage token
      if (s) {
        localStorage.removeItem('tended_access_token');
        localStorage.removeItem('tended_user_id');
        setManualToken(null);
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, []);

  const signUp = useCallback(async (email: string, password: string, name: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { name } },
    });
    if (error) throw error;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const callbackUrl = `${window.location.origin}/auth/callback?next=${encodeURIComponent('/onboarding')}`;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: callbackUrl },
    });
    if (error) throw error;
  }, []);

  const signInWithMagicLink = useCallback(async (email: string) => {
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { shouldCreateUser: false },
    });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    localStorage.removeItem('tended_access_token');
    localStorage.removeItem('tended_user_id');
    setManualToken(null);
    try {
      await supabase.auth.signOut();
    } catch {
      // Best-effort — local state is already cleared
    }
    // Hard redirect ensures cookies and cache are fully cleared
    window.location.href = '/login';
  }, []);

  /** Manual token injection — used when backend JWT is obtained without Supabase session */
  const login = useCallback((accessToken: string, _userId: string) => {
    localStorage.setItem('tended_access_token', accessToken);
    localStorage.setItem('tended_user_id', _userId);
    setManualToken(accessToken);
    window.location.href = '/dashboard';
  }, []);

  // Derive token: prefer Supabase session, fall back to manually stored token (hydration-safe)
  const token = session?.access_token ?? manualToken;

  return (
    <AuthContext.Provider
      value={{ user, session, token, loading, signIn, signUp, signInWithGoogle, signInWithMagicLink, signOut, login }}
    >
      {children}
    </AuthContext.Provider>
  );
}
