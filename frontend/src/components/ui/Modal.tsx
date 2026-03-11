'use client';

import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-brand-border bg-brand-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          {title && <h2 className="text-lg font-semibold text-brand-text">{title}</h2>}
          <button
            onClick={onClose}
            className="ml-auto rounded-lg p-1 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
