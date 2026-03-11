'use client';

import { useState, type FormEvent } from 'react';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

interface OracleInputProps {
  onSubmit: (content: string, keyword: string | null) => void;
  loading: boolean;
}

export function OracleInput({ onSubmit, loading }: OracleInputProps) {
  const [content, setContent] = useState('');
  const [keyword, setKeyword] = useState('');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    onSubmit(content, keyword.trim() || null);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="oracle-content" className="mb-1.5 block text-sm font-medium text-brand-text">
          Your Draft or Content Idea
        </label>
        <textarea
          id="oracle-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste your draft or describe the content you plan to write..."
          rows={8}
          className="w-full rounded-lg border border-brand-border bg-brand-bg px-3 py-2 text-sm text-brand-text placeholder:text-brand-text-muted focus:border-brand-accent focus:outline-none focus:ring-1 focus:ring-brand-accent/50 resize-none"
          required
        />
      </div>

      <Input
        id="oracle-keyword"
        label="Target Keyword (optional)"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        placeholder="e.g., content marketing strategy"
      />

      <Button type="submit" className="w-full" size="lg" loading={loading}>
        <Sparkles size={18} />
        Analyze
      </Button>

      <p className="text-xs text-center text-brand-text-muted">
        The Oracle will check your draft against your entire content ecosystem
      </p>
    </form>
  );
}
