'use client';

import { useState } from 'react';
import { useSWRFetch } from '@/lib/hooks/useSWRFetch';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { CreditCard, Check, ExternalLink } from 'lucide-react';
import type {
  SubscriptionResponse,
  CheckoutResponse,
  PortalResponse,
} from '@/lib/types/phase5';

const PLANS = [
  {
    tier: 'growth',
    name: 'Growth',
    price: '$99',
    period: '/mo',
    features: [
      '1 site',
      'Up to 500 posts',
      'Full landscape & dashboard',
      'Pre-Publish Oracle',
      '5 consolidations / month',
      'Content overlap detection',
      'Weekly ecosystem reports',
    ],
    limits: [],
    priceId: 'growth',
  },
  {
    tier: 'scale',
    name: 'Scale',
    price: '$299',
    period: '/mo',
    features: [
      'Up to 10 sites',
      'Up to 5,000 posts',
      'Everything in Growth',
      'Unlimited consolidations',
      'Impact tracking',
      'Steward profile',
      'Priority support',
    ],
    limits: [],
    priceId: 'scale',
  },
] as const;

export default function BillingPage() {
  const { session } = useAuth();
  const [upgrading, setUpgrading] = useState<string | null>(null);

  const { data: subscription, isLoading } = useSWRFetch<SubscriptionResponse>(
    '/billing/subscription'
  );

  const handleUpgrade = async (priceId: string) => {
    if (!session?.access_token) return;
    setUpgrading(priceId);
    try {
      const res = await apiFetch<CheckoutResponse>('/billing/checkout', {
        method: 'POST',
        token: session.access_token,
        body: JSON.stringify({
          price_id: priceId,
          success_url: `${window.location.origin}/billing?success=true`,
          cancel_url: `${window.location.origin}/billing`,
        }),
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      console.error('Checkout failed:', err);
    } finally {
      setUpgrading(null);
    }
  };

  const handleManage = async () => {
    if (!session?.access_token) return;
    try {
      const res = await apiFetch<PortalResponse>('/billing/portal', {
        token: session.access_token,
      });
      window.location.href = res.portal_url;
    } catch (err) {
      console.error('Portal failed:', err);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const currentTier = subscription?.tier ?? 'free';

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-brand-text">Billing</h1>
        <p className="text-sm text-brand-text-muted mt-1">
          Manage your subscription and usage.
        </p>
      </div>

      {/* Current Plan */}
      <Card>
        <div className="flex items-center justify-between">
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
          <div className="flex items-center gap-3">
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
              <Button variant="secondary" size="sm" onClick={handleManage}>
                <ExternalLink size={14} />
                Manage
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Plans */}
      <div className="grid grid-cols-2 gap-4">
        {PLANS.map((plan) => {
          const isCurrent = currentTier === plan.tier;
          const isUpgrade =
            PLANS.findIndex((p) => p.tier === plan.tier) >
            PLANS.findIndex((p) => p.tier === currentTier);

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
                  {isCurrent && <Badge color="#22c55e">Current</Badge>}
                </div>
                <div className="mb-4">
                  <span className="text-3xl font-bold text-brand-text">
                    {plan.price}
                  </span>
                  <span className="text-brand-text-muted">{plan.period}</span>
                </div>
                <ul className="space-y-2 mb-4">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm text-brand-text"
                    >
                      <Check size={14} className="text-brand-accent mt-0.5 shrink-0" />
                      {feature}
                    </li>
                  ))}
                  {plan.limits.map((limit) => (
                    <li
                      key={limit}
                      className="flex items-start gap-2 text-sm text-brand-text-muted line-through"
                    >
                      <span className="w-3.5 shrink-0" />
                      {limit}
                    </li>
                  ))}
                </ul>
              </div>
              {isUpgrade && plan.priceId && (
                <Button
                  className="w-full"
                  onClick={() => handleUpgrade(plan.priceId as string)}
                  loading={upgrading === plan.priceId}
                >
                  Upgrade to {plan.name}
                </Button>
              )}
              {isCurrent && (
                <Button variant="secondary" className="w-full" disabled>
                  Current Plan
                </Button>
              )}
              {!isUpgrade && !isCurrent && (
                <Button variant="ghost" className="w-full" disabled>
                  —
                </Button>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
