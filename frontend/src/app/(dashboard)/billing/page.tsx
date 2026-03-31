'use client';

import { useState, useEffect } from 'react';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Modal } from '@/components/ui/Modal';
import {
  CreditCard,
  Check,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  FileText,
  X,
} from 'lucide-react';
import type {
  SubscriptionResponse,
  CheckoutResponse,
  PortalResponse,
} from '@/lib/types/phase5';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Invoice {
  id: string;
  date: string;
  amount: number;
  status: string;
}

interface UsageResponse {
  posts_analyzed: number;
  posts_limit: number;
  sites_count?: number;
  sites_limit?: number;
}

/* ------------------------------------------------------------------ */
/*  Plan definitions                                                   */
/* ------------------------------------------------------------------ */

const PLANS = [
  {
    tier: 'growth',
    name: 'Growth',
    monthlyPrice: 149,
    annualPrice: 1490,
    features: [
      '1 site',
      'Up to 500 posts',
      'Full landscape & dashboard',
      'Pre-Publish Oracle',
      '5 consolidations / month',
      'Content overlap detection',
      'Weekly ecosystem reports',
    ],
    priceId: 'growth',
  },
  {
    tier: 'scale',
    name: 'Scale',
    monthlyPrice: 349,
    annualPrice: 3490,
    features: [
      'Up to 3 sites',
      'Up to 2,000 posts',
      'Everything in Growth',
      'Unlimited consolidations',
      'Impact tracking',
      'Steward profile',
      'Priority support',
    ],
    priceId: 'scale',
  },
] as const;

/* ------------------------------------------------------------------ */
/*  Cancel reasons & retention offers                                  */
/* ------------------------------------------------------------------ */

const CANCEL_REASONS = [
  { key: 'too_expensive', label: 'Too expensive' },
  { key: 'not_using', label: "I'm not using it enough" },
  { key: 'missing_features', label: 'Missing features I need' },
  { key: 'switching', label: 'Switching to a different tool' },
  { key: 'other', label: 'Other' },
] as const;

type CancelReason = (typeof CANCEL_REASONS)[number]['key'];

/* ------------------------------------------------------------------ */
/*  Cancel flow step type                                              */
/* ------------------------------------------------------------------ */

type CancelStep = 'reason' | 'confirm';

/* ------------------------------------------------------------------ */
/*  Billing Page                                                       */
/* ------------------------------------------------------------------ */

