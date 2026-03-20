'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

/* ── Types ── */

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastOptions {
  type?: ToastType;
  duration?: number;
  action?: ToastAction;
}

interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration: number;
  action?: ToastAction;
  dismissing?: boolean;
}

interface ToastContextValue {
  toast: (message: string, options?: ToastOptions) => string;
  dismiss: (id: string) => void;
}

/* ── Context ── */

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}

/* ── Color map ── */

const barColors: Record<ToastType, string> = {
  success: 'bg-brand-success',
  error: 'bg-brand-critical',
  info: 'bg-brand-accent',
  warning: 'bg-brand-warning',
};

const iconMap: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
  warning: '⚠',
};

const iconColors: Record<ToastType, string> = {
  success: 'text-brand-success',
  error: 'text-brand-critical',
  info: 'text-brand-accent',
  warning: 'text-brand-warning',
};

/* ── Single Toast ── */

function ToastCard({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const touchStartX = useRef<number>(0);
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-dismiss
  useEffect(() => {
    timerRef.current = setTimeout(() => {
      onDismiss(item.id);
    }, item.duration);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [item.id, item.duration, onDismiss]);

  // Swipe to dismiss
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    if (dx > 60) {
      onDismiss(item.id);
    }
  };

  return (
    <div
      ref={cardRef}
      role="alert"
      aria-live="assertive"
      className={`
        relative flex items-start gap-3 w-80 overflow-hidden
        bg-brand-surface border border-brand-border rounded-card shadow-lg
        ${item.dismissing ? 'toast-slide-out' : 'toast-slide-in'}
        cursor-pointer
      `}
      onClick={() => onDismiss(item.id)}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Left color bar */}
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${barColors[item.type]}`} />

      <div className="flex items-start gap-3 py-3 pl-4 pr-3 w-full">
        {/* Icon */}
        <span className={`mt-0.5 text-sm font-bold ${iconColors[item.type]}`}>
          {iconMap[item.type]}
        </span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-brand-text leading-snug">{item.message}</p>

          {item.action && (
            <button
              className="mt-1.5 text-xs font-medium text-brand-accent hover:text-brand-accent-hover transition-colors duration-fast"
              onClick={(e) => {
                e.stopPropagation();
                item.action!.onClick();
                onDismiss(item.id);
              }}
            >
              {item.action.label}
            </button>
          )}
        </div>

        {/* Close button */}
        <button
          aria-label="Dismiss notification"
          className="shrink-0 mt-0.5 text-brand-text-tertiary hover:text-brand-text-secondary transition-colors duration-fast"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(item.id);
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M1 1l12 12M13 1L1 13" />
          </svg>
        </button>
      </div>
    </div>
  );
}

/* ── Provider ── */

let toastCounter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    // Mark as dismissing for exit animation
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, dismissing: true } : t))
    );
    // Remove after animation
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 200);
  }, []);

  const toast = useCallback(
    (message: string, options: ToastOptions = {}): string => {
      const id = `toast-${++toastCounter}-${Date.now()}`;
      const type = options.type ?? 'info';
      // Undo actions get 5s; everything else defaults to 4s
      const duration =
        options.duration ??
        (options.action?.label === 'Undo' ? 5000 : 4000);

      setToasts((prev) => [
        ...prev,
        { id, message, type, duration, action: options.action },
      ]);

      return id;
    },
    []
  );

  const value: ToastContextValue = { toast, dismiss };

  return (
    <ToastContext.Provider value={value}>
      {children}

      {/* Toast container — top-right stack */}
      <div
        aria-label="Notifications"
        className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
      >
        {toasts.map((item) => (
          <div key={item.id} className="pointer-events-auto">
            <ToastCard item={item} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
