'use client';

import { useState, useCallback } from 'react';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { OracleInput } from '@/components/oracle/OracleInput';
import { VerdictDisplay } from '@/components/oracle/VerdictDisplay';
import { SimilarPostsList } from '@/components/oracle/SimilarPostsList';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ArrowLeft } from 'lucide-react';
import type { OracleVerdict } from '@/lib/types';

export default function OraclePage() {
  const { currentSite } = useSite();
  const { session } = useAuth();
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState<OracleVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (content: string, keyword: string | null) => {
      if (!currentSite) return;
      setLoading(true);
      setError(null);
      setVerdict(null);

      try {
        const result = await apiFetch<OracleVerdict>(
          `/sites/${currentSite.id}/intelligence/oracle`,
          {
            method: 'POST',
            token: session?.access_token,
            body: JSON.stringify({ content, target_keyword: keyword }),
          }
        );
        setVerdict(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Oracle analysis failed');
      } finally {
        setLoading(false);
      }
    },
    [currentSite, session?.access_token]
  );

  function handleReset() {
    setVerdict(null);
    setError(null);
  }

  if (!currentSite) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-brand-text-muted">Select a site to use the Oracle</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {!verdict ? (
        <>
          <div className="text-center mb-8">
            <p className="text-4xl mb-3">🔮</p>
            <h2 className="text-2xl font-bold text-brand-text">Pre-Publish Oracle</h2>
            <p className="text-brand-text-muted mt-2">
              Check your draft against your ecosystem before publishing
            </p>
          </div>

          <Card>
            <OracleInput onSubmit={(c, k) => void handleSubmit(c, k)} loading={loading} />
          </Card>

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-400">
              {error}
            </div>
          )}
        </>
      ) : (
        <>
          <Button variant="ghost" onClick={handleReset}>
            <ArrowLeft size={16} />
            Analyze another draft
          </Button>

          <VerdictDisplay verdict={verdict} />
          <SimilarPostsList posts={verdict.similar_posts} />
        </>
      )}
    </div>
  );
}
