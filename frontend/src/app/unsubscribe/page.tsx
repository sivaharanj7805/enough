'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function UnsubscribePage() {
  const searchParams = useSearchParams();
  const email = searchParams.get('email');
  const [status, setStatus] = useState<'loading' | 'done' | 'error'>('loading');

  useEffect(() => {
    if (!email) {
      setStatus('error');
      return;
    }

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/unsubscribe?email=${encodeURIComponent(email)}`)
      .then((res) => {
        if (res.ok) setStatus('done');
        else setStatus('error');
      })
      .catch(() => setStatus('error'));
  }, [email]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-sm p-12 max-w-md text-center">
        {status === 'loading' && (
          <p className="text-gray-500">Processing...</p>
        )}
        {status === 'done' && (
          <>
            <div className="text-5xl mb-4">&#10003;</div>
            <h1 className="text-2xl font-semibold mb-3">You&apos;ve been unsubscribed</h1>
            <p className="text-gray-500 text-sm leading-relaxed">
              You won&apos;t receive any more emails from Enough. If this was a mistake,
              just submit a new audit at{' '}
              <a href="https://enough.app" className="text-green-600 underline">
                enough.app
              </a>.
            </p>
          </>
        )}
        {status === 'error' && (
          <>
            <h1 className="text-2xl font-semibold mb-3">Something went wrong</h1>
            <p className="text-gray-500 text-sm">
              We couldn&apos;t process your unsubscribe request. Please try again or contact support.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
