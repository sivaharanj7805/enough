'use client';

import { Download } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import type { RedirectEntry } from '@/lib/types';

interface RedirectMapProps {
  entries: RedirectEntry[];
  isWordPress: boolean;
}

export function RedirectMap({ entries, isWordPress }: RedirectMapProps) {
  function exportCsv() {
    const header = 'old_url,new_url';
    const rows = entries.map(
      (e) => `"${e.old_url}","${e.new_url}"`
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'redirect-map.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-brand-text">Redirect Map</h3>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={exportCsv}>
            <Download size={14} />
            Export CSV
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!isWordPress}
            title={!isWordPress ? 'Only available for WordPress sites' : undefined}
          >
            Push to WordPress
          </Button>
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-brand-text-muted text-center py-4">No redirects needed</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brand-border">
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">Old URL</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">→</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-brand-text-muted">New URL (Pillar)</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.old_url} className="border-b border-brand-border/50 hover:bg-brand-surface-hover">
                  <td className="py-2 px-3 text-brand-text-muted font-mono text-xs truncate max-w-[280px]">
                    {entry.old_url}
                  </td>
                  <td className="py-2 px-3 text-brand-text-muted">→</td>
                  <td className="py-2 px-3 text-brand-accent font-mono text-xs truncate max-w-[280px]">
                    {entry.new_url}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
