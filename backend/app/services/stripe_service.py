"""Stripe subscription management — checkout, webhooks, usage limits.

Note: Stripe Python SDK is synchronous. All Stripe API calls are wrapped
in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import logging
from datetime import UTC

import asyncpg
import stripe

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tier limits — paid-only product, no free tier
# "free" = unsubscribed user, blocked from everything until they pay
TIER_LIMITS = {
    "free": {"sites": 0, "posts": 0, "consolidations_per_month": 0, "oracle": False},
    "growth": {"sites": 1, "posts": 500, "consolidations_per_month": 5, "oracle": True},
    "scale": {"sites": 3, "posts": 2000, "consolidations_per_month": -1, "oracle": True},
}


class StripeService:
    """Handle Stripe checkout, webhooks, and subscription management."""

    COMEBACK30_COUPON_ID = "COMEBACK30"

    def __init__(self) -> None:
        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key

    async def ensure_comeback30_coupon(self) -> None:
        """Create the COMEBACK30 coupon in Stripe if it doesn't already exist.

        30% off for 3 months, one redemption per customer.
        Called at app startup — best-effort, never blocks boot.
        """
        try:
            await asyncio.to_thread(stripe.Coupon.retrieve, self.COMEBACK30_COUPON_ID)
            logger.info("COMEBACK30 coupon already exists in Stripe")
        except stripe.InvalidRequestError:
            # Coupon doesn't exist — create it
            try:
                await asyncio.to_thread(
                    stripe.Coupon.create,
                    id=self.COMEBACK30_COUPON_ID,
                    percent_off=30,
                    duration="repeating",
                    duration_in_months=3,
                    name="Comeback 30% Off (3 months)",
                )
                # Create a promo code so customers can enter "COMEBACK30" at checkout
                await asyncio.to_thread(
                    stripe.PromotionCode.create,
                    coupon=self.COMEBACK30_COUPON_ID,
                    code=self.COMEBACK30_COUPON_ID,
                    max_redemptions_per_customer=1,
                )
                logger.info("Created COMEBACK30 coupon and promo code in Stripe")
            except Exception as e:
                logger.warning("Failed to create COMEBACK30 coupon: %s", e)
        except Exception as e:
            logger.warning("Could not verify COMEBACK30 coupon (Stripe unavailable): %s", e)

    def _resolve_price_id(self, price_id: str) -> str:
        """Resolve a tier name ('growth', 'scale') to a real Stripe price ID.

        Accepts either a tier name or a raw Stripe price ID (price_xxx).
        """
        if price_id.startswith("price_"):
            return price_id  # Already a real Stripe price ID
        settings = get_settings()
        mapping = {
            "growth": settings.stripe_price_growth,
            "scale": settings.stripe_price_scale,
        }
        resolved = mapping.get(price_id)
        if not resolved:
            raise ValueError(f"Unknown price tier: {price_id}. Use 'growth' or 'scale'.")
        return resolved

    @staticmethod
    def _validate_redirect_url(url: str) -> None:
        """Ensure redirect URLs point to our own frontend to prevent open redirects."""
        from urllib.parse import urlparse

        settings = get_settings()
        frontend_url = settings.frontend_url or "http://localhost:3000"
        parsed = urlparse(url)
        expected = urlparse(frontend_url)
        if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
            raise ValueError(f"Redirect URL must match {frontend_url} origin")

    async def create_checkout_session(
        self,
        db: asyncpg.Connection,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe checkout session and return the URL."""
        # Validate redirect URLs to prevent open redirects (SEC-3)
        self._validate_redirect_url(success_url)
        self._validate_redirect_url(cancel_url)

        # Resolve tier name to actual Stripe price ID
        stripe_price_id = self._resolve_price_id(price_id)

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
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id},
        )

        return session.url

    async def handle_webhook(
        self, db: asyncpg.Connection, payload: bytes, sig_header: str
    ) -> None:
        """Process a Stripe webhook event with idempotency protection.

        Uses the Stripe event ID to prevent duplicate processing. If the DB
        write fails, the event will be retried by Stripe (up to 3 days).
        """
        settings = get_settings()

        try:
            event = await asyncio.to_thread(
                stripe.Webhook.construct_event,
                payload, sig_header, settings.stripe_webhook_secret,
            )
        except stripe.SignatureVerificationError:
            logger.error("Invalid Stripe webhook signature")
            raise ValueError("Invalid signature")

        event_id = event["id"]
        event_type = event["type"]
        data = event["data"]["object"]

        logger.info("Stripe webhook: %s (event_id=%s)", event_type, event_id)

        # Idempotency: atomic INSERT ON CONFLICT — no race between check and insert
        inserted = await db.fetchval(
            "INSERT INTO webhook_events (event_id, event_type) VALUES ($1, $2) ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
            event_id, event_type,
        )
        if not inserted:
            logger.info("Skipping duplicate webhook event %s", event_id)
            return

        # Process the event inside a transaction so either all writes succeed or none
        async with db.transaction():

            if event_type == "checkout.session.completed":
                user_id = data.get("metadata", {}).get("user_id")
                subscription_id = data.get("subscription")
                customer_id = data.get("customer")
                if user_id and subscription_id:
                    sub = await asyncio.to_thread(
                        stripe.Subscription.retrieve, subscription_id
                    )
                    items = sub.get("items", {}).get("data", [])
                    if not items:
                        logger.error("Subscription %s has no items", subscription_id)
                        return
                    price_id = items[0]["price"]["id"]
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
                    email = await db.fetchval("SELECT email FROM profiles WHERE id = $1::uuid", user_id)
                    await self._notify_slack(f"New customer: {email or user_id} subscribed to {tier} plan")

            elif event_type == "customer.subscription.updated":
                subscription_id = data.get("id")
                items = data.get("items", {}).get("data", [])
                if not items:
                    logger.error("Subscription %s has no items", subscription_id)
                    return
                price_id = items[0]["price"]["id"]
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
                # Get user info before downgrading
                profile = await db.fetchrow(
                    "SELECT id, email FROM profiles WHERE stripe_subscription_id = $1",
                    subscription_id,
                )
                await db.execute(
                    """UPDATE profiles
                       SET subscription_status = 'free',
                           stripe_subscription_id = NULL,
                           subscription_ends_at = NULL
                       WHERE stripe_subscription_id = $1""",
                    subscription_id,
                )
                logger.info("Subscription %s cancelled, downgraded to free", subscription_id)
                churn_email = profile["email"] if profile else "unknown"
                await self._notify_slack(f"Churn: {churn_email} cancelled subscription {subscription_id}")

                # Send cancellation confirmation email and schedule win-back sequence
                if profile and profile["email"]:
                    await self._send_cancellation_email(profile["email"])
                    await self._schedule_winback(
                        db, str(profile["id"]), profile["email"],
                    )

            elif event_type == "customer.subscription.paused":
                subscription_id = data.get("id")
                await db.execute(
                    """UPDATE profiles
                       SET subscription_status = 'paused'
                       WHERE stripe_subscription_id = $1""",
                    subscription_id,
                )
                logger.info("Subscription %s paused", subscription_id)

            elif event_type == "invoice.payment_failed":
                subscription_id = data.get("subscription")
                if subscription_id:
                    # Implement 7-day grace period: set past_due with grace deadline
                    # Don't immediately lock out — give 7 days to fix payment
                    from datetime import datetime, timedelta
                    grace_deadline = datetime.now(UTC) + timedelta(days=7)
                    await db.execute(
                        """UPDATE profiles
                           SET subscription_status = 'past_due',
                               grace_period_ends_at = $1
                           WHERE stripe_subscription_id = $2
                             AND subscription_status != 'free'""",
                        grace_deadline, subscription_id,
                    )
                    logger.warning(
                        "Payment failed for subscription %s — 7-day grace period until %s",
                        subscription_id, grace_deadline.isoformat(),
                    )
                    await self._notify_slack(f"Payment failed: subscription {subscription_id}, grace until {grace_deadline.date()}")

                    # Send payment failure notification
                    profile = await db.fetchrow(
                        "SELECT email FROM profiles WHERE stripe_subscription_id = $1",
                        subscription_id,
                    )
                    if profile and profile["email"]:
                        await self._send_payment_failed_email(
                            profile["email"], grace_deadline,
                        )

    @staticmethod
    async def _notify_slack(message: str) -> None:
        """Send a Slack notification via webhook URL (non-blocking, best-effort)."""
        settings = get_settings()
        if not settings.slack_webhook_url:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    settings.slack_webhook_url,
                    json={"text": message},
                )
        except Exception as e:
            logger.warning("Slack notification failed: %s", e)

    def _price_to_tier(self, price_id: str) -> str:
        """Map a Stripe price ID to a tier name."""
        settings = get_settings()
        if price_id == settings.stripe_price_growth:
            return "growth"
        elif price_id == settings.stripe_price_scale:
            return "scale"
        logger.error("Unknown Stripe price_id: %s — defaulting to free", price_id)
        return "free"  # safe default — never grant paid access for unknown IDs

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

    async def _send_cancellation_email(self, email: str) -> None:
        """Send a cancellation confirmation email."""
        settings = get_settings()
        if not settings.resend_api_key:
            return
        try:
            import resend
            resend.api_key = settings.resend_api_key
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": settings.email_from,
                    "to": [email],
                    "subject": "Your Tended subscription has been cancelled",
                    "html": """
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;border:1px solid #e5e7eb;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
  </div>
  <h2 style="font-size:18px;">We're sorry to see you go</h2>
  <p>Your Tended subscription has been cancelled. Your data will remain available for 30 days.</p>
  <p>If this was a mistake, you can resubscribe anytime at <a href="https://tended.app" style="color:#16a34a;">tended.app/pricing</a>.</p>
  <p style="color:#94a3b8;font-size:13px;">Your content ecosystem won't monitor itself — we'll be here when you're ready to come back.</p>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    Tended — Publish Less. Grow More.
  </div>
</div>""",
                },
            )
            logger.info("Cancellation confirmation sent to %s", email)
        except Exception as e:
            logger.error("Failed to send cancellation email to %s: %s", email, e)

    async def _send_payment_failed_email(
        self, email: str, grace_deadline,
    ) -> None:
        """Send payment failure notification with grace period info."""
        settings = get_settings()
        if not settings.resend_api_key:
            return
        try:
            import resend
            resend.api_key = settings.resend_api_key
            deadline_str = grace_deadline.strftime("%B %d, %Y")
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": settings.email_from,
                    "to": [email],
                    "subject": "Action needed: payment failed for your Tended subscription",
                    "html": f"""
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;border:1px solid #e5e7eb;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
  </div>
  <h2 style="font-size:18px;color:#f97316;">Payment Failed</h2>
  <p>We were unable to process your latest payment. Your account remains active until <strong>{deadline_str}</strong> (7-day grace period).</p>
  <p>Please update your payment method to avoid losing access:</p>
  <div style="text-align:center;margin:20px 0;">
    <a href="https://tended.app/settings/billing" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Update Payment Method &rarr;</a>
  </div>
  <p style="color:#94a3b8;font-size:13px;">If your payment isn't updated by {deadline_str}, your account will be downgraded.</p>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    Tended — Publish Less. Grow More.
  </div>
</div>""",
                },
            )
        except Exception as e:
            logger.error("Failed to send payment failed email to %s: %s", email, e)

    async def _schedule_winback(
        self, db: asyncpg.Connection, user_id: str, email: str,
    ) -> None:
        """Schedule win-back email sequence after cancellation."""
        from datetime import datetime
        now = datetime.now(UTC)
        try:
            await db.execute(
                """INSERT INTO winback_emails (user_id, email, cancelled_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id) DO UPDATE SET
                       cancelled_at = $3,
                       day_7_sent_at = NULL,
                       day_30_sent_at = NULL,
                       day_60_sent_at = NULL""",
                user_id, email, now,
            )
            logger.info("Win-back sequence scheduled for user %s", user_id)
        except Exception as e:
            logger.error("Failed to schedule win-back for user %s: %s", user_id, e)

    async def process_winback_emails(self, db: asyncpg.Connection) -> int:
        """Process pending win-back emails. Called by cron.

        Sends:
        - Day 7: "Your content health has gone unchecked for a week"
        - Day 30: "Here's what changed on your blog since you left"
        - Day 60: Final attempt with discount offer
        """
        from datetime import datetime, timedelta
        settings = get_settings()
        if not settings.resend_api_key:
            return 0

        now = datetime.now(UTC)
        sent = 0

        # Day 7 win-backs
        day7_rows = await db.fetch(
            """SELECT id, user_id, email, cancelled_at FROM winback_emails
               WHERE day_7_sent_at IS NULL
                 AND cancelled_at <= $1
                 AND cancelled_at > $2""",
            now - timedelta(days=7),
            now - timedelta(days=30),
        )
        for row in day7_rows:
            if await self._send_winback_day7(row["email"]):
                await db.execute(
                    "UPDATE winback_emails SET day_7_sent_at = $1 WHERE id = $2",
                    now, row["id"],
                )
                sent += 1

        # Day 30 win-backs
        day30_rows = await db.fetch(
            """SELECT id, user_id, email, cancelled_at FROM winback_emails
               WHERE day_7_sent_at IS NOT NULL
                 AND day_30_sent_at IS NULL
                 AND cancelled_at <= $1
                 AND cancelled_at > $2""",
            now - timedelta(days=30),
            now - timedelta(days=60),
        )
        for row in day30_rows:
            if await self._send_winback_day30(row["email"]):
                await db.execute(
                    "UPDATE winback_emails SET day_30_sent_at = $1 WHERE id = $2",
                    now, row["id"],
                )
                sent += 1

        # Day 60 win-backs (final attempt with discount)
        day60_rows = await db.fetch(
            """SELECT id, user_id, email, cancelled_at FROM winback_emails
               WHERE day_30_sent_at IS NOT NULL
                 AND day_60_sent_at IS NULL
                 AND cancelled_at <= $1
                 AND cancelled_at > $2""",
            now - timedelta(days=60),
            now - timedelta(days=90),
        )
        for row in day60_rows:
            if await self._send_winback_day60(row["email"]):
                await db.execute(
                    "UPDATE winback_emails SET day_60_sent_at = $1 WHERE id = $2",
                    now, row["id"],
                )
                sent += 1

        logger.info("Win-back emails processed: %d sent", sent)
        return sent

    async def _send_winback_day7(self, email: str) -> bool:
        """Day 7: Your content health has gone unchecked for a week."""
        settings = get_settings()
        try:
            import resend
            resend.api_key = settings.resend_api_key
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": settings.email_from,
                    "to": [email],
                    "subject": "Your content health has gone unchecked for a week",
                    "html": """
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;border:1px solid #e5e7eb;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
  </div>
  <h2 style="font-size:18px;">It's been a week.</h2>
  <p>Since you cancelled, your blog's content ecosystem has been running unmonitored. New cannibalization pairs could be forming. Orphan posts are accumulating. Your competitors aren't waiting.</p>
  <p>Your health score, recommendations, and ecosystem map are still available — just pick up where you left off.</p>
  <div style="text-align:center;margin:20px 0;">
    <a href="https://tended.app" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Resubscribe &rarr;</a>
  </div>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    <a href="https://tended.app/unsubscribe" style="color:#94a3b8;">Unsubscribe</a>
    &bull; Tended — Publish Less. Grow More.
  </div>
</div>""",
                },
            )
            return True
        except Exception as e:
            logger.error("Win-back day 7 email failed for %s: %s", email, e)
            return False

    async def _send_winback_day30(self, email: str) -> bool:
        """Day 30: Here's what changed on your blog since you left."""
        settings = get_settings()
        try:
            import resend
            resend.api_key = settings.resend_api_key
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": settings.email_from,
                    "to": [email],
                    "subject": "Here's what changed on your blog since you left",
                    "html": """
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;border:1px solid #e5e7eb;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
  </div>
  <h2 style="font-size:18px;">A lot can change in a month.</h2>
  <p>Google's algorithms have updated. Your competitors have published new content. Rankings have shifted. Content decay doesn't pause when you stop monitoring.</p>
  <p>Without Tended, you're flying blind:</p>
  <ul>
    <li>No cannibalization alerts when new posts start competing</li>
    <li>No decay detection when rankings slip</li>
    <li>No consolidation recommendations to recover lost traffic</li>
    <li>No ecosystem health tracking</li>
  </ul>
  <p>Come back and see what's changed.</p>
  <div style="text-align:center;margin:20px 0;">
    <a href="https://tended.app" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Resubscribe &rarr;</a>
  </div>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    <a href="https://tended.app/unsubscribe" style="color:#94a3b8;">Unsubscribe</a>
    &bull; Tended
  </div>
</div>""",
                },
            )
            return True
        except Exception as e:
            logger.error("Win-back day 30 email failed for %s: %s", email, e)
            return False

    async def _send_winback_day60(self, email: str) -> bool:
        """Day 60: Final attempt with discount offer."""
        settings = get_settings()
        try:
            import resend
            resend.api_key = settings.resend_api_key
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": settings.email_from,
                    "to": [email],
                    "subject": "Final offer: 30% off Tended for 3 months",
                    "html": """
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;border:1px solid #e5e7eb;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
  </div>
  <h2 style="font-size:18px;">We'd like you back.</h2>
  <p>It's been 2 months since you left Tended. We've been improving the platform — better recommendations, faster analysis, and new AI readiness scoring.</p>
  <div style="background:#f0fdf4;padding:20px;border-radius:8px;text-align:center;margin:20px 0;border:1px solid #16a34a;">
    <div style="color:#16a34a;font-size:24px;font-weight:700;">30% off for 3 months</div>
    <div style="color:#94a3b8;font-size:14px;margin-top:8px;">$104.30/month instead of $149 — just use code COMEBACK30</div>
  </div>
  <p>This is our last email. If you'd like to come back, the offer is valid for 14 days.</p>
  <div style="text-align:center;margin:20px 0;">
    <a href="https://tended.app?coupon=COMEBACK30" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Claim 30% Off &rarr;</a>
  </div>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    <a href="https://tended.app/unsubscribe" style="color:#94a3b8;">Unsubscribe</a>
    &bull; Tended
  </div>
</div>""",
                },
            )
            return True
        except Exception as e:
            logger.error("Win-back day 60 email failed for %s: %s", email, e)
            return False

    async def _get_tier_limits(self, db: asyncpg.Connection, user_id: str) -> dict:
        """Return the TIER_LIMITS dict for a user based on their subscription.

        Handles past_due grace period and paused states.
        """
        sub = await self.get_subscription(db, user_id)
        tier = sub["tier"]
        if tier == "past_due":
            from datetime import datetime
            grace_row = await db.fetchrow(
                "SELECT grace_period_ends_at FROM profiles WHERE id = $1::uuid",
                user_id,
            )
            grace_ends = grace_row["grace_period_ends_at"] if grace_row else None
            if grace_ends and grace_ends > datetime.now(UTC):
                tier = "growth"
            else:
                tier = "free"
        if tier == "paused":
            tier = "free"
        return TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    async def check_usage_limits(
        self, db: asyncpg.Connection, user_id: str, feature: str
    ) -> bool:
        """Check if user is within their tier limits for a feature."""
        sub = await self.get_subscription(db, user_id)
        tier = sub["tier"]
        if tier == "past_due":
            # Check grace period: allow access during 7-day grace window
            from datetime import datetime
            grace_row = await db.fetchrow(
                "SELECT grace_period_ends_at FROM profiles WHERE id = $1::uuid",
                user_id,
            )
            grace_ends = grace_row["grace_period_ends_at"] if grace_row else None
            if grace_ends and grace_ends > datetime.now(UTC):
                tier = "growth"  # Still in grace period — keep access
            else:
                tier = "free"  # Grace period expired — lock out
        if tier == "paused":
            tier = "free"  # Paused subscriptions have no access

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
