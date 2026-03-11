'use client';

import { useContext } from 'react';
import { SiteContext } from '@/providers/SiteProvider';

export function useSite() {
  const context = useContext(SiteContext);
  if (!context) {
    throw new Error('useSite must be used within a SiteProvider');
  }
  return context;
}
