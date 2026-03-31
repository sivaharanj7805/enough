'use client';

import useSWR, { type SWRConfiguration } from 'swr';
import { apiFetch } from '@/lib/api';
import { useAuth } from './useAuth';

export function useSWRFetch<T>(
  path: string | null,
  config?: SWRConfiguration<T>
) {
  const { token } = useAuth();

  return useSWR<T>(
    path && token ? [path, token] : null,
    async ([url, currentToken]: [string, string | undefined]) => {
      return apiFetch<T>(url, { token: currentToken });
    },
    {
      revalidateOnFocus: false,
      ...config,
    }
  );
}
