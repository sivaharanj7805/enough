import type { Metadata } from 'next';
import { apiUrl } from '@/lib/api';

const FRONTEND_URL = process.env.NEXT_PUBLIC_FRONTEND_URL ?? 'https://usetended.io';
// Server-side only token for fetching public report metadata (not exposed to client)
const REPORT_API_TOKEN = process.env.REPORT_API_TOKEN || '';

interface AuditReportMeta {
  headline: string;
  total_posts: number;
  overall_health: number;
  cann_pair_count: number;
  thin_content_count: number;
  orphan_count: number;
  domain: string;
}

async function fetchAuditMeta(siteId: string): Promise<AuditReportMeta | null> {
  try {
    const res = await fetch(apiUrl(`/sites/${siteId}/audit-report`), {
      headers: REPORT_API_TOKEN ? { Authorization: `Bearer ${REPORT_API_TOKEN}` } : {},
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return res.json() as Promise<AuditReportMeta>;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ siteId: string }>;
}): Promise<Metadata> {
  const { siteId } = await params;
  const report = await fetchAuditMeta(siteId);

  if (!report) {
    return {
      title: 'Content Audit Report — Tended',
      description: 'AI-powered content intelligence audit.',
    };
  }

  const domain = report.domain ?? 'your blog';
  const title = `${domain} Content Audit — ${report.total_posts} posts analyzed`;
  const description =
    report.headline ||
    `Health score: ${report.overall_health}/100 · ${report.cann_pair_count} cannibalizing pairs · ${report.thin_content_count} thin posts`;

  const reportUrl = `${FRONTEND_URL}/report/${siteId}`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: reportUrl,
      siteName: 'Tended — Content Intelligence',
      type: 'article',
      images: [
        {
          url: apiUrl(`/sites/${siteId}/og-image`),
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [apiUrl(`/sites/${siteId}/og-image`)],
    },
    alternates: {
      canonical: reportUrl,
    },
  };
}

export default function ReportLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
