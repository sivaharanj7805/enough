'use client';

import React, { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: React.ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary wraps components that may throw during render (e.g. D3 visualizations).
 * Without this, a single render error crashes the entire page.
 *
 * Usage:
 *   <ErrorBoundary fallback={<p>Visualization unavailable</p>}>
 *     <EcosystemCanvas />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, info);
    this.props.onError?.(error, info);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center rounded-xl border border-red-500/30 bg-red-950/20 p-8 text-center"
        >
          <p className="text-sm font-medium text-red-400">Something went wrong rendering this view</p>
          <p className="mt-1 text-xs text-brand-text-muted">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>
          <button
            onClick={this.reset}
            className="mt-4 rounded-lg bg-brand-surface px-4 py-2 text-sm text-brand-text hover:bg-brand-surface-hover"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