export default function BillingPage() {
  const { session } = useAuth();
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [annual, setAnnual] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);

  // Cancel flow state
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelStep, setCancelStep] = useState<CancelStep>('reason');
  const [cancelReason, setCancelReason] = useState<CancelReason | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const { data: subscription, isLoading } =
    useSWRFetch<SubscriptionResponse>('/billing/subscription');

  const { data: usage } = useSWRFetch<UsageResponse>('/billing/usage');

  const { data: invoices } = useSWRFetch<Invoice[]>('/billing/invoices');

  // Reset cancel flow when modal closes
  useEffect(() => {
    if (!cancelModalOpen) {
      setCancelStep('reason');
      setCancelReason(null);
      setCancelling(false);
    }
  }, [cancelModalOpen]);

  /* ---- Handlers ---- */

  const handleUpgrade = async (priceId: string) => {
    if (!session?.access_token) return;
    setUpgrading(priceId);
    setBillingError(null);
    try {
      const res = await apiFetch<CheckoutResponse>('/billing/checkout', {
        method: 'POST',
        token: session.access_token,
        body: JSON.stringify({
          price_id: annual ? `${priceId}_annual` : priceId,
          success_url: `${window.location.origin}/billing?success=true`,
          cancel_url: `${window.location.origin}/billing`,
        }),
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      console.error('Checkout failed:', err);
      setBillingError('Checkout failed. Please try again.');
    } finally {
      setUpgrading(null);
    }
  };

  const handleManage = async () => {
    if (!session?.access_token) return;
    setBillingError(null);
    try {
      const res = await apiFetch<PortalResponse>('/billing/portal', {
        token: session.access_token,
      });
      window.location.href = res.portal_url;
    } catch (err) {
      console.error('Portal failed:', err);
      setBillingError('Failed to open billing portal. Please try again.');
    }
  };

  const handleConfirmCancel = async () => {
    if (!session?.access_token) return;
    setCancelling(true);
    try {
      await apiFetch('/billing/cancel', {
        method: 'POST',
        token: session.access_token,
        body: JSON.stringify({ reason: cancelReason }),
      });
      setCancelModalOpen(false);
      // Reload to reflect new status
      window.location.reload();
    } catch (err) {
      console.error('Cancel failed:', err);
      setCancelling(false);
    }
  };

  /* ---- Loading ---- */

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const currentTier = subscription?.tier ?? 'free';

  /* ---- Render ---- */

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">Billing</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          Manage your subscription, usage, and invoices.
        </p>
      </div>

      {/* Billing error */}
      {billingError && (
        <p className="text-sm text-red-400 mt-2">{billingError}</p>
      )}

      {/* 30-day money-back guarantee */}
      <div className="flex items-center gap-3 rounded-xl bg-[#22c55e]/10 border border-[#22c55e]/20 px-5 py-4">
        <ShieldCheck size={22} className="text-[#22c55e] flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-[#22c55e]">30-day money-back guarantee</p>
          <p className="text-xs text-brand-text-muted mt-0.5">
            Not happy? Get a full refund within the first 30 days. No questions asked.
          </p>
        </div>
      </div>

      {/* Current Plan Card */}
      <Card>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-accent/20">
              <CreditCard size={20} className="text-brand-accent" />
            </div>
            <div>
              <div className="text-sm text-brand-text-muted">Current Plan</div>
              <div className="text-lg font-bold text-brand-text capitalize">
                {currentTier}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {subscription?.current_period_end && (
              <span className="text-xs text-brand-text-muted">
                Renews{' '}
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </span>
            )}
            <Badge color={subscription?.status === 'active' ? '#22c55e' : '#f97316'}>
              {subscription?.status ?? 'active'}
            </Badge>
            {subscription?.stripe_subscription_id && (
              <Button variant="secondary" size="sm" onClick={() => void handleManage()}>
                <ExternalLink size={14} />
                Manage Payment Method
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Usage Meter */}
      {usage && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-brand-text">Usage</h3>
            <span className="text-sm text-brand-text-muted">
              {usage.posts_analyzed} of {usage.posts_limit} posts analyzed
            </span>
          </div>
          <ProgressBar
            value={usage.posts_analyzed}
            max={usage.posts_limit}
            color={
              usage.posts_analyzed / usage.posts_limit > 0.9
                ? '#ef4444'
                : usage.posts_analyzed / usage.posts_limit > 0.7
                  ? '#f97316'
                  : '#22c55e'
            }
          />
          {usage.posts_analyzed / usage.posts_limit > 0.9 && (
            <p className="text-xs text-[#f97316] mt-2">
              You&apos;re approaching your plan limit. Consider upgrading for more capacity.
            </p>
          )}
          {/* Sites usage (GAP-14) */}
          {usage.sites_count != null && usage.sites_limit != null && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-brand-text-muted">Sites</span>
                <span className="text-sm text-brand-text-muted">
                  {usage.sites_count} of {usage.sites_limit}
                </span>
              </div>
              <ProgressBar
                value={usage.sites_count}
                max={usage.sites_limit}
                color={usage.sites_count >= usage.sites_limit ? '#ef4444' : '#22c55e'}
              />
            </div>
          )}
        </Card>
      )}

      {/* Annual Toggle */}
      <div className="flex items-center justify-center gap-3">
        <span
          className={`text-sm font-medium ${!annual ? 'text-brand-text' : 'text-brand-text-muted'}`}
        >
          Monthly
        </span>
        <button
          onClick={() => setAnnual(!annual)}
          className={`relative w-12 h-6 rounded-full transition-colors ${
            annual ? 'bg-[#22c55e]' : 'bg-brand-surface-hover'
          }`}
          aria-label="Toggle annual billing"
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
              annual ? 'translate-x-6' : 'translate-x-0'
            }`}
          />
        </button>
        <span
          className={`text-sm font-medium ${annual ? 'text-brand-text' : 'text-brand-text-muted'}`}
        >
          Annual
        </span>
        {annual && (
          <span className="text-xs font-semibold text-[#22c55e] bg-[#22c55e]/10 px-2 py-0.5 rounded-full">
            Save 2 months
          </span>
        )}
      </div>

      {/* Plan Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PLANS.map((plan) => {
          const isCurrent = currentTier === plan.tier;
          const planIndex = PLANS.findIndex((p) => p.tier === plan.tier);
          const currentIndex = PLANS.findIndex((p) => p.tier === currentTier);
          const isUpgrade = planIndex > currentIndex;
          const isDowngrade = planIndex < currentIndex;
          const displayPrice = annual ? plan.annualPrice : plan.monthlyPrice;
          const period = annual ? '/year' : '/mo';

          return (
            <Card
              key={plan.tier}
              className={`flex flex-col ${
                isCurrent ? 'ring-2 ring-brand-accent border-brand-accent' : ''
              }`}
            >
              <div className="flex-1">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-lg font-bold text-brand-text">{plan.name}</h3>
                  {isCurrent && <Badge color="#22c55e">Current Plan</Badge>}
                </div>
                <div className="mb-4">
                  <span className="text-3xl font-bold text-brand-text">
                    ${displayPrice.toLocaleString()}
                  </span>
                  <span className="text-brand-text-muted">{period}</span>
                  {annual && (
                    <span className="block text-xs text-brand-text-muted mt-1">
                      ${plan.monthlyPrice}/mo billed monthly
                    </span>
                  )}
                </div>
                <ul className="space-y-2 mb-6">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm text-brand-text"
                    >
                      <Check
                        size={14}
                        className="text-brand-accent mt-0.5 shrink-0"
                      />
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
              {isUpgrade && (
                <Button
                  className="w-full"
                  onClick={() => void handleUpgrade(plan.priceId as string)}
                  loading={upgrading === plan.priceId}
                >
                  Upgrade to {plan.name}
                </Button>
              )}
              {isDowngrade && (
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() => void handleUpgrade(plan.priceId as string)}
                  loading={upgrading === plan.priceId}
                >
                  Downgrade to {plan.name}
                </Button>
              )}
              {isCurrent && (
                <Button variant="secondary" className="w-full" disabled>
                  Current Plan
                </Button>
              )}
            </Card>
          );
        })}
      </div>

      {/* Invoice History */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <FileText size={18} className="text-brand-text-muted" />
          <h3 className="text-sm font-semibold text-brand-text">Invoice History</h3>
        </div>
        {invoices && invoices.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-brand-border">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-brand-text-muted uppercase tracking-wider">
                    Date
                  </th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-brand-text-muted uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-brand-text-muted uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    className="border-b border-brand-border last:border-0"
                  >
                    <td className="py-3 px-3 text-brand-text">
                      {new Date(invoice.date).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-3 text-brand-text">
                      ${(invoice.amount / 100).toFixed(2)}
                    </td>
                    <td className="py-3 px-3">
                      <Badge
                        color={
                          invoice.status === 'paid'
                            ? '#22c55e'
                            : invoice.status === 'open'
                              ? '#f97316'
                              : '#64748b'
                        }
                      >
                        {invoice.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-brand-text-muted py-4 text-center">
            No invoices yet.
          </p>
        )}
      </Card>

      {/* Cancel Subscription */}
      {subscription?.stripe_subscription_id && subscription?.status === 'active' && (
        <div className="border border-brand-border rounded-xl p-6">
          <h3 className="text-sm font-semibold text-brand-text mb-2">
            Cancel Subscription
          </h3>
          <p className="text-sm text-brand-text-muted mb-4">
            You can cancel your subscription at any time. You&apos;ll retain access until
            the end of your current billing period.
          </p>
          <button
            onClick={() => setCancelModalOpen(true)}
            className="px-4 py-2 rounded-xl border border-red-500/50 text-red-400 text-sm font-medium
                       hover:bg-red-500/10 transition-colors"
          >
            Cancel Subscription
          </button>
        </div>
      )}

      {/* Cancel Modal */}
      <Modal
        open={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        title="Cancel Subscription"
      >
        {/* Step 1: Reason */}
        {cancelStep === 'reason' && (
          <div className="space-y-4">
            <p className="text-sm text-brand-text-muted">
              We&apos;re sorry to see you go. Could you tell us why you&apos;re cancelling?
            </p>
            <div className="space-y-2">
              {CANCEL_REASONS.map((reason) => (
                <button
                  key={reason.key}
                  onClick={() => {
                    setCancelReason(reason.key);
                    setCancelStep('confirm');
                  }}
                  className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-all ${
                    cancelReason === reason.key
                      ? 'border-brand-accent bg-brand-accent/10 text-brand-text'
                      : 'border-brand-border text-brand-text-muted hover:border-brand-text-muted hover:text-brand-text'
                  }`}
                >
                  {reason.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Confirmation */}
        {cancelStep === 'confirm' && (
          <div className="space-y-4">
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle size={18} className="text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-semibold text-brand-text mb-2">
                    Are you sure?
                  </h4>
                  {subscription?.current_period_end && (
                    <p className="text-sm text-brand-text-muted mb-2">
                      Your subscription will remain active until{' '}
                      <span className="font-semibold text-brand-text">
                        {new Date(subscription.current_period_end).toLocaleDateString()}
                      </span>
                      . After that date:
                    </p>
                  )}
                  <ul className="space-y-1.5 text-sm text-brand-text-muted">
                    <li className="flex items-start gap-2">
                      <X size={14} className="text-red-400 mt-0.5 shrink-0" />
                      You&apos;ll lose access to your dashboard and reports
                    </li>
                    <li className="flex items-start gap-2">
                      <X size={14} className="text-red-400 mt-0.5 shrink-0" />
                      Scheduled analyses will stop running
                    </li>
                    <li className="flex items-start gap-2">
                      <X size={14} className="text-red-400 mt-0.5 shrink-0" />
                      Your consolidation history and tracking data will be archived
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setCancelModalOpen(false)}
              >
                Keep my subscription
              </Button>
              <button
                onClick={() => void handleConfirmCancel()}
                disabled={cancelling}
                className="w-full px-4 py-2.5 rounded-xl bg-red-500 text-white text-sm font-semibold
                           hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {cancelling ? 'Cancelling...' : 'Confirm Cancellation'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
