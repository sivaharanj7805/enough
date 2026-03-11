'use client';

import useSWR, { type SWRConfiguration } from 'swr';
import { apiFetch } from '@/lib/api';
import { useAuth } from './useAuth';

export function useSWRFetch<T>(
  path: string | null,
  config?: SWRConfiguration<T>
) {
  const { session } = useAuth();
  const token = session?.access_token;

  return useSWR<T>(
    path ? [path, token] : null,
    async ([url]: [string]) => {
      return apiFetch<T>(url, { token });
    },
    {
      revalidateOnFocus: false,
      ...config,
    }
  );
}
