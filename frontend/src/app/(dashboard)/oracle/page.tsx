'use client';

// Oracle is now a persistent slide-in panel accessible via the "Ask Oracle" button
// on every page. This page redirects to Today so direct /oracle links still work.
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function OracleRedirect() {
  const router = useRouter();
  useEffect(() => {
    // Small delay so any direct link lands cleanly on Today
    // The Oracle FAB will be visible there
    router.replace('/today');
  }, [router]);
  return null;
}
