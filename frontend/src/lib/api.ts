// Use the /api/ proxy path which Next.js rewrites (dev) and Vercel rewrites (prod)
// route to the backend. This avoids CORS and CSP issues entirely since the browser
// sees all requests as same-origin.
const API_BASE = '/api';

// Absolute backend URL — only for server-side fetches, OAuth redirects, and OG image URLs
// where a relative path won't work.
const BACKEND_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/v1';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface FetchOptions extends Omit<RequestInit, 'headers'> {
  token?: string;
  headers?: Record<string, string>;
}

export async function apiFetch<T>(
  path: string,
  options?: FetchOptions
): Promise<T> {
  const { token, ...fetchOptions } = options || {};

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(fetchOptions.headers || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => 'Unknown error');
    throw new ApiError(`API error ${res.status}: ${errorText}`, res.status);
  }

  // 204 No Content — nothing to parse
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Absolute backend URL for OAuth redirects, server-side fetches, and OG images. */
export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}
