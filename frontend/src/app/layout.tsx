import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/providers/AuthProvider';
import { SiteProvider } from '@/providers/SiteProvider';
import { ToastProvider } from '@/components/ui/Toast';
import { CookieConsent } from '@/components/ui/CookieConsent';

const APP_URL = process.env.NEXT_PUBLIC_FRONTEND_URL ?? 'https://enough.app';

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: {
    default: 'Enough — Content Ecosystem Intelligence',
    template: '%s — Enough',
  },
  description:
    'Stop publishing more. Start publishing smarter. Enough analyses your content library, finds what\'s hurting you, and tells you exactly what to fix — in priority order.',
  keywords: ['content intelligence', 'SEO', 'content strategy', 'cannibalization', 'content audit'],
  authors: [{ name: 'Enough' }],
  creator: 'Enough',
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: APP_URL,
    siteName: 'Enough',
    title: 'Enough — Content Ecosystem Intelligence',
    description: 'Your blog has problems you don\'t know about yet. Enough finds them and tells you what to fix.',
    images: [
      {
        url: `${APP_URL}/og-default.png`,
        width: 1200,
        height: 630,
        alt: 'Enough — Content Ecosystem Intelligence Platform',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Enough — Content Ecosystem Intelligence',
    description: 'Your blog has problems you don\'t know about yet. Enough finds them and tells you what to fix.',
    images: [`${APP_URL}/og-default.png`],
  },
  robots: {
    index: true,
    follow: true,
  },
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
    ],
    apple: '/apple-touch-icon.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-brand-bg text-brand-text antialiased">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-brand-accent focus:text-white focus:rounded-lg"
        >
          Skip to main content
        </a>
        <ToastProvider>
          <AuthProvider>
            <SiteProvider>
              {children}
              <CookieConsent />
            </SiteProvider>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
