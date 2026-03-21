'use client';

import { Card } from '@/components/ui/Card';
import { Users } from 'lucide-react';

export default function CompetitorsPage() {
  return (
    <div className="max-w-3xl mx-auto py-8">
      <Card className="!p-8 text-center">
        <Users size={40} className="text-[#64748b] mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-[#e2e8f0] mb-2">
          Competitor Analysis — Coming Soon
        </h2>
        <p className="text-sm text-[#64748b] max-w-md mx-auto">
          We&apos;re building real competitor crawling and comparison.
          This feature will analyze competitor domains directly, not estimates.
          Check back soon.
        </p>
      </Card>
    </div>
  );
}
