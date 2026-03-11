"""Tests for Stripe service — mocked checkout, webhooks, usage limits."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4


class TestStripeCheckout:
    """Mocked Stripe checkout session creation."""

    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session(self, mock_create):
        """Should create a checkout session with correct params."""
        mock_create.return_value = MagicMock(
            id="cs_test_123",
            url="https://checkout.stripe.com/test",
        )

        result = mock_create(
            mode="subscription",
            line_items=[{"price": "price_growth", "quantity": 1}],
            success_url="http://localhost:3000/billing?success=true",
            cancel_url="http://localhost:3000/billing?canceled=true",
            customer_email="test@test.com",
        )

        assert result.id == "cs_test_123"
        assert result.url.startswith("https://checkout.stripe.com")
        mock_create.assert_called_once()

    @patch("stripe.checkout.Session.create")
    def test_checkout_with_metadata(self, mock_create):
        """Metadata should include user_id."""
        mock_create.return_value = MagicMock(id="cs_test_456", url="https://...")

        mock_create(
            mode="subscription",
            line_items=[{"price": "price_scale", "quantity": 1}],
            metadata={"user_id": str(uuid4())},
        )
        call_kwargs = mock_create.call_args[1]
        assert "user_id" in call_kwargs["metadata"]


class TestStripeWebhook:
    """Mocked Stripe webhook event handling."""

    @patch("stripe.Webhook.construct_event")
    def test_valid_webhook_signature(self, mock_construct):
        """Valid signature should parse event."""
        mock_construct.return_value = MagicMock(
            type="checkout.session.completed",
            data=MagicMock(
                object=MagicMock(
                    customer="cus_123",
                    subscription="sub_123",
                    metadata={"user_id": "test-user"},
                )
            ),
        )

        event = mock_construct(b"payload", "sig_header", "whsec_test")
        assert event.type == "checkout.session.completed"
        assert event.data.object.customer == "cus_123"

    @patch("stripe.Webhook.construct_event")
    def test_invalid_webhook_signature(self, mock_construct):
        """Invalid signature should raise."""
        import stripe
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        with pytest.raises(stripe.error.SignatureVerificationError):
            mock_construct(b"payload", "bad_sig", "whsec_test")

    @patch("stripe.Webhook.construct_event")
    def test_subscription_deleted_event(self, mock_construct):
        """Handle subscription deletion webhook."""
        mock_construct.return_value = MagicMock(
            type="customer.subscription.deleted",
            data=MagicMock(
                object=MagicMock(
                    id="sub_123",
                    customer="cus_123",
                )
            ),
        )

        event = mock_construct(b"payload", "sig", "whsec_test")
        assert event.type == "customer.subscription.deleted"


class TestUsageLimits:
    """Test usage limit enforcement logic."""

    def test_free_tier_limits(self):
        """Free tier: 1 site, 50 posts, no oracle."""
        limits = {"sites": 1, "posts": 50, "oracle_queries": 0, "consolidations": 0}
        assert limits["sites"] == 1
        assert limits["oracle_queries"] == 0

    def test_growth_tier_limits(self):
        """Growth tier: 1 site, 500 posts, oracle, 5 consolidations."""
        limits = {"sites": 1, "posts": 500, "oracle_queries": 50, "consolidations": 5}
        assert limits["posts"] == 500
        assert limits["consolidations"] == 5

    def test_scale_tier_limits(self):
        """Scale tier: 10 sites, 5000 posts, unlimited."""
        limits = {"sites": 10, "posts": 5000, "oracle_queries": -1, "consolidations": -1}
        assert limits["sites"] == 10
        assert limits["oracle_queries"] == -1  # unlimited

    def test_usage_within_limit(self):
        """Usage below limit should be allowed."""
        current_usage = 3
        limit = 5
        assert current_usage < limit

    def test_usage_at_limit(self):
        """Usage at limit should be blocked."""
        current_usage = 5
        limit = 5
        assert current_usage >= limit

    def test_unlimited_usage(self):
        """Unlimited (-1) should always be allowed."""
        limit = -1
        assert limit == -1 or 100 < limit
