'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { apiUrl } from '@/lib/api';

function UnsubscribeContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get('email');
  const [status, setStatus] = useState<'confirm' | 'loading' | 'done' | 'error'>(
    email ? 'confirm' : 'error'
  );

  const handleUnsubscribe = () => {
    if (!email) {
      setStatus('error');
      return;
    }

    setStatus('loading');

    fetch(apiUrl(`/unsubscribe?email=${encodeURIComponent(email)}`))
      .then((res) => {
        if (res.ok) setStatus('done');
        else setStatus('error');
      })
      .catch(() => setStatus('error'));
  };

  return (
    <div className="min-h-screen bg-[#0B0D11] flex items-center justify-center p-4">
      <div className="bg-[#111827] rounded-xl shadow-sm p-12 max-w-md text-center border border-[#1e293b]">
        {status === 'confirm' && (
          <>
            <h1 className="text-2xl font-semibold mb-3 text-[#e2e8f0]">Unsubscribe</h1>
            <p className="text-[#64748b] text-sm leading-relaxed mb-6">
              Are you sure you want to unsubscribe <strong>{email}</strong> from
              Tended emails?
            </p>
            <button
              onClick={handleUnsubscribe}
              className="px-6 py-2.5 rounded-xl bg-red-500 text-white text-sm font-semibold hover:bg-red-600 transition-colors"
            >
              Confirm Unsubscribe
            </button>
          </>
        )}
        {status === 'loading' && (
          <p className="text-[#64748b]">Processing...</p>
        )}
        {status === 'done' && (
          <>
            <div className="text-5xl mb-4">&#10003;</div>
            <h1 className="text-2xl font-semibold mb-3 text-[#e2e8f0]">You&apos;ve been unsubscribed</h1>
            <p className="text-[#64748b] text-sm leading-relaxed">
              You won&apos;t receive any more emails from Tended. If this was a mistake,
              just submit a new audit at{' '}
              <a href="https://usetended.io" className="text-green-600 underline">
                usetended.io
              </a>.
            </p>
          </>
        )}
        {status === 'error' && (
          <>
            <h1 className="text-2xl font-semibold mb-3 text-[#e2e8f0]">Something went wrong</h1>
            <p className="text-[#64748b] text-sm">
              We couldn&apos;t process your unsubscribe request. Please try again or contact support.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function UnsubscribePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0B0D11]" />}>
      <UnsubscribeContent />
    </Suspense>
  );
}
