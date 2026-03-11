'use client';

import {
  createContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react';
import type { Site } from '@/lib/types';
import { useSites } from '@/lib/hooks/useApi';

interface SiteContextValue {
  sites: Site[];
  currentSite: Site | null;
  selectSite: (siteId: string) => void;
  loading: boolean;
  error: Error | undefined;
}

export const SiteContext = createContext<SiteContextValue | null>(null);

export function SiteProvider({ children }: { children: ReactNode }) {
  const { data: response, error, isLoading } = useSites();
  const sites = useMemo(() => response?.sites ?? [], [response]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (sites.length > 0 && !selectedId) {
      const saved = typeof window !== 'undefined'
        ? localStorage.getItem('enough_site_id')
        : null;
      const found = saved && sites.find((s) => s.id === saved);
      setSelectedId(found ? saved : sites[0].id);
    }
  }, [sites, selectedId]);

  const selectSite = useCallback((siteId: string) => {
    setSelectedId(siteId);
    if (typeof window !== 'undefined') {
      localStorage.setItem('enough_site_id', siteId);
    }
  }, []);

  const currentSite = sites.find((s) => s.id === selectedId) ?? null;

  return (
    <SiteContext.Provider
      value={{
        sites,
        currentSite,
        selectSite,
        loading: isLoading,
        error,
      }}
    >
      {children}
    </SiteContext.Provider>
  );
}
