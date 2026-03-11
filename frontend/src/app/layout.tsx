import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/providers/AuthProvider';
import { SiteProvider } from '@/providers/SiteProvider';

export const metadata: Metadata = {
  title: 'Enough — Content Ecosystem Intelligence',
  description: 'See your content ecosystem as a living landscape. Find cannibalization, consolidate strategically.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-brand-bg text-brand-text antialiased">
        <AuthProvider>
          <SiteProvider>
            {children}
          </SiteProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
