'use client';

import { useEffect, useRef, useCallback, type ReactNode } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
}

export function Modal({ open, onClose, title, description, children }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const titleId = title ? 'modal-title' : undefined;
  const descriptionId = description ? 'modal-description' : undefined;

  // Focus trap: collect all focusable elements within the modal
  const getFocusableElements = useCallback(() => {
    if (!modalRef.current) return [];
    return Array.from(
      modalRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    );
  }, []);

  // Handle Escape key and Tab focus trap
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = getFocusableElements();
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose, getFocusableElements]);

  // Lock body scroll and manage focus
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      document.body.style.overflow = 'hidden';

      // Focus the first focusable element after render
      requestAnimationFrame(() => {
        const focusable = getFocusableElements();
        if (focusable.length > 0) {
          focusable[0].focus();
        }
      });
    }
    return () => {
      document.body.style.overflow = '';
      // Restore focus to the element that opened the modal
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
        previousFocusRef.current.focus();
      }
    };
  }, [open, getFocusableElements]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <div className="fixed inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={modalRef}
        className="relative z-10 w-full max-w-lg rounded-xl border border-brand-border bg-brand-surface p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-center justify-between">
          {title && (
            <h2 id={titleId} className="text-lg font-semibold text-brand-text">
              {title}
            </h2>
          )}
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="ml-auto rounded-lg p-1 text-brand-text-muted hover:bg-brand-surface-hover hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2"
          >
            <X size={18} />
          </button>
        </div>
        {description && (
          <p id={descriptionId} className="text-sm text-brand-text-muted mb-4">
            {description}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}
