"""Stripe subscription management — checkout, webhooks, usage limits.

Note: Stripe Python SDK is synchronous. All Stripe API calls are wrapped
in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import logging
from uuid import UUID

import asyncpg
import stripe

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tier limits
TIER_LIMITS = {
    "free": {"sites": 1, "posts": 50, "consolidations_per_month": 0, "oracle": False},
    "growth": {"sites": 1, "posts": 500, "consolidations_per_month": 5, "oracle": True},
    "scale": {"sites": 10, "posts": 5000, "consolidations_per_month": -1, "oracle": True},
}


class StripeService:
    """Handle Stripe checkout, webhooks, and subscription management."""

    def __init__(self) -> None:
        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key

    async def create_checkout_session(
        self,
        db: asyncpg.Connection,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe checkout session and return the URL."""
        # Get or create Stripe customer
        profile = await db.fetchrow(
            "SELECT email, stripe_customer_id FROM profiles WHERE id = $1::uuid",
            user_id,
        )
        if not profile:
            raise ValueError("User profile not found")

        customer_id = profile["stripe_customer_id"]
        if not customer_id:
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=profile["email"],
                metadata={"user_id": user_id},
            )
            customer_id = customer.id
            await db.execute(
                "UPDATE profiles SET stripe_customer_id = $1 WHERE id = $2::uuid",
                customer_id,
                user_id,
            )

        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id},
        )

        return session.url

    async def handle_webhook(
        self, db: asyncpg.Connection, payload: bytes, sig_header: str
    ) -> None:
        """Process a Stripe webhook event."""
        settings = get_settings()

        try:
            event = await asyncio.to_thread(
                stripe.Webhook.construct_event,
                payload, sig_header, settings.stripe_webhook_secret,
            )
        except stripe.SignatureVerificationError:
            logger.error("Invalid Stripe webhook signature")
            raise ValueError("Invalid signature")

        event_type = event["type"]
        data = event["data"]["object"]

        logger.info("Stripe webhook: %s", event_type)

        if event_type == "checkout.session.completed":
            user_id = data.get("metadata", {}).get("user_id")
            subscription_id = data.get("subscription")
            customer_id = data.get("customer")
            if user_id and subscription_id:
                # Determine tier from price
                sub = await asyncio.to_thread(
                    stripe.Subscription.retrieve, subscription_id
                )
                price_id = sub["items"]["data"][0]["price"]["id"]
                tier = self._price_to_tier(price_id)
                await db.execute(
                    """UPDATE profiles
                       SET stripe_subscription_id = $1,
                           stripe_customer_id = $2,
                           subscription_status = $3
                       WHERE id = $4::uuid""",
                    subscription_id,
                    customer_id,
                    tier,
                    user_id,
                )
                logger.info("Activated %s subscription for user %s", tier, user_id)

        elif event_type == "customer.subscription.updated":
            subscription_id = data.get("id")
            price_id = data["items"]["data"][0]["price"]["id"]
            tier = self._price_to_tier(price_id)
            current_period_end = data.get("current_period_end")

            await db.execute(
                """UPDATE profiles
                   SET subscription_status = $1,
                       subscription_ends_at = TO_TIMESTAMP($2)
                   WHERE stripe_subscription_id = $3""",
                tier,
                current_period_end,
                subscription_id,
            )

        elif event_type == "customer.subscription.deleted":
            subscription_id = data.get("id")
            await db.execute(
                """UPDATE profiles
                   SET subscription_status = 'free',
                       stripe_subscription_id = NULL,
                       subscription_ends_at = NULL
                   WHERE stripe_subscription_id = $1""",
                subscription_id,
            )
            logger.info("Subscription %s cancelled, downgraded to free", subscription_id)

        elif event_type == "invoice.payment_failed":
            subscription_id = data.get("subscription")
            if subscription_id:
                await db.execute(
                    """UPDATE profiles
                       SET subscription_status = 'past_due'
                       WHERE stripe_subscription_id = $1""",
                    subscription_id,
                )
                logger.warning("Payment failed for subscription %s", subscription_id)

    def _price_to_tier(self, price_id: str) -> str:
        """Map a Stripe price ID to a tier name."""
        settings = get_settings()
        if price_id == settings.stripe_price_growth:
            return "growth"
        elif price_id == settings.stripe_price_scale:
            return "scale"
        return "growth"  # default if unknown

    async def get_subscription(
        self, db: asyncpg.Connection, user_id: str
    ) -> dict:
        """Get current subscription details."""
        row = await db.fetchrow(
            """SELECT subscription_status, stripe_subscription_id,
                      subscription_ends_at
               FROM profiles WHERE id = $1::uuid""",
            user_id,
        )
        if not row:
            return {
                "tier": "free",
                "status": "active",
                "stripe_subscription_id": None,
                "current_period_end": None,
            }

        tier = row["subscription_status"] or "free"
        sub_id = row["stripe_subscription_id"]
        ends_at = row["subscription_ends_at"]

        return {
            "tier": tier,
            "status": "active" if tier != "past_due" else "past_due",
            "stripe_subscription_id": sub_id,
            "current_period_end": ends_at.isoformat() if ends_at else None,
        }

    async def get_portal_url(
        self, db: asyncpg.Connection, user_id: str, return_url: str
    ) -> str:
        """Create a Stripe customer portal session URL."""
        profile = await db.fetchrow(
            "SELECT stripe_customer_id FROM profiles WHERE id = $1::uuid",
            user_id,
        )
        if not profile or not profile["stripe_customer_id"]:
            raise ValueError("No Stripe customer found. Subscribe first.")

        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=profile["stripe_customer_id"],
            return_url=return_url,
        )
        return session.url

    async def check_usage_limits(
        self, db: asyncpg.Connection, user_id: str, feature: str
    ) -> bool:
        """Check if user is within their tier limits for a feature."""
        sub = await self.get_subscription(db, user_id)
        tier = sub["tier"]
        if tier == "past_due":
            tier = "free"  # Downgrade for past_due

        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

        if feature == "sites":
            count = await db.fetchval(
                "SELECT COUNT(*) FROM sites WHERE user_id = $1", user_id
            ) or 0
            return count < limits["sites"]

        elif feature == "posts":
            count = await db.fetchval(
                """SELECT COUNT(*) FROM posts p
                   JOIN sites s ON s.id = p.site_id
                   WHERE s.user_id = $1""",
                user_id,
            ) or 0
            return count < limits["posts"]

        elif feature == "oracle":
            return limits["oracle"]

        elif feature == "consolidation":
            if limits["consolidations_per_month"] == -1:
                return True  # Unlimited
            count = await db.fetchval(
                """SELECT COUNT(*) FROM impact_tracking it
                   JOIN sites s ON s.id = it.site_id
                   WHERE s.user_id = $1
                   AND it.created_at >= DATE_TRUNC('month', CURRENT_DATE)""",
                user_id,
            ) or 0
            return count < limits["consolidations_per_month"]

        return True
