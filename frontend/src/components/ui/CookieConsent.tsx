'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

const STORAGE_KEY = 'tended-cookie-consent';

interface CookiePreferences {
  essential: boolean;
  analytics: boolean;
}

function loadPreferences(): CookiePreferences | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as CookiePreferences;
  } catch {
    return null;
  }
}

function savePreferences(prefs: CookiePreferences) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

export function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const [managing, setManaging] = useState(false);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(true);

  useEffect(() => {
    const prefs = loadPreferences();
    if (!prefs) {
      setVisible(true);
    }
  }, []);

  const handleAccept = () => {
    savePreferences({ essential: true, analytics: true });
    setVisible(false);
  };

  const handleSavePreferences = () => {
    savePreferences({ essential: true, analytics: analyticsEnabled });
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="region"
      aria-label="Cookie consent"
      className="fixed bottom-0 left-0 right-0 z-[9998] border-t border-brand-border bg-brand-surface shadow-lg"
    >
      <div className="mx-auto max-w-4xl px-4 py-4 sm:px-6">
        {!managing ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-brand-text">
              We use cookies for authentication and analytics. By continuing, you agree to our use of cookies.{' '}
              <Link href="/privacy" className="text-brand-accent hover:underline">
                Privacy Policy
              </Link>
            </p>
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => setManaging(true)}
                className="text-sm text-brand-text-muted hover:text-brand-text transition-colors"
              >
                Manage
              </button>
              <button
                onClick={handleAccept}
                className="px-4 py-2 rounded-lg bg-brand-accent text-white text-sm font-medium hover:bg-brand-accent/90 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2"
              >
                Accept
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm font-medium text-brand-text">Manage cookie preferences</p>

            <div className="space-y-3">
              {/* Essential cookies — always on */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-brand-text">Essential</p>
                  <p className="text-xs text-brand-text-muted">Required for authentication and core functionality.</p>
                </div>
                <span className="text-xs text-brand-text-muted bg-brand-surface-hover px-2 py-1 rounded">
                  Always on
                </span>
              </div>

              {/* Analytics cookies — toggleable */}
              <div className="flex items-center justify-between">
                <div>
                  <label htmlFor="analytics-toggle" className="text-sm font-medium text-brand-text cursor-pointer">
                    Analytics
                  </label>
                  <p className="text-xs text-brand-text-muted">Help us understand how you use the app so we can improve it.</p>
                </div>
                <button
                  id="analytics-toggle"
                  role="switch"
                  aria-checked={analyticsEnabled}
                  onClick={() => setAnalyticsEnabled(!analyticsEnabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2 ${
                    analyticsEnabled ? 'bg-brand-accent' : 'bg-brand-border'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      analyticsEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setManaging(false)}
                className="text-sm text-brand-text-muted hover:text-brand-text transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleSavePreferences}
                className="px-4 py-2 rounded-lg bg-brand-accent text-white text-sm font-medium hover:bg-brand-accent/90 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2"
              >
                Save Preferences
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
